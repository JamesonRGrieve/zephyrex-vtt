# SPDX-License-Identifier: AGPL-3.0-or-later
"""A setting pregen's starting sheet by the fifth-edition SRD's creation rules (rpg_builder's
build_pregen). Pure: it reads the pregen's own line ("Level 1 Dragonborn Cleric, Acolyte background
(SRD 5.2.1)") and the srd5e module's documents (each class, background and species with its Foundry
system data), and returns what the rules fix: the three origins, the standard array as the SRD's
Standard Array by Class places it, the saving throws and skills granted outright, the features each
grants at that level, and the hit points. Every choice the rules leave to the player and the pregen's
data doesn't settle (a skill pick, the background's ability increase, the starting-equipment option, a
size, a feat) is a gap, reported and left open: nothing is guessed (operator, 2026-11-22).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Optional

# The SRD editions the srd5e module's documents follow (its 2024 packs).
EDITIONS = ("5.2", "5.2.1")
# A pregen's first line: its level, species, class and background, and the SRD it follows.
LINE = re.compile(r"Level (\d+) (.+?), (.+?) background \(SRD ([\d.]+)\)", re.IGNORECASE)


@dataclass(frozen=True)
class Document:
    """One module document: the trait it became and the record's source data."""

    trait_id: str
    source_id: str
    name: str
    data: Mapping[str, Any]


@dataclass
class Gap:
    what: str
    detail: str


@dataclass
class PregenLine:
    level: int
    species: str
    klass: str
    background: str
    edition: str


@dataclass
class Plan:
    """What the rules fix, and what they leave open."""

    line: Optional[PregenLine] = None
    origins: dict[str, str] = field(default_factory=dict)  # kind → trait_id
    features: list[str] = field(default_factory=list)  # source ids of granted features and spells
    abilities: dict[str, int] = field(default_factory=dict)  # characteristic slug → score
    saves: list[str] = field(default_factory=list)  # characteristic slugs
    skills: list[str] = field(default_factory=list)  # skill slugs, proficient
    hp: Optional[int] = None
    gaps: list[Gap] = field(default_factory=list)

    @property
    def buildable(self) -> bool:
        return self.line is not None and len(self.origins) == 3 and bool(self.abilities)


def name_key(name: str) -> str:
    """A name as compared: "Elf, High" and "High Elf" are one species."""
    first, _, rest = name.partition(",")
    words = f"{rest} {first}" if rest else first
    return " ".join(re.findall(r"[a-z]+", words.lower()))


def parse_line(text: str, classes: Sequence[str]) -> Optional[PregenLine]:
    """The pregen's line, with species and class split on the module's class names."""
    found = LINE.search(text or "")
    if found is None:
        return None
    level, who, background, edition = found.groups()
    for klass in sorted(classes, key=len, reverse=True):
        match = re.fullmatch(rf"(.+?) {re.escape(klass)}", who.strip(), re.IGNORECASE)
        if match:
            return PregenLine(int(level), match.group(1).strip(), klass, background.strip(), edition)
    return PregenLine(int(level), who.strip(), "", background.strip(), edition)


def _modifier(score: int) -> int:
    return (score - 10) // 2


def _at(advancement: Mapping[str, Any], level: int) -> bool:
    """Whether an advancement applies by this level (an origin's have level 0 or none)."""
    at = advancement.get("level")
    return at is None or int(at) <= level


