# SPDX-License-Identifier: AGPL-3.0-or-later
"""Imports a character sheet onto a person, from an installed line's module.

A sheet is what a vault note's frontmatter holds (tools/vault-import reads it): characteristics by
their short name, resources, skills with their rank and specialisation, and the Foundry documents
the character has (talents, gear). Each maps through the module's own records, never by guessing:
- a characteristic: the record ``characteristic:<slug>`` (its short name, by the module's rules);
- a resource: ``resource:<slug>`` (wounds, fate);
- a skill: the module's skill trait with that slug (sleightOfHand → sleight-of-hand);
- a document: the record whose source_id is its Foundry _id, when it's a trait (a talent).
Gear isn't a trait: it waits for the wiki's items (P3) and is reported as skipped, with anything
else that didn't map. Writes as the owner (the campaign's GM); a re-import replaces the person's
rows of the module's traits, so it's idempotent and drops what the sheet no longer has.
"""

from __future__ import annotations

import base64
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Optional

from zephyrex.extensions.rpg_modules.BLL_RPGModules import ContentModuleManager, ModuleRecordManager
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import (  # type: ignore[import-not-found]
    PersonTraitManager,
    TraitManager,
)

@dataclass
class SheetSummary:
    person_id: str
    written: int = 0
    removed: int = 0
    skipped: list[str] = field(default_factory=list)


def kebab(key: str) -> str:
    """A Foundry key as a slug: sleightOfHand → sleight-of-hand, animalHandling → animal-handling."""
    return re.sub(r"([a-z])([A-Z])", r"\1-\2", key).replace("_", "-").lower()


def foundry_id(reference: Any) -> Optional[str]:
    """A document's _id from a compendium UUID (Compendium.<system>.<pack>.Item.<id>) or a bare id."""
    uuid = compendium_uuid(reference)
    return None if uuid is None else uuid.rsplit(".", 1)[-1]


def compendium_uuid(reference: Any) -> Optional[str]:
    """The reference as given: a sheet's item (a UUID string, or {uuid, specialisation})."""
    if isinstance(reference, Mapping):
        reference = reference.get("uuid") or reference.get("source_id")
    return reference if isinstance(reference, str) and reference else None


def sheet_from_frontmatter(frontmatter: Mapping[str, Any]) -> Optional[dict[str, Any]]:
    """A sheet from a vault note's frontmatter, or None when the note has none. Reads the two blocks
    the source system builds its actors from: ``initial_build`` (base64 JSON: characteristics,
    wounds, fate) and ``canonical_sheet`` (skill advancements with their specialisation, where
    advance N is rank N, and the compendium documents the character has). canonical_sheet is
    authoritative where the two differ."""
    sheet = frontmatter.get("canonical_sheet")
    if not isinstance(sheet, Mapping):
        return None
    built: dict[str, Any] = {}
    encoded = frontmatter.get("initial_build")
    if isinstance(encoded, str) and encoded:
        built = json.loads(base64.b64decode(encoded))
    resources = {key: built[key] for key in ("wounds", "fate") if isinstance(built.get(key), (int, float))}
    return {
        "characteristics": dict(built.get("characteristics") or {}),
        "resources": resources,
        "skills": [
            {"skill": one["skill"], "specialisation": one.get("specialisation"), "rank": int(one["advance"])}
            for one in sheet.get("advancements") or []
            if isinstance(one, Mapping) and one.get("type") == "skill" and one.get("skill")
        ],
        "items": list(sheet.get("items") or []),
    }


def import_sheet(
    model_registry: Any, owner_id: str, person_id: str, line: str, sheet: Mapping[str, Any]
) -> SheetSummary:
    def as_owner(manager: type[Any]) -> Any:
        return manager(requester_id=owner_id, model_registry=model_registry)

    modules = [
        one
        for one in as_owner(ContentModuleManager).list(line=line)
        if str(one.created_by_user_id) == str(owner_id)
    ]
    if not modules:
        raise ValueError(f"the {line} module isn't installed for this account; install it first")
    module = modules[0]
    records = {row.source_id: row for row in as_owner(ModuleRecordManager).list(content_module_id=module.id)}
    # Records are keyed by Foundry's compendium UUID (the wiki's compendium_source); a sheet may name
    # the same document under another pack's UUID (one document shared by several packs), so its
    # bare _id is the fallback.
    by_foundry_id = {source_id.rsplit(".", 1)[-1]: source_id for source_id in records if source_id.startswith("Compendium.")}
    module_traits = {row.entity_id for row in records.values() if row.entity_type == "trait" and row.entity_id}
    skills = {
        trait.slug: trait.id
        for trait in as_owner(TraitManager).list(kind="skill")
        if trait.id in module_traits and trait.slug
    }
    shorts: dict[str, str] = {}
    for one in (module.rules or {}).get("characteristics") or []:
        if one.get("short"):
            shorts[one["short"]] = one["slug"]

    summary = SheetSummary(person_id=person_id)
    # (trait_id, specialisation) → the row's fields
    wanted: dict[tuple[str, str], dict[str, Any]] = {}

    def trait_of(source_id: str) -> Optional[str]:
        record = records.get(source_id)
        return record.entity_id if record is not None and record.entity_type == "trait" else None

    for short, value in (sheet.get("characteristics") or {}).items():
        trait_id = trait_of(f"characteristic:{shorts.get(short, kebab(short))}")
        if trait_id is None:
            summary.skipped.append(f"characteristic {short}")
            continue
        wanted[(trait_id, "")] = {"value": float(value)}
    for slug, value in (sheet.get("resources") or {}).items():
        trait_id = trait_of(f"resource:{kebab(slug)}")
        if trait_id is None:
            summary.skipped.append(f"resource {slug}")
            continue
        wanted[(trait_id, "")] = {"value": float(value)}
    for one in sheet.get("skills") or []:
        trait_id = skills.get(kebab(one["skill"]))
        specialisation = (one.get("specialisation") or "").strip()
        if trait_id is None:
            summary.skipped.append(f"skill {one['skill']}")
            continue
        wanted[(trait_id, specialisation)] = {"rank": int(one["rank"]), "specialisation": specialisation or None}
    for reference in sheet.get("items") or []:
        source_id = compendium_uuid(reference)
        if source_id is not None and source_id not in records:
            source_id = by_foundry_id.get(foundry_id(reference) or "", source_id)
        trait_id = trait_of(source_id) if source_id else None
        if trait_id is None:
            record = records.get(source_id or "")
            what = f"{record.source_type} {source_id}" if record is not None else f"unknown document {source_id}"
            summary.skipped.append(what)
            continue
        specialisation = (reference.get("specialisation") or "").strip() if isinstance(reference, Mapping) else ""
        wanted[(trait_id, specialisation)] = {"specialisation": specialisation or None}

    rows = as_owner(PersonTraitManager)
    existing = {
        (row.trait_id, (row.specialisation or "").strip()): row
        for row in rows.list(person_id=person_id)
        if row.trait_id in module_traits
    }
    for key, row in existing.items():
        if key not in wanted:
            rows.delete(id=row.id)
            summary.removed += 1
    for (trait_id, specialisation), fields in wanted.items():
        row = existing.get((trait_id, specialisation))
        if row is None:
            rows.create(person_id=person_id, trait_id=trait_id, **fields)
        else:
            rows.update(id=row.id, **fields)
        summary.written += 1
    return summary
