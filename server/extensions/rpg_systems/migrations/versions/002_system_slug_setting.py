# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_systems 002: a game system's slug (its stable name, redacted) and the wiki setting it
belongs to (setting_id: a reference by id to the wiki's rpg_core SettingModel, no foreign key, since
the wiki sits above vtt). Inspector-guarded: a no-op where a column is already there.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_rpg_systems_slug_setting"
down_revision: Union[str, None] = "001_rpg_systems_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Neither is unique: people make their own systems, and two may share a name. The seed (003) skips a
# slug already there, so the catalog holds each seeded slug once.
COLUMNS = [
    ("slug", "Stable name (redacted); from the name when not given"),
    ("setting_id", "The wiki's setting it belongs to (a reference, no FK)"),
]


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    present = _columns("game_systems")
    for name, comment in COLUMNS:
        if name in present:
            continue
        with op.batch_alter_table("game_systems") as batch:
            batch.add_column(sa.Column(name, sa.String(), nullable=True, comment=comment))
        op.create_index(f"ix_game_systems_{name}", "game_systems", [name], unique=False)


def downgrade() -> None:
    for name, _comment in reversed(COLUMNS):
        op.drop_index(f"ix_game_systems_{name}", table_name="game_systems")
        with op.batch_alter_table("game_systems") as batch:
            batch.drop_column(name)
