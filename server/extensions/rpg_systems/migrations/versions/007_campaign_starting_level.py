# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_systems 007: a campaign's starting level, the level its characters start at (a scenario's
pregens are built to it by rpg_builder's build_pregen); none is the pack's first. Added to the wiki's
campaigns, as 001 added game_system_id. Inspector-guarded.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_rpg_systems_campaign_starting_level"
down_revision: Union[str, None] = "006_rpg_systems_srd_5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COMMENT = "The level its characters start at (a scenario's pregens are built to it); none is the pack's first"


def upgrade() -> None:
    if "starting_level" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("campaigns")}:
        with op.batch_alter_table("campaigns") as batch:
            batch.add_column(sa.Column("starting_level", sa.Integer(), nullable=True, comment=COMMENT))


def downgrade() -> None:
    with op.batch_alter_table("campaigns") as batch:
        batch.drop_column("starting_level")
