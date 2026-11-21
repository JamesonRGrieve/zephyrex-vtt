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
