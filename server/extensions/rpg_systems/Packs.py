# SPDX-License-Identifier: AGPL-3.0-or-later
"""System packs: a game system's rules as data, one file per system slug (packs/<slug>.json, or a
private instance's VTT_PACKS_DIRS). A pack
says how a test is run (rpg_dice Percentile.py) and which characteristics and skills the system
has, seeded as its trait templates. Every value is cited to the system's rulebook."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

PACKS_DIR = Path(__file__).resolve().parent / "packs"


def pack_dirs() -> list[Path]:
    """Where packs are found: the open ones here, then each directory in VTT_PACKS_DIRS
    (os.pathsep-separated): a private instance's own packs, or the tests' synthetic one."""
    extra = [Path(one) for one in os.environ.get("VTT_PACKS_DIRS", "").split(os.pathsep) if one]
    return [PACKS_DIR, *extra]


@lru_cache(maxsize=None)
def load_pack(slug: str) -> Optional[dict[str, Any]]:
    """The pack for a system slug, or None when the system has no pack yet."""
    if not slug or "/" in slug or slug.startswith("."):
        return None
    for directory in pack_dirs():
        path = directory / f"{slug}.json"
        if path.is_file() and path.parent == directory:
            pack: dict[str, Any] = json.loads(path.read_text())
            return pack
    return None
