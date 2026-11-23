# SPDX-License-Identifier: AGPL-3.0-or-later
"""A combatant's weapon attacks and how one resolves, by the pack's rules (srd-5e's ``attack``): the
attack roll is a d20 + the ability modifier (Strength in melee, Dexterity at range, either for a
Finesse weapon) + the Proficiency Bonus, against the target's AC; a natural 20 is a Critical Hit (it
hits, and the damage dice roll twice), a natural 1 misses; the damage is the weapon's dice + the same
modifier, never below 0. Pure: the draw is passed in, so tests fix the dice.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional

from zephyrex.extensions.rpg_dice.D20 import proficiency_bonus  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_dice.Dice import roll  # type: ignore[import-not-found]

Draw = Callable[[int], int]


def modifier(score: float) -> int:
    return (int(score) - 10) // 2


@dataclass
class Attack:
    id: str
    name: str
    ability: str
    to_hit: int
    damage: str
    damage_type: Optional[str]
    versatile: Optional[str] = None
    range: Optional[dict[str, Any]] = None
    steps: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> str:
        reach = f"range {self.range['normal']}/{self.range['long']} ft" if self.range else "melee"
        kind = f" {self.damage_type}" if self.damage_type else ""
        return f"{self.to_hit:+d} to hit, {self.damage}{kind}; {reach}"


@dataclass
class AttackResult:
    attack: str
    target_ac: int
    roll: int
    total: int
    hit: bool
    critical: bool
    damage: int
    damage_roll: Optional[dict[str, Any]]
    steps: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _ability(pack: Mapping[str, Any], weapon: Mapping[str, Any], scores: Mapping[str, float]) -> str:
    """The attack's ability: the weapon's own when it names one, Finesse the better of its two, else
    melee or ranged by the pack."""
    rule = pack["attack"]
    shorts = {one["short"].lower(): one["slug"] for one in pack["characteristics"]}
    if weapon.get("ability") in shorts:
        return shorts[weapon["ability"]]
    if "finesse" in (weapon.get("properties") or []):
        return max(rule["finesse"], key=lambda slug: scores.get(slug, 10))
    return rule["melee"] if weapon.get("melee") else rule["ranged"]


def _signed(base: str, bonus: int) -> str:
    return base if bonus == 0 else f"{base}{bonus:+d}"


def attacks_for(
    pack: Mapping[str, Any],
    weapons: Sequence[Mapping[str, Any]],
    scores: Mapping[str, float],
    proficient: bool,
    level: Optional[float],
) -> list[Attack]:
    """Each weapon's attack. ``proficient`` adds the Proficiency Bonus (by ``level``, or a stat block's
    CR); a creature with no level adds none, and the steps say so."""
    bonus = proficiency_bonus(pack, max(1, int(level))) if proficient and level is not None else 0
    found = []
    for index, weapon in enumerate(weapons):
        ability = _ability(pack, weapon, scores)
        mod = modifier(scores.get(ability, pack["test"].get("no_sheet_score", 10)))
        steps = [{"step": "ability_modifier", "ability": ability, "value": mod}, {"step": "proficiency", "value": bonus}]
        found.append(
            Attack(
                id=f"attack:{weapon.get('slug') or index}",
                name=weapon["name"],
                ability=ability,
                to_hit=mod + bonus,
                damage=_signed(weapon["damage"], mod),
                damage_type=weapon.get("damage_type"),
                versatile=_signed(weapon["versatile"], mod) if weapon.get("versatile") else None,
                range=weapon.get("range"),
                steps=steps,
            )
        )
    return found


def _doubled(formula: str, times: int) -> str:
    """A Critical Hit's damage: every die count multiplied (1d8+3 → 2d8+3)."""
    return re.sub(r"(\d*)d(\d+)", lambda found: f"{int(found.group(1) or 1) * times}d{found.group(2)}", formula)


def resolve(pack: Mapping[str, Any], attack: Attack, target_ac: int, draw: Draw, natural: Optional[int] = None) -> AttackResult:
    """One attack roll against ``target_ac`` and, on a hit, its damage. ``natural`` is the d20 already
    rolled (Advantage keeps one of two); none rolls it here."""
    rule = pack["attack"]
    face = natural if natural is not None else draw(int(pack["test"].get("die", 20)))
    total = face + attack.to_hit
    critical = face >= int(rule["critical"]["natural"])
    hit = critical or (face != int(rule["miss"]) and total >= target_ac)
    steps = [{"step": "roll", "value": face}, *attack.steps, {"step": "ac", "value": target_ac}]
    if not hit:
        return AttackResult(attack.name, target_ac, face, total, False, False, 0, None, steps)
    formula = _doubled(attack.damage, int(rule["critical"]["dice"])) if critical else attack.damage
    damage = roll(formula, draw)
    return AttackResult(attack.name, target_ac, face, total, True, critical, max(0, damage.total), damage.as_dict(), steps)


def armor_class(pack: Mapping[str, Any], scores: Mapping[str, float], value: Optional[float]) -> int:
    """A creature's AC: its sheet's, else the pack's base (10 + the Dexterity modifier)."""
    if value is not None:
        return int(value)
    rule = pack["armor_class"]
    return int(rule["base"]) + modifier(scores.get(rule["characteristic"], pack["test"].get("no_sheet_score", 10)))
