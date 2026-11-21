# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_systems 004: each seeded game system gets the wiki's setting it belongs to. game-systems.json
names each system's setting by slug, and the wiki seeds its settings with those slugs (rpg_core 006,
the wiki's S6b). Only a system with no setting yet is given one, so a system someone has since
placed elsewhere keeps its place; a setting slug the wiki doesn't have leaves its systems as they
are. It runs after the wiki's rpg_core migrations because rpg_systems requires rpg_core (each
extension keeps its own history). The downgrade clears only the setting_ids this attached.
"""

import json
from pathlib import Path
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_rpg_systems_attach_settings"
down_revision: Union[str, None] = "003_rpg_systems_seed_game_systems"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SEED_FILE = Path(__file__).resolve().parents[2] / "game-systems.json"

game_systems = sa.table(
    "game_systems", sa.column("slug", sa.String), sa.column("setting_id", sa.String)
)
settings = sa.table("settings", sa.column("id", sa.String), sa.column("slug", sa.String))


def _seed() -> list[dict[str, Any]]:
    systems: list[dict[str, Any]] = json.loads(SEED_FILE.read_text())["systems"]
    return systems


def _setting_ids() -> dict[str, str]:
    """The wiki's settings by slug, or none where its table (or slug column) isn't there."""
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("settings"):
        return {}
    if "slug" not in {column["name"] for column in inspector.get_columns("settings")}:
        return {}
    rows = op.get_bind().execute(sa.select(settings.c.slug, settings.c.id).where(settings.c.slug.is_not(None)))
    return {str(slug): str(setting_id) for slug, setting_id in rows}


def upgrade() -> None:
    by_slug = _setting_ids()
    for system in _seed():
        setting_id = by_slug.get(system["setting"])
        if setting_id is None:
            continue
        op.execute(
            game_systems.update()
            .where(game_systems.c.slug == system["slug"], game_systems.c.setting_id.is_(None))
            .values(setting_id=setting_id)
        )


def downgrade() -> None:
    by_slug = _setting_ids()
    for system in _seed():
        setting_id = by_slug.get(system["setting"])
        if setting_id is None:
            continue
        op.execute(
            game_systems.update()
            .where(game_systems.c.slug == system["slug"], game_systems.c.setting_id == setting_id)
            .values(setting_id=None)
        )
