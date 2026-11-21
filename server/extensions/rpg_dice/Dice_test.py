# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dice.py against contract/roll-cases.json, the cases the lite twin (client/src/features/dice/roll.ts)
answers too."""

import json
import random
from pathlib import Path
from typing import Any

import pytest

from zephyrex.extensions.rpg_dice.Dice import MAX_DICE_PER_TERM, DiceError, drawing_from, roll

CASES = json.loads((Path(__file__).resolve().parents[3] / "contract" / "roll-cases.json").read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_roll_case(case: dict[str, Any]) -> None:
    draw = drawing_from(case["draws"])
    if "error" in case:
        with pytest.raises(DiceError) as refused:
            roll(case["formula"], draw, case.get("stats"))
        assert refused.value.code == case["error"]
        return
    result = roll(case["formula"], draw, case.get("stats")).as_dict()
    assert {key: result[key] for key in ("total", "terms", "stats")} == case["expect"]


def test_every_draw_is_used() -> None:
    """A case's draws are exactly what the formula rolls: one left over means the case is wrong."""
    for case in CASES:
        if "error" in case:
            continue
        remaining = list(case["draws"])
        roll(case["formula"], lambda _sides: remaining.pop(0), case.get("stats"))
        assert remaining == [], case["name"]


def test_live_draws_stay_on_the_die() -> None:
    """With a real random source, every face is on the die, and a pool at the cap still rolls."""
    source = random.Random(7)
    for _ in range(200):
        result = roll(f"{MAX_DICE_PER_TERM}d6", lambda sides: source.randint(1, sides))
        assert all(1 <= die.value <= 6 for die in result.terms[0].dice)
        assert MAX_DICE_PER_TERM <= result.total <= 6 * MAX_DICE_PER_TERM
