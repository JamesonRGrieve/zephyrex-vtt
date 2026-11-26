# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_scene 006: scene_item_spots, where a lying item is drawn on a scene (the operator, 2026-11-26:
"I haven't seen any loot functionality at all"). The wiki's item instances have a place but no
point; a fallen combatant's dropped things lie where the body fell, recorded here. Inspector-guarded.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_rpg_scene_scene_item_spots"
down_revision: Union[str, None] = "005_rpg_scene_scene_floor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_INFO = {"extension": "rpg_scene"}


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("scene_item_spots"):
        return
    op.create_table(
        "scene_item_spots",
        sa.Column("scene_id", sa.String(), sa.ForeignKey("scenes.id"), nullable=True, comment="Optional foreign key to SceneModel"),
        sa.Column("item_instance_id", sa.String(), nullable=True, comment="The wiki's item instance lying here"),
        sa.Column("x", sa.Float(), nullable=True, comment="Pixels"),
        sa.Column("y", sa.Float(), nullable=True, comment="Pixels"),
        sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True, comment="Optional foreign key to UserModel"),
        sa.Column("updated_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True, comment="Optional foreign key to UserModel"),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by_user_id", sa.String(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        comment="Where a lying item is drawn on a scene (a fallen combatant's things where the body fell)",
        info=TABLE_INFO,
    )
    op.create_index("ix_scene_item_spots_deleted_at", "scene_item_spots", ["deleted_at"], unique=False)
    op.create_index("ix_scene_item_spots_scene_id", "scene_item_spots", ["scene_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scene_item_spots_scene_id", table_name="scene_item_spots")
    op.drop_index("ix_scene_item_spots_deleted_at", table_name="scene_item_spots")
    op.drop_table("scene_item_spots")
