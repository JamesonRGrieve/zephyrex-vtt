# SPDX-License-Identifier: AGPL-3.0-or-later
"""The D20 Test against the generated srd-5e pack (SRD 5.2, Playing the Game › D20 Tests)."""

import pytest
from zephyrex.extensions.rpg_dice.D20 import ability_modifier, d20_test, proficiency_bonus
from zephyrex.extensions.rpg_dice.Percentile import TestError
from zephyrex.extensions.rpg_systems.Packs import load_pack

PACK = load_pack("srd-5e")


@pytest.mark.parametrize(("score", "modifier"), [(1, -5), (3, -4), (8, -1), (10, 0), (11, 0), (12, 1), (15, 2), (20, 5), (30, 10)])
def test_the_ability_modifier_table(score: int, modifier: int) -> None:
    assert ability_modifier(score) == modifier


@pytest.mark.parametrize(("level", "bonus"), [(1, 2), (4, 2), (5, 3), (12, 4), (17, 6), (20, 6), (30, 9)])
def test_the_proficiency_bonus_table(level: int, bonus: int) -> None:
    assert PACK is not None and proficiency_bonus(PACK, level) == bonus


def test_an_ability_check_meets_or_beats_the_dc() -> None:
    assert PACK is not None
    met = d20_test(PACK, 14, roll=13, difficulty="medium")
    assert (met.total, met.target, met.success) == (15, 15, True)
    missed = d20_test(PACK, 14, roll=12, difficulty="medium")
    assert (missed.total, missed.success) == (14, False)


def test_no_sheet_is_the_human_average_a_plain_d20() -> None:
    assert PACK is not None
    plain = d20_test(PACK, None, roll=11, difficulty="easy")
    assert (plain.total, plain.target, plain.success) == (11, 10, True)
    assert plain.steps[0] == {"step": "no_sheet", "value": 10.0, "rule": "the human average"}
    assert plain.steps[-1] == {"step": "dc", "difficulty": "easy", "value": 10}


def test_proficiency_and_expertise_by_level() -> None:
    assert PACK is not None
    assert d20_test(PACK, 16, roll=10, skill_rank=1, level=5).total == 10 + 3 + 3
    assert d20_test(PACK, 16, roll=10, skill_rank=2, level=5).total == 10 + 3 + 6
    unlevelled = d20_test(PACK, 16, roll=10, skill_rank=1)
    assert unlevelled.total == 13 and unlevelled.steps[1]["rule"] == "no level on the sheet"


def test_a_natural_20_is_not_an_automatic_success_on_a_check() -> None:
    assert PACK is not None
    assert d20_test(PACK, 1, roll=20, difficulty="nearly-impossible").success is False


def test_refusals() -> None:
    assert PACK is not None
    with pytest.raises(TestError):
        d20_test(PACK, 10, roll=21)
    with pytest.raises(TestError):
        d20_test(PACK, 10, roll=5, difficulty="heroic")
