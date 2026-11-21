# SPDX-License-Identifier: AGPL-3.0-or-later
"""Initial migration for rpg_table: multiplayer tables, their seats, whispers and lines. Until now these tables came only from the framework's
create_all fallback; this is their history from here. Generated from the models' own metadata and
reviewed (Migration_test holds the migrated schema equal to the models). Inspector guards make each
table a no-op where the fallback already made it, so an existing database keeps its rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_rpg_table_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("ext_rpg_table",)
# No depends_on: each extension has its own Alembic history; the order comes from rpg_table's required
# EXT_Dependency on conversations (a table is a conversation), rpg_core (campaigns) and genealogy (persons).
depends_on: Union[str, Sequence[str], None] = None

TABLE_INFO = {"extension": "rpg_table"}


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table('table_lines'):
        op.create_table(
            'table_lines',
            sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=True, comment='Optional foreign key to ConversationModel'),
            sa.Column('seat_id', sa.String(), nullable=True, comment='The seat that says it'),
            sa.Column('text', sa.String(), nullable=True),
            sa.Column('channel', sa.String(), nullable=True),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='What a seat says, at the table or in a whisper',
            info=TABLE_INFO,
        )
        op.create_index('ix_table_lines_deleted_at', 'table_lines', ['deleted_at'], unique=False)
    if not _has_table('table_seats'):
        op.create_table(
            'table_seats',
            sa.Column('person_id', sa.String(), sa.ForeignKey('persons.id'), nullable=True, comment='Optional foreign key to PersonModel'),
            sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=True, comment='Optional foreign key to ConversationModel'),
            sa.Column('name', sa.String(), nullable=True, comment="The character's name, as seated"),
            sa.Column('avatar', sa.String(), nullable=True, comment="The character's picture, as seated (none yet)"),
            sa.Column('controller_id', sa.String(), nullable=True, comment='The player who plays it; none for an NPC'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment="A character's seat at a table (the table's conversation)",
            info=TABLE_INFO,
        )
        op.create_index('ix_table_seats_deleted_at', 'table_seats', ['deleted_at'], unique=False)
    if not _has_table('table_whispers'):
        op.create_table(
            'table_whispers',
            sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=True, comment='Optional foreign key to ConversationModel'),
            sa.Column('table_conversation_id', sa.String(), nullable=True, comment="The table's conversation"),
            sa.Column('seat_a_id', sa.String(), nullable=True, comment='One seat'),
            sa.Column('seat_b_id', sa.String(), nullable=True, comment='The other seat'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment="A whisper between two seats: a conversation of its own, the host's",
            info=TABLE_INFO,
        )
        op.create_index('ix_table_whispers_deleted_at', 'table_whispers', ['deleted_at'], unique=False)
    if not _has_table('tables'):
        op.create_table(
            'tables',
            sa.Column('conversation_id', sa.String(), sa.ForeignKey('conversations.id'), nullable=True, comment='Optional foreign key to ConversationModel'),
            sa.Column('campaign_id', sa.String(), sa.ForeignKey('campaigns.id'), nullable=True, comment='Optional foreign key to CampaignModel'),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment="A campaign's multiplayer table: its conversation, hosted by the GM",
            info=TABLE_INFO,
        )
        op.create_index('ix_tables_deleted_at', 'tables', ['deleted_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_tables_deleted_at', table_name='tables')
    op.drop_table('tables')
    op.drop_index('ix_table_whispers_deleted_at', table_name='table_whispers')
    op.drop_table('table_whispers')
    op.drop_index('ix_table_seats_deleted_at', table_name='table_seats')
    op.drop_table('table_seats')
    op.drop_index('ix_table_lines_deleted_at', table_name='table_lines')
    op.drop_table('table_lines')
