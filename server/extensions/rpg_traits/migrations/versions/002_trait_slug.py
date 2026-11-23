# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_traits 002: a trait's slug, the option's stable name within its kind (repair, seafarer),
which a plot hook's character check names (the wiki's contract/requirement-cases.json). A trait made
before it keeps a NULL slug until it is next saved; checks match only traits that have one.
Inspector-guarded: a no-op where the column is already there.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_rpg_traits_trait_slug"
down_revision: Union[str, None] = "001_rpg_traits_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    if "slug" not in _columns("traits"):
        with op.batch_alter_table("traits") as batch:
            batch.add_column(
                sa.Column(
                    "slug",
                    sa.String(),
                    nullable=True,
                    comment=(
                        "The option's stable name within its kind (repair, seafarer): what a plot hook's "
                        "character check names (contract/requirement-cases.json). From the name when not given."
                    ),
                )
            )
        op.create_index("ix_traits_slug", "traits", ["slug"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_traits_slug", table_name="traits")
    with op.batch_alter_table("traits") as batch:
        batch.drop_column("slug")
