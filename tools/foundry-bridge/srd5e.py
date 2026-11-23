# SPDX-License-Identifier: AGPL-3.0-or-later
"""The fifth-edition SRD bridge: the SRD 5.2 rules (CC-BY-4.0) from the open fifth-edition Foundry system's
own packs, as a bridge reads a source system. Nothing is restated here:
documents come from the packs' _source YAML, and the character-creation rules (the six abilities,
the standard array, the random roll, the point costs) are parsed from the SRD's own text in the
content24 journal, and refused if that text no longer says them.

    python tools/foundry-bridge/srd5e.py --system <system checkout> --out srd5e.json --rules srd5e-rules.json
    python tools/foundry-bridge/srd5e.py --system <system checkout> --pack server/extensions/rpg_systems/packs/srd-5e.json

The bundle installs as a module (server/extensions/rpg_modules/Install.py, line "srd5e", system srd-5e).
Each document is keyed by Foundry's compendium UUID (Compendium.dnd5e.<pack>.Item.<_id>), the key the
wiki's compendium_import stores as compendium_source.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import yaml

LINE = "srd5e"
# The 2024 packs (SRD 5.2.1): classes with their subclasses and features, species and backgrounds
# (and species traits), feats, spells and equipment.
PACKS = ("classes24", "origins24", "feats24", "spells24", "equipment24")
# Which of the system's item types are traits in vtt, and of what kind (rpg_modules' "kinds" scheme): a
# character's origins and class, their spells, and each feat by what it belongs to (system.type.value).
KINDS = {
    "types": {"race": "species", "background": "background", "class": "class", "subclass": "subclass", "spell": "spell"},
    "fields": {
        "feat": {"path": ["type", "value"], "map": {"class": "class-feature", "race": "species-trait", "feat": "feat"}, "default": "feat"},
    },
}
CREATION_PAGE = "content24/chapter-2/character-creation.yml"


def _documents(root: Path, pack: str, problems: list[dict[str, str]]) -> Iterator[dict[str, Any]]:
    base = root / "packs" / "_source" / pack
    if not base.is_dir():
        problems.append({"pack": pack, "problem": "no _source directory"})
        return
    for path in sorted(base.rglob("*.yml")):
        if path.name == "_folder.yml":
            continue
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            problems.append({"pack": pack, "file": str(path.relative_to(base)), "problem": str(error)})
            continue
        if isinstance(document, dict) and document.get("_id") and document.get("type"):
            yield document


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _source(system: dict[str, Any]) -> dict[str, Any]:
    source = system.get("source") if isinstance(system.get("source"), dict) else {}
    return {"provenance": "srd", "book": source.get("book") or None, "page": source.get("page") or None}


def extract(root: Path) -> dict[str, Any]:
    """Every document of the 2024 packs as a bundle entry, keyed by its compendium UUID."""
    problems: list[dict[str, str]] = []
    documents = []
    for pack in PACKS:
        for document in _documents(root, pack, problems):
            system = document.get("system") or {}
            documents.append(
                {
                    "line": LINE,
                    "id": f"Compendium.dnd5e.{pack}.Item.{document['_id']}",
                    "foundry_id": document["_id"],
                    "name": document["name"],
                    "foundry_class": "Item",
                    "type": document["type"],
                    "pack": pack,
                    "category": pack,
                    "homebrew": False,
                    "conversion": False,
                    "img": document.get("img"),
                    "source": _source(system),
                    "system": system,
                    "items": [],
                    "hash": _hash({"name": document["name"], "img": document.get("img"), "system": system}),
                }
            )
    return {
        "line": LINE,
        "system": "srd-5e",
        "name": "SRD 5.2 content",
        "slug": "srd5e",
        "kinds": KINDS,
        "packs": list(PACKS),
        "documents": documents,
        "problems": problems,
    }


def _plain(value: Any) -> str:
    def walk(node: Any) -> Iterator[str]:
        if isinstance(node, dict):
            for child in node.values():
                yield from walk(child)
        elif isinstance(node, list):
            for child in node:
                yield from walk(child)
        elif isinstance(node, str):
            yield node

    text = re.sub(r"<[^>]+>", " ", " ".join(walk(value)))
    return re.sub(r"\s+", " ", html.unescape(text))


class RulesTextError(ValueError):
    """The SRD's creation text no longer says what the rules step reads from it."""


