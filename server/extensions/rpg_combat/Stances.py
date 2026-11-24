# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who fights whom in an encounter, from each combatant's own disposition toward the others
(operator, 2026-11-24: "Combat sides should be based on character disposition not blanket red team
and blue team"). Pure: the wiki's dispositions (world_narrative) and the encounter's overrides go
in, and out come, per combatant, a disposition (its stance toward the party, as a Foundry token
shows it) and who it is hostile to, plus the open choices where the record doesn't settle it.

- A's stance toward B: A's default disposition toward B the person, else toward the party when B is
  a player character, read as hostile (hostile, enraged), friendly (friendly, helpful) or neutral
  (neutral, cautious-neutral, wary).
- Hostility runs both ways: when A is hostile to B, B may act against A (hostile_between). Each
  combatant keeps its own hostility, so a change to one (set_disposition) moves both directions.
- Nothing on record toward someone leaves them neutral, not an enemy for being present; an NPC with
  nothing toward a player character is an open choice, and so is any pair whose default rows
  disagree. Between two NPCs, nothing on record is simply not hostile.
- An override (the encounter's start, or set_disposition mid-fight) replaces what the record says.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Stance = Literal["friendly", "neutral", "hostile"]
STANCES: tuple[str, ...] = ("friendly", "neutral", "hostile")
# The wiki's attitudes (contract/wiki.json attitudes), as a stance in a fight; "missing" is no stance.
ATTITUDES: dict[str, Stance] = {
    "friendly": "friendly",
    "helpful": "friendly",
    "neutral": "neutral",
    "cautious-neutral": "neutral",
    "wary": "neutral",
    "hostile": "hostile",
    "enraged": "hostile",
}


@dataclass(frozen=True)
class Fighter:
    person_id: str
    name: str
    is_pc: bool


@dataclass(frozen=True)
class Record:
    """One of the wiki's disposition rows: how ``person_id`` regards a person or the party."""

    person_id: str
    target_kind: str
    target_person_id: Optional[str]
    attitude: Optional[str]
    is_default: bool


@dataclass
class OpenChoice:
    person_id: str
    name: str
    toward: Optional[str]
    toward_name: Optional[str]
    reason: str
    options: list[str] = field(default_factory=lambda: list(STANCES))


@dataclass
class Stances:
    disposition: dict[str, Stance] = field(default_factory=dict)
    # Each person's own hostility (whom they are hostile to); hostile_between makes it mutual.
    hostile_to: dict[str, list[str]] = field(default_factory=dict)
    open_choices: list[OpenChoice] = field(default_factory=list)


def _stance_toward(person: Fighter, other: Fighter, records: Sequence[Record]) -> tuple[Optional[Stance], bool]:
    """A's stance toward B from the record, and whether the record disagrees with itself."""
    mine = [one for one in records if one.person_id == person.person_id and one.is_default and one.attitude in ATTITUDES]
    direct = {ATTITUDES[one.attitude] for one in mine if one.target_kind == "person" and one.target_person_id == other.person_id}  # type: ignore[index]
    if direct:
        return (next(iter(direct)), False) if len(direct) == 1 else (None, True)
    if other.is_pc:
        party = {ATTITUDES[one.attitude] for one in mine if one.target_kind == "party"}  # type: ignore[index]
        if party:
            return (next(iter(party)), False) if len(party) == 1 else (None, True)
    return None, False


def work_out(
    fighters: Sequence[Fighter],
    records: Iterable[Record],
    overrides: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Stances:
    """The stances of an encounter's combatants. ``overrides`` maps a person id to a ``disposition``
    and/or ``hostile_to`` (person ids) that replace what the record says of that person: a
    surrender (hostile_to []) ends their hostility both ways, a betrayal starts it both ways."""
    rows = list(records)
    given = dict(overrides or {})
    out = Stances()
    ids = {one.person_id for one in fighters}
    # Each person's own hostility, from the record; an override replaces it.
    own: dict[str, set[str]] = {one.person_id: set() for one in fighters}
    for person in fighters:
        for other in fighters:
            if other.person_id == person.person_id:
                continue
            stance, conflict = _stance_toward(person, other, rows)
            if stance == "hostile":
                own[person.person_id].add(other.person_id)
            elif stance is None and not person.is_pc and (conflict or other.is_pc):
                # A player character's stance is the player's. An NPC's is an open choice when its
                # records disagree, or when it has none toward a player character; toward another
                # NPC, none on record is simply not hostile.
                reason = "Its disposition records disagree" if conflict else "No disposition on record toward them"
                out.open_choices.append(OpenChoice(person.person_id, person.name, other.person_id, other.name, reason))
    for person_id, change in given.items():
        if person_id in own and change.get("hostile_to") is not None:
            own[person_id] = {one for one in change["hostile_to"] if one in ids and one != person_id}
        if person_id in own:
            out.open_choices = [one for one in out.open_choices if one.person_id != person_id]
    for person in fighters:
        party = [other for other in fighters if other.is_pc and other.person_id != person.person_id]
        if person.is_pc:
            out.disposition[person.person_id] = "friendly"
        elif any(other.person_id in own[person.person_id] for other in party):
            out.disposition[person.person_id] = "hostile"
        else:
            stances = {_stance_toward(person, other, rows)[0] for other in party}
            out.disposition[person.person_id] = "friendly" if party and stances == {"friendly"} else "neutral"
        change = given.get(person.person_id) or {}
        if change.get("disposition") is not None:
            out.disposition[person.person_id] = change["disposition"]
    out.hostile_to = {person_id: sorted(targets) for person_id, targets in own.items()}
    return out


def hostile_between(own: Mapping[str, Iterable[str]], one: str, other: str) -> bool:
    """Whether two combatants are enemies: either is hostile to the other (hostility runs both ways,
    so whoever someone is hostile to may act against them)."""
    return other in set(own.get(one) or ()) or one in set(own.get(other) or ())
