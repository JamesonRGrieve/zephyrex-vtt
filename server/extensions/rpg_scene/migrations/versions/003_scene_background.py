# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_scene 003: scenes.background_url, the scene's map picture by link (battlemap art the GM set or
rpg-ai generated), drawn under its grid. Inspector-guarded."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_rpg_scene_scene_background"
down_revision: Union[str, None] = "002_rpg_scene_scene_locations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "background_url" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("scenes")}:
        with op.batch_alter_table("scenes") as batch:
            batch.add_column(
                sa.Column(
                    "background_url",
                    sa.String(),
                    nullable=True,
                    comment="The scene's map picture by link (battlemap art, set or generated)",
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("scenes") as batch:
        batch.drop_column("background_url")
