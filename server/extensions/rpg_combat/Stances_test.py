# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who fights whom, from each combatant's current attitudes (rpg_combat.Stances)."""

from zephyrex.extensions.rpg_combat.Stances import Fighter, hostile_between, work_out

ADA = Fighter("ada", "Ada", True)
BRIN = Fighter("brin", "Brin", True)
VELL = Fighter("vell", "Sergeant Vell", False)
HESK = Fighter("hesk", "Old Hesk", False)
WOLF = Fighter("wolf", "The wolf", False)


def test_a_hostile_attitude_makes_enemies_both_ways_and_none_leaves_a_bystander() -> None:
    got = work_out([ADA, BRIN, VELL, HESK], {"vell": {"party": "hostile"}})
    assert got.disposition == {"ada": "friendly", "brin": "friendly", "vell": "hostile", "hesk": "neutral"}
    assert got.hostile_to["vell"] == ["ada", "brin"]
    assert hostile_between(got.hostile_to, "ada", "vell") and hostile_between(got.hostile_to, "vell", "ada")
    assert not hostile_between(got.hostile_to, "ada", "hesk")
    # Hesk has nothing toward the party: an open choice per player character, none toward Vell.
    assert {(one.person_id, one.toward) for one in got.open_choices} == {("hesk", "ada"), ("hesk", "brin")}


def test_toward_a_person_beats_toward_the_party_and_three_way_fights_work() -> None:
    # Vell hates the party but likes Brin; the wolf hates Vell and no one else.
    attitudes = {"vell": {"party": "hostile", "brin": "friendly"}, "wolf": {"vell": "enraged"}}
    got = work_out([ADA, BRIN, VELL, WOLF], attitudes)
    assert got.hostile_to["vell"] == ["ada"] and got.hostile_to["wolf"] == ["vell"]
    assert not hostile_between(got.hostile_to, "brin", "vell")
    assert hostile_between(got.hostile_to, "wolf", "vell") and not hostile_between(got.hostile_to, "wolf", "ada")


def test_an_override_settles_an_open_choice() -> None:
    settled = work_out([ADA, HESK], {}, {"hesk": {"disposition": "hostile", "hostile_to": ["ada"]}})
    assert settled.open_choices == [] and settled.disposition["hesk"] == "hostile"
    assert hostile_between(settled.hostile_to, "ada", "hesk")


def test_a_surrender_ends_hostility_both_ways() -> None:
    got = work_out([ADA, VELL], {"vell": {"party": "enraged"}}, {"vell": {"disposition": "neutral", "hostile_to": []}})
    assert not hostile_between(got.hostile_to, "ada", "vell") and got.disposition["vell"] == "neutral"


def test_friendly_toward_every_player_character_is_friendly() -> None:
    got = work_out([ADA, BRIN, HESK], {"hesk": {"party": "helpful"}})
    assert got.disposition["hesk"] == "friendly" and got.open_choices == []
