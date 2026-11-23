# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ability score methods against the generated srd-5e pack (SRD 5.2, Generate Your Scores)."""

import pytest
from zephyrex.extensions.rpg_builder.Abilities import AbilityError, check_scores
from zephyrex.extensions.rpg_systems.Packs import load_pack

PACK = load_pack("srd-5e") or {}
METHODS = PACK.get("ability_methods", {})
SIX = ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"]


def _scores(*values: int) -> dict[str, int]:
    return dict(zip(SIX, values))


def test_the_pack_states_the_three_methods() -> None:
    assert METHODS["standard_array"] == [15, 14, 13, 12, 10, 8]
    assert METHODS["roll"] == {"formula": "4d6kh3", "count": 6}
    assert METHODS["point_buy"]["pool"] == 27 and METHODS["point_buy"]["costs"]["14"] == 7


def test_the_standard_array_each_once() -> None:
    check_scores(METHODS, SIX, "standard_array", _scores(8, 15, 13, 12, 10, 14))
    with pytest.raises(AbilityError):
        check_scores(METHODS, SIX, "standard_array", _scores(15, 15, 13, 12, 10, 8))


def test_point_buy_within_the_pool_and_the_table() -> None:
    check_scores(METHODS, SIX, "point_buy", _scores(15, 15, 15, 8, 8, 8))  # 27
    with pytest.raises(AbilityError, match="cost 28"):
        check_scores(METHODS, SIX, "point_buy", _scores(15, 15, 15, 9, 8, 8))
    with pytest.raises(AbilityError, match="8 to 15"):
        check_scores(METHODS, SIX, "point_buy", _scores(16, 8, 8, 8, 8, 8))


def test_the_roll_is_the_servers_each_once() -> None:
    check_scores(METHODS, SIX, "roll", _scores(17, 9, 12, 12, 14, 6), rolled=[12, 6, 17, 14, 12, 9])
    with pytest.raises(AbilityError, match="rolled scores"):
        check_scores(METHODS, SIX, "roll", _scores(18, 9, 12, 12, 14, 6), rolled=[12, 6, 17, 14, 12, 9])
    with pytest.raises(AbilityError, match="roll the scores first"):
        check_scores(METHODS, SIX, "roll", _scores(10, 10, 10, 10, 10, 10))


def test_one_score_per_ability() -> None:
    with pytest.raises(AbilityError, match="missing"):
        check_scores(METHODS, SIX, "standard_array", {"strength": 15})
