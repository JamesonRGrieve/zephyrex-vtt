# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `test` ability under the fifth-edition SRD pack (srd-5e, generated from the SRD 5.2), against a real
server: an ability or skill check is d20 + ability modifier against the difficulty's DC; a character
with no sheet still gets the system's own test, at the human-average score (a plain d20), flagged;
a pack that states no such average refuses a sheetless test rather than invent one;
initiative is a Dexterity check; and roll_to_table posts the check as the seat's line."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_dice.EXT_RPGDice import RPGDiceExtension
from zephyrex.extensions.rpg_systems.EXT_RPGSystems import RPGSystemsExtension
from zephyrex.extensions.rpg_table.EXT_RPGTable import RPGTableExtension
from zephyrex.testing.factories import create_user

from test_support import percentile_system
from vtt_app import create


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    with TestClient(create()) as client:
        yield client


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _create(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = server.post(f"/v1/{resource}", json={resource: fields}, headers=_headers(user))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()[resource]
    return created


def _template(server: TestClient, user: Any, system_id: str, slug: str) -> str:
    response = server.get("/v1/trait", params={"slug": slug, "game_system_id": system_id}, headers=_headers(user))
    assert response.status_code == 200, response.text
    found = response.json()["traits"]
    assert len(found) == 1, found
    return str(found[0]["id"])


@pytest.fixture(scope="module")
def world(server: TestClient) -> dict[str, Any]:
    """A 5e campaign with a fighter (STR 16, proficient in Athletics) and a villager with no sheet,
    and a percentile campaign with a sheetless character."""
    gm, player = create_user(server), create_user(server)
    systems = {one["slug"]: one for one in asyncio.run(RPGSystemsExtension.game_systems(str(gm.id)))}
    dnd, percentile = systems["srd-5e"], percentile_system(server, gm)
    campaign = _create(server, gm, "campaign", name="Split Antler", user_id=gm.id, game_system_id=dnd["id"])
    fighter = _create(server, gm, "person", name="Brann", kind="pc", user_id=player.id, campaign_id=campaign["id"])
    _create(server, gm, "person_trait", person_id=fighter["id"], trait_id=_template(server, gm, dnd["id"], "strength"), value=16)
    _create(server, gm, "person_trait", person_id=fighter["id"], trait_id=_template(server, gm, dnd["id"], "athletics"), rank=1)
    villager = _create(server, gm, "person", name="Villager", kind="npc", campaign_id=campaign["id"])
    gothic = _create(server, gm, "campaign", name="Farport", user_id=gm.id, game_system_id=percentile["id"])
    acolyte = _create(server, gm, "person", name="Rhia", kind="pc", campaign_id=gothic["id"])
    return {"gm": gm, "player": player, "campaign": campaign, "fighter": fighter, "villager": villager, "acolyte": acolyte}


def _test(user: Any, person: dict[str, Any], name: str, **options: Any) -> dict[str, Any]:
    return asyncio.run(RPGDiceExtension.test(str(user.id), person["id"], name, **options))


def test_the_5e_skills_and_dcs_are_offered(world: dict[str, Any]) -> None:
    options = asyncio.run(RPGDiceExtension.test_options(str(world["gm"].id), world["villager"]["id"]))
    assert options["has_sheet"] is False
    assert {one["slug"] for one in options["characteristics"]} == {
        "strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"
    }
    assert len(options["skills"]) == 18 and options["default_difficulty"] == "medium"
    assert {one["slug"]: one["dc"] for one in options["difficulties"]}["hard"] == 20


def test_a_check_is_d20_plus_the_ability_modifier_against_the_dc(world: dict[str, Any]) -> None:
    for _ in range(10):
        checked = _test(world["player"], world["fighter"], "strength", difficulty="hard")
        assert (checked["test_kind"], checked["target"], checked["no_sheet"]) == ("d20-over", 20, False)
        assert 1 <= checked["roll"] <= 20 and checked["total"] == checked["roll"] + 3
        assert checked["success"] == (checked["total"] >= 20)
    skill = _test(world["player"], world["fighter"], "athletics")
    assert skill["skill_rank"] == 1 and skill["total"] == skill["roll"] + 3, "no Level on the sheet: no Proficiency Bonus"
    assert {"step": "proficiency", "rank": 1, "value": 0, "rule": "no level on the sheet"} in skill["steps"]


def test_advantage_keeps_the_higher_of_two_d20s_and_disadvantage_the_lower(world: dict[str, Any]) -> None:
    for _ in range(20):
        up = _test(world["player"], world["fighter"], "strength", advantage="advantage")
        assert len(up["rolls"]) == 2 and up["roll"] == max(up["rolls"]) and up["advantage"] == "advantage"
        assert up["total"] == up["roll"] + 3
        down = _test(world["player"], world["fighter"], "strength", advantage="disadvantage")
        assert len(down["rolls"]) == 2 and down["roll"] == min(down["rolls"])
    plain = _test(world["player"], world["fighter"], "strength")
    assert plain["rolls"] == [plain["roll"]] and plain["advantage"] is None


def test_a_pack_without_advantage_refuses_it(world: dict[str, Any]) -> None:
    with pytest.raises(HTTPException) as refused:
        _test(world["gm"], world["acolyte"], "might", advantage="advantage")
    assert refused.value.status_code == 422 and "no advantage" in str(refused.value.detail)


def test_no_sheet_still_gets_the_systems_test_a_plain_d20(world: dict[str, Any]) -> None:
    for _ in range(10):
        plain = _test(world["gm"], world["villager"], "persuasion", difficulty="easy")
        assert (plain["no_sheet"], plain["target"], plain["characteristic"]["value"]) == (True, 10, 10.0)
        assert plain["total"] == plain["roll"] and plain["success"] == (plain["roll"] >= 10)


def test_a_pack_with_no_stated_average_refuses_a_sheetless_test(world: dict[str, Any]) -> None:
    with pytest.raises(HTTPException) as refused:
        _test(world["gm"], world["acolyte"], "grace")
    assert refused.value.status_code == 422
    assert "states no average" in refused.value.detail["message"]


def test_5e_initiative_is_a_dexterity_check_sheet_or_not(world: dict[str, Any]) -> None:
    rolled = asyncio.run(RPGDiceExtension.initiative(str(world["gm"].id), world["villager"]["id"]))
    assert (rolled["dice"], rolled["characteristic"], rolled["value"], rolled["bonus"]) == ("1d20", "dexterity", 10.0, 0)
    assert rolled["total"] == rolled["roll"]


def test_roll_to_table_posts_a_check(server: TestClient, world: dict[str, Any]) -> None:
    gm = world["gm"]
    table = _create(server, gm, "table", name="Session 1", campaign_id=world["campaign"]["id"])
    _create(server, gm, "table_seat", conversation_id=table["conversation_id"], person_id=world["villager"]["id"], npc=True)
    posted = asyncio.run(
        RPGTableExtension.roll_to_table(str(gm.id), table["conversation_id"], world["villager"]["id"], name="stealth")
    )
    text = posted["line"]["text"]
    assert text.startswith("Stealth check: rolled ") and "against DC 15" in text and "no sheet" in text
