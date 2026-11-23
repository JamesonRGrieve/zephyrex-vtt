# SPDX-License-Identifier: AGPL-3.0-or-later
"""Encounters against a real server, under a d100 pack (the synthetic percentile-test pack): initiative
is 1d10 + the Grace bonus, rolled on the server; ties go to the higher Grace, then a roll-off;
a combatant with no stats waits for the GM's number; the turn passes in order, skipping the defeated,
and a new round follows the last; players see the order without hidden combatants and can't run it."""

import asyncio
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_combat.BLL_RPGCombat import ordered
from zephyrex.extensions.rpg_combat.EXT_RPGCombat import RPGCombatExtension
from zephyrex.extensions.rpg_dice.EXT_RPGDice import RPGDiceExtension
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
    return str(response.json()["traits"][0]["id"])


@pytest.fixture(scope="module")
def fight(server: TestClient) -> dict[str, Any]:
    """Two characters (Grace 35 and 42), a cultist with no stats, and a hidden one on a scene."""
    gm, player, stranger = create_user(server), create_user(server), create_user(server)
    system = percentile_system(server, gm)
    campaign = _create(server, gm, "campaign", name="Harbour", user_id=gm.id, game_system_id=system["id"])
    agility = _template(server, gm, system["id"], "grace")
    rhia = _create(server, gm, "person", name="Rhia", kind="pc", user_id=player.id, campaign_id=campaign["id"])
    osk = _create(server, gm, "person", name="Osk", kind="pc", campaign_id=campaign["id"])
    for person, value in ((rhia, 35), (osk, 42)):
        _create(server, gm, "person_trait", person_id=person["id"], trait_id=agility, value=value)
    cultist = _create(server, gm, "person", name="Cultist", kind="npc", campaign_id=campaign["id"])
    lurker = _create(server, gm, "person", name="Lurker", kind="npc", campaign_id=campaign["id"])
    scene = _create(server, gm, "scene", name="Chapel", campaign_id=campaign["id"], width=500, height=500)
    for person, hidden in ((rhia, False), (osk, False), (cultist, False), (lurker, True)):
        _create(server, gm, "scene_token", name=person["name"], scene_id=scene["id"], person_id=person["id"], is_hidden=hidden)
    return {
        "gm": gm, "player": player, "stranger": stranger, "campaign": campaign, "scene": scene,
        "rhia": rhia, "osk": osk, "cultist": cultist, "lurker": lurker,
    }


def test_initiative_is_1d10_plus_the_grace_bonus(fight: dict[str, Any]) -> None:
    for _ in range(20):
        rolled = asyncio.run(RPGDiceExtension.initiative(str(fight["player"].id), fight["rhia"]["id"]))
        assert (rolled["dice"], rolled["characteristic"], rolled["value"], rolled["bonus"]) == ("1d10", "grace", 35, 3)
        assert 1 <= rolled["roll"] <= 10 and rolled["total"] == rolled["roll"] + 3
    with pytest.raises(HTTPException) as refused:
        asyncio.run(RPGDiceExtension.initiative(str(fight["stranger"].id), fight["rhia"]["id"]))
    assert refused.value.status_code == 404


def test_ties_go_to_the_higher_characteristic_then_the_roll_off() -> None:
    def one(name: str, initiative: Any, tiebreak: Any = None, roll_off: Any = None) -> Any:
        return SimpleNamespace(id=name, name=name, initiative=initiative, tiebreak=tiebreak, roll_off=roll_off)

    found = ordered([one("waits", None), one("slow", 7, 30, 9), one("quick", 9, 30, 1), one("agile", 7, 41, 1), one("lucky", 7, 30, 10)])
    assert [each.id for each in found] == ["quick", "agile", "lucky", "slow", "waits"]


