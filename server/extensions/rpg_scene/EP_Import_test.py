# SPDX-License-Identifier: AGPL-3.0-or-later
"""A battlemap made outside (Cartography's Halloway parlour, a Dungeondraft export) becomes a real
scene: its Universal VTT walls, doors and lights imported onto a scene bound to its place, and its
picture uploaded, attached to that place and set as the scene's background, which the campaign's
players can then load."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.cloud.EXT_Cloud import EXT_Cloud
from zephyrex.extensions.rpg_scene.EXT_RPGScene import RPGSceneExtension
from zephyrex.testing.factories import create_user

from vtt_app import create

PNG = b"\x89PNG\r\n\x1a\n" + b"a parlour" * 4
MAP = {
    "format": 0.3,
    "level": "Ground floor",
    "resolution": {"map_origin": {"x": 0, "y": 0}, "map_size": {"x": 22, "y": 17}, "pixels_per_grid": 100},
    "line_of_sight": [[{"x": 1, "y": 1}, {"x": 9, "y": 1}, {"x": 9, "y": 6}]],
    "objects_line_of_sight": [],
    "portals": [{"position": {"x": 9, "y": 8.5}, "bounds": [{"x": 9, "y": 9}, {"x": 9, "y": 8}], "closed": True}],
    "lights": [{"position": {"x": 10.5, "y": 7}, "range": 6, "color": "ffffffff"}],
    "image": "",
}


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    with TestClient(create()) as client:
        yield client


@pytest.fixture(autouse=True)
def store(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    """The cloud extension's storage, kept in memory."""
    files: dict[str, bytes] = {}

    async def upload_file(cls: Any, path: str, content: bytes, provider: Any = None) -> dict[str, Any]:
        files[path] = content
        return {"provider": "memory", "path": path}

    async def download_file(cls: Any, provider: str, path: str) -> bytes:
        return files[path]

    monkeypatch.setattr(EXT_Cloud, "upload_file", classmethod(upload_file))
    monkeypatch.setattr(EXT_Cloud, "download_file", classmethod(download_file))
    return files


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _create(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = server.post(f"/v1/{resource}", json={resource: fields}, headers=_headers(user))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()[resource]
    return created


@pytest.fixture(scope="module")
def parlour(server: TestClient) -> dict[str, Any]:
    gm, player, stranger = create_user(server), create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="The Missing Merchant", user_id=gm.id)
    house = _create(server, gm, "location", name="Halloway house", kind="building", campaign_id=campaign["id"])
    _create(server, gm, "person", name="Brann", kind="pc", user_id=player.id, campaign_id=campaign["id"], location_id=house["id"])
    scene = _create(server, gm, "scene", name="Halloway house, ground floor", campaign_id=campaign["id"], location_id=house["id"])
    return {"gm": gm, "player": player, "stranger": stranger, "campaign": campaign, "house": house, "scene": scene}


def test_a_uvtt_maps_walls_doors_and_lights_onto_the_scene(server: TestClient, parlour: dict[str, Any]) -> None:
    gm, scene = parlour["gm"], parlour["scene"]
    imported = server.post(f"/v1/scene/{scene['id']}/import_uvtt", json={"import_uvtt": {"uvtt": MAP}}, headers=_headers(gm))
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert (body["level"], body["width"], body["height"], body["grid_size"]) == ("Ground floor", 2200, 1700, 100.0)
    assert (body["walls"], body["doors"], body["lights"], body["removed"]) == (1, 1, 1, 0)
    view = server.post(f"/v1/scene/{scene['id']}/view", json={"view": {}}, headers=_headers(gm)).json()["view"]
    assert sorted(wall["door_type"] or "none" for wall in view["walls"]) == ["door", "none"]
    assert (view["width"], view["height"]) == (2200, 1700)
    # Importing again replaces rather than doubles.
    again = asyncio.run(RPGSceneExtension.import_uvtt(str(gm.id), scene["id"], MAP))
    assert again["removed"] == 3
    walls = server.get(f"/v1/scene_wall?scene_id={scene['id']}", headers=_headers(gm)).json()["scene_walls"]
    assert len([one for one in walls if one["scene_id"] == scene["id"]]) == 2


def test_only_the_gm_imports_and_a_bad_file_is_refused(server: TestClient, parlour: dict[str, Any]) -> None:
    scene = parlour["scene"]
    refused = server.post(f"/v1/scene/{scene['id']}/import_uvtt", json={"import_uvtt": {"uvtt": MAP}}, headers=_headers(parlour["player"]))
    assert refused.status_code == 404
    bad = server.post(f"/v1/scene/{scene['id']}/import_uvtt", json={"import_uvtt": {"uvtt": {"format": 0.3}}}, headers=_headers(parlour["gm"]))
    assert bad.status_code == 422 and "Universal VTT" in bad.json()["detail"]["message"]


def test_the_map_picture_uploaded_is_served_to_the_campaigns_players(server: TestClient, parlour: dict[str, Any]) -> None:
    gm, player, stranger, scene = parlour["gm"], parlour["player"], parlour["stranger"], parlour["scene"]
    uploaded = server.post(
        "/v1/asset/upload", params={"name": "halloway-parlour.0.png"}, content=PNG, headers={**_headers(gm), "Content-Type": "image/png"}
    )
    assert uploaded.status_code == 201, uploaded.text
    asset = uploaded.json()["asset"]["id"]
    # Attached to its place as its map (not its portrait), for the wiki's record of it.
    _create(server, gm, "attachment", asset_id=asset, target_entity_type="location", target_entity_id=parlour["house"]["id"], role="map")
    shown = asyncio.run(RPGSceneExtension.set_scene_background(str(gm.id), scene["id"], f"/v1/asset/{asset}/content"))
    assert shown["background_url"] == f"/v1/asset/{asset}/content"
    # What's drawn is the scene's own route: the asset's serves only its uploader and record viewers.
    view = server.post(f"/v1/scene/{scene['id']}/view", json={"view": {}}, headers=_headers(player))
    assert view.status_code == 200, view.text
    assert view.json()["view"]["background_url"] == f"/v1/scene/{scene['id']}/background"
    picture = server.get(f"/v1/scene/{scene['id']}/background", headers=_headers(player))
    assert picture.status_code == 200, picture.text
    assert picture.content == PNG and picture.headers["content-type"] == "image/png"
    assert server.get(f"/v1/scene/{scene['id']}/background", headers=_headers(stranger)).status_code == 404
