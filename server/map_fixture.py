# SPDX-License-Identifier: AGPL-3.0-or-later
"""The map test world (the operator, 2026-11-25: "Maps are still completely fucked and need a
whole testing framework on the part of VTT"): a D&D SRD scenario shaped like The Missing Merchant,
with an outside, an inside and a fight, so the map is proven end to end through what play does.

    The Salt Coast (region)
      Saltmere (city)                       scene "Saltmere": 4096 × 2867, 68 px squares, a region per place
        Halloway house (building)           scene "Halloway house, ground floor": 2200 × 1700, 100 px squares
          The parlour (room)                  a region of the ground floor; where the party starts
          The cellar (room)                 scene "Halloway cellar": 1200 × 900, the fight
        The market (district)               a region of Saltmere
        Watch house (building)              a region of Saltmere (no map of its own)
      The coast road (region)               on no map

People: the party (Brann and Sefa, pcs) and Mara Halloway and Old Hesk in the parlour; a cellar
thug in the cellar; Captain Ord at the watch house. The scenario's tokens: Mara and Hesk on the
ground floor, the thug in the cellar (the party has none: their tokens come from where they are).

Every size and box is in PLACES / SCENES, which the client's render harness reads too
(contract/map-world.json is written from them by tools/map-world/export.py)."""

from __future__ import annotations

import base64
import struct
import zlib
from typing import Any

from fastapi.testclient import TestClient

SCENES: dict[str, dict[str, Any]] = {
    "Saltmere": {"place": "Saltmere", "width": 4096, "height": 2867, "grid_size": 68, "art": (196, 168, 112)},
    "Halloway house, ground floor": {"place": "Halloway house", "width": 2200, "height": 1700, "grid_size": 100, "art": (122, 82, 52)},
    "Halloway cellar": {"place": "The cellar", "width": 1200, "height": 900, "grid_size": 100, "art": (64, 70, 84)},
}


def art(colour: tuple[int, int, int]) -> str:
    """A scene's stand-in map art: a flat picture of one colour, as a data: URL (a real export's art
    is the operator's; the render test reads this colour back to prove the art is drawn)."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes(colour) * 8 for _ in range(8))
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(data).decode()
# Regions: (scene, place) → (x, y, width, height) in scene pixels.
REGIONS: dict[tuple[str, str], tuple[int, int, int, int]] = {
    ("Saltmere", "Halloway house"): (1224, 952, 408, 340),
    ("Saltmere", "The market"): (2040, 1360, 680, 544),
    ("Saltmere", "Watch house"): (2856, 680, 340, 272),
    ("Halloway house, ground floor", "The parlour"): (200, 500, 700, 800),
}
PLACES: list[tuple[str, str, str | None]] = [
    ("The Salt Coast", "region", None),
    ("Saltmere", "city", "The Salt Coast"),
    ("Halloway house", "building", "Saltmere"),
    ("The parlour", "room", "Halloway house"),
    ("The cellar", "room", "Halloway house"),
    ("The market", "district", "Saltmere"),
    ("Watch house", "building", "Saltmere"),
    ("The coast road", "region", "The Salt Coast"),
]
PEOPLE: list[tuple[str, str, str]] = [
    ("Brann", "pc", "The parlour"),
    ("Sefa", "pc", "The parlour"),
    ("Mara Halloway", "npc", "The parlour"),
    ("Old Hesk", "npc", "The parlour"),
    ("Cellar thug", "npc", "The cellar"),
    ("Captain Ord", "npc", "Watch house"),
]
# The scenario's own tokens: (scene, person, x, y).
TOKENS: list[tuple[str, str, int, int]] = [
    ("Halloway house, ground floor", "Mara Halloway", 500, 1100),
    ("Halloway house, ground floor", "Old Hesk", 400, 700),
    ("Halloway cellar", "Cellar thug", 600, 400),
]


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _create(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = server.post(f"/v1/{resource}", json={resource: fields}, headers=_headers(user))
    assert response.status_code == 201, f"{resource}: {response.text}"
    created: dict[str, Any] = response.json()[resource]
    return created


def seed(server: TestClient, author: Any, *, system_id: str | None = None, name: str = "The Missing Merchant (map world)") -> dict[str, Any]:
    """The scenario, made as ``author``: {"scenario", "places": {name: row}, "people": {name: row},
    "scenes": {name: row}}. The town map is current in the scenario (as on CT 7103), so a start
    must still open where the party is."""
    scenario = _create(server, author, "campaign", name=name, user_id=author.id, is_scenario=True, **({"game_system_id": system_id} if system_id else {}))
    places: dict[str, dict[str, Any]] = {}
    for place, kind, parent in PLACES:
        places[place] = _create(
            server, author, "location", name=place, kind=kind, campaign_id=scenario["id"], **({"parent_id": places[parent]["id"]} if parent else {})
        )
    people = {
        person: _create(server, author, "person", name=person, kind=kind, campaign_id=scenario["id"], location_id=places[where]["id"])
        for person, kind, where in PEOPLE
    }
    scenes: dict[str, dict[str, Any]] = {}
    for scene, shape in SCENES.items():
        scenes[scene] = _create(
            server, author, "scene", name=scene, campaign_id=scenario["id"], location_id=places[shape["place"]]["id"],
            width=shape["width"], height=shape["height"], grid_size=shape["grid_size"], background_url=art(shape["art"]),
        )
    for (scene, place), (x, y, width, height) in REGIONS.items():
        _create(
            server, author, "scene_region", name=place, scene_id=scenes[scene]["id"], location_id=places[place]["id"],
            shapes=[{"type": "rectangle", "x": x, "y": y, "width": width, "height": height}],
        )
    for scene, person, x, y in TOKENS:
        _create(server, author, "scene_token", name=person, scene_id=scenes[scene]["id"], person_id=people[person]["id"], x=x, y=y)
    from zephyrex.extensions.rpg_scene.EXT_RPGScene import RPGSceneExtension
    import asyncio

    asyncio.run(RPGSceneExtension.activate_scene(str(author.id), scenes["Saltmere"]["id"]))
    return {"scenario": scenario, "places": places, "people": people, "scenes": scenes}


def region_of(scene: str, place: str) -> tuple[int, int, int, int]:
    return REGIONS[(scene, place)]
