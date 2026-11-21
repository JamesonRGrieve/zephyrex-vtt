# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_scene 002: scenes know their places (the GM agent pilots characters to wiki locations).

- scenes.location_id (FK → locations.id): the wiki location the map shows;
- scenes.entry_x / entry_y: where arrivals appear (none = the scene's centre);
- scenes.is_active: the campaign's current scene, one per campaign (activate);
- scene_regions.location_id (FK → locations.id): a sub-location's area inside the scene.
Inspector-guarded: a no-op for a column that's already there.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_rpg_scene_scene_locations"
down_revision: Union[str, None] = "001_rpg_scene_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOCATION = "Optional foreign key to LocationModel"


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    scenes = _columns("scenes")
    with op.batch_alter_table("scenes") as batch:
        if "location_id" not in scenes:
            # batch mode, as the wiki's rpg_core does: SQLite can't add a foreign-key column in place,
            # so the column goes in plain and the key is a named constraint on the copied table.
            batch.add_column(sa.Column("location_id", sa.String(), nullable=True, comment=LOCATION))
            batch.create_foreign_key("fk_scenes_location_id_locations", "locations", ["location_id"], ["id"])
        if "entry_x" not in scenes:
            batch.add_column(
                sa.Column("entry_x", sa.Float(), nullable=True, comment="Where arrivals appear, pixels; none = the scene's centre")
            )
        if "entry_y" not in scenes:
            batch.add_column(
                sa.Column("entry_y", sa.Float(), nullable=True, comment="Where arrivals appear, pixels; none = the scene's centre")
            )
        if "is_active" not in scenes:
            batch.add_column(
                sa.Column(
                    "is_active", sa.Boolean(), nullable=True, comment="The campaign's current scene (one per campaign; activate)"
                )
            )
    if "location_id" not in _columns("scene_regions"):
        with op.batch_alter_table("scene_regions") as batch:
            batch.add_column(sa.Column("location_id", sa.String(), nullable=True, comment=LOCATION))
            batch.create_foreign_key("fk_scene_regions_location_id_locations", "locations", ["location_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("scene_regions") as batch:
        batch.drop_constraint("fk_scene_regions_location_id_locations", type_="foreignkey")
        batch.drop_column("location_id")
    with op.batch_alter_table("scenes") as batch:
        batch.drop_constraint("fk_scenes_location_id_locations", type_="foreignkey")
        for column in ("is_active", "entry_y", "entry_x", "location_id"):
            batch.drop_column(column)
