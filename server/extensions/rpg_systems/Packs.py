# SPDX-License-Identifier: AGPL-3.0-or-later
"""System packs: a game system's rules as data, one file per system slug (packs/<slug>.json). A pack
says how a test is run (rpg_dice Percentile.py) and which characteristics and skills the system
has, seeded as its trait templates. Every value is cited to the system's rulebook."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

PACKS_DIR = Path(__file__).resolve().parent / "packs"


@lru_cache(maxsize=None)
def load_pack(slug: str) -> Optional[dict[str, Any]]:
    """The pack for a system slug, or None when the system has no pack yet."""
    path = PACKS_DIR / f"{slug}.json"
    if not path.is_file() or path.parent != PACKS_DIR:
        return None
    pack: dict[str, Any] = json.loads(path.read_text())
    return pack
