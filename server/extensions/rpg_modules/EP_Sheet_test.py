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
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import PersonTraitManager
from zephyrex.testing.factories import create_user

from test_support import percentile_system
from vtt_app import create

RULES = {
    "characteristics": [
        {"slug": "wits", "key": "wits", "name": "Wits", "short": "WI"},
        {"slug": "nerve", "key": "nerve", "name": "Nerve", "short": "NE"},
    ],
    "resources": [{"slug": "health", "key": "health", "name": "Health"}, {"slug": "luck", "key": "luck", "name": "Luck"}],
}
KINDS = {"types": {"skill": "skill", "talent": "talent"}}


def _document(source_id: str, name: str, kind: str, **changes: Any) -> dict[str, Any]:
    document = {
        "line": "testline",
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
    "line": "testline",
    "system": "percentile-test",
    "name": "Test line",
    "slug": "testline",
    "kinds": KINDS,
    "packs": [],
    "problems": [],
    "documents": [
        _document("Compendium.source.test-skills.Item.Skill00000007", "Lore", "skill"),
        _document("Compendium.source.other-skills.Item.Skill10000007", "Lore", "skill", conversion=True, homebrew=True),
        _document("Compendium.source.test-skills.Item.Skill00000003", "Repair", "skill"),
        _document("Compendium.source.test-talents.Item.Talent000026", "Blade Training", "talent"),
        _document("Compendium.source.test-weapons.Item.j7K8l9M0n1O2p3Q4", "Torch", "weapon"),
    ],
}

SHEET = {
    "characteristics": {"WI": 30, "NE": 45, "Xyz": 5},
    "resources": {"health": 10, "luck": 3},
    "skills": [
        {"skill": "lore", "specialisation": "Old Kingdoms", "rank": 1},
        {"skill": "lore", "specialisation": "Stars", "rank": 3},
        {"skill": "repair", "rank": 2},
    ],
    "items": [
        {"uuid": "Compendium.source.test-talents-specializations.Item.Talent000026", "specialisation": "Edge"},
        "Compendium.source.test-weapons.Item.j7K8l9M0n1O2p3Q4",
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
    assert kebab("sleightOfHand") == "sleight-of-hand" and kebab("animalHandling") == "animal-handling" and kebab("repair") == "repair"
    assert foundry_id("Compendium.source.test-talents.Item.Talent000004") == "Talent000004"
    assert foundry_id({"uuid": "Compendium.x.y.Item.abc"}) == "abc" and foundry_id(None) is None


def test_a_vault_notes_frontmatter_is_a_sheet() -> None:
    built = {"characteristics": {"WI": 30, "NE": 45}, "health": 10, "luck": 3, "skills": ["Repair"]}
    frontmatter = {
        "initial_build": base64.b64encode(json.dumps(built).encode()).decode(),
        "canonical_sheet": {
            "source": "initial_build",
            "advancements": [
                {"type": "skill", "skill": "lore", "specialisation": "Old Kingdoms", "advance": 1},
                {"type": "characteristic", "characteristic": "ne", "advance": 1},
            ],
            "items": ["Compendium.source.test-talents.Item.Talent000004"],
        },
    }
    sheet = sheet_from_frontmatter(frontmatter)
    assert sheet is not None
    assert sheet["characteristics"] == {"WI": 30, "NE": 45}
    assert sheet["skills"] == [{"skill": "lore", "specialisation": "Old Kingdoms", "rank": 1}]
    assert sheet["items"] == ["Compendium.source.test-talents.Item.Talent000004"]
    assert sheet_from_frontmatter({"entity_type": "person"}) is None


def test_a_sheet_imports_through_the_module_and_a_test_rolls_on_it(app: Any) -> None:
    server = TestClient(app)
    registry = app.state.model_registry
    gm = create_user(server)
    system_id = percentile_system(server)["id"]
    campaign = _create(server, gm, "campaign", name="Harbour", user_id=gm.id, game_system_id=system_id)
    osk = _create(server, gm, "person", name="Osk", kind="pc", user_id=gm.id, campaign_id=campaign["id"])

    with pytest.raises(ValueError):
        import_sheet(registry, str(gm.id), osk["id"], "testline", SHEET)
    module = install(registry, str(gm.id), BUNDLE, rules=RULES)
    assert module.kinds["skill"] == 2, "the other line's copy of Lore is a record, not a second trait"
    _create(server, gm, "campaign_module", campaign_id=campaign["id"], content_module_id=module.module_id)

    first = import_sheet(registry, str(gm.id), osk["id"], "testline", SHEET)
    assert (first.written, first.removed) == (8, 0)
    assert sorted(first.skipped) == [
        "characteristic Xyz",
        "weapon Compendium.source.test-weapons.Item.j7K8l9M0n1O2p3Q4",
    ]

    lore = asyncio.run(RPGDiceExtension.test(str(gm.id), osk["id"], "lore", specialisation="Stars", difficulty="standard"))
    assert (lore["skill_rank"], lore["target"]) == (3, 50), "Wits 30 + rank 3 (+20)"
    repair = asyncio.run(RPGDiceExtension.test(str(gm.id), osk["id"], "repair"))
    assert (repair["skill_rank"], repair["target"]) == (2, 40), "Wits 30 + rank 2 (+10)"

    changed = {**SHEET, "skills": SHEET["skills"][1:]}
    second = import_sheet(registry, str(gm.id), osk["id"], "testline", changed)
    assert (second.written, second.removed) == (7, 1)
    rows = PersonTraitManager(requester_id=str(gm.id), model_registry=registry).list(person_id=osk["id"])
    assert len(rows) == 7, "a re-import replaces; it never duplicates"
    edge = [row for row in rows if row.specialisation == "Edge"]
    assert len(edge) == 1 and edge[0].rank is None
