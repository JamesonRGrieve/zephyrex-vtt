# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_combat 005: character_states, what a fight, a rest or a potion leaves on a character and
outlasts the fight: hit points now, spent Hit Point Dice, the Exhaustion level and the conditions it
has (Zephyrex RPG, 2026-11-28: the story follows the game's state). Inspector-guarded.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_rpg_combat_character_states"
down_revision: Union[str, None] = "004_rpg_combat_combatant_disposition"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE_INFO = {"extension": "rpg_combat"}


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table("character_states"):
        return
    op.create_table(
        "character_states",
        sa.Column("person_id", sa.String(), sa.ForeignKey("persons.id"), nullable=True, comment="Optional foreign key to PersonModel"),
        sa.Column("hp", sa.Integer(), nullable=True, comment="Hit points now; none = the sheet's maximum"),
        sa.Column("hit_dice_spent", sa.Integer(), nullable=True, comment="Hit Point Dice spent since the last Long Rest"),
        sa.Column("exhaustion", sa.Integer(), nullable=True, comment="The Exhaustion level (0 = none)"),
        sa.Column("conditions", sa.String(), nullable=True, comment="The conditions it has, names as JSON text"),
        sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True, comment="Optional foreign key to UserModel"),
        sa.Column("updated_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True, comment="Optional foreign key to UserModel"),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by_user_id", sa.String(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        comment="A character's state that outlasts a fight: hit points, spent Hit Point Dice, Exhaustion, conditions",
        info=TABLE_INFO,
    )
    op.create_index("ix_character_states_deleted_at", "character_states", ["deleted_at"], unique=False)
    op.create_index("ix_character_states_person_id", "character_states", ["person_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_character_states_person_id", table_name="character_states")
    op.drop_index("ix_character_states_deleted_at", table_name="character_states")
    op.drop_table("character_states")
