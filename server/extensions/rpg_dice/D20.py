# SPDX-License-Identifier: AGPL-3.0-or-later
"""A D20 Test, as a system pack's ``test`` spec of kind ``d20-over`` describes it
(rpg_systems/packs/dnd-5e.json, generated from the SRD's own text). Pure: the roll is given.

System Reference Document 5.2, Playing the Game › D20 Tests:
- Roll a d20 and add the relevant ability modifier ((score − 10) / 2, rounded down: the Ability
  Modifiers table), the Proficiency Bonus if the test uses something the creature is proficient in
  (doubled by Expertise; by level on the Proficiency Bonus table), and circumstantial modifiers.
- The test succeeds when the total equals or exceeds the target number, the DC (for an ability check:
  the Typical Difficulty Classes). A natural 20 or 1 decides only an attack roll, so an ability
  check has no automatic result.
- A creature with no sheet tests at the human-average score (10–11: Ability Scores), a +0 modifier.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Optional

from zephyrex.extensions.rpg_dice.Percentile import TestError  # type: ignore[import-not-found]


@dataclass
class D20Outcome:
    target: int
    roll: int
    total: int
    success: bool
    steps: list[dict[str, Any]] = field(default_factory=list)


def ability_modifier(score: float) -> int:
    """An ability score's modifier: (score − 10) / 2, rounded down."""
    return (int(score) - 10) // 2


def proficiency_bonus(pack: Mapping[str, Any], level: int) -> int:
    """The Proficiency Bonus for a level (or CR), from the pack's table."""
    for row in pack["proficiency"]["by_level"]:
        if level <= row["up_to"]:
            return int(row["bonus"])
    raise TestError(f"no Proficiency Bonus for level {level}")


def d20_test(
    pack: Mapping[str, Any],
    score: Optional[float],
    roll: int,
    skill_rank: Optional[int] = None,
    level: Optional[int] = None,
    difficulty: Optional[str] = None,
    modifiers: Sequence[int] = (),
) -> D20Outcome:
    """An ability check, or a skill check when ``skill_rank`` is 1 (proficient) or 2 (Expertise).
    ``score`` None is a creature with no sheet: the pack's human-average score. ``level`` gives the
    Proficiency Bonus; with none, proficiency adds nothing and the steps say so."""
    if not 1 <= roll <= int(pack["test"].get("die", 20)):
        raise TestError(f"a d20 roll is 1 to 20, not {roll}")
    spec = pack["test"]
    steps: list[dict[str, Any]] = []
    if score is None:
        score = float(spec["no_sheet_score"])
        steps.append({"step": "no_sheet", "value": score, "rule": "the human average"})
    modifier = ability_modifier(score)
    steps.append({"step": "ability_modifier", "score": score, "value": modifier})
    total = roll + modifier
    if skill_rank:
        multiplier = pack["skill_ranks"]["by_rank"].get(str(skill_rank))
        if multiplier is None:
            raise TestError(f"no skill rank {skill_rank} in this pack")
        if level is None:
            steps.append({"step": "proficiency", "rank": skill_rank, "value": 0, "rule": "no level on the sheet"})
        else:
            bonus = proficiency_bonus(pack, level) * int(multiplier)
            steps.append({"step": "proficiency", "rank": skill_rank, "level": level, "value": bonus})
            total += bonus
    difficulties = pack["difficulties"]
    name = difficulty or difficulties["default"]
    if name not in difficulties or name in ("default", "cite"):
        raise TestError(f"no difficulty {name!r}")
    extra = sum(modifiers)
    if modifiers:
        steps.append({"step": "modifiers", "listed": list(modifiers), "value": extra})
    total += extra
    target = int(difficulties[name])
    steps.append({"step": "dc", "difficulty": name, "value": target})
    return D20Outcome(target=target, roll=roll, total=total, success=total >= target, steps=steps)
