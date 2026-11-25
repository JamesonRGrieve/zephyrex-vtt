# SPDX-License-Identifier: AGPL-3.0-or-later
"""Installs a bridge's bundle (a source system's documents, read by a bridge such as
tools/foundry-bridge/srd5e.py, or a private instance's own) as a module, one of two kinds (operator,
2026-11-25: "The public domain stuff is instance wide" / "Private stuff is personal"):
- private (the default): one account's own, written as that owner, never as the framework's SYSTEM
  user, so on a hosted instance only that account sees it (the operator's own books);
- instance-wide: public-domain or open-licence content (the SRD, CC-BY), installed once and written
  as SYSTEM, whose rows every account reads and only the server changes. The bundle asks for it
  ("visibility": "instance", which srd5e.py writes), or the install does (instance_wide=True).
Either way a campaign plays only with the modules its GM enables (CampaignModule), and campaigns
stay their accounts' own.

The bundle names its game system, the module's name and slug, and which documents are traits (its
"kinds"). The documents that are traits in vtt become the module's traits of that game system, and every document (trait or not yet) gets a ModuleRecord with
its materialized data, so later phases (roll tables, the wiki's items and NPC templates, modifiers)
read them from there. A re-install is incremental:
- an unchanged document (same content hash) is left as it is;
- a changed one is updated in place;
- one the source no longer has is removed, with its trait.

An instance-wide install of a slug the installing account already has as its own takes that module
over in place (adopt): it, its records and its traits become the instance's under the same ids, so
the characters and campaigns built on them keep working. Installs run server-side
(tools/foundry-bridge/install.py), never as a route: the content is on the server's disk, and a
route would let any account copy it.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Optional

from zephyrex.extensions.rpg_modules.BLL_RPGModules import ContentModuleManager, ModuleRecordManager
from zephyrex.extensions.rpg_systems.BLL_RPGSystems import GameSystemManager, slugify  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import TraitManager  # type: ignore[import-not-found]
from zephyrex.lib.Environment import env

# A bundle says which game system it's for, under what name, and its module's slug: the bridge that
# writes it knows its source (a private instance's own), so no game is named here.

# Which source documents become traits, and of what kind, comes with the bundle (its "kinds"): the
# bridge that read the source system knows its item types. The scheme:
#   {"types": {item type: trait kind},
#    "fields": {item type: {"path": [keys into system], "map": {value: trait kind},
#                           "default": kind or null, "slug_unknown": bool}}}
# A type under "fields" takes its kind from a value in its system data (a feat's "type.value", an
# origin step's "step"), else the default, else (slug_unknown) the value itself as a slug.


@dataclass
class Summary:
    module_id: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    traits: int = 0
    kinds: dict[str, int] = field(default_factory=dict)
    instance_wide: bool = False
    # The installing account, when an instance-wide install took over its own module of the slug.
    adopted_from: Optional[str] = None


# What the bridge's rules step lists that has no Foundry document: (rules key, document class, trait kind).
RULE_DOCUMENTS = (("characteristics", "Characteristic", "characteristic"), ("resources", "Resource", "resource"))


def rule_documents(rules: Optional[Mapping[str, Any]], line: str) -> list[dict[str, Any]]:
    """The line's characteristics (the system's CHARACTERISTICS) and resources (wounds, fate, fatigue,
    insanity, corruption: the actor's tracks), from the bridge's rules step, as documents to install
    like any other: keyed ``<kind>:<slug>`` (the system has no _id for them), so they're recorded,
    updated and removed the same way."""
    found = []
    for key, foundry_class, kind in RULE_DOCUMENTS:
        for one in (rules or {}).get(key) or []:
            body = {name: one.get(name) for name in ("name", "short", "key", "max") if one.get(name) is not None}
            found.append(
                {
                    "line": line,
                    "id": f"{kind}:{one['slug']}",
                    "name": one["name"],
                    "foundry_class": foundry_class,
                    "type": kind,
                    "homebrew": False,
                    "conversion": False,
                    "source": None,
                    "system": body,
                    "hash": hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16],
                }
            )
    return found


def trait_kind(document: Mapping[str, Any], kinds: Optional[Mapping[str, Any]] = None) -> Optional[str]:
    """The trait kind a source document becomes under its bundle's ``kinds`` scheme, or None when it
    isn't a trait in vtt (yet)."""
    for _key, foundry_class, kind in RULE_DOCUMENTS:
        if document.get("foundry_class") == foundry_class:
            return kind
    if document.get("foundry_class") != "Item":
        return None
    scheme = kinds or {}
    kind = document.get("type") or ""
    by_field = (scheme.get("fields") or {}).get(kind)
    if by_field:
        value: Any = document.get("system") or {}
        for key in by_field.get("path") or []:
            value = value.get(key) if isinstance(value, Mapping) else None
        mapped = (by_field.get("map") or {}).get(value) if isinstance(value, str) else None
        if mapped:
            return str(mapped)
        if by_field.get("slug_unknown") and isinstance(value, str) and value:
            return slugify(value)
        default = by_field.get("default")
        return str(default) if default else None
    if kind == "skill" and document.get("conversion"):
        # Another line's copy of a skill this line has itself: kept as a record, never a second trait
        # a test's name would find twice.
        return None
    found = (scheme.get("types") or {}).get(kind)
    return str(found) if found else None


def _description(document: Mapping[str, Any]) -> Optional[str]:
    described = (document.get("system") or {}).get("description")
    if isinstance(described, Mapping):
        described = described.get("value")
    return described if isinstance(described, str) and described else None


def _text(value: Any) -> Optional[str]:
    return None if value is None else re.sub(r"\s+", " ", html.unescape(str(value))).strip() or None


def _data(document: Mapping[str, Any]) -> Any:
    """A record's data: the document's materialized system, and for an origin-path step the system's
    own normalized reading of it (normalizeOrigin: grants, choices, modifiers, requirements) under
    `_origin`, which the character builder reads."""
    system = document.get("system")
    origin = document.get("origin")
    if origin is None or not isinstance(system, Mapping):
        return system
    return {**system, "_origin": origin}


def _installs(model_registry: Any, slug: str) -> list[tuple[str, str]]:
    """Every live install of a slug, the instance's and each account's own, oldest first: (module id,
    who wrote it). Read from the table itself: a ROOT read would also list soft-deleted rows."""
    manager = ContentModuleManager(requester_id=env("ROOT_ID"), model_registry=model_registry)
    session = manager.db
    try:
        Module = manager.DB
        rows = (
            session.query(Module.id, Module.created_by_user_id)
            .filter(Module.slug == slug, Module.deleted_at.is_(None))
            .order_by(Module.created_at)
            .all()
        )
        return [(str(module_id), str(owner)) for module_id, owner in rows]
    finally:
        session.close()


def _adopt(model_registry: Any, module_id: str) -> None:
    """Makes one account's own module the instance's: it, its records and the traits made from them
    are re-owned by SYSTEM in place (the same ids, so person traits and campaign links stand)."""
    system_id = str(env("SYSTEM_ID"))
    manager = ContentModuleManager(requester_id=env("ROOT_ID"), model_registry=model_registry)
    records = ModuleRecordManager(requester_id=env("ROOT_ID"), model_registry=model_registry)
    traits = TraitManager(requester_id=env("ROOT_ID"), model_registry=model_registry)
    session = manager.db
    try:
        Module, Record, Trait = manager.DB, records.DB, traits.DB
        trait_ids = [
            row.entity_id
            for row in session.query(Record).filter(Record.content_module_id == module_id, Record.entity_type == "trait")
            if row.entity_id
        ]
        session.query(Module).filter(Module.id == module_id).update({"created_by_user_id": system_id}, synchronize_session=False)
        session.query(Record).filter(Record.content_module_id == module_id).update({"created_by_user_id": system_id}, synchronize_session=False)
        for start in range(0, len(trait_ids), 500):
            chunk = trait_ids[start : start + 500]
            session.query(Trait).filter(Trait.id.in_(chunk)).update({"created_by_user_id": system_id}, synchronize_session=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def instance_wide_bundle(bundle: Mapping[str, Any]) -> bool:
    """Whether a bundle asks to be installed for the whole instance (open content)."""
    return str(bundle.get("visibility") or "private") == "instance"


def install(
    model_registry: Any,
    owner_id: str,
    bundle: Mapping[str, Any],
    *,
    instance_wide: Optional[bool] = None,
    system_ref: Optional[str] = None,
    content_ref: Optional[str] = None,
    rules: Optional[dict[str, Any]] = None,
) -> Summary:
    line = bundle["line"]
    system_slug = bundle.get("system")
    if not system_slug:
        raise ValueError(f"the bundle for line {line!r} names no game system (its 'system' slug)")

    shared = instance_wide_bundle(bundle) if instance_wide is None else instance_wide
    writer = str(env("SYSTEM_ID")) if shared else str(owner_id)

    def as_writer(manager: type[Any]) -> Any:
        return manager(requester_id=writer, model_registry=model_registry)

    catalog = GameSystemManager(requester_id=env("ROOT_ID"), model_registry=model_registry)
    systems = catalog.list(slug=system_slug)
    system_id = systems[0].id if systems else None

    slug = str(bundle.get("slug") or line)
    modules = as_writer(ContentModuleManager)
    every = _installs(model_registry, slug)
    found = [modules.get(id=module_id) for module_id, by in every if by == writer]
    adopted_from = None
    if shared and not found:
        own = [module_id for module_id, by in every if by == str(owner_id)]
        if own:
            _adopt(model_registry, own[0])
            adopted_from = str(owner_id)
            found = [modules.get(id=own[0])]
    documents = rule_documents(rules, line) + list(bundle["documents"])
    fields = {
        "system_ref": system_ref,
        "content_ref": content_ref,
        "document_count": len(documents),
        "rules": rules,
    }
    if found:
        module = modules.update(id=found[0].id, **fields)
    else:
        module = modules.create(name=str(bundle.get("name") or line), slug=slug, line=line, game_system_id=system_id, **fields)

    records = as_writer(ModuleRecordManager)
    traits = as_writer(TraitManager)
    existing = {row.source_id: row for row in records.list(content_module_id=module.id)}
    summary = Summary(module_id=module.id, instance_wide=shared, adopted_from=adopted_from)
    wanted: set[str] = set()
    for document in documents:
        source_id = document["id"]
        wanted.add(source_id)
        kind = trait_kind(document, bundle.get("kinds"))
        source = document.get("source") or {}
        record_fields = {
            "source_type": document.get("type"),
            "content_hash": document.get("hash"),
            "homebrew": bool(document.get("homebrew")),
            "conversion": bool(document.get("conversion")),
            "provenance": source.get("provenance"),
            "book": _text(source.get("book")),
            "page": _text(source.get("page")),
            "data": _data(document),
        }
        trait_fields = {
            "name": document["name"],
            "kind": kind,
            "slug": slugify(document["name"]),
            "description": _description(document),
            "game_system_id": system_id,
        }
        if kind is not None:
            summary.kinds[kind] = summary.kinds.get(kind, 0) + 1
        record = existing.get(source_id)
        if record is not None and record.content_hash == document.get("hash"):
            summary.unchanged += 1
            continue
        if record is not None:
            if record.entity_type == "trait" and record.entity_id and kind is not None:
                traits.update(id=record.entity_id, **{k: v for k, v in trait_fields.items() if k != "game_system_id"})
            records.update(id=record.id, **record_fields)
            summary.updated += 1
            continue
        entity_id = traits.create(**trait_fields).id if kind is not None else None
        records.create(
            content_module_id=module.id,
            source_id=source_id,
            entity_type="trait" if entity_id else None,
            entity_id=entity_id,
            **record_fields,
        )
        summary.created += 1
    for source_id, record in existing.items():
        if source_id in wanted:
            continue
        if record.entity_type == "trait" and record.entity_id:
            traits.delete(id=record.entity_id)
        records.delete(id=record.id)
        summary.removed += 1
    summary.traits = sum(summary.kinds.values())
    return summary
