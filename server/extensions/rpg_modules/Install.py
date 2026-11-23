# SPDX-License-Identifier: AGPL-3.0-or-later
"""Installs a bridge's bundle (a source system's documents, read by a bridge such as
tools/foundry-bridge/srd5e.py, or a private instance's own) as a private module of one account.

The bundle names its game system, the module's name and slug, and which documents are traits (its
"kinds"). The documents that are traits in vtt become the owner's traits of that game system, and every document (trait or not yet) gets a ModuleRecord with
its materialized data, so later phases (roll tables, the wiki's items and NPC templates, modifiers)
read them from there. A re-install is incremental:
- an unchanged document (same content hash) is left as it is;
- a changed one is updated in place;
- one the source no longer has is removed, with its trait.

Everything is written as the owner, never as the framework's SYSTEM user: on a hosted instance
only that account sees the module. Installs run server-side (tools/foundry-bridge/install.py), never
as a route: the content is on the server's disk, and a route would let any account copy it.
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


def install(
    model_registry: Any,
    owner_id: str,
    bundle: Mapping[str, Any],
    *,
    system_ref: Optional[str] = None,
    content_ref: Optional[str] = None,
    rules: Optional[dict[str, Any]] = None,
) -> Summary:
    line = bundle["line"]
    system_slug = bundle.get("system")
    if not system_slug:
        raise ValueError(f"the bundle for line {line!r} names no game system (its 'system' slug)")

    def as_owner(manager: type[Any]) -> Any:
        return manager(requester_id=owner_id, model_registry=model_registry)

    catalog = GameSystemManager(requester_id=env("ROOT_ID"), model_registry=model_registry)
    systems = catalog.list(slug=system_slug)
    system_id = systems[0].id if systems else None

    slug = str(bundle.get("slug") or line)
    modules = as_owner(ContentModuleManager)
    found = [one for one in modules.list(slug=slug) if str(one.created_by_user_id) == str(owner_id)]
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

    records = as_owner(ModuleRecordManager)
    traits = as_owner(TraitManager)
    existing = {row.source_id: row for row in records.list(content_module_id=module.id)}
    summary = Summary(module_id=module.id)
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
