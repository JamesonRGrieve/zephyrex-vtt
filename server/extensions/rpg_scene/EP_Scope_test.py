# SPDX-License-Identifier: AGPL-3.0-or-later
"""The map at a scope (the operator, on The Missing Merchant's map: "It also needs a scope-out mode
that shows, for example, the town instead of the house, with a group token for each group of notable
NPCs if multiple occupy the same building"): the town shows a group marker per occupied building,
the party as its own group, positions from a region or the GM's pin, the scene's art or a label; and
arrivals at a place spread out rather than packing into a block."""

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
    with TestClient(create()) as client:
        yield client


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _create(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = server.post(f"/v1/{resource}", json={resource: fields}, headers=_headers(user))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()[resource]
    return created


def _scope(server: TestClient, user: Any, campaign_id: str, location_id: Any = None) -> Any:
    return server.post("/v1/scene/scope", json={"scope": {"campaign_id": campaign_id, "location_id": location_id}}, headers=_headers(user))


@pytest.fixture(scope="module")
def town(server: TestClient) -> dict[str, Any]:
    gm, player, stranger = create_user(server), create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="The Missing Merchant", user_id=gm.id)
    place = lambda name, kind, parent=None: _create(  # noqa: E731
        server, gm, "location", name=name, kind=kind, parent_id=parent, campaign_id=campaign["id"]
    )
    coast = place("The Salt Coast", "region")
    saltmere = place("Saltmere", "city", coast["id"])
    house = place("Halloway house", "building", saltmere["id"])
    parlour = place("The parlour", "room", house["id"])
    inn = place("The Drowned Lantern", "building", saltmere["id"])
    person = lambda name, kind, where, **more: _create(  # noqa: E731
        server, gm, "person", name=name, kind=kind, campaign_id=campaign["id"], location_id=where, **more
    )
    person("Old Hesk", "npc", parlour["id"])
    person("Mara Halloway", "npc", house["id"])
    person("Tobin Halloway", "npc", parlour["id"])
    person("Innkeeper Rusk", "npc", inn["id"])
    brann = person("Brann", "pc", inn["id"], user_id=player.id)
    person("Town crier", "npc", saltmere["id"])
    return {"gm": gm, "player": player, "stranger": stranger, "campaign": campaign, "coast": coast, "saltmere": saltmere, "house": house, "inn": inn, "brann": brann}


def test_the_town_shows_a_group_per_occupied_building_and_the_party(server: TestClient, town: dict[str, Any]) -> None:
    shown = _scope(server, town["gm"], town["campaign"]["id"], town["saltmere"]["id"])
    assert shown.status_code == 200, shown.text
    body = shown.json()
    assert (body["location"]["name"], body["scope"], body["parent"]["name"]) == ("Saltmere", "city", "The Salt Coast")
    assert [one["name"] for one in body["path"]] == ["The Salt Coast", "Saltmere"]
    markers = {one["name"]: one for one in body["markers"]}
    assert set(markers) == {"Halloway house", "The Drowned Lantern"}
    assert markers["Halloway house"]["count"] == 3 and markers["Halloway house"]["kind"] == "building"
    assert [one["name"] for one in markers["Halloway house"]["people"]] == ["Mara Halloway", "Old Hesk", "Tobin Halloway"]
    assert all(0 < one["x"] < 1 and 0 < one["y"] < 1 and one["placed"] is False for one in body["markers"])
    assert [(one["location_id"], [p["name"] for p in one["people"]]) for one in body["parties"]] == [(town["inn"]["id"], ["Brann"])]
    assert [one["name"] for one in body["here"]] == ["Town crier"]
    # No scene of the town yet: a labelled placeholder, never a bare grid.
    assert body["background"] == {"url": None, "scene_id": None, "label": "Saltmere"}


