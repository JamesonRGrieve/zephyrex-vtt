# SPDX-License-Identifier: AGPL-3.0-or-later
"""Percentile.py under the [redacted] pack, against contract/[redacted]-test-cases.json:
the core rulebook's own worked examples, the rules they rest on, and the tests the pack refuses."""

import json
from pathlib import Path
from typing import Any

import pytest

# Aliased: pytest would collect a function named `test` and a class named `Test…` as tests.
from zephyrex.extensions.rpg_dice.Percentile import TestError as PercentileError
from zephyrex.extensions.rpg_dice.Percentile import test as percentile_test

HERE = Path(__file__).resolve()
PACK = json.loads((HERE.parents[1] / "rpg_systems" / "packs" / "redacted.json").read_text())
CASES = json.loads((HERE.parents[3] / "contract" / "[redacted]-test-cases.json").read_text())


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
def test_the_pack_runs_the_books_tests(case: dict[str, Any]) -> None:
    outcome = _run(case)
    got = {"target": outcome.target, "success": outcome.success, "degrees": outcome.degrees, "natural": outcome.natural}
    assert got == case["expect"]


@pytest.mark.parametrize("case", CASES["refused"], ids=[case["name"] for case in CASES["refused"]])
def test_the_pack_refuses_what_the_rules_forbid(case: dict[str, Any]) -> None:
    with pytest.raises(PercentileError):
        _run(case)


def test_the_pack_holds_the_books_skills_and_characteristics() -> None:
    characteristics = {one["slug"] for one in PACK["characteristics"]}
    assert len(characteristics) == 10
    assert len(PACK["skills"]) == 28
    assert {one["characteristic"] for one in PACK["skills"]} <= characteristics
    assert [one["slug"] for one in PACK["skills"] if one["specialist"]] == [
        "[redacted]", "[redacted]", "linguistics", "navigate", "operate", "scholastic-lore", "trade",
    ]
