# SPDX-License-Identifier: AGPL-3.0-or-later
"""Check.py against contract/check-cases.json: rpg_state's derivative pipeline, and checks."""

import json
from pathlib import Path
from typing import Any

import pytest
from zephyrex.extensions.rpg_dice.Check import Contribution, check, resolve
from zephyrex.extensions.rpg_dice.Dice import drawing_from

CASES = json.loads((Path(__file__).resolve().parents[3] / "contract" / "check-cases.json").read_text())


@pytest.mark.parametrize("case", CASES["resolve"], ids=[case["name"] for case in CASES["resolve"]])
def test_resolve_case(case: dict[str, Any]) -> None:
    contributions = [Contribution(**row) for row in case["contributions"]]
    resolved = resolve(case["base"], contributions, case.get("qualifiers", ()))
    assert resolved.as_dict() == case["expect"]


@pytest.mark.parametrize("case", CASES["check"], ids=[case["name"] for case in CASES["check"]])
def test_check_case(case: dict[str, Any]) -> None:
    checked = check(
        case["formula"],
        drawing_from(case["draws"]),
        case["stats"],
        case.get("target"),
        case.get("compare", ">="),
    ).as_dict()
    assert {key: checked[key] for key in ("total", "success", "margin")} == case["expect"]
