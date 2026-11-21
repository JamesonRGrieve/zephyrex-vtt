# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_systems 005: seed the game systems added to game-systems.json since 003, and give them their
wiki setting: redacted, for the [redacted] bridge's six lines (operator, 2026-11-21). As 003 and
004 do: a slug already there is left alone; rows are the framework's SYSTEM user's (the catalog is
public, the module content is not); the setting is matched by slug when the wiki has it.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op
from zephyrex.lib.Environment import env

revision: str = "005_rpg_systems_seed_added_systems"
down_revision: Union[str, None] = "004_rpg_systems_attach_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_FILE = Path(__file__).resolve().parents[2] / "game-systems.json"
ADDED = ("redacted",)

game_systems = sa.table(
    "game_systems",
    sa.column("id", sa.String),
    sa.column("name", sa.String),
    sa.column("slug", sa.String),
    sa.column("setting_id", sa.String),
    sa.column("created_by_user_id", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)
settings = sa.table("settings", sa.column("id", sa.String), sa.column("slug", sa.String))


def _setting_id(slug: str) -> str | None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("settings") or "slug" not in {c["name"] for c in inspector.get_columns("settings")}:
        return None
    row = op.get_bind().execute(sa.select(settings.c.id).where(settings.c.slug == slug)).first()
    return None if row is None else str(row[0])


def upgrade() -> None:
    systems: list[dict[str, Any]] = [one for one in json.loads(SEED_FILE.read_text())["systems"] if one["slug"] in ADDED]
    present = {row[0] for row in op.get_bind().execute(sa.select(game_systems.c.slug)) if row[0]}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [
        {
            "id": str(uuid.uuid4()),
            "name": one["name"],
            "slug": one["slug"],
            "setting_id": _setting_id(one["setting"]),
            "created_by_user_id": env("SYSTEM_ID"),
            "created_at": now,
        }
        for one in systems
        if one["slug"] not in present
    ]
    if rows:
        op.bulk_insert(game_systems, rows)


def downgrade() -> None:
    op.execute(game_systems.delete().where(game_systems.c.slug.in_(ADDED), game_systems.c.updated_at.is_(None)))
