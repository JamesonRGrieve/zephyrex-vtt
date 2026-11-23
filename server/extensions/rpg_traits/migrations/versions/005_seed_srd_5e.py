# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_traits 005: the fifth-edition SRD pack's abilities and skills, as trait templates of the srd-5e
game system (rpg_systems' seed). The pack file (rpg_systems/packs/srd-5e.json, generated from the
SRD 5.2's own text) is the source. A character holds an ability score as a PersonTrait value, and a
skill as a PersonTrait rank (1: proficient, 2: Expertise).

Written as the framework's SYSTEM user, so everyone reads them and only ROOT and SYSTEM change them.
A template already there (same system, kind and slug) is left as it is; with no srd-5e
system, it does nothing. The downgrade removes only the templates nobody has changed since.
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence, Union

import sqlalchemy as sa
from alembic import op
from zephyrex.lib.Environment import env

revision: str = "005_rpg_traits_seed_dnd_5e"
down_revision: Union[str, None] = "004_rpg_traits_person_trait_specialisation"
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
    names = {one["slug"]: one["name"] for one in pack["characteristics"]}
    found = [
        {
            "kind": "characteristic",
            "slug": one["slug"],
            "name": one["name"],
            "description": f"{one['name']} ({one['short']}). {source}, {pack['characteristics_cite']}.",
        }
        for one in pack["characteristics"]
    ]
    found += [
        {
            "kind": "skill",
            "slug": one["slug"],
            "name": one["name"],
            "description": (
                f"Governed by {names[one['characteristic']]}"
                + f". {source}, {one['cite']}."
            ),
        }
        for one in pack["skills"]
    ]
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
            traits.c.kind.in_(["characteristic", "skill"]),
            traits.c.updated_at.is_(None),
        )
    )
