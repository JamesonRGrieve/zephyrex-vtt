# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Foundry bridge's install step: install a line's bundle (extract.mjs) as one account's private
module, server-side. Run on the server host, with the app's environment (its database), never
through a route: the content is on the server's disk, and the module belongs to --owner alone.

    python tools/foundry-bridge/install.py --bundle dh2.json --owner <user id> \
        [--system-ref <sha>] [--content-ref <sha>] [--rules rules.json]
"""

from __future__ import annotations

import argparse
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
    args = parser.parse_args()

    from fastapi.testclient import TestClient
    from vtt_app import create
    from zephyrex.extensions.rpg_modules.Install import install

    app = create()
    with TestClient(app):
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
