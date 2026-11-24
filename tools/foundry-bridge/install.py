# SPDX-License-Identifier: AGPL-3.0-or-later
"""The bridge's install step: install a line's bundle (srd5e.py's, or a private instance's own bridge's) as one account's private
module, server-side. Run on the server host, with the app's environment (its database), never
through a route: the content is on the server's disk, and the module belongs to --owner alone.

    python tools/foundry-bridge/install.py --bundle srd5e.json --owner <user id> \
        [--system-ref <sha>] [--content-ref <sha>] [--rules rules.json] [--app module:factory]

--app boots a composing app instead of vtt's own (rpg-ai's server, which loads vtt's extensions);
run it from that app's server directory with its environment, so the module lands in its database.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

SERVER = Path(__file__).resolve().parents[2] / "server"
sys.path.insert(0, str(SERVER))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--owner", required=True, help="The user id the module belongs to")
    parser.add_argument("--system-ref")
    parser.add_argument("--content-ref")
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--app", default="vtt_app:create", help="The app factory to boot, module:function")
    args = parser.parse_args()

    from fastapi.testclient import TestClient

    module, _, factory = args.app.partition(":")
    sys.path.insert(0, str(Path.cwd()))
    app = getattr(importlib.import_module(module), factory or "create")()
    with TestClient(app):
        # The extensions are importable as zephyrex.extensions.* only once the app has loaded them
        # (a composing app such as rpg-ai loads the suite's from its own roots).
        from zephyrex.extensions.rpg_modules.Install import install

        summary = install(
            app.state.model_registry,
            args.owner,
            json.loads(args.bundle.read_text()),
            system_ref=args.system_ref,
            content_ref=args.content_ref,
            rules=json.loads(args.rules.read_text()) if args.rules else None,
        )
    print(json.dumps(asdict(summary), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
