# SPDX-License-Identifier: AGPL-3.0-or-later
"""The map is never empty for a table (the operator: "The map is also completely nonfunctional"):
a player reads the campaign's current scene (scenes are the GM's rows, so membership is checked,
not the player's own read); with none active the first becomes current; a campaign with no scene
gets a default grid scene at the party's wiki location with their tokens; and a scenario's scenes
copy into a playthrough with its characters remapped."""

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


def _current(server: TestClient, user: Any, campaign_id: str) -> Any:
    response = server.post("/v1/scene/current", json={"current": {"campaign_id": campaign_id}}, headers=_headers(user))
    assert response.status_code == 200, response.text
    return response.json()["scene"]


def test_a_player_sees_the_gms_scene_and_the_first_becomes_current(server: TestClient) -> None:
    gm, player, stranger = create_user(server), create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="[redacted]", user_id=gm.id)
    _create(server, gm, "person", name="Rhia", kind="pc", user_id=player.id, campaign_id=campaign["id"])
    bridge = _create(server, gm, "scene", name="Bridge", campaign_id=campaign["id"], width=800, height=600)
    shown = _current(server, player, campaign["id"])
    assert shown is not None and shown["id"] == bridge["id"], "not active yet: the first becomes current"
    assert _current(server, gm, campaign["id"])["id"] == bridge["id"]
    assert _current(server, stranger, campaign["id"]) is None


def test_a_campaign_with_no_scene_gets_one_where_the_party_is(server: TestClient) -> None:
    gm, player = create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="Split Antler", user_id=gm.id)
    inn = _create(server, gm, "location", name="The Split Antler")
    road = _create(server, gm, "location", name="North Road")
    brann = _create(server, gm, "person", name="Brann", kind="pc", user_id=player.id, campaign_id=campaign["id"], location_id=inn["id"])
    _create(server, gm, "person", name="Innkeeper", kind="npc", campaign_id=campaign["id"], location_id=inn["id"])
    _create(server, gm, "person", name="Bandit", kind="npc", campaign_id=campaign["id"], location_id=road["id"])

    made = _current(server, player, campaign["id"])
    assert made is not None and (made["name"], made["location_id"]) == ("The Split Antler", inn["id"])
    assert _current(server, player, campaign["id"])["id"] == made["id"], "made once"
    tokens = asyncio.run(RPGSceneExtension.scene_tokens(str(gm.id), made["id"]))
    assert sorted(one["name"] for one in tokens) == ["Brann", "Innkeeper"]
    assert brann["id"] in {one["entity_id"] for one in tokens}
    cells = {(one["token_id"]) for one in tokens}
    assert len(cells) == 2


def test_a_scenarios_scenes_copy_into_its_playthrough(server: TestClient) -> None:
    author, player, other = create_user(server), create_user(server), create_user(server)
    scenario = _create(server, author, "campaign", name="Scenario", user_id=author.id)
    vell = _create(server, author, "person", name="Vell", kind="npc", campaign_id=scenario["id"])
    deck = _create(server, author, "scene", name="Deck", campaign_id=scenario["id"], width=1000, height=600)
    _create(server, author, "scene_wall", scene_id=deck["id"], points=[[500, 0], [500, 400]])
    _create(server, author, "scene_token", name="Vell", scene_id=deck["id"], person_id=vell["id"], x=100, y=100)
    asyncio.run(RPGSceneExtension.activate_scene(str(author.id), deck["id"]))

    playthrough = _create(server, author, "campaign", name="Playthrough", user_id=author.id)
    copy_of_vell = _create(server, author, "person", name="Vell", kind="npc", campaign_id=playthrough["id"])
    copied = asyncio.run(
        RPGSceneExtension.copy_scenes(str(author.id), scenario["id"], playthrough["id"], {vell["id"]: copy_of_vell["id"]})
    )
    assert [one["name"] for one in copied] == ["Deck"] and copied[0]["campaign_id"] == playthrough["id"]
    assert _current(server, author, playthrough["id"])["id"] == copied[0]["id"]
    tokens = asyncio.run(RPGSceneExtension.scene_tokens(str(author.id), copied[0]["id"]))
    assert [one["entity_id"] for one in tokens] == [copy_of_vell["id"]]
    walls = server.get("/v1/scene_wall", params={"scene_id": copied[0]["id"]}, headers=_headers(author)).json()["scene_walls"]
    assert [wall["points"] for wall in walls] == [[[500, 0], [500, 400]]]

    with pytest.raises(HTTPException) as refused:
        asyncio.run(RPGSceneExtension.copy_scenes(str(other.id), scenario["id"], playthrough["id"], {}))
    assert refused.value.status_code == 404
