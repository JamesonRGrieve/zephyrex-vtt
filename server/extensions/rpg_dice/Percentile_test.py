# SPDX-License-Identifier: AGPL-3.0-or-later
"""Percentile.py on the synthetic percentile-test pack (server/test_packs/), against
contract/percentile-test-cases.json: cases worked by hand from the d100 roll-under rules, and the tests
the pack refuses."""

import json
from pathlib import Path
from typing import Any

import pytest

# Aliased: pytest would collect a function named `test` and a class named `Test…` as tests.
from zephyrex.extensions.rpg_dice.Percentile import TestError as PercentileError
from zephyrex.extensions.rpg_dice.Percentile import test as percentile_test

HERE = Path(__file__).resolve()
PACK = json.loads((HERE.parents[2] / "test_packs" / "percentile-test.json").read_text())
CASES = json.loads((HERE.parents[3] / "contract" / "percentile-test-cases.json").read_text())


def _run(case: dict[str, Any]) -> Any:
    return percentile_test(
        PACK,
        characteristic=case["characteristic"],
        roll=case["roll"],
        skill_rank=case.get("skill_rank"),
        trained=case.get("trained", True),
        specialist=case.get("specialist", False),
        difficulty=case.get("difficulty"),
        modifiers=case.get("modifiers", []),
    )


@pytest.mark.parametrize("case", CASES["cases"], ids=[case["name"] for case in CASES["cases"]])
def test_the_pack_runs_its_cases(case: dict[str, Any]) -> None:
    outcome = _run(case)
    got = {"target": outcome.target, "success": outcome.success, "degrees": outcome.degrees, "natural": outcome.natural}
    assert got == case["expect"]


@pytest.mark.parametrize("case", CASES["refused"], ids=[case["name"] for case in CASES["refused"]])
def test_the_pack_refuses_what_the_rules_forbid(case: dict[str, Any]) -> None:
    with pytest.raises(PercentileError):
        _run(case)


def test_every_skill_names_a_characteristic_of_the_pack() -> None:
    characteristics = {one["slug"] for one in PACK["characteristics"]}
    assert {one["characteristic"] for one in PACK["skills"]} <= characteristics
    assert [one["slug"] for one in PACK["skills"] if one["specialist"]] == ["lore"]


# A career line's pack, as the Foundry bridge's rules step writes one (synthetic: no content): gen1
# degrees, untrained at half the characteristic, three ranks, Advanced skills not untrained.
CAREER = {
    "test": {
        "natural_success": 1,
        "natural_failure": 100,
        "modifier_cap": 60,
        "degrees": "gen1",
        "untrained": "half",
        "untrained_skill": -20,
    },
    "skill_ranks": {"by_rank": {"1": 0, "2": 10, "3": 20}},
    "difficulties": {"standard": 0, "hard": -20, "default": "standard"},
}


@pytest.mark.parametrize(
    ("characteristic", "roll", "options", "expect"),
    [
        (40, 38, {}, (40, True, 0)),
        (40, 15, {}, (40, True, 2)),
        (40, 49, {}, (40, False, 0)),
        (40, 72, {}, (40, False, 3)),
        (41, 20, {"trained": False}, (20, True, 0)),
        (41, 30, {"trained": False, "difficulty": "hard"}, (0, False, 3)),
        (40, 55, {"skill_rank": 3}, (60, True, 0)),
    ],
)
def test_a_career_line_scores_gen1_and_halves_untrained(
    characteristic: int, roll: int, options: dict[str, Any], expect: tuple[int, bool, int]
) -> None:
    outcome = percentile_test(CAREER, characteristic=characteristic, roll=roll, **options)
    assert (outcome.target, outcome.success, outcome.degrees) == expect


def test_a_career_line_refuses_an_advanced_skill_untrained_and_a_fourth_rank() -> None:
    with pytest.raises(PercentileError):
        percentile_test(CAREER, characteristic=40, roll=10, trained=False, specialist=True)
    with pytest.raises(PercentileError):
        percentile_test(CAREER, characteristic=40, roll=10, skill_rank=4)
