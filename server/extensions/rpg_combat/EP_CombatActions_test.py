# SPDX-License-Identifier: AGPL-3.0-or-later
"""combat_options and take_combat_action against a real server under the srd-5e pack: a fighter with a
longsword and a Guard built by npc_sheet (its Spear, hit points, AC and Proficiency Bonus) fight;
each is offered only its own attacks and the other as a hostile target, an attack resolves on the
server and takes the damage from the target's hit points, a second action in a turn and a second
reaction in a round are refused, as is anything not offered, and only the GM may ask."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_builder.EXT_RPGBuilder import RPGBuilderExtension
from zephyrex.extensions.rpg_combat.EXT_RPGCombat import RPGCombatExtension
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
    found = response.json()["traits"]
    assert len(found) == 1, found
    return str(found[0]["id"])


def _run(call: Any) -> Any:
    return asyncio.run(call)


@pytest.fixture(scope="module")
def fight(server: TestClient) -> dict[str, Any]:
    gm, player = create_user(server), create_user(server)
    systems = {one["slug"]: one for one in _run(RPGSystemsExtension.game_systems(str(gm.id)))}
    system_id = systems["srd-5e"]["id"]
    campaign = _create(server, gm, "campaign", name="Split Antler", user_id=gm.id, game_system_id=system_id)
    brann = _create(server, gm, "person", name="Brann", kind="pc", user_id=player.id, campaign_id=campaign["id"])
    for slug, field, value in (
        ("strength", "value", 16), ("dexterity", "value", 14), ("hit-points", "value", 12),
        ("proficiency-bonus", "value", 2), ("longsword", None, None),
    ):
        fields = {field: value} if field else {}
        _create(server, gm, "person_trait", person_id=brann["id"], trait_id=_template(server, gm, system_id, slug), **fields)
    guard = _create(server, gm, "person", name="Holt", kind="npc", campaign_id=campaign["id"])
    _run(RPGBuilderExtension.npc_sheet(str(gm.id), guard["id"], "guard"))
    # The guard's stance is the wiki's: a default disposition, hostile toward the party.
    _create(server, gm, "disposition", person_id=guard["id"], target_kind="party", attitude="hostile", is_default=True)
    started = _run(RPGCombatExtension.start_encounter(str(gm.id), campaign["id"], person_ids=[brann["id"], guard["id"]]))
    assert started["status"] == "running", started
    return {"gm": gm, "player": player, "encounter": started, "brann": brann, "guard": guard}


def _options(fight: dict[str, Any], person: dict[str, Any]) -> dict[str, Any]:
    return _run(RPGCombatExtension.combat_options(str(fight["gm"].id), fight["encounter"]["id"], person["id"]))


def test_each_is_offered_its_own_attacks_and_the_other_as_a_hostile_target(fight: dict[str, Any]) -> None:
    brann, guard = _options(fight, fight["brann"]), _options(fight, fight["guard"])
    assert [(one["id"], one["kind"], one["needs_target"]) for one in brann["actions"]] == [("attack:longsword", "attack", True)]
    assert brann["actions"][0]["summary"].startswith("+5 to hit, 1d8+3 slashing")
    assert [(one["person_id"], one["hostile"]) for one in brann["targets"]] == [(fight["guard"]["id"], True)]
    assert [one["id"] for one in guard["actions"]] == ["attack:spear"] and guard["hp_max"] == 11
    assert guard["actions"][0]["summary"].startswith("+3 to hit, 1d6+1 piercing"), "the Guard: STR 13, PB 2 at CR 1/8"
    assert brann["reach"] == "unchecked" and brann["reaction"] == {"available": True, "trigger": None}
    assert [brann["turn"], guard["turn"]].count(True) == 1


def test_an_attack_resolves_and_its_damage_comes_off_the_targets_hit_points(fight: dict[str, Any]) -> None:
    gm, encounter = str(fight["gm"].id), fight["encounter"]["id"]
    acting, other = (fight["brann"], fight["guard"]) if _options(fight, fight["brann"])["turn"] else (fight["guard"], fight["brann"])
    action = _options(fight, acting)["actions"][0]["id"]
    before = _options(fight, other)["hp_max"]
    result = _run(RPGCombatExtension.take_combat_action(gm, encounter, acting["id"], action, target_ids=[other["id"]]))
    assert result["target_ac"] == (16 if other is fight["guard"] else 12)
    assert result["hit"] == (result["critical"] or (result["roll"] != 1 and result["total"] >= result["target_ac"]))
    if result["hit"]:
        assert result["target_hp"] == max(0, before - result["damage"])
    else:
        assert (result["damage"], result["target_hp"]) == (0, before)
    assert _options(fight, acting)["action_available"] is False
    with pytest.raises(HTTPException) as again:
        _run(RPGCombatExtension.take_combat_action(gm, encounter, acting["id"], action, target_ids=[other["id"]]))
    assert again.value.status_code == 422 and "already taken" in again.value.detail["message"]
    # Off its turn, the other may answer with its reaction, once a round.
    answer = _options(fight, other)["actions"][0]["id"]
    if not _options(fight, other)["hp"] == 0:
        _run(RPGCombatExtension.take_combat_action(gm, encounter, other["id"], answer, target_ids=[acting["id"]], use_reaction=True))
        assert _options(fight, other)["reaction"]["available"] is False
        with pytest.raises(HTTPException) as twice:
            _run(RPGCombatExtension.take_combat_action(gm, encounter, other["id"], answer, target_ids=[acting["id"]], use_reaction=True))
        assert "reaction is already used" in twice.value.detail["message"]


def test_anything_not_offered_is_refused_and_only_the_gm_asks(fight: dict[str, Any]) -> None:
    gm, encounter = str(fight["gm"].id), fight["encounter"]["id"]
    with pytest.raises(HTTPException) as unknown:
        _run(RPGCombatExtension.take_combat_action(gm, encounter, fight["brann"]["id"], "attack:greataxe", target_ids=[fight["guard"]["id"]], use_reaction=True))
    assert unknown.value.status_code == 422 and "combat_options lists them" in unknown.value.detail["message"]
    with pytest.raises(HTTPException) as player:
        _run(RPGCombatExtension.combat_options(str(fight["player"].id), encounter, fight["brann"]["id"]))
    assert player.value.status_code == 404


def test_stances_come_from_each_ones_dispositions_and_change_mid_fight(server: TestClient, fight: dict[str, Any]) -> None:
    """The operator: "Combat sides should be based on character disposition not blanket red team and
    blue team". A foe hostile to the party on record is an enemy, and hostility runs both ways; a
    bystander with nothing on record stays neutral, not an enemy, and is an open choice; a betrayal
    and a surrender change it mid-fight."""
    gm = str(fight["gm"].id)
    campaign_id = fight["brann"]["campaign_id"]
    hesk = _create(server, fight["gm"], "person", name="Old Hesk", kind="npc", campaign_id=campaign_id)
    drowned = _create(server, fight["gm"], "person", name="The drowned thing", kind="npc", campaign_id=campaign_id)
    _create(server, fight["gm"], "disposition", person_id=drowned["id"], target_kind="party", attitude="enraged", is_default=True)
    started = _run(RPGCombatExtension.start_encounter(gm, campaign_id, person_ids=[fight["brann"]["id"], hesk["id"], drowned["id"]]))
    stances = {one["name"]: (one["disposition"], one["hostile_to"]) for one in started["combatants"]}
    assert stances["The drowned thing"] == ("hostile", [fight["brann"]["id"]])
    assert stances["Old Hesk"] == ("neutral", []) and stances["Brann"][0] == "friendly"
    assert {one["name"] for one in started["open_choices"]} == {"Old Hesk"}
    assert started["open_choices"][0]["options"] == ["friendly", "neutral", "hostile"]

    def targets() -> dict[str, bool]:
        seen = _run(RPGCombatExtension.combat_options(gm, started["id"], fight["brann"]["id"]))
        return {one["name"]: one["hostile"] for one in seen["targets"]}

    assert targets() == {"Old Hesk": False, "The drowned thing": True}
    # Hesk turns on Brann; the drowned thing yields.
    turned = _run(RPGCombatExtension.set_disposition(gm, started["id"], hesk["id"], disposition="hostile", hostile_to=[fight["brann"]["id"]]))
    assert {one["name"]: one["disposition"] for one in turned["combatants"]}["Old Hesk"] == "hostile"
    _run(RPGCombatExtension.set_disposition(gm, started["id"], drowned["id"], disposition="neutral", hostile_to=[]))
    assert targets() == {"Old Hesk": True, "The drowned thing": False}
    with pytest.raises(HTTPException) as wrong:
        _run(RPGCombatExtension.set_disposition(gm, started["id"], hesk["id"], disposition="red team"))
    assert wrong.value.status_code == 422 and "friendly, neutral or hostile" in wrong.value.detail["message"]
    with pytest.raises(HTTPException) as player:
        _run(RPGCombatExtension.set_disposition(str(fight["player"].id), started["id"], hesk["id"], disposition="hostile"))
    assert player.value.status_code == 404
