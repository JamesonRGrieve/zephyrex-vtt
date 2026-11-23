# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ability scores by the rules as written, against a real server under the srd-5e pack: the methods
offered, the roll kept on the server (a player can't roll again for a better set), scores checked
against the method and written as the character's values, which tests then use; a player sets them
once, the GM may redo them; a stranger gets a 404; a pack without methods says so."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_builder.EXT_RPGBuilder import RPGBuilderExtension
from zephyrex.extensions.rpg_dice.EXT_RPGDice import RPGDiceExtension
from zephyrex.extensions.rpg_systems.EXT_RPGSystems import RPGSystemsExtension
from zephyrex.testing.factories import create_user

from test_support import percentile_system
from vtt_app import create

SIX = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    with TestClient(create()) as client:
        yield client


def _create(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = server.post(f"/v1/{resource}", json={resource: fields}, headers={"Authorization": f"Bearer {user.jwt}"})
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()[resource]
    return created


@pytest.fixture(scope="module")
def world(server: TestClient) -> dict[str, Any]:
    gm, player, stranger = create_user(server), create_user(server), create_user(server)
    systems = {one["slug"]: one for one in asyncio.run(RPGSystemsExtension.game_systems(str(gm.id)))}
    campaign = _create(server, gm, "campaign", name="Split Antler", user_id=gm.id, game_system_id=systems["srd-5e"]["id"])
    percentile = percentile_system(server, gm)
    gothic = _create(server, gm, "campaign", name="Farport", user_id=gm.id, game_system_id=percentile["id"])
    return {
        "gm": gm, "player": player, "stranger": stranger,
        "brann": _create(server, gm, "person", name="Brann", kind="pc", user_id=player.id, campaign_id=campaign["id"]),
        "ilse": _create(server, gm, "person", name="Ilse", kind="pc", user_id=player.id, campaign_id=campaign["id"]),
        "rhia": _create(server, gm, "person", name="Rhia", kind="pc", user_id=player.id, campaign_id=gothic["id"]),
    }


def _run(call: Any) -> Any:
    return asyncio.run(call)


def test_the_methods_are_the_packs(world: dict[str, Any]) -> None:
    options = _run(RPGBuilderExtension.builder_options(str(world["player"].id), world["brann"]["id"]))
    assert [one["slug"] for one in options["abilities"]] == SIX and all(one["score"] is None for one in options["abilities"])
    assert options["methods"]["standard_array"] == [15, 14, 13, 12, 10, 8] and options["can_set"] is True


def test_the_standard_array_sets_the_scores_and_tests_use_them(world: dict[str, Any]) -> None:
    player = str(world["player"].id)
    scores = dict(zip(SIX, [15, 14, 13, 8, 10, 12]))
    done = _run(RPGBuilderExtension.set_abilities(player, world["brann"]["id"], "standard_array", scores))
    assert {one["slug"]: one["score"] for one in done["abilities"]} == {k: float(v) for k, v in scores.items()}
    assert done["can_set"] is False
    checked = _run(RPGDiceExtension.test(player, world["brann"]["id"], "strength"))
    assert checked["no_sheet"] is False and checked["total"] == checked["roll"] + 2
    with pytest.raises(HTTPException) as again:
        _run(RPGBuilderExtension.set_abilities(player, world["brann"]["id"], "standard_array", scores))
    assert again.value.status_code == 422 and "already set" in again.value.detail["message"]
    redone = _run(RPGBuilderExtension.set_abilities(str(world["gm"].id), world["brann"]["id"], "point_buy", dict(zip(SIX, [15, 15, 15, 8, 8, 8]))))
    assert redone["abilities"][1]["score"] == 15.0, "the GM may redo them"


def test_the_roll_is_kept_and_used_once(world: dict[str, Any]) -> None:
    player = str(world["player"].id)
    rolled = _run(RPGBuilderExtension.roll_abilities(player, world["ilse"]["id"]))
    assert len(rolled["scores"]) == 6 and all(3 <= score <= 18 for score in rolled["scores"])
    assert all(len(dice) == 4 for dice in rolled["dice"])
    assert all(score == sum(sorted(dice)[1:]) for score, dice in zip(rolled["scores"], rolled["dice"])), "4d6 keep the highest 3"
    assert _run(RPGBuilderExtension.roll_abilities(player, world["ilse"]["id"], again=True))["scores"] == rolled["scores"], "a player can't re-roll"
    wrong = dict(zip(SIX, [18] * 6))
    with pytest.raises(HTTPException):
        _run(RPGBuilderExtension.set_abilities(player, world["ilse"]["id"], "roll", wrong))
    done = _run(RPGBuilderExtension.set_abilities(player, world["ilse"]["id"], "roll", dict(zip(SIX, rolled["scores"]))))
    assert done["rolled"]["used"] is True
    fresh = _run(RPGBuilderExtension.roll_abilities(str(world["gm"].id), world["ilse"]["id"], again=True))
    assert fresh["used"] is False, "the GM may roll a new set"


def test_strangers_and_packs_without_methods(world: dict[str, Any]) -> None:
    with pytest.raises(HTTPException) as stranger:
        _run(RPGBuilderExtension.builder_options(str(world["stranger"].id), world["brann"]["id"]))
    assert stranger.value.status_code == 404
    with pytest.raises(HTTPException) as plain:
        _run(RPGBuilderExtension.builder_options(str(world["player"].id), world["rhia"]["id"]))
    assert plain.value.status_code == 422 and "no ability score methods" in plain.value.detail["message"]


def test_class_background_and_species_are_chosen_by_the_steps(server: TestClient, world: dict[str, Any]) -> None:
    gm, player = world["gm"], world["player"]
    campaign_id = world["brann"]["campaign_id"]
    fighter = _create(server, gm, "trait", name="Fighter", kind="class", campaign_id=campaign_id)
    wizard = _create(server, gm, "trait", name="Wizard", kind="class", campaign_id=campaign_id)
    soldier = _create(server, gm, "trait", name="Soldier", kind="background", campaign_id=campaign_id)
    _create(server, gm, "trait", name="Dwarf", kind="species", campaign_id=campaign_id)

    steps = _run(RPGBuilderExtension.builder_choices(str(player.id), world["brann"]["id"]))["steps"]
    assert [(one["step"], one["name"]) for one in steps[:3]] == [(1, "Choose a Class"), (2, "Character Origin"), (3, "Ability Scores")]
    assert [choice["kind"] for choice in steps[1]["choices"]] == ["background", "species"]
    assert [option["name"] for option in steps[0]["choices"][0]["options"]] == ["Fighter", "Wizard"]

    done = _run(RPGBuilderExtension.choose(str(player.id), world["brann"]["id"], "class", fighter["id"]))
    assert done["steps"][0]["choices"][0]["chosen"]["name"] == "Fighter"
    with pytest.raises(HTTPException) as again:
        _run(RPGBuilderExtension.choose(str(player.id), world["brann"]["id"], "class", wizard["id"]))
    assert again.value.status_code == 422 and "already chosen" in again.value.detail["message"]
    changed = _run(RPGBuilderExtension.choose(str(gm.id), world["brann"]["id"], "class", wizard["id"]))
    assert changed["steps"][0]["choices"][0]["chosen"]["name"] == "Wizard", "the GM may change it, one class kept"
    with pytest.raises(HTTPException) as wrong:
        _run(RPGBuilderExtension.choose(str(player.id), world["brann"]["id"], "class", soldier["id"]))
    assert wrong.value.status_code == 422 and "isn't a class" in wrong.value.detail["message"]
    with pytest.raises(HTTPException) as unknown:
        _run(RPGBuilderExtension.choose(str(player.id), world["brann"]["id"], "alignment", soldier["id"]))
    assert unknown.value.status_code == 422


def test_an_npc_gets_the_closest_compendium_sheet(server: TestClient, world: dict[str, Any]) -> None:
    gm, player = str(world["gm"].id), str(world["player"].id)
    campaign_id = world["brann"]["campaign_id"]
    barkeep = _create(server, world["gm"], "person", name="Old Tam", kind="npc", campaign_id=campaign_id)
    guard = _create(server, world["gm"], "person", name="Sergeant Holt", kind="npc", campaign_id=campaign_id)

    made = _run(RPGBuilderExtension.npc_sheet(gm, barkeep["id"], "barkeeper", "a gruff tavern keeper"))
    assert (made["source_name"], made["sheet"]["source"], made["sheet_id"]) == ("Commoner", "compendium", barkeep["id"])
    checked = _run(RPGDiceExtension.test(gm, barkeep["id"], "strength"))
    assert checked["no_sheet"] is False and checked["total"] == checked["roll"]

    held = _run(RPGBuilderExtension.sheet_for_npc(gm, guard["id"], "town guard", campaign_id=campaign_id))
    assert held["source_name"] == "Guard" and held["sheet"]["hp"] == 11
    perceives = _run(RPGDiceExtension.test(gm, guard["id"], "perception"))
    assert perceives["skill_rank"] == 1 and perceives["total"] == perceives["roll"]  # WIS 11: +0; no level, no PB

    with pytest.raises(HTTPException) as again:
        _run(RPGBuilderExtension.npc_sheet(gm, guard["id"], "guard"))
    assert again.value.status_code == 422 and "already has a sheet" in again.value.detail["message"]
    with pytest.raises(HTTPException) as player_call:
        _run(RPGBuilderExtension.npc_sheet(player, barkeep["id"], "guard", replace=True))
    assert player_call.value.status_code == 404
    rest = server.post(
        "/v1/sheet/npc",
        json={"npc": {"person_id": guard["id"], "role": "veteran mercenary", "replace": True}},
        headers={"Authorization": f"Bearer {world['gm'].jwt}"},
    )
    assert rest.status_code == 200, rest.text
    assert rest.json()["source_name"] == "Warrior Veteran"
