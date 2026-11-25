# SPDX-License-Identifier: AGPL-3.0-or-later
"""A place's map made into its scene (the operator, 2026-11-25: "MAPS ARE STILL FUCKING BROKEN":
on CT 7103 no scenario had a map although the vault had them beside its location notes, and a
start opened on a blank 2000×1500 grid). map_location takes a Universal VTT file (.dd2vtt: walls,
doors, lights, size, grid and embedded art) or a plain picture and makes it the place's scene on
the scenario; a start copies it and opens on it with the party on squares no wall crosses, and its
art loads for the players. The UVTT here is synthetic in a Dungeondraft export's shape (the
vault's own maps are the operator's content, not this public repo's)."""

import asyncio
import base64
import struct
import time
import zlib
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.cloud.EXT_Cloud import EXT_Cloud
from zephyrex.extensions.rpg_scene.EXT_RPGScene import RPGSceneExtension
from zephyrex.extensions.rpg_scene.Maps import MapError, picture, wall_cells
from zephyrex.testing.factories import create_user

from vtt_app import create


def png(width: int, height: int) -> bytes:
    """A real (flat grey) PNG of the size asked, without an image library."""
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x80" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


LANTERN_ART = png(220, 170)
# The Leaning Lantern as a Dungeondraft export: 22 × 17 squares at 100 px, a bar wall straight
# across the middle (where a careless arrival would stand), a door, a hearth's light, its art.
LANTERN = {
    "format": 0.3,
    "resolution": {"map_origin": {"x": 0, "y": 0}, "map_size": {"x": 22, "y": 17}, "pixels_per_grid": 100},
    "line_of_sight": [[{"x": 0, "y": 8.5}, {"x": 22, "y": 8.5}], [{"x": 1, "y": 1}, {"x": 21, "y": 1}, {"x": 21, "y": 16}, {"x": 1, "y": 16}, {"x": 1, "y": 1}]],
    "objects_line_of_sight": [],
    "portals": [{"position": {"x": 11, "y": 1}, "bounds": [{"x": 10.5, "y": 1}, {"x": 11.5, "y": 1}], "closed": True}],
    "lights": [{"position": {"x": 4, "y": 4}, "range": 6, "color": "ffffa040"}],
    "image": base64.b64encode(LANTERN_ART).decode(),
}
CUSTOMS_ART = png(300, 200)


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


def test_a_pictures_kind_and_size_are_read_from_its_header() -> None:
    assert picture(LANTERN_ART) == ("image/png", 220, 170)
    gif = b"GIF89a" + struct.pack("<HH", 40, 30) + b"\x00" * 8
    assert picture(gif) == ("image/gif", 40, 30)
    webp = b"RIFF" + b"\x00" * 4 + b"WEBPVP8X" + b"\x00" * 8 + (399).to_bytes(3, "little") + (299).to_bytes(3, "little")
    assert picture(webp) == ("image/webp", 400, 300)
    with pytest.raises(MapError):
        picture(b"not a picture at all")
    assert (8, 8) in wall_cells([[[0, 850], [2200, 850]]], 100, 22, 17), "a wall across the middle blocks its row"


