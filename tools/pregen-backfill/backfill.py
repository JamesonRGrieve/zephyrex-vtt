# SPDX-License-Identifier: AGPL-3.0-or-later
"""Builds pregens' starting sheets (rpg_builder's build_pregen), server-side. A dry run unless --write.

    python tools/pregen-backfill/backfill.py --owner <the pregens' owner> [--setting <setting id>] \
        [--campaign <campaign id>] [--level <n>] [--app module:factory] [--write] [--replace]

By default every setting pregen of the owner (a pc with no campaign); with --campaign, that
campaign's player characters (a scenario's pregens), the owner being its GM, built to the
campaign's starting level (or --level). Each is built from its
own line ("Level 1 Dragonborn Cleric, Acolyte background (SRD 5.2.1)") and the srd5e module, which must be installed for its
system first (tools/foundry-bridge/install.py). The dry run prints, per pregen, what would be built
and every choice left open; nothing is guessed. A pregen whose setting has no system with a rules
pack is listed as skipped with the reason. Run with the app's environment, never through a route;
--app boots a composing app (rpg-ai) from the current directory, as foundry-bridge/install.py does.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from collections import Counter
from pathlib import Path

SERVER = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--owner", required=True, help="The pregens' owner (who imported them)")
    parser.add_argument("--setting", help="Only this setting's pregens")
    parser.add_argument("--campaign", help="This campaign's player characters (a scenario's pregens) instead")
    parser.add_argument("--level", type=int, help="Build to this level (default: the campaign's starting level, else 1)")
    parser.add_argument("--app", default="vtt_app:create", help="The app factory to boot, module:function")
    parser.add_argument("--write", action="store_true", help="Write the sheets (default: a dry run)")
    parser.add_argument("--replace", action="store_true", help="Rebuild pregens that already have a sheet")
    args = parser.parse_args()

    from fastapi import HTTPException
    from fastapi.testclient import TestClient

    module, _, factory = args.app.partition(":")
    sys.path.insert(0, str(Path.cwd()))
    app = getattr(importlib.import_module(module), factory or "create")()
    results, skipped = [], []
    with TestClient(app):
        # The extensions are importable as zephyrex.extensions.* only once the app has loaded them
        # (a composing app such as rpg-ai loads the suite's from its own roots).
        from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager
        from zephyrex.extensions.rpg_builder.BLL_RPGBuilder import BuilderManager, PregenRequest

        registry = app.state.model_registry
        persons = PersonManager(requester_id=args.owner, model_registry=registry)
        builder = BuilderManager(requester_id=args.owner, model_registry=registry)
        live = [persons.DB.deleted_at.is_(None)]
        if args.campaign:
            pregens = [person for person in persons.list(filters=live, campaign_id=args.campaign) if getattr(person, "kind", None) == "pc"]
        else:
            filters = {"setting_id": args.setting} if args.setting else {}
            pregens = [
                person
                for person in persons.list(filters=live, **filters)
                if person.campaign_id is None and getattr(person, "setting_id", None) and getattr(person, "kind", None) == "pc"
            ]
        for person in sorted(pregens, key=lambda one: one.name or ""):
            body = PregenRequest(person_id=person.id, replace=args.replace, dry_run=not args.write, level=args.level)
            try:
                results.append(builder.build_pregen_for(body).model_dump())
            except HTTPException as error:
                detail = error.detail.get("message") if isinstance(error.detail, dict) else str(error.detail)
                skipped.append({"person_id": person.id, "name": person.name, "reason": detail})
    built = [one for one in results if one["built"]]
    gaps = Counter(gap["what"] for one in results for gap in one["gaps"])
    print(
        json.dumps(
            {
                "mode": "write" if args.write else "dry-run",
                "pregens": len(pregens),
                "buildable": len(built),
                "written": sum(one["written"] for one in results),
                "open_choices_by_kind": dict(gaps),
                "results": results,
                "skipped": skipped,
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
