# SPDX-License-Identifier: AGPL-3.0-or-later
"""Imports character sheets from vault notes onto a campaign's persons, server-side.

    python tools/vault-import/import.py --notes "<vault>/<scenario>/Characters/Pregens" \
        --owner <the GM's user id> --campaign <campaign id> --line <line> [--app module:factory] [--dry-run]

Each note whose frontmatter has a ``canonical_sheet`` becomes the sheet of the campaign's person
with the note's ``name`` (the wiki importer makes the persons first). The line's module must be
installed for --owner, or for the whole instance (open content; tools/foundry-bridge); this enables it on the campaign, then writes the
sheet through it (rpg_modules.Sheet). Run with the app's environment, never through a route; --app
boots a composing app (rpg-ai) from the current directory, as foundry-bridge/install.py does. The
dry run boots it too (the sheet reader is an extension's) and writes nothing.
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
    parser.add_argument("--owner", required=True, help="The campaign's GM, who enables the module and writes the sheets")
    parser.add_argument("--campaign", required=True, help="The campaign whose persons get the sheets")
    parser.add_argument("--line", required=True, help="The installed module's line key (its bundle's)")
    parser.add_argument("--app", default="vtt_app:create", help="The app factory to boot, module:function")
    parser.add_argument("--dry-run", action="store_true", help="Print the sheets read; write nothing")
    args = parser.parse_args()

    notes = sorted(args.notes.glob("*.md")) if args.notes.is_dir() else [args.notes]
    from fastapi.testclient import TestClient

    module, _, factory = args.app.partition(":")
    sys.path.insert(0, str(Path.cwd()))
    app = getattr(importlib.import_module(module), factory or "create")()
    with TestClient(app):
        # The extensions are importable as zephyrex.extensions.* only once the app has loaded them
        # (a composing app such as rpg-ai loads the suite's from its own roots), the dry run's too.
        from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager
        from zephyrex.extensions.rpg_modules.BLL_RPGModules import CampaignModuleManager, ContentModuleManager
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

        registry = app.state.model_registry

        def as_owner(manager: type) -> object:
            return manager(requester_id=args.owner, model_registry=registry)

        from zephyrex.lib.Environment import env

        listed = as_owner(ContentModuleManager).list(line=args.line)
        installed = [one for one in listed if str(one.created_by_user_id) == str(args.owner)] + [
            one for one in listed if str(one.created_by_user_id) == str(env("SYSTEM_ID"))
        ]
        if not installed:
            print(f"the {args.line} module isn't installed for {args.owner} or the instance; run tools/foundry-bridge first")
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
