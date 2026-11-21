# SPDX-License-Identifier: AGPL-3.0-or-later
"""Initial migration for rpg_combat: encounters and their combatants. Written from the models' own
metadata (Migration_test holds the migrated schema equal to the models). Inspector guards make each
table a no-op where the framework's create_all fallback already made it.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_rpg_combat_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("ext_rpg_combat",)
# No depends_on: each extension has its own Alembic history; the order comes from rpg_combat's required
# EXT_Dependency on rpg_core (campaigns), rpg_scene (scenes, tokens) and genealogy (persons).
depends_on: Union[str, Sequence[str], None] = None

TABLE_INFO = {"extension": "rpg_combat"}


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _audit() -> list[sa.Column]:
    return [
        sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
        sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_by_user_id', sa.String(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    if not _has_table('encounters'):
        op.create_table(
            'encounters',
            sa.Column('campaign_id', sa.String(), sa.ForeignKey('campaigns.id'), nullable=True, comment='Optional foreign key to CampaignModel'),
            sa.Column('scene_id', sa.String(), sa.ForeignKey('scenes.id'), nullable=True, comment='Optional foreign key to SceneModel'),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('status', sa.String(), nullable=True, comment='setup, running or ended (start, end)'),
            sa.Column('round', sa.Integer(), nullable=True, comment='The round being fought; 0 before the start'),
            sa.Column('current_combatant_id', sa.String(), nullable=True, comment='Whose turn it is (next)'),
            *_audit(),
            sa.PrimaryKeyConstraint('id'),
            comment='A fight in a campaign, perhaps on a scene; its GM runs it',
            info=TABLE_INFO,
        )
        op.create_index('ix_encounters_deleted_at', 'encounters', ['deleted_at'], unique=False)
    if not _has_table('combatants'):
        op.create_table(
            'combatants',
            sa.Column('encounter_id', sa.String(), sa.ForeignKey('encounters.id'), nullable=True, comment='Optional foreign key to EncounterModel'),
            sa.Column('person_id', sa.String(), sa.ForeignKey('persons.id'), nullable=True, comment='Optional foreign key to PersonModel'),
            sa.Column('scene_token_id', sa.String(), sa.ForeignKey('scene_tokens.id'), nullable=True, comment='Optional foreign key to SceneTokenModel'),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('initiative', sa.Float(), nullable=True, comment='Rolled (or set by the GM); highest acts first'),
            sa.Column('tiebreak', sa.Float(), nullable=True, comment='The initiative characteristic, which breaks ties'),
            sa.Column('roll_off', sa.Integer(), nullable=True, comment='A d10, for ties the characteristic leaves'),
            sa.Column('is_defeated', sa.Boolean(), nullable=True, comment='Out of the fight: skipped when the turn passes'),
            sa.Column('is_hidden', sa.Boolean(), nullable=True, comment="The GM's alone (an ambusher not yet seen)"),
            *_audit(),
            sa.PrimaryKeyConstraint('id'),
            comment='A character in an encounter, with their initiative',
            info=TABLE_INFO,
        )
        op.create_index('ix_combatants_deleted_at', 'combatants', ['deleted_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_combatants_deleted_at', table_name='combatants')
    op.drop_table('combatants')
    op.drop_index('ix_encounters_deleted_at', table_name='encounters')
    op.drop_table('encounters')