def rules(root: Path) -> dict[str, Any]:
    """The character-creation rules, parsed from the SRD's own words (content24, Character Creation)."""
    page = root / "packs" / "_source" / CREATION_PAGE
    text = _plain(yaml.safe_load(page.read_text(encoding="utf-8")))

    def find(pattern: str, what: str) -> re.Match[str]:
        found = re.search(pattern, text)
        if found is None:
            raise RulesTextError(f"the SRD's creation text no longer states {what}")
        return found

    array = find(r"Standard Array\. Use the following six scores for your abilities: ([\d, ]+)\.", "the standard array")
    roll = find(r"Random Generation\. Roll \[\[/r (\w+)\]\].*?Do this (\w+) more times", "the random generation")
    pool = find(r"You have (\d+) points to spend on your ability scores", "the point-buy pool")
    costs = find(r"Ability Score Point Costs Score Cost ((?:\d+ \d+ ?)+)", "the point-cost table")
    abilities = find(r"assign them to ([A-Z][a-z]+(?:, [A-Z][a-z]+)*,? and [A-Z][a-z]+)", "the six abilities")
    by_class = find(r"Standard Array by Class Class Str\. Dex\. Con\. Int\. Wis\. Cha\. ((?:@UUID\[[^\]]+\]\{[A-Za-z]+\} (?:\d+ ){5}\d+ ?)+)", "the Standard Array by Class table")
    pairs = costs.group(1).split()
    names = [name.strip() for name in re.split(r",\s*(?:and\s+)?|\s+and\s+", abilities.group(1)) if name.strip()]
    standard = sorted((int(score) for score in array.group(1).replace(" ", "").split(",") if score), reverse=True)
    # Each class's row: its six scores in the abilities' order, keyed by the class's compendium UUID.
    placed: dict[str, dict[str, Any]] = {}
    for uuid, name, row in re.findall(r"@UUID\[([^\]]+)\]\{([A-Za-z]+)\} ((?:\d+ ){5}\d+)", by_class.group(1)):
        scores = [int(score) for score in row.split()]
        if sorted(scores, reverse=True) != standard:
            raise RulesTextError(f"the Standard Array by Class row for {name} isn't the standard array")
        placed[uuid] = {"name": name, "scores": dict(zip((one.lower() for one in names), scores))}
    extra = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}.get(roll.group(2), 0)
    return {
        "line": LINE,
        "source": {"book": "SRD 5.2.1", "page": "Character Creation", "pack": "dnd5e.content24"},
        "abilities": [{"slug": name.lower(), "name": name, "short": name[:3].upper()} for name in names],
        "ability_methods": {
            "standard_array": [int(score) for score in array.group(1).replace(" ", "").split(",") if score],
            # The SRD's suggested placement of the standard array for each class (Step 3).
            "standard_array_by_class": placed,
            "roll": {"formula": roll.group(1), "count": 1 + extra},
            "point_buy": {
                "pool": int(pool.group(1)),
                "costs": {pairs[index]: int(pairs[index + 1]) for index in range(0, len(pairs) - 1, 2)},
            },
        },
    }


# Where the test rules are stated in the SRD's own text (content24, chapter 1).
D20_PAGE = "content24/chapter-1/d20-tests.yml"
PLAYING_PAGE = "content24/chapter-1/playing-the-game.yml"
COMBAT_PAGE = "content24/chapter-1/combat.yml"
LEGAL_PAGE = "content24/legal-information.yml"
_ABILITY = "(Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma)"
_NUMBER = r"([+−-]?\d+)"


def _number(text: str) -> int:
    return int(text.replace("−", "-").replace("+", ""))


def _range(text: str) -> tuple[int, int]:
    low, _, high = text.partition("–")
    return int(low), int(high or low)


NPC_FOLDER = "actors24/humanoid"


def _skill_keys(root: Path) -> dict[str, str]:
    """dnd5e's own skill abbreviations (module/config.mjs: acr → acrobatics) as pack skill slugs."""
    config = (root / "module" / "config.mjs").read_text(encoding="utf-8")
    found = re.findall(r'(\w{3}): \{\s*label: "DND5E\.Skill\w+",\s*ability: "\w+",\s*fullKey: "(\w+)"', config)
    if not found:
        raise RulesTextError("dnd5e's config no longer lists its skills with their full keys")
    return {short: re.sub(r"([a-z])([A-Z])", r"\1-\2", full).lower() for short, full in found}


