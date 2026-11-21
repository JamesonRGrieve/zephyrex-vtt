# SPDX-License-Identifier: AGPL-3.0-or-later
"""A character's stat, resolved, and a check rolled against it: the VTT as referee.

``resolve`` is the derivative pipeline rpg_traits' models describe (from rpg_state's docs), as a pure function of
plain data, so ``contract/check-cases.json`` holds it exactly; the manager gathers that data from the
records. A stat starts at the sum of the person's own values for the trait (every live stack), then
each contribution aimed at it applies, phase by phase:

1. ``override``: the last by ``order_index`` replaces the value;
2. ``additive``: each is added;
3. ``multiplicative``: each multiplies;
4. ``clamp``: a bound. A value of 0 or more is a floor (the stat is at least it); a negative value
   is a ceiling at its size (``-20``: at most 20). So "never below 0" is ``0`` and "at most 20" is
   ``-20``. The trait model says only that "the sign selects min vs max"; this is the reading the VTT
   takes, recorded in docs/DESIGN.md.

Within a phase, contributions sharing a ``stacking_group`` keep only the largest (by size; a tie
keeps the earlier ``order_index``, then the lower id), and the rest apply in ``order_index`` order
(then id). A contribution with a ``qualifier`` applies only while that qualifier is switched on.
Its size: ``value`` times the person's own value of the source trait (1 when they have none), when
it comes from a trait; ``value`` while the source item is worn or held, when it comes from an item
(otherwise it doesn't apply); ``value`` itself when it comes from neither.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

from zephyrex.extensions.rpg_dice.Dice import Draw, Roll, roll

PHASES = ("override", "additive", "multiplicative", "clamp")
Compare = Literal[">=", "<="]


@dataclass(frozen=True)
class Contribution:
    """One derivative row aimed at the stat, with what it needs from the person already looked up."""

    id: str
    operation: str
    value: float
    order_index: int = 0
    stacking_group: str | None = None
    qualifier: str | None = None
    source: Literal["trait", "item", "constant"] = "constant"
    source_value: float | None = None
    """The person's own value of the source trait (``source == "trait"``), if they have it."""
    item_active: bool = False
    """Whether the person wears or holds the source item (``source == "item"``)."""

    def size(self) -> float | None:
        """What it contributes, or None when it doesn't apply."""
        if self.source == "item":
            return self.value if self.item_active else None
        if self.source == "trait":
            return self.value * (self.source_value if self.source_value is not None else 1.0)
        return self.value


@dataclass(frozen=True)
class Step:
    id: str
    operation: str
    size: float
    result: float

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "operation": self.operation, "size": self.size, "result": self.result}


@dataclass(frozen=True)
class Resolution:
    base: float
    value: float
    steps: tuple[Step, ...]

    def as_dict(self) -> dict[str, Any]:
        return {"base": self.base, "value": self.value, "steps": [step.as_dict() for step in self.steps]}


def resolve(
    base_values: Iterable[float],
    contributions: Iterable[Contribution],
    qualifiers: Iterable[str] = (),
) -> Resolution:
    """The stat: its base (the sum of the person's own values) through every contribution aimed at it."""
    on = set(qualifiers)
    base = float(sum(base_values))
    sized = [
        (row, size)
        for row in contributions
        if (row.qualifier is None or row.qualifier in on) and (size := row.size()) is not None
    ]
    result = base
    steps: list[Step] = []
    for phase in PHASES:
        rows = [(row, size) for row, size in sized if row.operation == phase]
        best: dict[str, tuple[Contribution, float]] = {}
        loose: list[tuple[Contribution, float]] = []
        for row, size in sorted(rows, key=lambda pair: (pair[0].order_index, pair[0].id)):
            if row.stacking_group is None:
                loose.append((row, size))
            elif row.stacking_group not in best or abs(size) > abs(best[row.stacking_group][1]):
                best[row.stacking_group] = (row, size)
        applied = sorted([*loose, *best.values()], key=lambda pair: (pair[0].order_index, pair[0].id))
        for row, size in applied:
            if phase == "override":
                result = size
            elif phase == "additive":
                result += size
            elif phase == "multiplicative":
                result *= size
            else:
                result = max(result, size) if size >= 0 else min(result, -size)
            steps.append(Step(id=row.id, operation=phase, size=size, result=result))
    return Resolution(base=base, value=result, steps=tuple(steps))


@dataclass(frozen=True)
class Check:
    roll: Roll
    target: float | None
    compare: Compare
    success: bool | None
    margin: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.roll.as_dict(),
            "target": self.target,
            "compare": self.compare,
            "success": self.success,
            "margin": self.margin,
        }


def check(
    formula: str,
    draw: Draw,
    stats: Mapping[str, float],
    target: float | None = None,
    compare: Compare = ">=",
) -> Check:
    """Rolls ``formula`` with the resolved ``stats``; against ``target``, meeting or beating it (``>=``),
    or rolling at or under it (``<=``). ``margin`` is how far past the target, below zero on a failure."""
    rolled = roll(formula, draw, stats)
    if target is None:
        return Check(roll=rolled, target=None, compare=compare, success=None, margin=None)
    margin = rolled.total - target if compare == ">=" else target - rolled.total
    return Check(roll=rolled, target=target, compare=compare, success=margin >= 0, margin=margin)
