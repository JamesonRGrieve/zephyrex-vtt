# SPDX-License-Identifier: AGPL-3.0-or-later
"""Initial migration for rpg_dice: saved dice formulae, roll tables and their entries. Until now these tables came only from the framework's
create_all fallback; this is their history from here. Generated from the models' own metadata and
reviewed (Migration_test holds the migrated schema equal to the models). Inspector guards make each
table a no-op where the fallback already made it, so an existing database keeps its rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_rpg_dice_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("ext_rpg_dice",)
# No depends_on: each extension has its own Alembic history; the order comes from rpg_dice's required
# EXT_Dependency on rpg_systems (a formula or table may belong to a game system).
depends_on: Union[str, Sequence[str], None] = None

TABLE_INFO = {"extension": "rpg_dice"}


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table('dice_formulae'):
        op.create_table(
            'dice_formulae',
            sa.Column('game_system_id', sa.String(), sa.ForeignKey('game_systems.id'), nullable=True, comment='Optional foreign key to GameSystemModel'),
            sa.Column('description', sa.String(), nullable=True),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('formula', sa.String(), nullable=True, comment='Dice notation (rpg_dice Dice.py)'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment="A saved formula, e.g. a system's attack roll; game_system_id NULL = any system",
            info=TABLE_INFO,
        )
        op.create_index('ix_dice_formulae_deleted_at', 'dice_formulae', ['deleted_at'], unique=False)
    if not _has_table('roll_tables'):
        op.create_table(
            'roll_tables',
            sa.Column('game_system_id', sa.String(), sa.ForeignKey('game_systems.id'), nullable=True, comment='Optional foreign key to GameSystemModel'),
            sa.Column('description', sa.String(), nullable=True),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('formula', sa.String(), nullable=True, comment='The roll that picks an entry'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment="A roll table (random encounters, loot); its entries cover the formula's range",
            info=TABLE_INFO,
        )
        op.create_index('ix_roll_tables_deleted_at', 'roll_tables', ['deleted_at'], unique=False)
    if not _has_table('roll_table_entries'):
        op.create_table(
            'roll_table_entries',
            sa.Column('roll_table_id', sa.String(), sa.ForeignKey('roll_tables.id'), nullable=True, comment='Optional foreign key to RollTableModel'),
            sa.Column('range_low', sa.Integer(), nullable=True, comment='The lowest roll that picks this entry'),
            sa.Column('range_high', sa.Integer(), nullable=True, comment='The highest roll that picks this entry'),
            sa.Column('result_text', sa.String(), nullable=True),
            sa.Column('result_entity_type', sa.String(), nullable=True, comment='What the entry names, if a record'),
            sa.Column('result_entity_id', sa.String(), nullable=True),
            sa.Column('weight', sa.Integer(), nullable=True, comment='Draw weight, for tables rolled by weight'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='One row of a roll table: a range of results and what it gives',
            info=TABLE_INFO,
        )
        op.create_index('ix_roll_table_entries_deleted_at', 'roll_table_entries', ['deleted_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_roll_table_entries_deleted_at', table_name='roll_table_entries')
    op.drop_table('roll_table_entries')
    op.drop_index('ix_roll_tables_deleted_at', table_name='roll_tables')
    op.drop_table('roll_tables')
    op.drop_index('ix_dice_formulae_deleted_at', table_name='dice_formulae')
    op.drop_table('dice_formulae')
