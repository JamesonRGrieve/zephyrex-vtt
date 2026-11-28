# SPDX-License-Identifier: AGPL-3.0-or-later
"""A character's lasting state under the srd-5e pack (Zephyrex RPG, 2026-11-28: the story follows the
game's state): hit points outlast a fight and start the next; 0 hit points is Unconscious until
healed; a Short Rest spends Hit Point Dice (the class's die plus the Constitution modifier) and a
Long Rest restores everything and an Exhaustion level; conditions are the pack's; character_sheet
shows it all; the GM alone rests or sets a condition, and never mid-fight."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_combat.EXT_RPGCombat import RPGCombatExtension
from zephyrex.extensions.rpg_combat.Recovery import recovery_for
from zephyrex.extensions.rpg_dice.EXT_RPGDice import RPGDiceExtension
from zephyrex.extensions.rpg_systems.EXT_RPGSystems import RPGSystemsExtension
from zephyrex.testing.factories import create_user

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
    found = [one for one in response.json()["traits"] if one.get("campaign_id") is None]
    assert len(found) == 1, found
    return str(found[0]["id"])


def _run(call: Any) -> Any:
    return asyncio.run(call)


def _table(server: TestClient) -> dict[str, Any]:
    gm, player, stranger = create_user(server), create_user(server), create_user(server)
    systems = {one["slug"]: one for one in _run(RPGSystemsExtension.game_systems(str(gm.id)))}
    system_id = systems["srd-5e"]["id"]
    campaign = _create(server, gm, "campaign", name="Split Antler", user_id=gm.id, game_system_id=system_id)
    brann = _create(server, gm, "person", name="Brann", kind="pc", user_id=player.id, campaign_id=campaign["id"])
    for slug, value in (("strength", 16), ("dexterity", 14), ("constitution", 14), ("hit-points", 30), ("proficiency-bonus", 2)):
        _create(server, gm, "person_trait", person_id=brann["id"], trait_id=_template(server, gm, system_id, slug), value=value)
    # A third-level Fighter: three d10 Hit Point Dice.
    fighter = _create(server, gm, "trait", name="Fighter", kind="class", game_system_id=system_id, campaign_id=campaign["id"])
    level = _create(server, gm, "trait", name="Level", kind="resource", game_system_id=system_id, campaign_id=campaign["id"])
    _create(server, gm, "person_trait", person_id=brann["id"], trait_id=fighter["id"])
    _create(server, gm, "person_trait", person_id=brann["id"], trait_id=level["id"], value=3)
    registry = server.app.state.model_registry  # type: ignore[attr-defined]
    # The highest face every time, so the arithmetic is the rules', not luck's.
    recovery = recovery_for(registry, str(gm.id), campaign["id"], draw=lambda sides: sides)
    return {"gm": gm, "player": player, "stranger": stranger, "campaign": campaign, "brann": brann, "recovery": recovery}


@pytest.fixture(scope="module")
def table(server: TestClient) -> dict[str, Any]:
    return _table(server)


def _sheet_state(table: dict[str, Any], who: Any) -> dict[str, Any]:
    sheet = _run(RPGDiceExtension.character_sheet(str(who.id), table["brann"]["id"]))
    return dict(sheet["state"])


def test_a_whole_character_has_its_sheets_hit_points_and_all_its_hit_dice(table: dict[str, Any]) -> None:
    state = _sheet_state(table, table["player"])
    assert state == {
        "hp": 30,
        "hp_max": 30,
        "hit_dice": {"die": "d10", "total": 3, "spent": 0, "left": 3},
        "exhaustion": 0,
        "conditions": [],
    }, "the player reads their own state on the sheet"


def test_a_short_rest_spends_hit_dice_until_whole(table: dict[str, Any]) -> None:
    recovery, brann = table["recovery"], table["brann"]["id"]
    recovery.set_hp(brann, 5)
    rested = recovery.rest_all([brann], "short")["rested"][0]
    # d10 (10) + Con +2 = 12 a die: 5 → 17 → 29 → 30, three dice.
    assert [one["regained"] for one in rested["rolls"]] == [12, 12, 12]
    assert (rested["hp_before"], rested["hp"], rested["hit_dice"]["left"]) == (5, 30, 0)
    recovery.set_hp(brann, 20)
    assert recovery.rest_all([brann], "short")["rested"][0]["rolls"] == [], "no dice left to spend"


def test_zero_hit_points_is_unconscious_until_healed_and_a_long_rest_restores(table: dict[str, Any]) -> None:
    recovery, brann, gm = table["recovery"], table["brann"]["id"], str(table["gm"].id)
    assert recovery.set_hp(brann, 0)["conditions"] == ["Unconscious"]
    refused = recovery.rest_all([brann], "long")["rested"][0]
    assert refused["refused"].startswith("A long rest needs at least 1 Hit Point") and refused["hp"] == 0
    _run(RPGCombatExtension.set_condition(gm, brann, "exhaustion"))
    tired = _run(RPGCombatExtension.set_condition(gm, brann, "Exhaustion"))
    assert (tired["exhaustion"], tired["dies"]) == (2, False) and "Exhaustion" in tired["conditions"]
    healed = recovery.heal(brann, "2d4+2")
    assert (healed["rolled"], healed["hp"], healed["conditions"]) == (10, 10, ["Exhaustion"]), "any healing ends Unconscious"
    rested = _run(RPGCombatExtension.rest(gm, table["campaign"]["id"], [brann], "long"))["rested"][0]
    assert (rested["hp"], rested["hit_dice"]["spent"], rested["exhaustion"]) == (30, 0, 1)


def test_conditions_are_the_packs_and_come_off_again(table: dict[str, Any]) -> None:
    gm, brann = str(table["gm"].id), table["brann"]["id"]
    assert "Prone" in _run(RPGCombatExtension.set_condition(gm, brann, "prone"))["conditions"]
    assert "Prone" in _sheet_state(table, table["gm"])["conditions"]
    assert "Prone" not in _run(RPGCombatExtension.set_condition(gm, brann, "Prone", present=False))["conditions"]
    with pytest.raises(HTTPException) as unknown:
        _run(RPGCombatExtension.set_condition(gm, brann, "Flying"))
    assert unknown.value.status_code == 422 and "Grappled" in unknown.value.detail["message"]
    with pytest.raises(HTTPException) as rest_kind:
        _run(RPGCombatExtension.rest(gm, table["campaign"]["id"], [brann], "nap"))
    assert rest_kind.value.status_code == 422 and "short or long" in rest_kind.value.detail["message"]


def test_only_the_gm_rests_or_sets_a_condition(table: dict[str, Any]) -> None:
    brann = table["brann"]["id"]
    for who in (table["player"], table["stranger"]):
        with pytest.raises(HTTPException) as refused:
            _run(RPGCombatExtension.rest(str(who.id), table["campaign"]["id"], [brann], "long"))
        assert refused.value.status_code == 404
        with pytest.raises(HTTPException) as refused:
            _run(RPGCombatExtension.set_condition(str(who.id), brann, "Prone"))
        assert refused.value.status_code == 404


def test_hit_points_outlast_a_fight_and_no_one_rests_in_one(server: TestClient) -> None:
    table = _table(server)
    gm, brann = str(table["gm"].id), table["brann"]["id"]
    table["recovery"].set_hp(brann, 7)
    guard = _create(server, table["gm"], "person", name="Holt", kind="npc", campaign_id=table["campaign"]["id"])
    started = _run(RPGCombatExtension.start_encounter(gm, table["campaign"]["id"], person_ids=[brann, guard["id"]]))
    options = _run(RPGCombatExtension.combat_options(gm, started["id"], brann))
    assert (options["hp"], options["hp_max"]) == (7, 30), "the fight starts from what the last one left"
    with pytest.raises(HTTPException) as mid_fight:
        _run(RPGCombatExtension.rest(gm, table["campaign"]["id"], [brann], "short"))
    assert mid_fight.value.status_code == 422 and "Initiative" in mid_fight.value.detail["message"]
    # A heal mid-fight shows in the fight.
    table["recovery"].heal(brann, "1d4")
    assert _run(RPGCombatExtension.combat_options(gm, started["id"], brann))["hp"] == 11
