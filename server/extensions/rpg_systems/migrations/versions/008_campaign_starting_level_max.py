# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_systems 008: the highest starting level a campaign offers (a one-shot playable at 1 to 4:
the operator, 2026-11-25, "supposed to be selectable 1-4, not constant 4"); none is the pack's
highest. Added to the wiki's campaigns beside 007's starting_level. Inspector-guarded.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "008_rpg_systems_campaign_starting_level_max"
down_revision: Union[str, None] = "007_rpg_systems_campaign_starting_level"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COMMENT = "The highest starting level it offers (a one-shot's 1 to 4); none is the pack's highest"


def upgrade() -> None:
    if "starting_level_max" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("campaigns")}:
        with op.batch_alter_table("campaigns") as batch:
            batch.add_column(sa.Column("starting_level_max", sa.Integer(), nullable=True, comment=COMMENT))


def downgrade() -> None:
    with op.batch_alter_table("campaigns") as batch:
        batch.drop_column("starting_level_max")
