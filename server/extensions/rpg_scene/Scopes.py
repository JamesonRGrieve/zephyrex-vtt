# SPDX-License-Identifier: AGPL-3.0-or-later
"""A place at one scope, and who is where inside it (operator, 2026-11-24: "It also needs a
scope-out mode that shows, for example, the town instead of the house, with a group token for each
group of notable NPCs if multiple occupy the same building"). Pure: the wiki's places (their parent
and kind) and people (where each is, and whether a player character), plus the positions VTT knows,
go in; out come the scope's markers.

- The scope is one place; its markers are the places directly inside it that someone is in, however
  deep (a person in the Halloway parlour counts for the Halloway house, at town scope).
- Each marker groups the NPCs there; the party (the player characters) is its own group where it is.
- People at the scope place itself, in no place inside it, are ``here``.
- A marker's position is a fraction of the scope's map (0 to 1 across and down): the position the
  GM pinned, else the centre of a region of the scope's scene bound to that place, else an even
  layout (``placed`` false), so a map with no positions still reads.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Optional

# The margin an even layout keeps from the map's edges, as a share of it.
LAYOUT_MARGIN = 0.15
# How far the party's group sits from a building's NPC group when both are there, as a share.
PARTY_OFFSET = 0.06


@dataclass(frozen=True)
class Place:
    id: str
    name: str
    kind: Optional[str]
    parent_id: Optional[str]
    picture: Optional[str] = None


@dataclass(frozen=True)
class Person:
    id: str
    name: str
    location_id: Optional[str]
    is_pc: bool
    picture: Optional[str] = None


@dataclass
class Group:
    """The people in one place inside the scope."""

    place: Place
    npcs: list[Person] = field(default_factory=list)
    party: list[Person] = field(default_factory=list)
    x: float = 0.5
    y: float = 0.5
    placed: bool = False


@dataclass
class Scoped:
    place: Place
    parent: Optional[Place]
    path: list[Place]  # the root down to the scope
    groups: list[Group]
    here_npcs: list[Person]
    here_party: list[Person]


def ancestry(places: Mapping[str, Place], place_id: Optional[str]) -> list[str]:
    """A place and its parents, nearest first; a loop or a missing parent ends it."""
    chain: list[str] = []
    current = place_id
    while current and current in places and current not in chain:
        chain.append(current)
        current = places[current].parent_id
    return chain


def even_layout(count: int) -> list[tuple[float, float]]:
    """``count`` spots spread evenly inside the map's margin, row by row."""
    if count <= 0:
        return []
    columns = math.ceil(math.sqrt(count))
    rows = math.ceil(count / columns)
    span = 1 - 2 * LAYOUT_MARGIN
    spots = []
    for index in range(count):
        row, column = divmod(index, columns)
        x = LAYOUT_MARGIN + span * ((column + 0.5) / columns)
        y = LAYOUT_MARGIN + span * ((row + 0.5) / rows) if rows > 1 else 0.5
        spots.append((round(x, 4), round(y, 4)))
    return spots


def scope(
    places: Mapping[str, Place],
    people: Sequence[Person],
    scope_id: str,
    positions: Optional[Mapping[str, tuple[float, float]]] = None,
) -> Scoped:
    """Who is where inside ``scope_id``. ``positions`` maps a place inside it to where its marker
    sits on the scope's map (pinned or from a region), fractions of the map."""
    known = dict(positions or {})
    groups: dict[str, Group] = {}
    here_npcs: list[Person] = []
    here_party: list[Person] = []
    for person in sorted(people, key=lambda one: (one.name.casefold(), one.id)):
        chain = ancestry(places, person.location_id)
        if scope_id not in chain:
            continue
        at = chain.index(scope_id)
        if at == 0:
            (here_party if person.is_pc else here_npcs).append(person)
            continue
        child = places[chain[at - 1]]
        group = groups.setdefault(child.id, Group(place=child))
        (group.party if person.is_pc else group.npcs).append(person)
    ordered = sorted(groups.values(), key=lambda one: (one.place.name.casefold(), one.place.id))
    unplaced = [group for group in ordered if group.place.id not in known]
    for group, spot in zip(unplaced, even_layout(len(unplaced))):
        group.x, group.y = spot
    for group in ordered:
        if group.place.id in known:
            x, y = known[group.place.id]
            group.x, group.y, group.placed = min(1.0, max(0.0, x)), min(1.0, max(0.0, y)), True
    place = places[scope_id]
    parent = places.get(place.parent_id) if place.parent_id else None
    path = [places[one] for one in reversed(ancestry(places, scope_id))]
    return Scoped(place=place, parent=parent, path=path, groups=ordered, here_npcs=here_npcs, here_party=here_party)


def party_spot(group: Group) -> tuple[float, float]:
    """Where the party's group sits in a place: beside the NPCs' group when both are there."""
    if not group.npcs:
        return group.x, group.y
    return round(min(1.0, group.x + PARTY_OFFSET), 4), group.y
