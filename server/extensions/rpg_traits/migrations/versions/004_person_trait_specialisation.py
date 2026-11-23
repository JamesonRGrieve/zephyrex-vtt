# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_traits 004: a person's trait carries the specialisation it holds of a specialist skill (Lore
(Stars), Craft (Wood)), one row per specialisation, so a test can tell them apart.
Inspector-guarded: a no-op where the column is already there.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_rpg_traits_person_trait_specialisation"
down_revision: Union[str, None] = "003_rpg_traits_seed_dark_heresy_2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "specialisation" not in _columns("person_traits"):
        with op.batch_alter_table("person_traits") as batch:
            batch.add_column(
                sa.Column(
                    "specialisation",
                    sa.String(),
                    nullable=True,
                    comment=(
                        "Which specialisation of a specialist skill the person holds at this rank (Lore "
                        "(Stars), Craft (Wood)): one row per specialisation. NULL for skills without them."
                    ),
                )
            )


def downgrade() -> None:
    with op.batch_alter_table("person_traits") as batch:
        batch.drop_column("specialisation")
