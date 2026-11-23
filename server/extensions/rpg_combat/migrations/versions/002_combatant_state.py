# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_combat 002: a combatant's state in the fight: its hit points now and their maximum (from the
sheet when first needed) and the rounds it took its action and used its reaction in. Inspector-guarded: a no-op where the
columns are already there.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_rpg_combat_combatant_state"
down_revision: Union[str, None] = "001_rpg_combat_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (
    ("hp", "Hit points now, in this fight; from the sheet when first needed"),
    ("hp_max", "The hit point maximum, from the sheet"),
    ("reaction_round", "The round its reaction was used in; free again the next round"),
    ("action_round", "The round it took its action in, on its turn"),
)


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    present = _columns("combatants")
    with op.batch_alter_table("combatants") as batch:
        for name, comment in COLUMNS:
            if name not in present:
                batch.add_column(sa.Column(name, sa.Integer(), nullable=True, comment=comment))


def downgrade() -> None:
    with op.batch_alter_table("combatants") as batch:
        for name, _ in COLUMNS:
            batch.drop_column(name)
