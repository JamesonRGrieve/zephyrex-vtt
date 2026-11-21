# SPDX-License-Identifier: AGPL-3.0-or-later
"""Initial migration for rpg_traits: owns ``traits``, ``derivative_traits`` and ``person_traits``
(split from rpg_state, which never had a migration). It runs after rpg_systems, the wiki's rpg_core
and genealogy (required EXT_Dependency), so the tables its foreign keys name exist. Inspector guards
make each table a no-op where it already exists (from an earlier create_all).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_rpg_traits_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = ("ext_rpg_traits",)
# No depends_on: each extension has its own Alembic history (EXT_RPGTraits.py orders it).
depends_on: Union[str, Sequence[str], None] = None

TABLE_INFO = {"extension": "rpg_traits"}


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
    if not _has_table("traits"):
        op.create_table(
            "traits",
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("game_system_id", sa.String(), sa.ForeignKey("game_systems.id"), nullable=True, comment="Optional foreign key to GameSystemModel"),
            sa.Column("campaign_id", sa.String(), sa.ForeignKey("campaigns.id"), nullable=True, comment="Optional foreign key to CampaignModel"),
            sa.Column("kind", sa.String(), nullable=True),
            sa.Column("default_duration_seconds", sa.Integer(), nullable=True),
            *_audit_columns(),
            sa.PrimaryKeyConstraint("id"),
            comment="Unified property catalog: stats, skills, spells, resources, progression and status effects",
            info=TABLE_INFO,
        )
        op.create_index("ix_traits_deleted_at", "traits", ["deleted_at"])
    if not _has_table("derivative_traits"):
        op.create_table(
            "derivative_traits",
            sa.Column("source_trait_id", sa.String(), nullable=True),
            sa.Column("source_item_id", sa.String(), nullable=True),
            sa.Column("target_trait_id", sa.String(), nullable=True),
            sa.Column("operation", sa.String(), nullable=True),
            sa.Column("value", sa.Float(), nullable=True),
            sa.Column("order_index", sa.Integer(), nullable=True),
            sa.Column("stacking_group", sa.String(), nullable=True),
            sa.Column("qualifier", sa.String(), nullable=True),
            *_audit_columns(),
            sa.PrimaryKeyConstraint("id"),
            comment="How a trait or an item contributes to another trait",
            info=TABLE_INFO,
        )
        op.create_index("ix_derivative_traits_deleted_at", "derivative_traits", ["deleted_at"])
    if not _has_table("person_traits"):
        op.create_table(
            "person_traits",
            sa.Column("person_id", sa.String(), sa.ForeignKey("persons.id"), nullable=True, comment="Optional foreign key to PersonModel"),
            sa.Column("trait_id", sa.String(), sa.ForeignKey("traits.id"), nullable=True, comment="Optional foreign key to TraitModel"),
            sa.Column("value", sa.Float(), nullable=True),
            sa.Column("rank", sa.Integer(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
            sa.Column("source_person_id", sa.String(), nullable=True),
            sa.Column("source_item_instance_id", sa.String(), nullable=True),
            sa.Column("target_location_id", sa.String(), nullable=True),
            sa.Column("notes", sa.String(), nullable=True),
            *_audit_columns(),
            sa.PrimaryKeyConstraint("id"),
            comment="A character's value of a trait, or an applied status effect",
            info=TABLE_INFO,
        )
        op.create_index("ix_person_traits_deleted_at", "person_traits", ["deleted_at"])


def downgrade() -> None:
    for table in ("person_traits", "derivative_traits", "traits"):
        op.drop_index(f"ix_{table}_deleted_at", table_name=table)
        op.drop_table(table)
