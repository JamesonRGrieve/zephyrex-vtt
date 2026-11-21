# SPDX-License-Identifier: AGPL-3.0-or-later
"""Vision.py against contract/vision-cases.json: what a token perceives (A23)."""

import json
from pathlib import Path
from typing import Any

import pytest
from zephyrex.extensions.rpg_scene.Vision import Scene, Token, Wall, perceive

CASES = json.loads((Path(__file__).resolve().parents[3] / "contract" / "vision-cases.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_vision_case(case: dict[str, Any]) -> None:
    seen = perceive(
        Scene(**case.get("scene", {})),
        Token(**case["viewer"]),
        [Token(**token) for token in case["tokens"]],
        [Wall(**wall) for wall in case["walls"]],
    )
    assert seen.as_dict() == case["expect"]


def test_a_move_is_blocked_by_walls_that_restrict_movement() -> None:
    from zephyrex.extensions.rpg_scene.Vision import blocks_move

    wall = Wall(id="w", points=[[0, 100], [200, 100]])
    assert blocks_move((50, 50), (50, 150), [wall]) == "w"
    assert blocks_move((50, 50), (150, 50), [wall]) is None, "alongside, not across"
    assert blocks_move((50, 50), (50, 150), [Wall(id="w", points=[[0, 100], [200, 100]], move_restriction="none")]) is None
    assert blocks_move((50, 50), (50, 150), [Wall(id="d", points=[[0, 100], [200, 100]], door_type="door", door_state="open")]) is None
    assert blocks_move((50, 50), (50, 150), [Wall(id="d", points=[[0, 100], [200, 100]], door_type="door")]) == "d"
    one_way = [Wall(id="o", points=[[0, 100], [200, 100]], direction="left")]
    blocked = [blocks_move((50, 50), (50, 150), one_way), blocks_move((50, 150), (50, 50), one_way)]
    assert sorted(blocked, key=str) == sorted(["o", None], key=str), "one side only"


def test_a_path_goes_round_a_wall_and_never_through_it() -> None:
    from zephyrex.extensions.rpg_scene.Vision import blocks_move, find_path

    wall = Wall(id="w", points=[[250, 0], [250, 200]])
    path = find_path((50, 50), (450, 50), 100, (500, 300), [wall])
    assert path is not None and path[0] == (50.0, 50.0) and path[-1] == (450.0, 50.0)
    assert all(blocks_move(a, b, [wall]) is None for a, b in zip(path, path[1:]))
    assert any(point[1] > 200 for point in path), "round the end of the wall"
    closed = Wall(id="c", points=[[250, 0], [250, 300]])
    assert find_path((50, 50), (450, 50), 100, (500, 300), [closed]) is None
    assert find_path((50, 50), (450, 50), 100, (500, 300), []) == [(50.0, 50.0), (150.0, 50.0), (250.0, 50.0), (350.0, 50.0), (450.0, 50.0)]


def test_points_in_region_shapes() -> None:
    from zephyrex.extensions.rpg_scene.Vision import in_shape, shape_box

    square = {"type": "polygon", "points": [0, 0, 100, 0, 100, 100, 0, 100]}
    assert in_shape((50, 50), square) and not in_shape((150, 50), square)
    assert in_shape((5, 5), {"type": "polygon", "points": [[0, 0], [10, 0], [10, 10], [0, 10]]})
    assert in_shape((10, 10), {"type": "rectangle", "x": 0, "y": 0, "width": 20, "height": 20})
    assert in_shape((3, 4), {"type": "circle", "x": 0, "y": 0, "radius": 5})
    assert not in_shape((4, 4), {"type": "circle", "x": 0, "y": 0, "radius": 5})
    assert shape_box(square) == (0, 0, 100, 100)
