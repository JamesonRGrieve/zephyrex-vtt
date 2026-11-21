# SPDX-License-Identifier: AGPL-3.0-or-later
"""Initial migration for rpg_scene: scenes, their levels, map features (zephyr-cartography's scene-spec model), tokens, walls, lights, tiles, map pins and regions. Until now these tables came only from the framework's
create_all fallback; this is their history from here. Generated from the models' own metadata and
reviewed (Migration_test holds the migrated schema equal to the models). Inspector guards make each
table a no-op where the fallback already made it, so an existing database keeps its rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_rpg_scene_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("ext_rpg_scene",)
# No depends_on: each extension has its own Alembic history; the order comes from rpg_scene's required
# EXT_Dependency on rpg_core (campaigns) and genealogy (persons).
depends_on: Union[str, Sequence[str], None] = None

TABLE_INFO = {"extension": "rpg_scene"}


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table('scenes'):
        op.create_table(
            'scenes',
            sa.Column('campaign_id', sa.String(), sa.ForeignKey('campaigns.id'), nullable=True, comment='Optional foreign key to CampaignModel'),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('width', sa.Integer(), nullable=True, comment='Pixels'),
            sa.Column('height', sa.Integer(), nullable=True, comment='Pixels'),
            sa.Column('grid_size', sa.Float(), nullable=True, comment='Pixels per grid cell'),
            sa.Column('grid_distance', sa.Float(), nullable=True, comment='Distance units per cell'),
            sa.Column('grid_units', sa.String(), nullable=True, comment='What the distance units are'),
            sa.Column('token_vision', sa.Boolean(), nullable=True, comment='Whether tokens see only what their sight allows'),
            sa.Column('global_illumination', sa.Boolean(), nullable=True, comment='Lit everywhere, whatever the darkness'),
            sa.Column('darkness_level', sa.Float(), nullable=True, comment='0 (day) to 1 (pitch dark)'),
            sa.Column('background_color', sa.String(), nullable=True, comment='#rrggbb shown where there is no art'),
            sa.Column('padding', sa.Float(), nullable=True, comment='Share of width and height around the map'),
            sa.Column('splats', sa.JSON(), nullable=True, comment='Terrain paint layers (cartography); masks are attachments'),
            sa.Column('flags', sa.JSON(), nullable=True, comment="Other systems' data about the place, kept as given"),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='A playable area in a campaign: the battlemap a table plays on',
            info=TABLE_INFO,
        )
        op.create_index('ix_scenes_deleted_at', 'scenes', ['deleted_at'], unique=False)
    if not _has_table('scene_levels'):
        op.create_table(
            'scene_levels',
            sa.Column('scene_id', sa.String(), sa.ForeignKey('scenes.id'), nullable=True, comment='Optional foreign key to SceneModel'),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('sort', sa.Integer(), nullable=True, comment='Bottom to top'),
            sa.Column('bottom', sa.Float(), nullable=True, comment='Floor elevation, distance units'),
            sa.Column('top', sa.Float(), nullable=True, comment='Ceiling elevation, distance units; NULL = open'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='A level (floor) of a scene',
            info=TABLE_INFO,
        )
        op.create_index('ix_scene_levels_deleted_at', 'scene_levels', ['deleted_at'], unique=False)
    if not _has_table('scene_features'):
        op.create_table(
            'scene_features',
            sa.Column('scene_level_id', sa.String(), sa.ForeignKey('scene_levels.id'), nullable=True, comment='Optional foreign key to SceneLevelModel'),
            sa.Column('scene_id', sa.String(), sa.ForeignKey('scenes.id'), nullable=True, comment='Optional foreign key to SceneModel'),
            sa.Column('kind', sa.String(), nullable=True),
            sa.Column('key', sa.String(), nullable=True, comment='The name other features use for this one'),
            sa.Column('sort', sa.Integer(), nullable=True, comment='Drawing order within its kind'),
            sa.Column('spec', sa.JSON(), nullable=True, comment='The scene-spec v1 feature'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment="A map feature in zephyr-cartography's scene-spec model",
            info=TABLE_INFO,
        )
        op.create_index('ix_scene_features_deleted_at', 'scene_features', ['deleted_at'], unique=False)
    if not _has_table('scene_tokens'):
        op.create_table(
            'scene_tokens',
            sa.Column('person_id', sa.String(), sa.ForeignKey('persons.id'), nullable=True, comment='Optional foreign key to PersonModel'),
            sa.Column('scene_level_id', sa.String(), sa.ForeignKey('scene_levels.id'), nullable=True, comment='Optional foreign key to SceneLevelModel'),
            sa.Column('scene_id', sa.String(), sa.ForeignKey('scenes.id'), nullable=True, comment='Optional foreign key to SceneModel'),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('x', sa.Float(), nullable=True, comment='Left edge, pixels'),
            sa.Column('y', sa.Float(), nullable=True, comment='Top edge, pixels'),
            sa.Column('width', sa.Float(), nullable=True, comment='Grid cells'),
            sa.Column('height', sa.Float(), nullable=True, comment='Grid cells'),
            sa.Column('elevation', sa.Float(), nullable=True, comment='Distance units (not yet used for sight)'),
            sa.Column('rotation', sa.Float(), nullable=True, comment='Degrees clockwise from facing down the screen'),
            sa.Column('sight_range', sa.Float(), nullable=True, comment='Distance units; NULL = unlimited'),
            sa.Column('sight_angle', sa.Float(), nullable=True, comment='Degrees of the sight cone'),
            sa.Column('disposition', sa.String(), nullable=True),
            sa.Column('is_hidden', sa.Boolean(), nullable=True, comment='Hidden from players: never perceived'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='A token on a scene; person_id is the character it stands for',
            info=TABLE_INFO,
        )
        op.create_index('ix_scene_tokens_deleted_at', 'scene_tokens', ['deleted_at'], unique=False)
    if not _has_table('scene_lights'):
        op.create_table(
            'scene_lights',
            sa.Column('scene_feature_id', sa.String(), sa.ForeignKey('scene_features.id'), nullable=True, comment='Optional foreign key to SceneFeatureModel'),
            sa.Column('scene_level_id', sa.String(), sa.ForeignKey('scene_levels.id'), nullable=True, comment='Optional foreign key to SceneLevelModel'),
            sa.Column('scene_id', sa.String(), sa.ForeignKey('scenes.id'), nullable=True, comment='Optional foreign key to SceneModel'),
            sa.Column('x', sa.Float(), nullable=True, comment='Pixels'),
            sa.Column('y', sa.Float(), nullable=True, comment='Pixels'),
            sa.Column('bright', sa.Float(), nullable=True, comment='Bright radius, distance units'),
            sa.Column('dim', sa.Float(), nullable=True, comment='Dim radius, distance units'),
            sa.Column('angle', sa.Float(), nullable=True, comment='Degrees of the cone'),
            sa.Column('rotation', sa.Float(), nullable=True, comment='Degrees clockwise'),
            sa.Column('color', sa.String(), nullable=True, comment='#rrggbb, NULL for white'),
            sa.Column('darkness', sa.Boolean(), nullable=True, comment='A darkness source, not a light'),
            sa.Column('walls', sa.Boolean(), nullable=True, comment='Walls stop it'),
            sa.Column('is_hidden', sa.Boolean(), nullable=True, comment='Switched off'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='A light or darkness source on a scene',
            info=TABLE_INFO,
        )
        op.create_index('ix_scene_lights_deleted_at', 'scene_lights', ['deleted_at'], unique=False)
    if not _has_table('scene_notes'):
        op.create_table(
            'scene_notes',
            sa.Column('scene_feature_id', sa.String(), sa.ForeignKey('scene_features.id'), nullable=True, comment='Optional foreign key to SceneFeatureModel'),
            sa.Column('scene_level_id', sa.String(), sa.ForeignKey('scene_levels.id'), nullable=True, comment='Optional foreign key to SceneLevelModel'),
            sa.Column('scene_id', sa.String(), sa.ForeignKey('scenes.id'), nullable=True, comment='Optional foreign key to SceneModel'),
            sa.Column('x', sa.Float(), nullable=True, comment='Pixels'),
            sa.Column('y', sa.Float(), nullable=True, comment='Pixels'),
            sa.Column('text', sa.String(), nullable=True),
            sa.Column('icon', sa.String(), nullable=True),
            sa.Column('size', sa.Float(), nullable=True, comment='Pixels'),
            sa.Column('entity_type', sa.String(), nullable=True, comment='The wiki entity the pin opens'),
            sa.Column('entity_id', sa.String(), nullable=True),
            sa.Column('is_global', sa.Boolean(), nullable=True, comment='Shown whatever a token can see'),
            sa.Column('readable', sa.Boolean(), nullable=True, comment='A sign: players read it on hover'),
            sa.Column('is_hidden', sa.Boolean(), nullable=True, comment='Hidden from players'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='A map pin on a scene',
            info=TABLE_INFO,
        )
        op.create_index('ix_scene_notes_deleted_at', 'scene_notes', ['deleted_at'], unique=False)
    if not _has_table('scene_regions'):
        op.create_table(
            'scene_regions',
            sa.Column('scene_feature_id', sa.String(), sa.ForeignKey('scene_features.id'), nullable=True, comment='Optional foreign key to SceneFeatureModel'),
            sa.Column('scene_level_id', sa.String(), sa.ForeignKey('scene_levels.id'), nullable=True, comment='Optional foreign key to SceneLevelModel'),
            sa.Column('scene_id', sa.String(), sa.ForeignKey('scenes.id'), nullable=True, comment='Optional foreign key to SceneModel'),
            sa.Column('name', sa.String(), nullable=True),
            sa.Column('shapes', sa.JSON(), nullable=True),
            sa.Column('behaviours', sa.JSON(), nullable=True),
            sa.Column('is_hidden', sa.Boolean(), nullable=True, comment='Hidden from players, behaviours off'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='An area of a scene with behaviours',
            info=TABLE_INFO,
        )
        op.create_index('ix_scene_regions_deleted_at', 'scene_regions', ['deleted_at'], unique=False)
    if not _has_table('scene_tiles'):
        op.create_table(
            'scene_tiles',
            sa.Column('scene_feature_id', sa.String(), sa.ForeignKey('scene_features.id'), nullable=True, comment='Optional foreign key to SceneFeatureModel'),
            sa.Column('scene_level_id', sa.String(), sa.ForeignKey('scene_levels.id'), nullable=True, comment='Optional foreign key to SceneLevelModel'),
            sa.Column('scene_id', sa.String(), sa.ForeignKey('scenes.id'), nullable=True, comment='Optional foreign key to SceneModel'),
            sa.Column('x', sa.Float(), nullable=True, comment='Left edge, pixels'),
            sa.Column('y', sa.Float(), nullable=True, comment='Top edge, pixels'),
            sa.Column('width', sa.Float(), nullable=True, comment='Pixels'),
            sa.Column('height', sa.Float(), nullable=True, comment='Pixels'),
            sa.Column('rotation', sa.Float(), nullable=True, comment='Degrees clockwise'),
            sa.Column('sort', sa.Integer(), nullable=True, comment='Drawing order'),
            sa.Column('mirror_x', sa.Boolean(), nullable=True),
            sa.Column('mirror_y', sa.Boolean(), nullable=True),
            sa.Column('alpha', sa.Float(), nullable=True, comment='0 to 1'),
            sa.Column('is_hidden', sa.Boolean(), nullable=True, comment='Hidden from players'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='An image placed on a scene',
            info=TABLE_INFO,
        )
        op.create_index('ix_scene_tiles_deleted_at', 'scene_tiles', ['deleted_at'], unique=False)
    if not _has_table('scene_walls'):
        op.create_table(
            'scene_walls',
            sa.Column('scene_feature_id', sa.String(), sa.ForeignKey('scene_features.id'), nullable=True, comment='Optional foreign key to SceneFeatureModel'),
            sa.Column('scene_level_id', sa.String(), sa.ForeignKey('scene_levels.id'), nullable=True, comment='Optional foreign key to SceneLevelModel'),
            sa.Column('scene_id', sa.String(), sa.ForeignKey('scenes.id'), nullable=True, comment='Optional foreign key to SceneModel'),
            sa.Column('points', sa.JSON(), nullable=True, comment='[[x, y], ...] pixels, a polyline'),
            sa.Column('door_type', sa.String(), nullable=True),
            sa.Column('door_state', sa.String(), nullable=True),
            sa.Column('sight_restriction', sa.String(), nullable=True),
            sa.Column('move_restriction', sa.String(), nullable=True),
            sa.Column('light_restriction', sa.String(), nullable=True),
            sa.Column('sound_restriction', sa.String(), nullable=True),
            sa.Column('direction', sa.String(), nullable=True, comment='One-way walls block one side only'),
            sa.Column('created_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('updated_by_user_id', sa.String(), sa.ForeignKey('users.id'), nullable=True, comment='Optional foreign key to UserModel'),
            sa.Column('id', sa.String(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
            sa.Column('deleted_by_user_id', sa.String(), nullable=True),
            sa.Column('deleted_at', sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            comment='A wall or door on a scene, as a polyline; scene_feature_id is the feature that made it',
            info=TABLE_INFO,
        )
        op.create_index('ix_scene_walls_deleted_at', 'scene_walls', ['deleted_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_scene_walls_deleted_at', table_name='scene_walls')
    op.drop_table('scene_walls')
    op.drop_index('ix_scene_tiles_deleted_at', table_name='scene_tiles')
    op.drop_table('scene_tiles')
    op.drop_index('ix_scene_regions_deleted_at', table_name='scene_regions')
    op.drop_table('scene_regions')
    op.drop_index('ix_scene_notes_deleted_at', table_name='scene_notes')
    op.drop_table('scene_notes')
    op.drop_index('ix_scene_lights_deleted_at', table_name='scene_lights')
    op.drop_table('scene_lights')
    op.drop_index('ix_scene_tokens_deleted_at', table_name='scene_tokens')
    op.drop_table('scene_tokens')
    op.drop_index('ix_scene_features_deleted_at', table_name='scene_features')
    op.drop_table('scene_features')
    op.drop_index('ix_scene_levels_deleted_at', table_name='scene_levels')
    op.drop_table('scene_levels')
    op.drop_index('ix_scenes_deleted_at', table_name='scenes')
    op.drop_table('scenes')
