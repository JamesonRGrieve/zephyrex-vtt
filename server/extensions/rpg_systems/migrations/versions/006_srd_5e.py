# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_systems 006: the fifth-edition system is the open SRD 5.2's, named generically: a database seeded
earlier with the dnd-5e row gets it renamed in place to srd-5e, "SRD 5.2 (fifth-edition rules)", so its
campaigns, traits and module links keep their id. Setting-specific systems are no longer seeded publicly
(operator ruling, 2026-11-23); rows already in a database are left as they are."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_rpg_systems_srd_5e"
down_revision: Union[str, None] = "005_rpg_systems_seed_added_systems"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

game_systems = sa.table("game_systems", sa.column("slug", sa.String), sa.column("name", sa.String))
NAME = "SRD 5.2 (fifth-edition rules)"


def upgrade() -> None:
    bind = op.get_bind()
    present = {row[0] for row in bind.execute(sa.select(game_systems.c.slug))}
    if "dnd-5e" in present and "srd-5e" not in present:
        op.execute(game_systems.update().where(game_systems.c.slug == "dnd-5e").values(slug="srd-5e", name=NAME))


def downgrade() -> None:
    """Nothing to undo: the old name isn't restored into open code."""