def plan(
    line: Optional[PregenLine],
    catalog: Mapping[str, Mapping[str, Document]],
    pack: Mapping[str, Any],
) -> Plan:
    """The pregen's sheet: ``catalog`` is kind (class, background, species) → name_key → document."""
    result = Plan(line=line)
    if line is None:
        result.gaps.append(Gap("line", "No 'Level N <species> <class>, <background> background (SRD x)' line to build from"))
        return result
    if line.edition not in EDITIONS:
        result.gaps.append(Gap("edition", f"SRD {line.edition}: the srd5e module carries SRD 5.2.1 only"))
        return result
    if line.level != 1:
        result.gaps.append(Gap("level", f"Level {line.level}: build_pregen builds level 1 characters only"))
        return result

    chosen: dict[str, Document] = {}
    for kind, name in (("class", line.klass), ("background", line.background), ("species", line.species)):
        document = catalog.get(kind, {}).get(name_key(name)) if name else None
        if document is None:
            result.gaps.append(Gap(kind, f"No {kind} called {name or '(none)'!r} in the srd5e module"))
        else:
            chosen[kind] = document
            result.origins[kind] = document.trait_id

    abilities = {one["short"].lower(): one["slug"] for one in pack["characteristics"]}
    skills = {one["key"]: one["slug"] for one in pack["skills"] if one.get("key")}
    klass = chosen.get("class")
    if klass is not None:
        placed = (pack.get("ability_methods", {}).get("standard_array_by_class") or {}).get(klass.source_id)
        if placed is None:
            result.gaps.append(Gap("abilities", f"The SRD's Standard Array by Class has no row for {klass.name}"))
        else:
            result.abilities = {slug: int(score) for slug, score in placed["scores"].items()}

    for kind, document in chosen.items():
        system = document.data or {}
        for advancement in system.get("advancement") or []:
            if not _at(advancement, line.level):
                continue
            kind_of = advancement.get("type")
            title = advancement.get("title") or kind_of
            config = advancement.get("configuration") or {}
            if kind_of == "Trait":
                # A class's second set (classRestriction: secondary) is for multiclassing only.
                if advancement.get("classRestriction") == "secondary":
                    continue
                for grant in config.get("grants") or []:
                    family, _, key = grant.partition(":")
                    if family == "skills" and key in skills:
                        result.skills.append(skills[key])
                    elif family == "saves" and key in abilities:
                        result.saves.append(abilities[key])
                for choice in config.get("choices") or []:
                    pool = ", ".join(choice.get("pool") or [])
                    result.gaps.append(Gap(kind, f"{document.name} › {title}: choose {choice.get('count')} of {pool}"))
            elif kind_of == "ItemGrant":
                if config.get("optional"):
                    result.gaps.append(Gap(kind, f"{document.name} › {title}: optional grants"))
                for item in config.get("items") or []:
                    if not item.get("optional") and item.get("uuid"):
                        result.features.append(item["uuid"])
            elif kind_of == "ItemChoice":
                counts = config.get("choices") or {}
                if any(int(level) <= line.level and (one or {}).get("count") for level, one in counts.items()):
                    result.gaps.append(Gap(kind, f"{document.name} › {title}: choose from its options"))
            elif kind_of == "AbilityScoreImprovement":
                points = config.get("points") or 0
                if points:
                    allowed = [abilities.get(key, key) for key in ("str", "dex", "con", "int", "wis", "cha") if key not in (config.get("locked") or [])]
                    result.gaps.append(
                        Gap(kind, f"{document.name} › {title}: {points} points among {', '.join(allowed)}, at most +{config.get('cap', points)} each")
                    )
            elif kind_of == "Size":
                sizes = config.get("sizes") or []
                if len(sizes) > 1:
                    result.gaps.append(Gap(kind, f"{document.name} › size: one of {', '.join(sizes)}"))
            elif kind_of == "Subclass" and advancement.get("level") is not None:
                result.gaps.append(Gap(kind, f"{document.name} › {title}: choose a subclass"))
        if system.get("startingEquipment"):
            wealth = system.get("wealth")
            alternative = f", or {wealth} GP instead" if wealth else ""
            result.gaps.append(Gap("equipment", f"{document.name}'s starting equipment: choose its option{alternative}"))

    result.saves = list(dict.fromkeys(result.saves))
    result.skills = list(dict.fromkeys(result.skills))
    result.features = list(dict.fromkeys(result.features))
    if klass is not None and result.abilities:
        die = str(((klass.data or {}).get("hd") or {}).get("denomination") or "")
        if die.startswith("d") and die[1:].isdigit():
            result.hp = int(die[1:]) + _modifier(result.abilities.get("constitution", 10))
    return result
