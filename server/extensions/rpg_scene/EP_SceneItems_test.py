# SPDX-License-Identifier: AGPL-3.0-or-later
"""Things lying on the map (the operator, 2026-11-26: "I haven't seen any loot functionality at
all"): the scene view carries the wiki's unowned item instances at a place the scene shows (its own
place, or one of its regions'), each on a free square by its place; what someone carries isn't
drawn. A fallen combatant's things drop where the body fell (drop_where_fallen, through the wiki's
drop_item): still theirs by right, at their place, drawn on the body's square; items_here lists what
the map draws, and the wiki's take_item takes a thing off it."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_scene.BLL_RPGScene import drop_where_fallen
from zephyrex.extensions.rpg_scene.EXT_RPGScene import RPGSceneExtension
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


def _view(server: TestClient, user: Any, scene_id: str) -> dict[str, Any]:
    response = server.post(f"/v1/scene/{scene_id}/view", json={"view": {}}, headers=_headers(user))
    assert response.status_code == 200, response.text
    found: dict[str, Any] = response.json()["view"]
    return found


def test_lying_things_are_drawn_and_a_fallen_bodys_things_drop_where_it_fell(server: TestClient) -> None:
    gm, player = create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="The Ford", user_id=gm.id)
    ford = _create(server, gm, "location", name="The ford", kind="region", campaign_id=campaign["id"])
    mill = _create(server, gm, "location", name="The mill", kind="building", parent_id=ford["id"], campaign_id=campaign["id"])
    scene = _create(server, gm, "scene", name="The ford", campaign_id=campaign["id"], location_id=ford["id"], width=1000, height=800)
    _create(
        server, gm, "scene_region", name="The mill", scene_id=scene["id"], location_id=mill["id"],
        shapes=[{"type": "rectangle", "x": 600, "y": 0, "width": 400, "height": 300}],
    )
    brann = _create(server, gm, "person", name="Brann", kind="pc", user_id=player.id, campaign_id=campaign["id"], location_id=ford["id"])
    bandit = _create(server, gm, "person", name="Bandit", kind="npc", campaign_id=campaign["id"], location_id=ford["id"])
    _create(server, gm, "scene_token", name="Brann", scene_id=scene["id"], person_id=brann["id"], x=100, y=100)
    _create(server, gm, "scene_token", name="Bandit", scene_id=scene["id"], person_id=bandit["id"], x=400, y=500)

    key = _create(server, gm, "item", name="Silver key", campaign_id=campaign["id"])
    sack = _create(server, gm, "item", name="Flour sack", campaign_id=campaign["id"])
    knife = _create(server, gm, "item", name="Knife", campaign_id=campaign["id"])
    coin = _create(server, gm, "item", name="Coin purse", campaign_id=campaign["id"])
    lying = _create(server, gm, "item_instance", item_id=key["id"], location_id=ford["id"])
    milled = _create(server, gm, "item_instance", item_id=sack["id"], location_id=mill["id"], quantity=3)
    _create(server, gm, "item_instance", item_id=knife["id"], owner_person_id=brann["id"])
    purse = _create(server, gm, "item_instance", item_id=coin["id"], owner_person_id=bandit["id"])

    drawn = {one["name"]: one for one in _view(server, gm, scene["id"])["items"]}
    assert set(drawn) == {"Silver key", "Flour sack"}, "what someone carries isn't lying here"
    assert drawn["Flour sack"]["quantity"] == 3
    sack_x, sack_y = drawn["Flour sack"]["x"], drawn["Flour sack"]["y"]
    assert 600 <= sack_x + 50 <= 1000 and 0 <= sack_y + 50 <= 300, "in the mill's region"
    assert drawn["Silver key"]["id"] == lying["id"] and drawn["Silver key"]["location_id"] == ford["id"]
    squares = {(one["x"] // 100, one["y"] // 100) for one in drawn.values()}
    assert (1, 1) not in squares and (4, 5) not in squares, "never on someone's square"
    # The player sees what lies here too.
    assert {one["name"] for one in _view(server, player, scene["id"])["items"]} == {"Silver key", "Flour sack"}
    assert milled["id"] in {one["id"] for one in drawn.values()}

    here = asyncio.run(RPGSceneExtension.items_here(str(gm.id), scene["id"]))
    assert {(one["name"], one["quantity"]) for one in here["items"]} == {("Silver key", 1), ("Flour sack", 3)}
    assert {one["item_instance_id"] for one in here["items"]} == {lying["id"], milled["id"]}

    # The bandit falls: the purse lies on the body's square, at the bandit's place, still the bandit's.
    from zephyrex.extensions.world_inventory.BLL_WorldInventory import ItemInstanceManager  # type: ignore[import-not-found]
    from zephyrex.lib.Environment import env

    registry = server.app.state.model_registry  # type: ignore[attr-defined]
    assert drop_where_fallen(registry, bandit["id"], scene["id"]) == 1
    dropped = ItemInstanceManager(requester_id=env("ROOT_ID"), model_registry=registry).get(id=purse["id"])
    assert (dropped.owner_person_id, str(dropped.location_id)) == (bandit["id"], ford["id"]), "dropping never changes the owner"
    after = {one["name"]: one for one in _view(server, gm, scene["id"])["items"]}
    assert (after["Coin purse"]["x"], after["Coin purse"]["y"]) == (400.0, 500.0), "where the body fell"
    assert drop_where_fallen(registry, bandit["id"], scene["id"]) == 0, "nothing more on them"
    # Brann loots the purse (the wiki's take_item): it's off the map and on his sheet.
    from zephyrex.extensions.AbstractExtensionProvider import loaded_ability
    from zephyrex.extensions.rpg_dice.EXT_RPGDice import RPGDiceExtension  # type: ignore[import-not-found]

    take = loaded_ability(registry, "rpg_core", "take_item")
    assert take is not None, "the wiki offers take_item (13ceb82+)"
    taken = take(registry, str(gm.id), person_id=brann["id"], item_instance_id=purse["id"])
    taken = asyncio.run(taken) if hasattr(taken, "__await__") else taken
    assert taken["taken"] == 1
    assert "Coin purse" not in {one["name"] for one in asyncio.run(RPGSceneExtension.items_here(str(gm.id), scene["id"]))["items"]}
    gear = asyncio.run(RPGDiceExtension.character_sheet(str(gm.id), brann["id"]))["gear"]
    assert sorted(one["name"] for one in gear) == ["Coin purse", "Knife"], "his own knife (owned, nowhere) and the purse he carries"
    assert asyncio.run(RPGSceneExtension.current_scene(str(gm.id), campaign["id"])) is not None