def test_a_places_map_becomes_its_scene_and_a_start_opens_on_it(server: TestClient, store: dict[str, bytes]) -> None:
    gm, player = create_user(server), create_user(server)
    scenario = _create(server, gm, "campaign", name="The Tavern Start", user_id=gm.id, is_scenario=True)
    town = _create(server, gm, "location", name="Harrowgate", kind="city", campaign_id=scenario["id"])
    lantern = _create(server, gm, "location", name="The Leaning Lantern", kind="building", parent_id=town["id"], campaign_id=scenario["id"])
    customs = _create(server, gm, "location", name="Harrowgate Customs House", kind="building", parent_id=town["id"], campaign_id=scenario["id"])
    for name in ("Brann", "Sefa", "Tam"):
        _create(server, gm, "person", name=name, kind="pc", campaign_id=scenario["id"], location_id=lantern["id"])

    def map_of(user: Any, location_id: str, **given: Any) -> dict[str, Any]:
        return dict(asyncio.run(RPGSceneExtension.map_location(str(user.id), location_id, **given)))

    made = map_of(gm, lantern["id"], uvtt=LANTERN, image_name="the-leaning-lantern.dd2vtt")
    assert made["created"] and made["name"] == "The Leaning Lantern"
    assert (made["width"], made["height"], made["grid_size"]) == (2200, 1700, 100.0)
    assert (made["walls"], made["doors"], made["lights"]) == (2, 1, 1)
    assert made["background_url"] == f"/v1/scene/{made['scene_id']}/background"
    assert list(store.values()) == [LANTERN_ART], "the UVTT's own art, uploaded"
    from zephyrex.extensions.attachments.BLL_Attachments import AttachmentManager  # type: ignore[import-not-found]
    from zephyrex.lib.Environment import env as _env

    links = AttachmentManager(requester_id=_env("ROOT_ID"), model_registry=server.app.state.model_registry)  # type: ignore[attr-defined]
    linked = links.list(filters=[links.DB.deleted_at.is_(None)], target_entity_type="location", target_entity_id=lantern["id"])
    assert [(one.role, str(one.asset_id)) for one in linked] == [("map", made["asset_id"])]

    again = map_of(gm, lantern["id"], uvtt=LANTERN)
    assert (again["scene_id"], again["created"], again["asset_id"]) == (made["scene_id"], False, made["asset_id"])
    walls = server.get("/v1/scene_wall", params={"scene_id": made["scene_id"]}, headers=_headers(gm)).json()["scene_walls"]
    assert len([one for one in walls if one["scene_id"] == made["scene_id"]]) == 3, "replaced, never doubled"
    assert len(store) == 1, "the same picture is uploaded once"

    plain = map_of(gm, customs["id"], image_base64=base64.b64encode(CUSTOMS_ART).decode(), image_name="Harrowgate Customs House.png", grid_size=50)
    assert plain["created"] and (plain["width"], plain["height"], plain["grid_size"]) == (300, 200, 50.0)
    assert plain["walls"] == 0 and plain["background_url"]

    # The Lantern's upper floor (Wiki asked: a `map:` list, ground first): its own scene, floor 1,
    # named for it; again it is the same scene. The place still opens on its floor 0.
    upstairs = map_of(gm, lantern["id"], image_base64=base64.b64encode(png(160, 120)).decode(), floor=1)
    assert upstairs["created"] and upstairs["floor"] == 1 and upstairs["scene_id"] != made["scene_id"]
    assert upstairs["name"] == "The Leaning Lantern (level 1)"
    assert map_of(gm, lantern["id"], image_base64=base64.b64encode(png(160, 120)).decode(), floor=1)["scene_id"] == upstairs["scene_id"]
    assert map_of(gm, lantern["id"], uvtt=LANTERN)["scene_id"] == made["scene_id"], "floor 0 is untouched by floor 1"

    with pytest.raises(HTTPException) as refused:
        map_of(player, lantern["id"], uvtt=LANTERN)
    assert refused.value.status_code == 404
    with pytest.raises(HTTPException) as bad:
        map_of(gm, customs["id"], image_base64=base64.b64encode(b"not a picture").decode())
    assert bad.value.status_code == 422

    # The start: the playthrough opens on the Lantern's map, its art loads, the party is on it and
    # no one stands on the bar wall.
    accepted = server.post(f"/v1/campaign/{scenario['id']}/instantiate", json={"instantiate": {}}, headers=_headers(gm))
    assert accepted.status_code == 202, accepted.text
    start = accepted.json()["start"]
    deadline = time.monotonic() + 90
    while start["state"] == "running":
        assert time.monotonic() < deadline, start
        time.sleep(0.5)
        start = server.get(f"/v1/campaign_start/{start['id']}", headers=_headers(gm)).json()["campaign_start"]
    assert start["state"] == "done", start.get("error") or start
    playthrough = str(start["campaign_id"])
    shown = asyncio.run(RPGSceneExtension.current_scene(str(gm.id), playthrough))
    assert shown is not None and shown["name"] == "The Leaning Lantern" and shown["campaign_id"] == playthrough
    assert shown["floor"] == 0, "the ground floor, not the upstairs"
    art = server.get(f"/v1/scene/{shown['id']}/background", headers=_headers(gm))
    assert art.status_code == 200 and art.content == LANTERN_ART
    from zephyrex.extensions.rpg_scene.BLL_RPGScene import SceneTokenManager, SceneWallManager
    from zephyrex.lib.Environment import env

    registry = server.app.state.model_registry  # type: ignore[attr-defined]
    tokens = SceneTokenManager(requester_id=env("ROOT_ID"), model_registry=registry)
    on = tokens.list(filters=[tokens.DB.deleted_at.is_(None)], scene_id=shown["id"])
    assert sorted(one.name for one in on) == ["Brann", "Sefa", "Tam"]
    copied_walls = SceneWallManager(requester_id=env("ROOT_ID"), model_registry=registry).list(scene_id=shown["id"])
    blocked = wall_cells((one.points or [] for one in copied_walls), 100, 22, 17)
    cells = {(int(one.x // 100), int(one.y // 100)) for one in on}
    assert not cells & blocked, (cells, "on a wall")
    assert len(cells) == 3


def test_the_server_maps_a_system_level_scenarios_place(server: TestClient, store: dict[str, bytes]) -> None:
    """vault_import --system runs as SYSTEM: SYSTEM is the GM of a scenario it wrote, so it maps
    that scenario's places; every account then reads the scene (a SYSTEM row)."""
    from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignManager  # type: ignore[import-not-found]
    from zephyrex.extensions.world_spatial.BLL_WorldSpatial import LocationManager  # type: ignore[import-not-found]
    from zephyrex.lib.Environment import env

    registry = server.app.state.model_registry  # type: ignore[attr-defined]
    system = str(env("SYSTEM_ID"))
    scenario = CampaignManager(requester_id=system, model_registry=registry).create(name="Goblin Ambush", user_id=system, is_scenario=True)
    road = LocationManager(requester_id=system, model_registry=registry).create(name="The North Pass", kind="region", campaign_id=scenario.id)
    made = asyncio.run(RPGSceneExtension.map_location(system, road.id, uvtt=LANTERN))
    assert made["created"] and made["walls"] == 2
    reader = create_user(server)
    seen = server.get(f"/v1/scene/{made['scene_id']}", headers=_headers(reader))
    assert seen.status_code == 200, seen.text
