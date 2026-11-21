# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_scene against a real server: a scene with a wall, a player's view through their own token, the
GM's view through an NPC's, a hidden token never perceived, the 404 for anyone else, and the ability."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_scene.EXT_RPGScene import RPGSceneExtension
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
def room(server: TestClient) -> dict[str, Any]:
    """A 100 px grid of 5 ft cells. The hero at (0, 0); an orc 15 ft east; a goblin behind a wall to
    the south; an assassin the GM has hidden right beside the hero; a closed door in the wall."""
    gm, player = create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="The Vaults", user_id=gm.id)
    hero = _create(server, gm, "person", name="Ada", campaign_id=campaign["id"], user_id=player.id, kind="pc")
    scene = _create(server, gm, "scene", name="Entry Hall", campaign_id=campaign["id"])
    viewer = _create(server, gm, "scene_token", name="Ada", scene_id=scene["id"], person_id=hero["id"])
    orc = _create(server, gm, "scene_token", name="Orc", scene_id=scene["id"], x=300, y=0, disposition="hostile")
    goblin = _create(server, gm, "scene_token", name="Goblin", scene_id=scene["id"], x=0, y=400)
    _create(server, gm, "scene_token", name="Assassin", scene_id=scene["id"], x=100, y=0, is_hidden=True)
    door = _create(
        server, gm, "scene_wall", scene_id=scene["id"], points=[[-100, 250], [300, 250]], door_type="door"
    )
    return {"gm": gm, "player": player, "scene": scene, "viewer": viewer, "orc": orc, "goblin": goblin, "door": door}


def _snapshot(server: TestClient, user: Any, scene_id: str, token_id: str) -> Any:
    body = {"snapshot": {"token_id": token_id}}
    return server.post(f"/v1/scene/{scene_id}/snapshot", json=body, headers=_headers(user))


def test_a_player_sees_through_their_own_token(server: TestClient, room: dict[str, Any]) -> None:
    response = _snapshot(server, room["player"], room["scene"]["id"], room["viewer"]["id"])
    assert response.status_code == 200, response.text
    snapshot = response.json()["snapshot"]
    assert snapshot["lit"] is True and snapshot["units"] == "ft"
    assert snapshot["seen"] == [
        {"id": room["orc"]["id"], "name": "Orc", "person_id": None, "disposition": "hostile", "distance": 15.0}
    ]
    assert snapshot["doors"] == [{"id": room["door"]["id"], "door_type": "door", "door_state": "closed"}]


def test_opening_the_door_shows_whats_behind_it(server: TestClient, room: dict[str, Any]) -> None:
    door = server.get(f"/v1/scene_wall/{room['door']['id']}", headers=_headers(room["gm"]))
    opened = server.put(
        f"/v1/scene_wall/{room['door']['id']}",
        json={"scene_wall": {"door_state": "open"}},
        headers={**_headers(room["gm"]), "If-Match": door.headers["ETag"]},
    )
    assert opened.status_code == 200, opened.text
    seen = _snapshot(server, room["player"], room["scene"]["id"], room["viewer"]["id"]).json()["snapshot"]["seen"]
    assert [one["name"] for one in seen] == ["Orc", "Goblin"]
    server.put(
        f"/v1/scene_wall/{room['door']['id']}",
        json={"scene_wall": {"door_state": "closed"}},
        headers={**_headers(room["gm"]), "If-Match": opened.headers["ETag"]},
    )


def test_the_gm_sees_through_an_npcs_token(server: TestClient, room: dict[str, Any]) -> None:
    response = _snapshot(server, room["gm"], room["scene"]["id"], room["orc"]["id"])
    assert response.status_code == 200, response.text
    assert [one["name"] for one in response.json()["snapshot"]["seen"]] == ["Ada"]


def test_anyone_else_gets_the_same_404_as_a_missing_token(server: TestClient, room: dict[str, Any]) -> None:
    stranger = create_user(server)
    assert _snapshot(server, stranger, room["scene"]["id"], room["viewer"]["id"]).status_code == 404
    # A player can't look through someone else's token either.
    assert _snapshot(server, room["player"], room["scene"]["id"], room["orc"]["id"]).status_code == 404
    missing = "00000000-0000-4000-8000-000000000000"
    assert _snapshot(server, stranger, room["scene"]["id"], missing).status_code == 404


def test_scene_snapshot_is_an_ability(room: dict[str, Any]) -> None:
    info = getattr(getattr(vars(RPGSceneExtension)["scene_snapshot"], "__func__", None), "_ability_info", None)
    assert info is not None and info["name"] == "scene_snapshot"
    snapshot = asyncio.run(
        RPGSceneExtension.scene_snapshot(str(room["player"].id), room["scene"]["id"], room["viewer"]["id"])
    )
    assert [one["name"] for one in snapshot["seen"]] == ["Orc"]
