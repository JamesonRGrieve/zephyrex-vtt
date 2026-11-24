# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_combat 003: a combatant's side in its fight (friendly, hostile or neutral), set when the
encounter starts or by the GM; none follows its token's disposition. Inspector-guarded.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_rpg_combat_combatant_side"
down_revision: Union[str, None] = "002_rpg_combat_combatant_state"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COMMENT = "Its side in this fight (friendly, hostile, neutral); none follows its token's disposition"


def upgrade() -> None:
    if "side" not in {column["name"] for column in sa.inspect(op.get_bind()).get_columns("combatants")}:
        with op.batch_alter_table("combatants") as batch:
            batch.add_column(sa.Column("side", sa.String(), nullable=True, comment=COMMENT))


def downgrade() -> None:
    with op.batch_alter_table("combatants") as batch:
        batch.drop_column("side")
