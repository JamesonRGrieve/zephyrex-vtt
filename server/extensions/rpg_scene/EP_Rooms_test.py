# SPDX-License-Identifier: AGPL-3.0-or-later
"""Live rooms (server-framework `rooms`): what changes on a scene is heard in that scene's room, by
the people who may see the scene, and the change never carries the record (a hidden token's move
gives away nothing); what changes at a table is heard in its conversation's room."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
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


def _changes(server: TestClient, user: Any, room: str, after: str | None = None) -> Any:
    params = {"after": after} if after else {}
    return server.get(f"/v1/room/{room}/changes", params=params, headers=_headers(user))


def test_a_token_move_is_heard_in_its_scene_room_and_says_nothing_of_where(server: TestClient) -> None:
    gm, stranger = create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="[redacted]", user_id=gm.id)
    scene = _create(server, gm, "scene", name="Bridge", campaign_id=campaign["id"])
    room = f"scene/{scene['id']}"
    start = _changes(server, gm, room)
    assert start.status_code == 200, start.text
    cursor = start.json()["next"]

    token = _create(server, gm, "scene_token", name="Assassin", scene_id=scene["id"], x=100, y=0, is_hidden=True)
    current = server.get(f"/v1/scene_token/{token['id']}", headers=_headers(gm))
    moved = server.put(
        f"/v1/scene_token/{token['id']}",
        json={"scene_token": {"x": 400, "y": 250}},
        headers={**_headers(gm), "If-Match": current.headers["ETag"]},
    )
    assert moved.status_code == 200, moved.text

    heard = _changes(server, gm, room, cursor).json()["changes"]
    mine = [one for one in heard if one["record"]["id"] == token["id"]]
    assert [one["op"] for one in mine] == ["created", "updated"]
    assert all(one["room"] == {"type": "scene", "id": scene["id"]} for one in mine)
    assert not any(key in str(change) for change in mine for key in ("400", "250", "Assassin")), "no record data"

    assert _changes(server, stranger, room).status_code == 404, "only those who may see the scene may listen"


def test_a_seat_is_heard_in_its_tables_conversation_room(server: TestClient) -> None:
    gm = create_user(server)
    campaign = _create(server, gm, "campaign", name="[redacted]", user_id=gm.id)
    table = _create(server, gm, "table", name="Session 1", campaign_id=campaign["id"])
    room = f"conversation/{table['conversation_id']}"
    cursor = _changes(server, gm, room).json()["next"]
    captain = _create(server, gm, "person", name="Captain Vell", campaign_id=campaign["id"], user_id=None)
    seat = _create(
        server, gm, "table_seat", conversation_id=table["conversation_id"], person_id=captain["id"], npc=True
    )
    heard = _changes(server, gm, room, cursor).json()["changes"]
    assert any(one["record"]["id"] == seat["id"] and one["op"] == "created" for one in heard)


def test_scenes_and_tables_are_news_in_their_campaigns_room_but_token_moves_are_not(server: TestClient) -> None:
    gm = create_user(server)
    campaign = _create(server, gm, "campaign", name="[redacted]", user_id=gm.id)
    room = f"campaign/{campaign['id']}"
    assert _changes(server, gm, room).status_code == 200
    # A cursor needs a change in the room to point at (an empty room's `next` is null).
    _create(server, gm, "scene", name="Hold", campaign_id=campaign["id"])
    cursor = _changes(server, gm, room).json()["next"]
    assert cursor
    scene = _create(server, gm, "scene", name="Bridge", campaign_id=campaign["id"])
    table = _create(server, gm, "table", name="Session 1", campaign_id=campaign["id"])
    token = _create(server, gm, "scene_token", name="Osk", scene_id=scene["id"])
    heard = {one["record"]["id"] for one in _changes(server, gm, room, cursor).json()["changes"]}
    assert {scene["id"], table["id"]} <= heard
    assert token["id"] not in heard, "a token's changes stay in its scene's room"
