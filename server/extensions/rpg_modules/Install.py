# SPDX-License-Identifier: AGPL-3.0-or-later
"""Installs a line's bundle (tools/foundry-bridge/extract.mjs) as a private module of one account.

P1 (operator's [redacted] bridge, 2026-11-21): the documents that are traits in vtt become the owner's
traits of the line's game system, and every document (trait or not yet) gets a ModuleRecord with
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

import html
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Optional

from zephyrex.extensions.rpg_modules.BLL_RPGModules import ContentModuleManager, ModuleRecordManager
from zephyrex.extensions.rpg_systems.BLL_RPGSystems import GameSystemManager, slugify  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import TraitManager  # type: ignore[import-not-found]
from zephyrex.lib.Environment import env

# The [redacted] lines' game systems (rpg_systems' seed); dh1 has no seeded system yet.
LINE_SYSTEMS: dict[str, str] = {
    "bc": "redacted",
    "dh1": "redacted",
    "dh2": "redacted",
    "dw": "redacted",
    "ow": "redacted",
    "rt": "redacted",
}
LINE_NAMES: dict[str, str] = {
    "bc": "[redacted]",
    "dh1": "[redacted]",
    "dh2": "[redacted]",
    "dw": "[redacted]",
    "ow": "[redacted]",
    "rt": "[redacted]",
}

# Foundry item types that are traits in vtt, and the trait kind each becomes.
TRAIT_KINDS: dict[str, str] = {
    "skill": "skill",
    "talent": "talent",
    "trait": "trait",
    "psychicPower": "psychic-power",
    "condition": "condition",
    "malignancy": "malignancy",
    "mutation": "mutation",
    "mentalDisorder": "mental-disorder",
    "criticalInjury": "critical-injury",
    "darkPact": "dark-pact",
    "vehicleTrait": "vehicle-trait",
}
# An origin-path document's step becomes its kind.
ORIGIN_STEPS: dict[str, str] = {
    "homeWorld": "homeworld",
    "background": "background",
    "role": "role",
    "elite": "elite-advance",
    "divination": "divination",
}


@dataclass
class Summary:
    module_id: str
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    traits: int = 0
    kinds: dict[str, int] = field(default_factory=dict)


def trait_kind(document: Mapping[str, Any]) -> Optional[str]:
    """The trait kind a source document becomes, or None when it isn't a trait in vtt (yet)."""
    if document.get("foundry_class") != "Item":
        return None
    kind = document.get("type")
    if kind == "originPath":
        step = (document.get("system") or {}).get("step")
        return ORIGIN_STEPS.get(step) or (slugify(step) if isinstance(step, str) and step else "origin")
    return TRAIT_KINDS.get(kind or "")


def _description(document: Mapping[str, Any]) -> Optional[str]:
    described = (document.get("system") or {}).get("description")
    if isinstance(described, Mapping):
        described = described.get("value")
    return described if isinstance(described, str) and described else None


def _text(value: Any) -> Optional[str]:
    return None if value is None else re.sub(r"\s+", " ", html.unescape(str(value))).strip() or None


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
    if line not in LINE_SYSTEMS:
        raise ValueError(f"no module for line {line!r}")

    def as_owner(manager: type[Any]) -> Any:
        return manager(requester_id=owner_id, model_registry=model_registry)

    catalog = GameSystemManager(requester_id=env("ROOT_ID"), model_registry=model_registry)
    systems = catalog.list(slug=LINE_SYSTEMS[line])
    system_id = systems[0].id if systems else None

    slug = f"redacted-{line}"
    modules = as_owner(ContentModuleManager)
    found = [one for one in modules.list(slug=slug) if str(one.created_by_user_id) == str(owner_id)]
    documents = list(bundle["documents"])
    fields = {
        "system_ref": system_ref,
        "content_ref": content_ref,
        "document_count": len(documents),
        "rules": rules,
    }
    if found:
        module = modules.update(id=found[0].id, **fields)
    else:
        module = modules.create(name=LINE_NAMES[line], slug=slug, line=line, game_system_id=system_id, **fields)

    records = as_owner(ModuleRecordManager)
    traits = as_owner(TraitManager)
    existing = {row.source_id: row for row in records.list(content_module_id=module.id)}
    summary = Summary(module_id=module.id)
    wanted: set[str] = set()
    for document in documents:
        source_id = document["id"]
        wanted.add(source_id)
        kind = trait_kind(document)
        source = document.get("source") or {}
        record_fields = {
            "source_type": document.get("type"),
            "content_hash": document.get("hash"),
            "homebrew": bool(document.get("homebrew")),
            "conversion": bool(document.get("conversion")),
            "provenance": source.get("provenance"),
            "book": _text(source.get("book")),
            "page": _text(source.get("page")),
            "data": document.get("system"),
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
