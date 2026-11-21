# SPDX-License-Identifier: AGPL-3.0-or-later
"""The 5e half of the Foundry bridge: the [redacted] rules (SRD 5.2.1) from the dnd5e Foundry system's
own packs, the way extract.mjs and rules.mjs read the redacted system. Nothing is restated here:
documents come from the packs' _source YAML, and the character-creation rules (the six abilities,
the standard array, the random roll, the point costs) are parsed from the SRD's own text in the
content24 journal, and refused if that text no longer says them.

    python tools/foundry-bridge/dnd5e.py --system <dnd5e checkout> --out dnd5e.json --rules dnd5e-rules.json

The bundle installs like a [redacted] line's (server/extensions/rpg_modules/Install.py, line "dnd5e").
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

LINE = "dnd5e"
# The 2024 packs (SRD 5.2.1): classes with their subclasses and features, species and backgrounds
# (and species traits), feats, spells and equipment.
PACKS = ("classes24", "origins24", "feats24", "spells24", "equipment24")
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
    return {"line": LINE, "packs": list(PACKS), "documents": documents, "problems": problems}


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
    pairs = costs.group(1).split()
    names = [name.strip() for name in re.split(r",\s*(?:and\s+)?|\s+and\s+", abilities.group(1)) if name.strip()]
    extra = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}.get(roll.group(2), 0)
    return {
        "line": LINE,
        "source": {"book": "SRD 5.2.1", "page": "Character Creation", "pack": "dnd5e.content24"},
        "abilities": [{"slug": name.lower(), "name": name, "short": name[:3].upper()} for name in names],
        "ability_methods": {
            "standard_array": [int(score) for score in array.group(1).replace(" ", "").split(",") if score],
            "roll": {"formula": roll.group(1), "count": 1 + extra},
            "point_buy": {
                "pool": int(pool.group(1)),
                "costs": {pairs[index]: int(pairs[index + 1]) for index in range(0, len(pairs) - 1, 2)},
            },
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--system", required=True, type=Path, help="The dnd5e Foundry system checkout")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--rules", type=Path)
    args = parser.parse_args()
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
