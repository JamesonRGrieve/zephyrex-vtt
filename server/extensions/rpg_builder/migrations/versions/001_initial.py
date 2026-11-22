# SPDX-License-Identifier: AGPL-3.0-or-later
"""Initial migration for rpg_builder: ability rolls the server kept for character creation. Written
from the model's metadata (Migration_test holds the migrated schema equal to it); inspector-guarded.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_rpg_builder_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("ext_rpg_builder",)
# No depends_on: the order comes from rpg_builder's required EXT_Dependency on genealogy (persons).
depends_on: Union[str, Sequence[str], None] = None

TABLE_INFO = {"extension": "rpg_builder"}


def upgrade() -> None:
    if sa.inspect(op.get_bind()).has_table('ability_rolls'):
        return
    op.create_table(
        'ability_rolls',
        sa.Column('person_id', sa.String(), sa.ForeignKey('persons.id'), nullable=True, comment='Optional foreign key to PersonModel'),
        sa.Column('scores', sa.JSON(), nullable=True, comment='The six totals rolled, in order'),
        sa.Column('dice', sa.JSON(), nullable=True, comment='Every die of each roll, kept and dropped'),
        sa.Column('is_used', sa.Boolean(), nullable=True, comment="Applied to the character's scores"),
        sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
        sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_by_user_id', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        comment='Ability scores the server rolled for a character (character creation)',
        info=TABLE_INFO,
    )
    op.create_index('ix_ability_rolls_deleted_at', 'ability_rolls', ['deleted_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_ability_rolls_deleted_at', table_name='ability_rolls')
    op.drop_table('ability_rolls')
