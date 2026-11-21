# SPDX-License-Identifier: AGPL-3.0-or-later
"""Imports character sheets from vault notes onto a campaign's persons, server-side.

    python tools/vault-import/import.py --notes "<vault>/OneShots/[redacted]/Characters/Pregens" \
        --owner <the GM's user id> --campaign <campaign id> [--line dh2] [--app module:factory] [--dry-run]

Each note whose frontmatter has a ``canonical_sheet`` becomes the sheet of the campaign's person
with the note's ``name`` (the wiki importer makes the persons first). The line's module must be
installed for --owner (tools/foundry-bridge); this enables it on the campaign, then writes the
sheet through it (rpg_modules.Sheet). Run with the app's environment, never through a route; --app
boots a composing app (rpg-ai) from the current directory, as foundry-bridge/install.py does.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

SERVER = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER))


def frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    block = text.split("---", 2)[1]
    found = yaml.safe_load(block)
    return found if isinstance(found, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--notes", required=True, type=Path, help="A note, or a folder of notes")
    parser.add_argument("--owner", required=True, help="The campaign's GM, who owns the installed module")
    parser.add_argument("--campaign", required=True, help="The campaign whose persons get the sheets")
    parser.add_argument("--line", default="dh2")
    parser.add_argument("--app", default="vtt_app:create", help="The app factory to boot, module:function")
    parser.add_argument("--dry-run", action="store_true", help="Print the sheets read; write nothing")
    args = parser.parse_args()

    notes = sorted(args.notes.glob("*.md")) if args.notes.is_dir() else [args.notes]
    from zephyrex.extensions.rpg_modules.Sheet import import_sheet, sheet_from_frontmatter

    sheets = []
    for note in notes:
        matter = frontmatter(note)
        sheet = sheet_from_frontmatter(matter)
        if sheet is not None:
            sheets.append((str(matter.get("name") or note.stem), sheet))
    if args.dry_run:
        print(json.dumps(dict(sheets), indent=1))
        return 0

    from fastapi.testclient import TestClient
    from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager
    from zephyrex.extensions.rpg_modules.BLL_RPGModules import CampaignModuleManager, ContentModuleManager

    module, _, factory = args.app.partition(":")
    sys.path.insert(0, str(Path.cwd()))
    app = getattr(importlib.import_module(module), factory or "create")()
    with TestClient(app):
        registry = app.state.model_registry

        def as_owner(manager: type) -> object:
            return manager(requester_id=args.owner, model_registry=registry)

        installed = [
            one
            for one in as_owner(ContentModuleManager).list(slug=f"redacted-{args.line}")
            if str(one.created_by_user_id) == str(args.owner)
        ]
        if not installed:
            print(f"the {args.line} module isn't installed for {args.owner}; run tools/foundry-bridge first")
            return 1
        enabled = as_owner(CampaignModuleManager)
        if not enabled.list(campaign_id=args.campaign, content_module_id=installed[0].id):
            enabled.create(campaign_id=args.campaign, content_module_id=installed[0].id)
        persons = {person.name: person for person in as_owner(PersonManager).list(campaign_id=args.campaign)}
        results, missing = [], []
        for name, sheet in sheets:
            person = persons.get(name)
            if person is None:
                missing.append(name)
                continue
            results.append(asdict(import_sheet(registry, args.owner, person.id, args.line, sheet)) | {"name": name})
    print(json.dumps({"imported": results, "no_person_named": missing}, indent=1))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
