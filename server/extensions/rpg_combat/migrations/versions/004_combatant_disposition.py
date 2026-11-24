# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_combat 004: a combatant's stance is its own disposition, not a team (operator, 2026-11-24:
"Combat sides should be based on character disposition not blanket red team and blue team"). It
gains its disposition toward the party and whom it is hostile to (person ids, JSON text); 003's
side carries over as the disposition, then goes. Inspector-guarded.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_rpg_combat_combatant_disposition"
down_revision: Union[str, None] = "003_rpg_combat_combatant_side"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DISPOSITION = "Its stance toward the party in this fight (friendly, neutral, hostile)"
HOSTILE_TO = "Whom it is hostile to, person ids as JSON text; hostility runs both ways"


def _columns() -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns("combatants")}


def upgrade() -> None:
    present = _columns()
    with op.batch_alter_table("combatants") as batch:
        if "disposition" not in present:
            batch.add_column(sa.Column("disposition", sa.String(), nullable=True, comment=DISPOSITION))
        if "hostile_to" not in present:
            batch.add_column(sa.Column("hostile_to", sa.String(), nullable=True, comment=HOSTILE_TO))
    if "side" in present:
        op.execute("UPDATE combatants SET disposition = side WHERE side IS NOT NULL AND disposition IS NULL")
        with op.batch_alter_table("combatants") as batch:
            batch.drop_column("side")


def downgrade() -> None:
    with op.batch_alter_table("combatants") as batch:
        batch.add_column(sa.Column("side", sa.String(), nullable=True))
    op.execute("UPDATE combatants SET side = disposition")
    with op.batch_alter_table("combatants") as batch:
        batch.drop_column("hostile_to")
        batch.drop_column("disposition")
