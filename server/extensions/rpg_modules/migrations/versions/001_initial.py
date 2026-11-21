# SPDX-License-Identifier: AGPL-3.0-or-later
"""Initial migration for rpg_modules: private rules and content modules from the Foundry bridge
(content_modules), the source documents each installed and the vtt records they became
(module_records), and the modules a campaign enables (campaign_modules). Generated from the models'
own metadata and reviewed (Migration_test holds the migrated schema equal to the models);
Inspector-guarded, so a table already there is left as it is.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_rpg_modules_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("ext_rpg_modules",)
# No depends_on: each extension has its own Alembic history; the order comes from rpg_modules'
# required EXT_Dependency on rpg_systems, rpg_traits and rpg_core.
depends_on: Union[str, Sequence[str], None] = None

TABLE_INFO = {"extension": "rpg_modules"}


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table('content_modules'):
        op.create_table(
            'content_modules',
            sa.Column('game_system_id', sa.String(), sa.ForeignKey('game_systems.id'), nullable=True, comment='Optional foreign key to GameSystemModel'),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('slug', sa.String(), nullable=True, comment='redacted-dh2, redacted-rt…'),
            sa.Column('line', sa.String(), nullable=True, comment="The source's line key (dh2, rt…)"),
            sa.Column('system_ref', sa.String(), nullable=True, comment='The redacted system commit it was read with'),
            sa.Column('content_ref', sa.String(), nullable=True, comment='The content repository commit it was read from'),
            sa.Column('document_count', sa.Integer(), nullable=True, comment='Source documents installed'),
            sa.Column('rules', sa.JSON(), nullable=True, comment="The line's test rules (characteristics, ranks, difficulties…)"),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='A private rules/content module, owned by the account that installed it',
            info=TABLE_INFO,
        )
        op.create_index('ix_content_modules_deleted_at', 'content_modules', ['deleted_at'], unique=False)
    if not _has_table('campaign_modules'):
        op.create_table(
            'campaign_modules',
            sa.Column('content_module_id', sa.String(), sa.ForeignKey('content_modules.id'), nullable=True, comment='Optional foreign key to ContentModuleModel'),
            sa.Column('campaign_id', sa.String(), sa.ForeignKey('campaigns.id'), nullable=True, comment='Optional foreign key to CampaignModel'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='A module enabled for a campaign',
            info=TABLE_INFO,
        )
        op.create_index('ix_campaign_modules_deleted_at', 'campaign_modules', ['deleted_at'], unique=False)
    if not _has_table('module_records'):
        op.create_table(
            'module_records',
            sa.Column('content_module_id', sa.String(), sa.ForeignKey('content_modules.id'), nullable=True, comment='Optional foreign key to ContentModuleModel'),
            sa.Column('source_id', sa.String(), nullable=True, comment="The Foundry document's _id"),
            sa.Column('source_type', sa.String(), nullable=True, comment='Its Foundry type (talent, skill, originPath…)'),
            sa.Column('entity_type', sa.String(), nullable=True, comment='The vtt record it became (trait…)'),
            sa.Column('entity_id', sa.String(), nullable=True, comment="That record's id"),
            sa.Column('content_hash', sa.String(), nullable=True),
            sa.Column('homebrew', sa.Boolean(), nullable=True),
            sa.Column('conversion', sa.Boolean(), nullable=True, comment="Another line's document, ported to this one"),
            sa.Column('provenance', sa.String(), nullable=True, comment='raw, homebrew… as the source labels it for the line'),
            sa.Column('book', sa.String(), nullable=True),
            sa.Column('page', sa.String(), nullable=True),
            sa.Column('data', sa.JSON(), nullable=True, comment="The document's system data, materialized for the line"),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='A source document of a module, and the vtt record it became',
            info=TABLE_INFO,
        )
        op.create_index('ix_module_records_deleted_at', 'module_records', ['deleted_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_module_records_deleted_at', table_name='module_records')
    op.drop_table('module_records')
    op.drop_index('ix_campaign_modules_deleted_at', table_name='campaign_modules')
    op.drop_table('campaign_modules')
    op.drop_index('ix_content_modules_deleted_at', table_name='content_modules')
    op.drop_table('content_modules')
