# SPDX-License-Identifier: AGPL-3.0-or-later
"""A percentile test, d100 roll-under with degrees of success and failure, as a system pack's
``test`` spec describes it (rpg_systems/packs/<system>.json). Pure: the roll is given, so the server
rolls with its own random source and the tests (contract/percentile-test-cases.json) give theirs.

The rules, as a d100 roll-under pack states them:
- The target is the characteristic, plus the skill's rank bonus (an untrained skill instead takes the
  pack's penalty), plus the test's modifiers. The modifiers are summed first, and their total is held
  within ± the cap.
- The test succeeds when the roll is at or under the target. A roll of the natural success
  value (1) always succeeds and of the natural failure value (100) always fails, whatever the
  target.
- Success gives one degree, plus the target's tens digit minus the roll's; failure gives one, plus
  the roll's tens digit minus the target's. An automatic success or failure still has at
  least one degree.

Percentile packs differ only in what their spec says:
- ``degrees``: "gen2" (the tens-digit rule above; "tens" is its old name) or "gen1" (the margin's full
  tens, so a bare pass or fail scores 0 degrees);
- ``untrained``: "penalty" (an aptitude line: the characteristic plus ``untrained_skill``, -20) or
  "half" (a career line: half the characteristic, rounded down);
- the skill ranks a pack lists (four on aptitude lines, three on career lines);
- a skill that can't be attempted untrained (a specialist skill, or another the pack marks).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Natural = Optional[Literal["success", "failure"]]


class TestError(ValueError):
    """A test the pack can't run (an unknown skill or difficulty, a specialist skill untrained)."""


@dataclass
class Outcome:
    target: int
    roll: int
    success: bool
    degrees: int
    natural: Natural = None
    # How the target was reached, step by step, for the table to read.
    steps: list[dict[str, Any]] = field(default_factory=list)


def _tens(value: int) -> int:
    return value // 10


def capped(modifiers: Sequence[int], cap: int) -> int:
    """The modifiers' total, held within ±cap."""
    return max(-cap, min(cap, sum(modifiers)))


def _further(method: str, a: int, b: int) -> int:
    """Degrees past the first between ``a`` and ``b`` (the larger first)."""
    if method == "gen1":
        return abs(a - b) // 10
    return _tens(a) - _tens(b)


def resolve(target: int, roll: int, spec: Mapping[str, Any]) -> tuple[bool, int, Natural]:
    """Whether a roll succeeds against a final target, by how many degrees, and whether it was a
    natural success or failure."""
    if not 1 <= roll <= 100:
        raise TestError(f"a percentile roll is 1 to 100, not {roll}")
    natural: Natural = None
    if roll == spec["natural_success"]:
        natural, success = "success", True
    elif roll == spec["natural_failure"]:
        natural, success = "failure", False
    else:
        success = roll <= target
    method = spec.get("degrees", "gen2")
    if method not in ("gen1", "gen2", "tens"):
        raise TestError(f"no degrees method {method!r}")
    further = _further(method, target, roll) if success else _further(method, roll, target)
    if method == "gen1":
        # A gen1 line prints the further degrees alone: a bare pass is 0 degrees of success.
        return success, max(0, further), natural
    return success, max(1, 1 + further), natural


def test(
    pack: Mapping[str, Any],
    *,
    characteristic: int,
    roll: int,
    skill_rank: Optional[int] = None,
    trained: bool = True,
    specialist: bool = False,
    difficulty: Optional[str] = None,
    modifiers: Sequence[int] = (),
) -> Outcome:
    """A characteristic or skill test under a pack. For a characteristic test leave ``skill_rank``
    unset and ``trained`` true. For a skill test, ``skill_rank`` is the pack's rank (1–4 on an aptitude
    line, 1–3 on a career line); ``trained`` false is untrained, refused when
    ``specialist`` says the skill can't be attempted untrained (a specialist skill, or
    another the pack marks)."""
    spec = pack["test"]
    steps: list[dict[str, Any]] = [{"step": "characteristic", "value": characteristic}]
    base = characteristic
    if not trained:
        if specialist:
            raise TestError("this skill can't be attempted untrained")
        if spec.get("untrained", "penalty") == "half":
            halved = characteristic // 2
            steps.append({"step": "untrained", "value": halved - characteristic, "rule": "half"})
            base = halved
        else:
            steps.append({"step": "untrained", "value": spec["untrained_skill"]})
            base += spec["untrained_skill"]
    elif skill_rank is not None:
        bonus = pack["skill_ranks"]["by_rank"].get(str(skill_rank))
        if bonus is None:
            raise TestError(f"no skill rank {skill_rank} in this pack")
        steps.append({"step": "skill_rank", "rank": skill_rank, "value": bonus})
        base += bonus
    difficulties = pack["difficulties"]
    name = difficulty or difficulties["default"]
    if name not in difficulties or name in ("default", "cite"):
        raise TestError(f"no difficulty {name!r}")
    wanted = [difficulties[name], *modifiers]
    total = capped(wanted, spec["modifier_cap"])
    steps.append({"step": "modifiers", "difficulty": name, "listed": wanted, "value": total})
    target = base + total
    success, degrees, natural = resolve(target, roll, spec)
    return Outcome(target=target, roll=roll, success=success, degrees=degrees, natural=natural, steps=steps)