def test_the_gm_runs_a_fight_from_the_scene(server: TestClient, fight: dict[str, Any]) -> None:
    gm = str(fight["gm"].id)
    started = asyncio.run(RPGCombatExtension.start_encounter(gm, fight["campaign"]["id"], scene_id=fight["scene"]["id"]))
    assert started["status"] == "setup", "the NPCs have no stats: the fight waits for the GM's numbers"
    assert {one["name"] for one in started["unrolled"]} == {"Cultist", "Lurker"}
    by_name = {one["name"]: one for one in started["combatants"]}
    assert set(by_name) == {"Rhia", "Osk", "Cultist", "Lurker"} and by_name["Lurker"]["is_hidden"] is True
    assert 4 <= by_name["Rhia"]["initiative"] <= 13 and 5 <= by_name["Osk"]["initiative"] <= 14

    with pytest.raises(HTTPException) as early:
        asyncio.run(RPGCombatExtension.start_combat(gm, started["id"]))
    assert early.value.status_code == 422 and "Cultist" in early.value.detail["message"]

    for name, value in (("Cultist", 20), ("Lurker", 0)):
        path = f"/v1/combatant/{by_name[name]['id']}"
        current = server.get(path, headers=_headers(fight["gm"]))
        updated = server.put(
            path,
            json={"combatant": {"initiative": value}},
            headers={**_headers(fight["gm"]), "If-Match": current.headers["ETag"]},
        )
        assert updated.status_code == 200, updated.text

    running = asyncio.run(RPGCombatExtension.start_combat(gm, started["id"]))
    names = [one["name"] for one in running["combatants"]]
    assert names[0] == "Cultist" and names[-1] == "Lurker"
    assert (running["status"], running["round"], running["current_combatant_id"]) == ("running", 1, by_name["Cultist"]["id"])

    # Rhia falls; the turn skips her, and after the last a new round starts at the top.
    rhia = by_name["Rhia"]["id"]
    current = server.get(f"/v1/combatant/{rhia}", headers=_headers(fight["gm"]))
    server.put(
        f"/v1/combatant/{rhia}",
        json={"combatant": {"is_defeated": True}},
        headers={**_headers(fight["gm"]), "If-Match": current.headers["ETag"]},
    )
    seen = []
    for _ in range(3):
        passed = asyncio.run(RPGCombatExtension.next_turn(gm, started["id"]))
        seen.append((passed["round"], passed["current_combatant_id"]))
    assert seen == [(1, by_name["Osk"]["id"]), (1, by_name["Lurker"]["id"]), (2, by_name["Cultist"]["id"])]

    current_encounter = asyncio.run(RPGCombatExtension.current_encounter(gm, fight["campaign"]["id"]))
    assert current_encounter is not None and current_encounter["id"] == started["id"]

    ended = asyncio.run(RPGCombatExtension.end_encounter(gm, started["id"]))
    assert (ended["status"], ended["current_combatant_id"]) == ("ended", None)
    assert asyncio.run(RPGCombatExtension.current_encounter(gm, fight["campaign"]["id"])) is None


def test_players_see_the_order_but_not_hidden_combatants_and_cant_run_it(server: TestClient, fight: dict[str, Any]) -> None:
    gm = str(fight["gm"].id)
    encounter = asyncio.run(
        RPGCombatExtension.start_encounter(
            gm, fight["campaign"]["id"], person_ids=[fight["rhia"]["id"], fight["osk"]["id"], fight["lurker"]["id"]],
            hidden_person_ids=[fight["lurker"]["id"]],
        )
    )
    shown = server.get(f"/v1/encounter/{encounter['id']}/order", headers=_headers(fight["player"]))
    assert shown.status_code == 200, shown.text
    order = shown.json()["encounter"]
    assert {one["name"] for one in order["combatants"]} == {"Rhia", "Osk"}
    assert order["gm"] is False
    assert [one["controlled"] for one in order["combatants"] if one["name"] == "Rhia"] == [True]
    assert [one["controlled"] for one in order["combatants"] if one["name"] == "Osk"] == [False]

    assert server.get(f"/v1/encounter/{encounter['id']}/order", headers=_headers(fight["stranger"])).status_code == 404
    for action in ("next", "end", "start"):
        refused = server.post(
            f"/v1/encounter/{encounter['id']}/{action}", json={"control": {}}, headers=_headers(fight["player"])
        )
        assert refused.status_code == 404, (action, refused.text)

    # Round and status are the server's: an update can't set them.
    current = server.get(f"/v1/encounter/{encounter['id']}", headers=_headers(fight["gm"]))
    server.put(
        f"/v1/encounter/{encounter['id']}",
        json={"encounter": {"name": "Ambush", "status": "ended", "round": 9}},
        headers={**_headers(fight["gm"]), "If-Match": current.headers["ETag"]},
    )
    after = server.get(f"/v1/encounter/{encounter['id']}/order", headers=_headers(fight["gm"])).json()["encounter"]
    # The Lurker has no Grace, so this fight is still in setup: the update moved neither.
    assert (after["name"], after["status"], after["round"]) == ("Ambush", "setup", 0)


def test_only_the_gm_makes_encounters_and_combatants_must_be_the_campaigns(server: TestClient, fight: dict[str, Any]) -> None:
    refused = server.post(
        "/v1/encounter", json={"encounter": {"campaign_id": fight["campaign"]["id"]}}, headers=_headers(fight["player"])
    )
    assert refused.status_code == 404, refused.text
    other = _create(server, fight["gm"], "campaign", name="Elsewhere", user_id=fight["gm"].id)
    outsider = _create(server, fight["gm"], "person", name="Outsider", campaign_id=other["id"])
    encounter = _create(server, fight["gm"], "encounter", campaign_id=fight["campaign"]["id"])
    wrong = server.post(
        "/v1/combatant",
        json={"combatant": {"encounter_id": encounter["id"], "person_id": outsider["id"]}},
        headers=_headers(fight["gm"]),
    )
    assert wrong.status_code == 422, wrong.text
