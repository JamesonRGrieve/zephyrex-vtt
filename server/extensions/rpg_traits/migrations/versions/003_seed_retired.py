# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_traits 003: retired. It seeded a setting-specific system's trait templates from a pack that is no
longer in open code (operator ruling, 2026-11-23); such packs reach a private instance through the
private module install. A database that ran it keeps its rows. The revision id is kept as it was, being
recorded in databases' migration history."""

from typing import Sequence, Union

revision: str = "003_rpg_traits_seed_dark_heresy_2e"
down_revision: Union[str, None] = "002_rpg_traits_trait_slug"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Nothing: the pack it read is private now."""


def downgrade() -> None:
    """Nothing to undo."""
