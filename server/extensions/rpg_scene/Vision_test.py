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
