# SPDX-License-Identifier: AGPL-3.0-or-later
"""Initial migration for rpg_systems: owns ``game_systems``, and adds the game system to the wiki's
``campaigns`` (rpg_core) and ``items`` (world_inventory), with real foreign keys. It runs after those
extensions' migrations (the framework orders by required EXT_Dependency and FKs), so the tables it
touches exist. Inspector guards make each step a no-op where the table or column is already there.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_rpg_systems_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("ext_rpg_systems",)
# No depends_on: each extension has its own Alembic history; the order comes from rpg_systems'
# required EXT_Dependency on rpg_core and world_inventory (EXT_RPGSystems.py).
depends_on: Union[str, Sequence[str], None] = None

TABLE_INFO = {"extension": "rpg_systems"}

# (table, column): the game system rpg_systems gives other extensions' records.
INJECTED: list[tuple[str, str]] = [("campaigns", "game_system_id"), ("items", "game_system_id")]


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def _audit_columns() -> list:
    return [
        sa.Column("created_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True, comment="Optional foreign key to UserModel"),
        sa.Column("updated_by_user_id", sa.String(), sa.ForeignKey("users.id"), nullable=True, comment="Optional foreign key to UserModel"),
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_by_user_id", sa.String(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    if not _has_table("game_systems"):
        op.create_table(
            "game_systems",
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("name", sa.String(), nullable=True),
            *_audit_columns(),
            sa.PrimaryKeyConstraint("id"),
            comment="Reference catalog of supported RPG systems (DnD 5e, Pathfinder 2e, ...)",
            info=TABLE_INFO,
        )
        op.create_index("ix_game_systems_deleted_at", "game_systems", ["deleted_at"])
    for table, column in INJECTED:
        if not _has_table(table) or column in _columns(table):
            continue
        # batch mode: SQLite can't add a column with a foreign key in place; Alembic copies the table.
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column(column, sa.String(), nullable=True, comment="Optional foreign key to GameSystemModel"))
            batch.create_foreign_key(f"fk_{table}_{column}_game_systems", "game_systems", [column], ["id"])


def downgrade() -> None:
    for table, column in reversed(INJECTED):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_{column}_game_systems", type_="foreignkey")
            batch.drop_column(column)
    op.drop_index("ix_game_systems_deleted_at", table_name="game_systems")
    op.drop_table("game_systems")