def test_scoping_out_shows_the_town_as_one_group_and_players_see_it_too(server: TestClient, town: dict[str, Any]) -> None:
    answer = _scope(server, town["player"], town["campaign"]["id"], town["coast"]["id"])
    assert answer.status_code == 200, answer.text
    region = answer.json()
    assert region["parent"] is None and [one["name"] for one in region["markers"]] == ["Saltmere"]
    assert region["markers"][0]["count"] == 5
    assert _scope(server, town["stranger"], town["campaign"]["id"], town["saltmere"]["id"]).status_code == 404


def test_a_region_on_the_towns_map_and_a_pin_place_the_markers(server: TestClient, town: dict[str, Any]) -> None:
    gm, campaign = town["gm"], town["campaign"]
    scene = _create(
        server, gm, "scene", name="Saltmere", campaign_id=campaign["id"], location_id=town["saltmere"]["id"], width=2000, height=1000,
        background_url="https://maps.example/saltmere.webp",
    )
    _create(
        server, gm, "scene_region", scene_id=scene["id"], location_id=town["house"]["id"], name="Halloway house",
        shapes=[{"type": "rectangle", "x": 200, "y": 100, "width": 200, "height": 200}],
    )
    body = _scope(server, gm, campaign["id"], town["saltmere"]["id"]).json()
    assert body["background"] == {"url": "https://maps.example/saltmere.webp", "scene_id": scene["id"], "label": "Saltmere"}
    house = next(one for one in body["markers"] if one["name"] == "Halloway house")
    assert (house["x"], house["y"], house["placed"]) == (0.15, 0.2, True)

    pinned = server.post(
        "/v1/scene/place_on_scope",
        json={"place_on_scope": {"campaign_id": campaign["id"], "location_id": town["inn"]["id"], "x": 0.7, "y": 0.6}},
        headers=_headers(gm),
    )
    assert pinned.status_code == 200, pinned.text
    inn = next(one for one in pinned.json()["markers"] if one["name"] == "The Drowned Lantern")
    assert (inn["x"], inn["y"], inn["placed"]) == (0.7, 0.6, True)
    # The party sits beside the inn's NPCs.
    assert (pinned.json()["parties"][0]["x"], pinned.json()["parties"][0]["y"]) == (0.76, 0.6)
    refused = server.post(
        "/v1/scene/place_on_scope",
        json={"place_on_scope": {"campaign_id": campaign["id"], "location_id": town["inn"]["id"], "x": 0.1, "y": 0.1}},
        headers=_headers(town["player"]),
    )
    assert refused.status_code == 404


def test_the_scope_ability_defaults_to_the_partys_place(town: dict[str, Any]) -> None:
    shown = asyncio.run(RPGSceneExtension.scene_scope(str(town["gm"].id), town["campaign"]["id"]))
    assert shown["location"]["name"] == "The Drowned Lantern"
    assert [one["name"] for one in shown["here"]] == ["Innkeeper Rusk"]


def test_a_crowd_arriving_at_a_default_scene_spreads_out(server: TestClient) -> None:
    gm, player = create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="Crowded", user_id=gm.id)
    hall = _create(server, gm, "location", name="The hall", campaign_id=campaign["id"])
    _create(server, gm, "person", name="Ada", kind="pc", user_id=player.id, campaign_id=campaign["id"], location_id=hall["id"])
    for name in ("Bo", "Cy", "Di", "Ed", "Flo"):
        _create(server, gm, "person", name=name, kind="npc", campaign_id=campaign["id"], location_id=hall["id"])
    made = server.post("/v1/scene/current", json={"current": {"campaign_id": campaign["id"]}}, headers=_headers(gm)).json()["scene"]
    view = server.post(f"/v1/scene/{made['id']}/view", json={"view": {}}, headers=_headers(gm))
    assert view.status_code == 200, view.text
    cells = [(int(one["x"] // 100), int(one["y"] // 100)) for one in view.json()["view"]["tokens"]]
    assert len(cells) == 6
    for index, one in enumerate(cells):
        for other in cells[index + 1 :]:
            assert max(abs(one[0] - other[0]), abs(one[1] - other[1])) >= 2, f"{one} and {other} touch"
