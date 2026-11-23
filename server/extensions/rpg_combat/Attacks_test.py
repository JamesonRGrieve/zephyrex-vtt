# SPDX-License-Identifier: AGPL-3.0-or-later
"""Weapon attacks by the srd-5e pack's rules, with the dice fixed."""

import json
from pathlib import Path

from zephyrex.extensions.rpg_combat.Attacks import armor_class, attacks_for, resolve
from zephyrex.extensions.rpg_dice.Dice import drawing_from

PACK = json.loads((Path(__file__).resolve().parents[1] / "rpg_systems" / "packs" / "srd-5e.json").read_text())
WEAPONS = {one["slug"]: one for one in PACK["weapons"]}
SCORES = {"strength": 16, "dexterity": 14, "constitution": 12, "intelligence": 10, "wisdom": 10, "charisma": 8}


def test_melee_uses_strength_ranged_dexterity_and_finesse_the_better() -> None:
    sword, bow, rapier = attacks_for(PACK, [WEAPONS["longsword"], WEAPONS["shortbow"], WEAPONS["rapier"]], SCORES, True, 1)
    assert (sword.ability, sword.to_hit, sword.damage) == ("strength", 3 + 2, "1d8+3")
    assert (bow.ability, bow.to_hit, bow.damage) == ("dexterity", 2 + 2, "1d6+2")
    assert (rapier.ability, rapier.to_hit) == ("strength", 5), "Finesse takes the better of Strength and Dexterity"
    agile = attacks_for(PACK, [WEAPONS["rapier"]], {**SCORES, "dexterity": 18}, True, 1)[0]
    assert (agile.ability, agile.to_hit, agile.damage) == ("dexterity", 4 + 2, "1d8+4")


def test_no_level_adds_no_proficiency_and_says_so() -> None:
    sword = attacks_for(PACK, [WEAPONS["longsword"]], SCORES, True, None)[0]
    assert sword.to_hit == 3 and {"step": "proficiency", "value": 0} in sword.steps


def test_a_hit_rolls_damage_a_miss_none_a_natural_20_doubles_the_dice_and_a_natural_1_misses() -> None:
    sword = attacks_for(PACK, [WEAPONS["longsword"]], SCORES, True, 1)[0]  # +5, 1d8+3
    hit = resolve(PACK, sword, 15, drawing_from([10, 6]))
    assert (hit.hit, hit.critical, hit.total, hit.damage) == (True, False, 15, 9)
    miss = resolve(PACK, sword, 16, drawing_from([10]))
    assert (miss.hit, miss.damage, miss.damage_roll) == (False, 0, None)
    critical = resolve(PACK, sword, 30, drawing_from([20, 4, 5]))
    assert (critical.hit, critical.critical, critical.damage) == (True, True, 4 + 5 + 3)
    assert critical.damage_roll["formula"] == "2d8+3"
    fumble = resolve(PACK, sword, 2, drawing_from([1]))
    assert not fumble.hit, "a natural 1 misses whatever the total"


def test_damage_is_never_below_zero_and_ac_defaults_to_ten_plus_dexterity() -> None:
    weak = attacks_for(PACK, [WEAPONS["club"]], {**SCORES, "strength": 3}, False, None)[0]  # 1d4-4
    assert resolve(PACK, weak, 5, drawing_from([15, 1])).damage == 0
    assert armor_class(PACK, SCORES, None) == 12 and armor_class(PACK, SCORES, 16) == 16
