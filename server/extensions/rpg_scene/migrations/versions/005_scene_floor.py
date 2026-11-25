# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_scene 005: scenes.floor, which floor of its place a map is (0, the one the place opens on;
1, 2… the floors a vault names in order: The Split Antler's upper storeys, a cellar). A place's
floors are each their own scene. Inspector-guarded."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_rpg_scene_scene_floor"
down_revision: Union[str, None] = "004_rpg_scene_scope_places"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if "floor" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("scenes")}:
        with op.batch_alter_table("scenes") as batch:
            batch.add_column(
                sa.Column("floor", sa.Integer(), nullable=True, comment="Which floor of its place this map is; 0 (or none) the one it opens on")
            )


def downgrade() -> None:
    with op.batch_alter_table("scenes") as batch:
        batch.drop_column("floor")
