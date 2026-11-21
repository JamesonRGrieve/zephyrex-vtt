# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_systems 003: seed the game systems the operator named (game-systems.json), names only. A
system whose slug is already there is left as it is, so this is safe on any database. setting_id
stays empty until the wiki's settings exist; then it is attached by the setting slug in the file.
The rows are written as the framework's SYSTEM user: readable by everyone signed in (the catalog is
the rules), changeable only by ROOT and SYSTEM. The downgrade removes only the seeded rows nobody has
changed since (their updated_at is unset).
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op
from zephyrex.lib.Environment import env

revision: str = "003_rpg_systems_seed_game_systems"
down_revision: Union[str, None] = "002_rpg_systems_slug_setting"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_FILE = Path(__file__).resolve().parents[2] / "game-systems.json"

game_systems = sa.table(
    "game_systems",
    sa.column("id", sa.String),
    sa.column("name", sa.String),
    sa.column("slug", sa.String),
    sa.column("created_by_user_id", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)


def _seed() -> list[dict[str, Any]]:
    systems: list[dict[str, Any]] = json.loads(SEED_FILE.read_text())["systems"]
    return systems


def upgrade() -> None:
    bind = op.get_bind()
    present = {row[0] for row in bind.execute(sa.select(game_systems.c.slug)) if row[0]}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [
        {
            "id": str(uuid.uuid4()),
            "name": one["name"],
            "slug": one["slug"],
            "created_by_user_id": env("SYSTEM_ID"),
            "created_at": now,
        }
        for one in _seed()
        if one["slug"] not in present
    ]
    if rows:
        op.bulk_insert(game_systems, rows)


def downgrade() -> None:
    slugs = [one["slug"] for one in _seed()]
    op.execute(game_systems.delete().where(game_systems.c.slug.in_(slugs), game_systems.c.updated_at.is_(None)))
