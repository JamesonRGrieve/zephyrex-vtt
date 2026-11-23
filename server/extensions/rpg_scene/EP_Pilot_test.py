# SPDX-License-Identifier: AGPL-3.0-or-later
"""The GM agent pilots characters on the map as time advances: scenes and regions know their wiki
places, a campaign has one current scene, pilot_token walks a token round walls (a step at a time
under max_distance), moves it between scenes, takes it off the maps for a place no map shows, and
the person's wiki location follows the token."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
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


def _person(server: TestClient, user: Any, person_id: str) -> dict[str, Any]:
    found: dict[str, Any] = server.get(f"/v1/person/{person_id}", headers=_headers(user)).json()["person"]
    return found


def test_the_gm_pilots_a_character_round_walls_between_scenes_and_off_the_map(server: TestClient) -> None:
    gm = create_user(server)
    campaign = _create(server, gm, "campaign", name="Harbour", user_id=gm.id)
    ship = _create(server, gm, "location", name="The Grey Gull")
    deck = _create(server, gm, "location", name="Pilgrim Deck", parent_id=ship["id"])
    chapel = _create(server, gm, "location", name="Chapel", parent_id=deck["id"])
    brig = _create(server, gm, "location", name="Brig", parent_id=ship["id"])
    planet = _create(server, gm, "location", name="Farport")
    vell = _create(server, gm, "person", name="Captain Vell", campaign_id=campaign["id"])
    deck_scene = _create(
        server, gm, "scene", name="Pilgrim Deck", campaign_id=campaign["id"], location_id=deck["id"], width=1000, height=600
    )
    brig_scene = _create(
        server, gm, "scene", name="Brig", campaign_id=campaign["id"], location_id=brig["id"], width=500, height=300
    )
    _create(
        server, gm, "scene_region", name="Chapel", scene_id=deck_scene["id"], location_id=chapel["id"],
        shapes=[{"type": "rectangle", "x": 600, "y": 0, "width": 400, "height": 300}],
    )
    # A bulkhead down the middle of the deck, open only at the far end.
    _create(server, gm, "scene_wall", scene_id=deck_scene["id"], points=[[500, 0], [500, 400]])

    def pilot(**target: Any) -> dict[str, Any]:
        return asyncio.run(RPGSceneExtension.pilot_token(str(gm.id), vell["id"], **target))

    activated = asyncio.run(RPGSceneExtension.activate_scene(str(gm.id), deck_scene["id"]))
    assert activated["id"] == deck_scene["id"]
    current = asyncio.run(RPGSceneExtension.current_scene(str(gm.id), campaign["id"]))
    assert current is not None and current["location_id"] == deck["id"]

    placed = pilot(location_id=chapel["id"])
    assert (placed["scene_id"], placed["x"], placed["y"]) == (deck_scene["id"], 800.0, 100.0), "the region's centre cell"
    assert placed["location_id"] == chapel["id"] and _person(server, gm, vell["id"])["location_id"] == chapel["id"]

    short = pilot(scene_id=deck_scene["id"], x=50, y=50, max_distance=10)
    assert short["arrived"] is False and short["remaining"] > 0, "two cells this tick, round the bulkhead later"
    walked = pilot(scene_id=deck_scene["id"], x=50, y=50)
    assert (walked["arrived"], walked["x"], walked["y"]) == (True, 0.0, 0.0)
    assert walked["location_id"] == deck["id"], "outside the chapel: the deck"

    moved = pilot(location_id=brig["id"])
    assert moved["scene_id"] == brig_scene["id"] and moved["removed"] == 1
    tokens = asyncio.run(RPGSceneExtension.scene_tokens(str(gm.id), deck_scene["id"]))
    assert all(one["entity_id"] != vell["id"] for one in tokens), "one token per person"

    away = pilot(location_id=planet["id"])
    assert (away["token_id"], away["removed"], away["location_id"]) == (None, 1, planet["id"])
    assert _person(server, gm, vell["id"])["location_id"] == planet["id"]

    with pytest.raises(HTTPException) as stranger:
        asyncio.run(RPGSceneExtension.pilot_token(str(create_user(server).id), vell["id"], location_id=deck["id"]))
    assert stranger.value.status_code == 404


def test_a_sealed_room_has_no_way_through(server: TestClient) -> None:
    gm = create_user(server)
    campaign = _create(server, gm, "campaign", name="Vault", user_id=gm.id)
    vell = _create(server, gm, "person", name="Vell", campaign_id=campaign["id"])
    scene = _create(server, gm, "scene", name="Vault", campaign_id=campaign["id"], width=500, height=300)
    _create(server, gm, "scene_wall", scene_id=scene["id"], points=[[250, 0], [250, 300]])
    asyncio.run(RPGSceneExtension.pilot_token(str(gm.id), vell["id"], scene_id=scene["id"], x=50, y=50))
    with pytest.raises(HTTPException) as sealed:
        asyncio.run(RPGSceneExtension.pilot_token(str(gm.id), vell["id"], scene_id=scene["id"], x=450, y=50))
    assert sealed.value.status_code == 422


def test_only_activate_makes_a_scene_current(server: TestClient) -> None:
    gm = create_user(server)
    campaign = _create(server, gm, "campaign", name="Vault", user_id=gm.id)
    first = _create(server, gm, "scene", name="One", campaign_id=campaign["id"])
    second = _create(server, gm, "scene", name="Two", campaign_id=campaign["id"])
    current = server.get(f"/v1/scene/{first['id']}", headers=_headers(gm))
    put = server.put(
        f"/v1/scene/{first['id']}",
        json={"scene": {"is_active": True}},
        headers={**_headers(gm), "If-Match": current.headers["ETag"]},
    )
    assert put.status_code in (200, 422)
    after = server.get(f"/v1/scene/{first['id']}", headers=_headers(gm)).json()["scene"]
    assert not after.get("is_active"), "not through a PUT"
    asyncio.run(RPGSceneExtension.activate_scene(str(gm.id), first["id"]))
    asyncio.run(RPGSceneExtension.activate_scene(str(gm.id), second["id"]))
    found = asyncio.run(RPGSceneExtension.current_scene(str(gm.id), campaign["id"]))
    assert found is not None and found["id"] == second["id"], "one current scene per campaign"
