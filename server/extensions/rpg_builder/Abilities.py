# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ability scores by a pack's own methods (``ability_methods``; the 5e SRD 5.2, Creating a
Character › Generate Your Scores). Pure: rolls are given.

- standard_array: the six scores, each used once;
- point_buy: every score has a cost on the table (8–15), and the costs sum to no more than the pool;
- roll: the six totals the server rolled for this character, each used once.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any


class AbilityError(ValueError):
    """Scores the method doesn't allow."""


def check_scores(methods: Mapping[str, Any], abilities: Sequence[str], method: str, scores: Mapping[str, int], rolled: Sequence[int] = ()) -> None:
    """Refuse scores that aren't one per ability or that the method doesn't allow."""
    if set(scores) != set(abilities):
        missing = sorted(set(abilities) - set(scores))
        extra = sorted(set(scores) - set(abilities))
        raise AbilityError(f"give one score per ability (missing {missing}, unknown {extra})")
    given = [int(value) for value in scores.values()]
    if method == "standard_array":
        if Counter(given) != Counter(methods["standard_array"]):
            raise AbilityError(f"the standard array is {', '.join(map(str, methods['standard_array']))}, each used once")
    elif method == "point_buy":
        costs = {int(score): int(cost) for score, cost in methods["point_buy"]["costs"].items()}
        priced = [score for score in given if score not in costs]
        if priced:
            raise AbilityError(f"point buy scores are {min(costs)} to {max(costs)}")
        spent = sum(costs[score] for score in given)
        if spent > methods["point_buy"]["pool"]:
            raise AbilityError(f"those cost {spent} points; the pool is {methods['point_buy']['pool']}")
    elif method == "roll":
        if not rolled:
            raise AbilityError("roll the scores first")
        if Counter(given) != Counter(rolled):
            raise AbilityError(f"use the rolled scores {', '.join(map(str, rolled))}, each once")
    else:
        raise AbilityError(f"no method {method!r}")
