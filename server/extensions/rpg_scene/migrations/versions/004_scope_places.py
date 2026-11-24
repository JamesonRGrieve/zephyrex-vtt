# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_scene 004: scope_places, where a place's marker sits on its parent's map at the scope above
it (operator, 2026-11-24: a scope-out mode showing "the town instead of the house"). The wiki's
places have no coordinates; these are the VTT's, as fractions of the parent's map. Inspector-guarded.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_rpg_scene_scope_places"
down_revision: Union[str, None] = "003_rpg_scene_scene_background"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_INFO = {"extension": "rpg_scene"}


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("scope_places"):
        return
    op.create_table(
        "scope_places",
        sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=True, comment="Optional foreign key to CampaignModel"),
        sa.Column("location_id", sa.String(), sa.ForeignKey("locations.id"), nullable=True, comment="Optional foreign key to LocationModel"),
        sa.Column("x", sa.Float(), nullable=True, comment="Across its parent's map, 0 (left) to 1 (right)"),
        sa.Column("y", sa.Float(), nullable=True, comment="Down its parent's map, 0 (top) to 1 (bottom)"),
        sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True, comment="Optional foreign key to UserModel"),
        sa.Column("updated_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True, comment="Optional foreign key to UserModel"),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by_user_id", sa.String(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        comment="Where a place's marker sits on its parent's map, at the scope above it",
        info=TABLE_INFO,
    )
    op.create_index("ix_scope_places_deleted_at", "scope_places", ["deleted_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_scope_places_deleted_at", table_name="scope_places")
    op.drop_table("scope_places")