def npc_stat_blocks(root: Path, abilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The SRD's humanoid stat blocks (Commoner, Guard, Bandit, Noble, Priest…), as the 2024 actor pack
    states them: ability scores, skill proficiencies (1, or 2 for Expertise), hit points, armour class
    and challenge rating. Nothing is adjusted."""
    skills = _skill_keys(root)
    short = {one["short"].lower(): one["slug"] for one in abilities}
    blocks = []
    for path in sorted((root / "packs" / "_source" / NPC_FOLDER).glob("*.yml")):
        if path.name == "_folder.yml":
            continue
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        system = document.get("system") or {}
        if document.get("type") != "npc":
            continue
        scores = {short[key]: int(value["value"]) for key, value in (system.get("abilities") or {}).items() if key in short}
        if len(scores) != len(abilities):
            raise RulesTextError(f"{document.get('name')} doesn't give all six ability scores")
        attributes = system.get("attributes") or {}
        blocks.append(
            {
                "slug": path.stem,
                "name": document["name"],
                "cr": (system.get("details") or {}).get("cr"),
                "abilities": scores,
                "skills": {skills[key]: int(value["value"]) for key, value in (system.get("skills") or {}).items() if key in skills and value.get("value")},
                "hp": (attributes.get("hp") or {}).get("max"),
                "ac": (attributes.get("ac") or {}).get("flat"),
                "uuid": f"Compendium.dnd5e.actors24.Actor.{document['_id']}",
            }
        )
    return blocks


def test_pack(root: Path) -> dict[str, Any]:
    """vtt's rules pack for the fifth-edition SRD 5.2 (rpg_systems/packs/srd-5e.json), parsed from its own text:
    a D20 Test (d20 + ability modifier + Proficiency Bonus if proficient, against a DC), the
    abilities and skills, the Typical Difficulty Classes, the modifier and Proficiency Bonus tables,
    the human-average score (for a creature with no sheet), and Initiative (a Dexterity check)."""

    def page(name: str) -> str:
        return _plain(yaml.safe_load((root / "packs" / "_source" / name).read_text(encoding="utf-8")))

    def find(text: str, pattern: str, what: str) -> re.Match[str]:
        found = re.search(pattern, text)
        if found is None:
            raise RulesTextError(f"the SRD no longer states {what}")
        return found

    d20, playing, combat, legal = page(D20_PAGE), page(PLAYING_PAGE), page(COMBAT_PAGE), page(LEGAL_PAGE)
    abilities = rules(root)["abilities"]
    by_name = {one["name"]: one["slug"] for one in abilities}

    table = find(d20, r"Skills Skill Ability Example Uses (.*?)(?: \d+\.\d+ dnd5e|$)", "the Skills table").group(1)
    skills = [
        {"slug": re.sub(r"[^a-z]+", "-", name.lower()).strip("-"), "name": name, "characteristic": by_name[ability],
         "specialist": False, "cite": "Playing the Game › D20 Tests › Skills"}
        for name, ability in re.findall(r"([A-Z][a-z]+(?: of)?(?: [A-Z][a-z]+)?) " + _ABILITY + r" ", table)
    ]
    if not skills or len({one["slug"] for one in skills}) != len(skills):
        raise RulesTextError("the SRD's Skills table no longer reads as one skill per row")
    # Each skill's key in the Foundry system's documents (skills:ath in a class's skill choices).
    keys = {slug: short for short, slug in _skill_keys(root).items()}
    for one in skills:
        if one["slug"] not in keys:
            raise RulesTextError(f"the Foundry system has no skill key for {one['name']}")
        one["key"] = keys[one["slug"]]

    classes = find(d20, r"Typical Difficulty Classes Task Difficulty DC ((?:[A-Z][a-z]+(?: [a-z]+)? \d+ ?)+)", "the Typical Difficulty Classes")
    difficulties: dict[str, Any] = {
        re.sub(r"\s+", "-", label.strip().lower()): int(dc)
        for label, dc in re.findall(r"([A-Z][a-z]+(?: [a-z]+)?) (\d+)", classes.group(1))
    }

    modifiers = find(playing, r"Ability Modifiers Score Modifier ((?:\d+(?:–\d+)? [+−]?\d+ ?)+)", "the Ability Modifiers table")
    for scores, modifier in re.findall(r"(\d+(?:–\d+)?) ([+−]?\d+)", modifiers.group(1)):
        low, high = _range(scores)
        if any((score - 10) // 2 != _number(modifier) for score in range(low, high + 1)):
            raise RulesTextError(f"the Ability Modifiers table gives {modifier} for {scores}, not (score − 10) / 2 rounded down")

    proficiency = find(d20, r"Proficiency Bonus Level or CR Bonus ((?:(?:Up to \d+|\d+–\d+) \+\d+ ?)+)", "the Proficiency Bonus table")
    by_level = [
        {"up_to": _range(levels.replace("Up to ", ""))[1], "bonus": _number(bonus)}
        for levels, bonus in re.findall(r"(Up to \d+|\d+–\d+) (\+\d+)", proficiency.group(1))
    ]
    find(d20, r"expertise\]? feature doubles the Proficiency Bonus", "that Expertise doubles the Proficiency Bonus")
    average = find(playing, r"(\d+)–\d+ This represents the human average", "the human-average score")
    initiative = find(combat, r"they make a " + _ABILITY + r" check that determines their place in the Initiative order", "how Initiative is rolled")
    creation = page(CREATION_PAGE)
    steps = re.findall(r"Step (\d): ([A-Z][A-Za-z ]+?) text ", creation)
    origin = find(creation, r"origin involves choosing a @UUID\[[^\]]+\]\{(\w+)\}, a @UUID\[[^\]]+\]\{(\w+)\}", "what an origin is chosen from")
    picks = {"Choose a Class": ["class"], "Character Origin": [origin.group(1), origin.group(2)]}
    if [name for _, name in steps[:3]] != ["Choose a Class", "Character Origin", "Ability Scores"]:
        raise RulesTextError("the SRD's creation steps no longer begin class, origin, ability scores")
    attribution = find(legal, r"(This work includes material from the System Reference Document .*?legalcode) \.", "the attribution").group(1)

    return {
        "$comment": (
            "The fifth-edition SRD 5.2 pack, generated by tools/foundry-bridge/srd5e.py --pack from the SRD's own text in "
            "the open fifth-edition Foundry system's content24 journal; nothing is restated by hand. " + attribution.replace(" .", ".")
        ),
        "system": "srd-5e",
        "source": "System Reference Document 5.2",
        "license": "CC-BY-4.0",
        "test": {
            "kind": "d20-over",
            "die": 20,
            "modifier": "(score − 10) / 2, rounded down",
            "no_sheet_score": int(average.group(1)),
            "cite": {
                "core_mechanic": "Playing the Game › D20 Tests",
                "modifier": "Playing the Game › Ability Scores and Modifiers",
                "no_sheet_score": "Playing the Game › Ability Scores (10–11: the human average)",
            },
        },
        "initiative": {
            "dice": "1d20",
            "characteristic": by_name[initiative.group(1)],
            "bonus": "modifier",
            "ties": [],
            "cite": "Playing the Game › Combat › Initiative",
        },
        "proficiency": {"by_level": by_level, "cite": "Playing the Game › D20 Tests › Proficiency"},
        "skill_ranks": {"by_rank": {"1": 1, "2": 2}, "names": ["proficient", "expertise"]},
        # The SRD leaves the DC to the GM; vtt's default when none is chosen is the table's middle row.
        "difficulties": {**difficulties, "default": "medium", "cite": "Playing the Game › D20 Tests › Typical Difficulty Classes"},
        "characteristics": abilities,
        "characteristics_cite": "Playing the Game › Ability Scores and Modifiers",
        # The SRD's humanoid stat blocks, for an NPC's sheet (rpg_builder's npc_sheet); the Commoner
        # is the SRD's ordinary person, used when no other block fits.
        "npcs": {"blocks": npc_stat_blocks(root, abilities), "generic": "commoner", "cite": "Monsters › Humanoids (actors24)"},
        # Character creation's three methods (Step 3), from the same text the module's rules step reads.
        "ability_methods": {**rules(root)["ability_methods"], "cite": "Creating a Character › Generate Your Scores"},
        # The creation steps a builder walks, with the trait kinds each chooses (the module's 5e kinds).
        "creation": {
            "steps": [
                {"step": int(number), "name": name, **({"choices": picks[name]} if name in picks else {})}
                for number, name in steps
            ],
            "cite": "Creating a Character",
        },
        "skills": skills,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--system", required=True, type=Path, help="The dnd5e Foundry system checkout")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--pack", type=Path, help="Write vtt's srd-5e rules pack (rpg_systems/packs/srd-5e.json)")
    parser.add_argument("--rules", type=Path)
    args = parser.parse_args()
    if args.pack:
        pack = test_pack(args.system)
        args.pack.write_text(json.dumps(pack, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"skills": len(pack["skills"]), "difficulties": pack["difficulties"]}, ensure_ascii=False))
        if not args.out:
            return 0
    if not args.out:
        parser.error("--out or --pack is required")
    bundle = extract(args.system)
    args.out.write_text(json.dumps(bundle) + "\n", encoding="utf-8")
    types: dict[str, int] = {}
    for document in bundle["documents"]:
        types[document["type"]] = types.get(document["type"], 0) + 1
    summary: dict[str, Any] = {"documents": len(bundle["documents"]), "problems": len(bundle["problems"]), "types": types}
    if args.rules:
        found = rules(args.system)
        args.rules.write_text(json.dumps(found) + "\n", encoding="utf-8")
        summary["rules"] = found["ability_methods"]
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
