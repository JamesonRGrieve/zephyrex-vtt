# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_traits 006: the fifth-edition SRD pack's weapons and resources, as trait templates of the srd-5e
game system, for combat (rpg_combat's combat_options). The pack file (rpg_systems/packs/srd-5e.json,
generated from the SRD 5.2's own text and the open fifth-edition system's equipment) is the source.
A character wields a weapon as a PersonTrait row of a weapon template, and holds its Hit Points and
Armor Class as PersonTrait values of the resource templates.

Written as the framework's SYSTEM user, as 005 is. A template already there (same system, kind and
slug) is left as it is; with no srd-5e system, it does nothing. The downgrade removes only the
templates nobody has changed since.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op
from zephyrex.lib.Environment import env

revision: str = "006_rpg_traits_seed_srd_5e_combat"
down_revision: Union[str, None] = "005_rpg_traits_seed_dnd_5e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PACK_FILE = Path(__file__).resolve().parents[3] / "rpg_systems" / "packs" / "srd-5e.json"

game_systems = sa.table("game_systems", sa.column("id", sa.String), sa.column("slug", sa.String))
traits = sa.table(
    "traits",
    sa.column("id", sa.String),
    sa.column("name", sa.String),
    sa.column("description", sa.String),
    sa.column("kind", sa.String),
    sa.column("slug", sa.String),
    sa.column("game_system_id", sa.String),
    sa.column("campaign_id", sa.String),
    sa.column("created_by_user_id", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)


def _templates(pack: dict[str, Any]) -> list[dict[str, str]]:
    source = pack["source"]
    found = []
    for one in pack.get("weapons") or []:
        reach = "melee" if one["melee"] else "ranged"
        detail = ", ".join([f"{one['damage']} {one['damage_type'] or ''}".strip(), *one["properties"]])
        found.append(
            {
                "kind": "weapon",
                "slug": one["slug"],
                "name": one["name"],
                "description": f"A {one['category']} {reach} weapon: {detail}. {source}, Equipment › Weapons.",
            }
        )
    for one in pack.get("resources") or []:
        found.append({"kind": "resource", "slug": one["slug"], "name": one["name"], "description": f"{source}, {one['cite']}."})
    return found


def _system_id() -> str | None:
    pack = json.loads(PACK_FILE.read_text())
    row = op.get_bind().execute(sa.select(game_systems.c.id).where(game_systems.c.slug == pack["system"])).first()
    return None if row is None else str(row[0])


def upgrade() -> None:
    system_id = _system_id()
    if system_id is None:
        return
    bind = op.get_bind()
    present = {
        (row[0], row[1])
        for row in bind.execute(sa.select(traits.c.kind, traits.c.slug).where(traits.c.game_system_id == system_id))
    }
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [
        {
            "id": str(uuid.uuid4()),
            **one,
            "game_system_id": system_id,
            "campaign_id": None,
            "created_by_user_id": env("SYSTEM_ID"),
            "created_at": now,
        }
        for one in _templates(json.loads(PACK_FILE.read_text()))
        if (one["kind"], one["slug"]) not in present
    ]
    if rows:
        op.bulk_insert(traits, rows)


def downgrade() -> None:
    system_id = _system_id()
    if system_id is None:
        return
    op.execute(
        traits.delete().where(
            traits.c.game_system_id == system_id,
            traits.c.kind.in_(["weapon", "resource"]),
            traits.c.updated_at.is_(None),
        )
    )
