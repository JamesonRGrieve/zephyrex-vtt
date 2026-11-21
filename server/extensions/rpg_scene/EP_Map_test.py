# SPDX-License-Identifier: AGPL-3.0-or-later
"""The map model against a real server: zephyr-cartography's features kept whole, and the records
they generate (walls, lights, tiles, pins, regions) linked to the feature and the level that made
them, so a feature's own records can be found and re-synced without touching hand-placed ones."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.testing.factories import create_user

from vtt_app import create

# A room as zephyr-cartography's scene spec writes it, with fields vtt itself never reads: the
# server keeps them all, so an import loses nothing and the shared model stays the authority.
ROOM = {
    "type": "room",
    "key": "hall",
    "points": [[0, 0], [400, 0], [400, 300], [0, 300]],
    "floor": "floor.flagstone",
    "wall": "wall.stone",
    "wallKind": "solid",
    "ceiling": True,
    "lit": True,
    "doors": [{"at": 0.5, "side": 0, "type": "secret", "state": "closed"}],
    "windows": [{"at": 0.25, "side": 2}],
    "daylight": True,
    "movementCost": 1,
}


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    yield TestClient(create())


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _post(server: TestClient, user: Any, resource: str, **fields: Any) -> Any:
    return server.post(f"/v1/{resource}", json={resource: fields}, headers=_headers(user))


def _create(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = _post(server, user, resource, **fields)
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()[resource]
    return created


@pytest.fixture(scope="module")
def built(server: TestClient) -> dict[str, Any]:
    gm = create_user(server)
    campaign = _create(server, gm, "campaign", name="The Vaults", user_id=gm.id)
    scene = _create(server, gm, "scene", name="Keep", campaign_id=campaign["id"], background_color="#202020")
    ground = _create(server, gm, "scene_level", name="Ground", scene_id=scene["id"], bottom=0, top=20)
    room = _create(
        server, gm, "scene_feature", scene_id=scene["id"], scene_level_id=ground["id"], kind="room", key="hall", spec=ROOM
    )
    made = {"scene_id": scene["id"], "scene_level_id": ground["id"], "scene_feature_id": room["id"]}
    wall = _create(server, gm, "scene_wall", points=[[0, 0], [400, 0]], **made)
    secret = _create(server, gm, "scene_wall", points=[[180, 0], [220, 0]], door_type="secret", **made)
    hand = _create(server, gm, "scene_wall", scene_id=scene["id"], points=[[0, 500], [100, 500]])
    light = _create(server, gm, "scene_light", x=200, y=150, bright=10, dim=20, color="#ffcc88", **made)
    tile = _create(server, gm, "scene_tile", x=0, y=0, width=400, height=300, **made)
    pin = _create(server, gm, "scene_note", x=200, y=150, text="Keep out", readable=True, **made)
    ceiling = _create(
        server, gm, "scene_region", name="Ceiling of Upper", shapes=[{"type": "polygon", "points": ROOM["points"]}], **made
    )
    return {
        "gm": gm,
        "scene": scene,
        "level": ground,
        "room": room,
        "walls": [wall, secret],
        "hand": hand,
        "light": light,
        "tile": tile,
        "pin": pin,
        "ceiling": ceiling,
    }


def test_a_feature_is_kept_whole(server: TestClient, built: dict[str, Any]) -> None:
    got = server.get(f"/v1/scene_feature/{built['room']['id']}", headers=_headers(built["gm"]))
    assert got.status_code == 200, got.text
    feature = got.json()["scene_feature"]
    assert feature["kind"] == "room" and feature["key"] == "hall"
    assert feature["spec"] == ROOM
    assert feature["scene_level_id"] == built["level"]["id"]


def test_a_features_own_walls_are_found_and_hand_placed_ones_are_not(server: TestClient, built: dict[str, Any]) -> None:
    listed = server.get(
        "/v1/scene_wall", params={"scene_feature_id": built["room"]["id"]}, headers=_headers(built["gm"])
    )
    assert listed.status_code == 200, listed.text
    ids = {wall["id"] for wall in listed.json()["scene_walls"]}
    assert ids == {wall["id"] for wall in built["walls"]}
    assert built["hand"]["id"] not in ids


def test_the_generated_records_carry_their_level_and_feature(built: dict[str, Any]) -> None:
    for name in ("light", "tile", "pin", "ceiling"):
        record = built[name]
        assert record["scene_feature_id"] == built["room"]["id"], name
        assert record["scene_level_id"] == built["level"]["id"], name
    assert built["light"]["color"] == "#ffcc88" and built["light"]["walls"] is True
    assert built["pin"]["readable"] is True
    assert built["walls"][1]["door_type"] == "secret"
    assert built["walls"][0]["light_restriction"] == "normal" and built["walls"][0]["sound_restriction"] == "normal"


@pytest.mark.parametrize(
    ("resource", "fields"),
    [
        ("scene_feature", {"kind": "castle", "spec": {}}),
        ("scene_feature", {"kind": "room"}),
        ("scene_light", {"color": "orange"}),
        ("scene_tile", {"width": 0, "height": 10}),
        ("scene_region", {"shapes": []}),
    ],
)
def test_malformed_map_records_are_refused(
    server: TestClient, built: dict[str, Any], resource: str, fields: dict[str, Any]
) -> None:
    response = _post(server, built["gm"], resource, scene_id=built["scene"]["id"], **fields)
    assert response.status_code == 422, response.text
