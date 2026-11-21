# SPDX-License-Identifier: AGPL-3.0-or-later
"""Importing a character sheet (a vault note's frontmatter, as tools/vault-import reads it) onto a
person, through an installed module's records: characteristics, resources, specialised skills and
talents land as the person's traits, gear is reported as skipped until the wiki's items, a re-import
replaces rather than duplicates, and a test then rolls against the imported sheet."""

import asyncio
import base64
import json
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_dice.EXT_RPGDice import RPGDiceExtension
from zephyrex.extensions.rpg_modules.Install import install
from zephyrex.extensions.rpg_modules.Sheet import foundry_id, import_sheet, kebab, sheet_from_frontmatter
from zephyrex.extensions.rpg_systems.EXT_RPGSystems import RPGSystemsExtension
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import PersonTraitManager
from zephyrex.testing.factories import create_user

from vtt_app import create

RULES = {
    "characteristics": [
        {"slug": "intelligence", "key": "intelligence", "name": "Intelligence", "short": "Int"},
        {"slug": "fellowship", "key": "fellowship", "name": "Fellowship", "short": "Fel"},
    ],
    "resources": [{"slug": "wounds", "key": "wounds", "name": "Wounds"}, {"slug": "fate", "key": "fate", "name": "Fate"}],
}


def _document(source_id: str, name: str, kind: str, **changes: Any) -> dict[str, Any]:
    document = {
        "line": "dh2",
        "id": source_id,
        "name": name,
        "foundry_class": "Item",
        "type": kind,
        "homebrew": False,
        "conversion": False,
        "source": None,
        "system": {"description": {"value": f"<p>{name}</p>"}},
        "hash": f"h-{source_id}",
    }
    document.update(changes)
    return document


BUNDLE = {
    "line": "dh2",
    "packs": [],
    "problems": [],
    "documents": [
        _document("SRCSkill00000007", "[redacted]", "skill"),
        _document("RTSkill000000007", "[redacted]", "skill", conversion=True, homebrew=True),
        _document("SRCSkill00000003", "Charm", "skill"),
        _document("SRCaTlnt00000026", "Weapon Training", "talent"),
        _document("j7K8l9M0n1O2p3Q4", "[redacted]", "weapon"),
    ],
}

SHEET = {
    "characteristics": {"Int": 30, "Fel": 45, "Xyz": 5},
    "resources": {"wounds": 10, "fate": 3},
    "skills": [
        {"skill": "[redacted]", "specialisation": "[redacted]", "rank": 1},
        {"skill": "[redacted]", "specialisation": "[redacted]", "rank": 3},
        {"skill": "charm", "rank": 2},
    ],
    "items": [
        {"uuid": "Compendium.redacted.dh2-core-items-talents-specializations.Item.SRCaTlnt00000026", "specialisation": "Flame"},
        "Compendium.redacted.dh2-core-items-weapons.Item.j7K8l9M0n1O2p3Q4",
    ],
}


@pytest.fixture(scope="module")
def app() -> Iterator[Any]:
    application = create()
    with TestClient(application):
        yield application


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _create(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = server.post(f"/v1/{resource}", json={resource: fields}, headers=_headers(user))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()[resource]
    return created


def test_keys_and_references() -> None:
    assert kebab("[redacted]") == "[redacted]" and kebab("[redacted]") == "[redacted]" and kebab("charm") == "charm"
    assert foundry_id("Compendium.redacted.dh2-core-items-talents.Item.SRCaTlnt00000004") == "SRCaTlnt00000004"
    assert foundry_id({"uuid": "Compendium.x.y.Item.abc"}) == "abc" and foundry_id(None) is None


def test_a_vault_notes_frontmatter_is_a_sheet() -> None:
    built = {"characteristics": {"Int": 30, "Fel": 45}, "wounds": 10, "fate": 3, "skills": ["Charm"]}
    frontmatter = {
        "initial_build": base64.b64encode(json.dumps(built).encode()).decode(),
        "canonical_sheet": {
            "source": "initial_build",
            "advancements": [
                {"type": "skill", "skill": "[redacted]", "specialisation": "[redacted]", "advance": 1},
                {"type": "characteristic", "characteristic": "fel", "advance": 1},
            ],
            "items": ["Compendium.redacted.dh2-core-items-talents.Item.SRCaTlnt00000004"],
        },
    }
    assert sheet_from_frontmatter(frontmatter) == {
        "characteristics": {"Int": 30, "Fel": 45},
        "resources": {"wounds": 10, "fate": 3},
        "skills": [{"skill": "[redacted]", "specialisation": "[redacted]", "rank": 1}],
        "items": ["Compendium.redacted.dh2-core-items-talents.Item.SRCaTlnt00000004"],
    }
    assert sheet_from_frontmatter({"entity_type": "person"}) is None


def test_a_sheet_imports_through_the_module_and_a_test_rolls_on_it(app: Any) -> None:
    server = TestClient(app)
    registry = app.state.model_registry
    gm = create_user(server)
    systems = asyncio.run(RPGSystemsExtension.game_systems(str(gm.id)))
    heresy = next(one for one in systems if one["slug"] == "redacted")["id"]
    campaign = _create(server, gm, "campaign", name="[redacted]", user_id=gm.id, game_system_id=heresy)
    osk = _create(server, gm, "person", name="Osk", kind="pc", user_id=gm.id, campaign_id=campaign["id"])

    with pytest.raises(ValueError):
        import_sheet(registry, str(gm.id), osk["id"], "dh2", SHEET)
    module = install(registry, str(gm.id), BUNDLE, rules=RULES)
    assert module.kinds["skill"] == 2, "the RT conversion of [redacted] is a record, not a second trait"
    _create(server, gm, "campaign_module", campaign_id=campaign["id"], content_module_id=module.module_id)

    first = import_sheet(registry, str(gm.id), osk["id"], "dh2", SHEET)
    assert (first.written, first.removed) == (8, 0)
    assert sorted(first.skipped) == ["characteristic Xyz", "weapon j7K8l9M0n1O2p3Q4"]

    lore = asyncio.run(
        RPGDiceExtension.test(str(gm.id), osk["id"], "[redacted]", specialisation="[redacted]", difficulty="challenging")
    )
    assert (lore["skill_rank"], lore["target"]) == (3, 50), "Int 30 + Experienced (+20)"
    charm = asyncio.run(RPGDiceExtension.test(str(gm.id), osk["id"], "charm"))
    assert (charm["skill_rank"], charm["target"]) == (2, 55), "Fel 45 + Trained (+10)"

    changed = {**SHEET, "skills": SHEET["skills"][1:]}
    second = import_sheet(registry, str(gm.id), osk["id"], "dh2", changed)
    assert (second.written, second.removed) == (7, 1)
    rows = PersonTraitManager(requester_id=str(gm.id), model_registry=registry).list(person_id=osk["id"])
    assert len(rows) == 7, "a re-import replaces; it never duplicates"
    flame = [row for row in rows if row.specialisation == "Flame"]
    assert len(flame) == 1 and flame[0].rank is None
