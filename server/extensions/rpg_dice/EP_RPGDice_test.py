# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_dice against a real server: rolls and checks made on the server, a refused formula, a stat
resolved from a character's traits, the GM-or-own-player rule, and the abilities an agent calls."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_dice.EXT_RPGDice import RPGDiceExtension
from zephyrex.testing.factories import create_user

from vtt_app import create


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    yield TestClient(create())


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _create(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = server.post(f"/v1/{resource}", json={resource: fields}, headers=_headers(user))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()[resource]
    return created


@pytest.fixture(scope="module")
def table(server: TestClient) -> dict[str, Any]:
    """A GM's campaign with one character: Dexterity (the system's template) 3, plus a +2 that always applies."""
    gm = create_user(server)
    system = _create(server, gm, "game_system", name="Test System")
    campaign = _create(server, gm, "campaign", name="Test Campaign", game_system_id=system["id"], user_id=gm.id)
    hero = _create(server, gm, "person", name="Ada", campaign_id=campaign["id"], kind="pc")
    dexterity = _create(server, gm, "trait", name="Dexterity", kind="attribute", game_system_id=system["id"])
    _create(server, gm, "person_trait", person_id=hero["id"], trait_id=dexterity["id"], value=3)
    _create(server, gm, "derivative_trait", target_trait_id=dexterity["id"], operation="additive", value=2)
    return {"gm": gm, "hero": hero, "dexterity": dexterity}


def test_a_roll_is_made_on_the_server(server: TestClient, table: dict[str, Any]) -> None:
    response = server.post("/v1/dice/roll", json={"roll": {"formula": "2d6+1"}}, headers=_headers(table["gm"]))
    assert response.status_code == 200, response.text
    rolled = response.json()["roll"]
    assert len(rolled["terms"][0]["dice"]) == 2
    assert all(1 <= die["value"] <= 6 for die in rolled["terms"][0]["dice"])
    assert rolled["total"] == rolled["terms"][0]["value"] + 1


def test_a_formula_that_cant_be_rolled_is_a_422_naming_why(server: TestClient, table: dict[str, Any]) -> None:
    response = server.post("/v1/dice/roll", json={"roll": {"formula": "2d6x"}}, headers=_headers(table["gm"]))
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["type"] == "bad_token"


def test_a_roll_needs_a_sign_in(server: TestClient) -> None:
    assert server.post("/v1/dice/roll", json={"roll": {"formula": "1d6"}}).status_code in (401, 403)


def test_a_check_resolves_the_stat_from_the_characters_traits(server: TestClient, table: dict[str, Any]) -> None:
    body = {"check": {"person_id": table["hero"]["id"], "formula": "1d20 + @dexterity", "target": 6}}
    response = server.post("/v1/dice/check", json=body, headers=_headers(table["gm"]))
    assert response.status_code == 200, response.text
    checked = response.json()["check"]
    [dexterity] = checked["resolved"]
    assert (dexterity["name"], dexterity["base"], dexterity["value"]) == ("dexterity", 3, 5)
    assert checked["stats"] == {"dexterity": 5}
    die = checked["terms"][0]["dice"][0]["value"]
    assert checked["total"] == die + 5
    assert checked["success"] is True and checked["margin"] == die - 1


def test_a_check_names_a_stat_the_character_lacks(server: TestClient, table: dict[str, Any]) -> None:
    body = {"check": {"person_id": table["hero"]["id"], "formula": "1d20 + @charisma"}}
    response = server.post("/v1/dice/check", json=body, headers=_headers(table["gm"]))
    assert response.status_code == 422
    assert response.json()["detail"]["errors"][0]["type"] == "unknown_stat"


def test_someone_elses_character_is_not_found(server: TestClient, table: dict[str, Any]) -> None:
    """The same 404 as a character that doesn't exist, so a stranger learns nothing about the id."""
    stranger = create_user(server)
    body = {"check": {"person_id": table["hero"]["id"], "formula": "1d20"}}
    assert server.post("/v1/dice/check", json=body, headers=_headers(stranger)).status_code == 404
    missing = {"check": {"person_id": "00000000-0000-4000-8000-000000000000", "formula": "1d20"}}
    assert server.post("/v1/dice/check", json=missing, headers=_headers(stranger)).status_code == 404


def test_roll_and_check_are_abilities() -> None:
    members = vars(RPGDiceExtension).values()
    infos = [getattr(getattr(member, "__func__", member), "_ability_info", None) for member in members]
    abilities = {info["name"] for info in infos if info is not None}
    assert {"roll", "check"} <= abilities


def test_the_roll_ability_rolls_on_the_server(table: dict[str, Any]) -> None:
    rolled = asyncio.run(RPGDiceExtension.roll(str(table["gm"].id), "3d6"))
    assert 3 <= rolled["total"] <= 18


def test_a_players_own_check_counts_a_gm_hidden_trait_without_showing_it(server: TestClient) -> None:
    """A player checks their own character. Dexterity is the system's template, so the player may name
    it whoever made it. A curse the GM made for this campaign (which the player can't read) still
    counts, folded into one hidden step; naming the curse is refused exactly as a name that doesn't
    exist, so its existence isn't confirmed either."""
    gm, player = create_user(server), create_user(server)
    system = _create(server, gm, "game_system", name="Secret System")
    campaign = _create(server, gm, "campaign", name="Hidden Things", game_system_id=system["id"], user_id=gm.id)
    hero = _create(server, gm, "person", name="Bram", campaign_id=campaign["id"], user_id=player.id, kind="pc")
    dexterity = _create(server, gm, "trait", name="Dexterity", kind="attribute", game_system_id=system["id"])
    curse = _create(server, gm, "trait", name="Curse", kind="status_effect", campaign_id=campaign["id"])
    _create(server, gm, "person_trait", person_id=hero["id"], trait_id=dexterity["id"], value=3)
    _create(server, gm, "person_trait", person_id=hero["id"], trait_id=curse["id"], value=2)
    hidden = _create(
        server, gm, "derivative_trait", source_trait_id=curse["id"], target_trait_id=dexterity["id"],
        operation="additive", value=1,
    )

    body = {"check": {"person_id": hero["id"], "formula": "1d20 + @dexterity"}}
    response = server.post("/v1/dice/check", json=body, headers=_headers(player))
    assert response.status_code == 200, response.text
    [stat] = response.json()["check"]["resolved"]
    assert stat["value"] == 5
    assert hidden["id"] not in {step["id"] for step in stat["steps"]}
    assert stat["steps"] == [{"id": "hidden", "operation": "hidden", "size": 2, "result": 5}]

    def named(stat: str) -> Any:
        probe = {"check": {"person_id": hero["id"], "formula": f"1d20 + @{stat}"}}
        return server.post("/v1/dice/check", json=probe, headers=_headers(player))

    # The GM's secret and a name that doesn't exist answer alike, apart from the name itself.
    secret, nothing = named("curse"), named("nonexistent")
    assert (secret.status_code, nothing.status_code) == (422, 422)
    assert secret.json()["detail"]["errors"] == nothing.json()["detail"]["errors"] == [
        {"type": "unknown_stat", "loc": ["formula"]}
    ]
    assert secret.json()["detail"]["message"] == "There is no stat called @curse"
    assert nothing.json()["detail"]["message"] == "There is no stat called @nonexistent"

    # The GM sees every step, by name.
    seen = server.post("/v1/dice/check", json=body, headers=_headers(gm)).json()["check"]["resolved"][0]["steps"]
    assert [step["id"] for step in seen] == [hidden["id"]]


def test_fold_hidden_keeps_only_the_net_effect() -> None:
    from zephyrex.extensions.rpg_dice.BLL_RPGDice import fold_hidden
    from zephyrex.extensions.rpg_dice.Check import Step

    steps = [
        Step(id="a", operation="additive", size=2, result=12),
        Step(id="x", operation="additive", size=3, result=15),
        Step(id="y", operation="multiplicative", size=2, result=30),
        Step(id="b", operation="clamp", size=-20, result=20),
    ]
    folded = [step.model_dump() for step in fold_hidden(10, steps, {"a", "b"})]
    assert folded == [
        {"id": "a", "operation": "additive", "size": 2, "result": 12},
        {"id": "hidden", "operation": "hidden", "size": 18, "result": 30},
        {"id": "b", "operation": "clamp", "size": -20, "result": 20},
    ]


def test_an_items_bonus_counts_only_while_worn(server: TestClient, table: dict[str, Any]) -> None:
    """A ring of protection adds to Dexterity only while it sits in one of the character's
    equipment slots; in their pack it's carried, not worn, and adds nothing."""
    gm, hero, dexterity = table["gm"], table["hero"], table["dexterity"]
    ring = _create(server, gm, "item", name="Ring of Grace")
    _create(server, gm, "derivative_trait", source_item_id=ring["id"], target_trait_id=dexterity["id"],
            operation="additive", value=1)
    hand = _create(server, gm, "location", name="Left hand", kind="equipment_slot", associated_person_id=hero["id"])
    pack = _create(server, gm, "location", name="Pack", kind="container", associated_person_id=hero["id"])
    instance = _create(server, gm, "item_instance", item_id=ring["id"], location_id=pack["id"])

    def dexterity_now() -> float:
        body = {"check": {"person_id": hero["id"], "formula": "@dexterity"}}
        response = server.post("/v1/dice/check", json=body, headers=_headers(gm))
        assert response.status_code == 200, response.text
        value: float = response.json()["check"]["resolved"][0]["value"]
        return value

    assert dexterity_now() == 5  # in the pack: 3, plus the +2 that always applies
    current = server.get(f"/v1/item_instance/{instance['id']}", headers=_headers(gm))
    moved = server.put(
        f"/v1/item_instance/{instance['id']}",
        json={"item_instance": {"location_id": hand["id"]}},
        headers={**_headers(gm), "If-Match": current.headers["ETag"]},
    )
    assert moved.status_code == 200, moved.text
    assert dexterity_now() == 6  # worn on the left hand
