# SPDX-License-Identifier: AGPL-3.0-or-later
"""A place at one scope and who is where inside it (rpg_scene.Scopes)."""

from zephyrex.extensions.rpg_scene.Scopes import Person, Place, ancestry, even_layout, party_spot, scope

REGION = Place("coast", "The Salt Coast", "region", None)
TOWN = Place("saltmere", "Saltmere", "city", "coast")
HOUSE = Place("halloway", "Halloway house", "building", "saltmere")
PARLOUR = Place("parlour", "The parlour", "room", "halloway")
INN = Place("inn", "The Drowned Lantern", "building", "saltmere")
DOCKS = Place("docks", "The docks", "district", "saltmere")
PLACES = {one.id: one for one in (REGION, TOWN, HOUSE, PARLOUR, INN, DOCKS)}

PEOPLE = [
    Person("oh", "Old Hesk", "parlour", False),
    Person("ma", "Mara Halloway", "halloway", False),
    Person("ti", "Tobin Halloway", "parlour", False),
    Person("in", "Innkeeper Rusk", "inn", False),
    Person("br", "Brann", "inn", True),
    Person("se", "Sefa", "inn", True),
    Person("cr", "Town crier", "saltmere", False),
    Person("far", "A stranger", None, False),
]


def test_at_town_scope_each_occupied_building_is_one_group() -> None:
    got = scope(PLACES, PEOPLE, "saltmere")
    by_place = {group.place.id: group for group in got.groups}
    # The parlour's two count for the Halloway house; the empty docks have no marker.
    assert set(by_place) == {"halloway", "inn"}
    assert [one.name for one in by_place["halloway"].npcs] == ["Mara Halloway", "Old Hesk", "Tobin Halloway"]
    assert [one.name for one in by_place["inn"].npcs] == ["Innkeeper Rusk"]
    assert [one.name for one in by_place["inn"].party] == ["Brann", "Sefa"]
    assert [one.name for one in got.here_npcs] == ["Town crier"] and got.here_party == []
    assert got.parent == REGION and [one.id for one in got.path] == ["coast", "saltmere"]


def test_scoping_in_shows_the_rooms_and_out_shows_the_town() -> None:
    house = scope(PLACES, PEOPLE, "halloway")
    assert [group.place.id for group in house.groups] == ["parlour"]
    assert [one.name for one in house.here_npcs] == ["Mara Halloway"]
    region = scope(PLACES, PEOPLE, "coast")
    assert [group.place.id for group in region.groups] == ["saltmere"] and region.parent is None
    assert len(region.groups[0].npcs) == 5 and len(region.groups[0].party) == 2


def test_a_pinned_position_wins_and_the_rest_are_laid_out_evenly() -> None:
    got = scope(PLACES, PEOPLE, "saltmere", {"inn": (0.8, 1.4)})
    by_place = {group.place.id: group for group in got.groups}
    assert (by_place["inn"].x, by_place["inn"].y, by_place["inn"].placed) == (0.8, 1.0, True)
    assert by_place["halloway"].placed is False and (by_place["halloway"].x, by_place["halloway"].y) == (0.5, 0.5)
    # The party sits beside the inn's NPCs, not on them.
    assert party_spot(by_place["inn"]) == (0.86, 1.0)


def test_an_even_layout_spreads_inside_the_margin_and_a_loop_ends_ancestry() -> None:
    spots = even_layout(4)
    assert spots == [(0.325, 0.325), (0.675, 0.325), (0.325, 0.675), (0.675, 0.675)]
    assert len(set(spots)) == 4
    looped = {"a": Place("a", "A", None, "b"), "b": Place("b", "B", None, "a")}
    assert ancestry(looped, "a") == ["a", "b"]
