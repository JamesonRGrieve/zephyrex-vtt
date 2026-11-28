# SPDX-License-Identifier: AGPL-3.0-or-later
"""The VTT's rows go with the wiki records they belong to (Zephyrex RPG Wiki, 2026-11-28: deleted
playthroughs left 330 person_traits, 45 scene_tokens and 8 scenes live on prod).

One rule for every VTT table, read from the tables themselves rather than listed by hand: a row
belongs to the campaign or the person its ``campaign_id`` or ``person_id`` names, and goes when that
record goes; a row that references a VTT row going (a scene's tokens, walls and spots, an
encounter's combatants, a removed trait's values) goes with it, until nothing more follows. Rows are
soft-deleted (``deleted_at``), as the wiki removes its own.

- ``remove_for`` is the wiki's remove hook (rpg_core ``register_remove_hook``): it runs before a
  campaign's records are removed, with their ids.
- ``sweep_orphans`` finds the rows already left behind: those whose campaign or person no live read
  finds. Run with ``dry_run`` first; on prod, the operator runs it."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import sqlalchemy as sa

# The wiki records a VTT row belongs to, by the column naming it.
OWNERS = {"campaign_id": "campaigns", "person_id": "persons"}
# The VTT's own extensions: this repository's extension folders (each has a manifest).
VTT_EXTENSIONS = frozenset(path.parent.name for path in Path(__file__).resolve().parent.parent.glob("*/manifest.toml"))


def _metadata(model_registry: Any) -> sa.MetaData:
    from zephyrex.extensions.rpg_systems.BLL_RPGSystems import GameSystemManager  # type: ignore[import-not-found]
    from zephyrex.lib.Environment import env

    return GameSystemManager(requester_id=env("ROOT_ID"), model_registry=model_registry).DB.__table__.metadata


def vtt_tables(metadata: sa.MetaData) -> list[sa.Table]:
    """The VTT's soft-deletable tables, by name."""
    return sorted(
        (table for table in metadata.tables.values() if (table.info or {}).get("extension") in VTT_EXTENSIONS and "deleted_at" in table.c and "id" in table.c),
        key=lambda table: table.name,
    )


def _references(table: sa.Table) -> list[tuple[sa.Column, str]]:
    """Each foreign-key column of a table and the table it points at."""
    return [(column, key.column.table.name) for column in table.c for key in column.foreign_keys]


def _chunks(values: Iterable[str], size: int = 500) -> Iterable[list[str]]:
    values = list(values)
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _going(session: Any, tables: list[sa.Table], gone: dict[str, set[str]]) -> dict[str, set[str]]:
    """The live VTT rows that go, by table: those owned by a record in ``gone`` (wiki table → ids),
    then those referencing a VTT row that goes, until nothing more follows."""
    going: dict[str, set[str]] = {table.name: set() for table in tables}
    vtt = {table.name for table in tables}

    def mark(table: sa.Table, column: sa.Column, ids: set[str]) -> bool:
        grew = False
        for chunk in _chunks(sorted(ids)):
            rows = session.execute(sa.select(table.c.id).where(table.c.deleted_at.is_(None), column.in_(chunk))).scalars()
            for row in rows:
                if str(row) not in going[table.name]:
                    going[table.name].add(str(row))
                    grew = True
        return grew

    for table in tables:
        for column, target in _references(table):
            if column.name in OWNERS and OWNERS[column.name] == target and gone.get(target):
                mark(table, column, gone[target])
    grew = True
    while grew:
        grew = False
        for table in tables:
            for column, target in _references(table):
                if target in vtt and going.get(target):
                    grew = mark(table, column, going[target]) or grew
    return {name: ids for name, ids in going.items() if ids}


def _soft_delete(session: Any, tables: list[sa.Table], going: dict[str, set[str]], requester_id: str) -> None:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for table in tables:
        ids = going.get(table.name)
        if not ids:
            continue
        values: dict[str, Any] = {"deleted_at": now}
        if "deleted_by_user_id" in table.c:
            values["deleted_by_user_id"] = str(requester_id)
        for chunk in _chunks(sorted(ids)):
            session.execute(table.update().where(table.c.id.in_(chunk), table.c.deleted_at.is_(None)).values(**values))


def _invalidate(names: Iterable[str]) -> None:
    """The entity cache forgets the tables written behind the managers' backs."""
    from zephyrex.logic.AbstractLogicManager.manager import _cache_sync_run, get_entity_cache

    cache = get_entity_cache()
    if cache is None:
        return
    for name in names:
        _cache_sync_run(cache.invalidate_table(name))


def _apply(model_registry: Any, requester_id: str, gone: dict[str, set[str]], dry_run: bool) -> dict[str, int]:
    tables = vtt_tables(_metadata(model_registry))
    session = model_registry.DB.session()
    try:
        going = _going(session, tables, gone)
        if not dry_run and going:
            _soft_delete(session, tables, going, requester_id)
            session.commit()
    finally:
        session.close()
    if not dry_run:
        _invalidate(going)
    return {f"vtt.{name}": len(ids) for name, ids in sorted(going.items())}


def remove_for(model_registry: Any, requester_id: str, campaign_ids: list[str], record_ids: list[str], dry_run: bool = False) -> dict[str, int]:
    """The wiki's remove hook: the VTT rows of the campaigns going and of their records (people
    among them), soft-deleted before the wiki's own; {"vtt.<table>": count}. The ids are matched by
    the column's own table (a campaign_id against the campaigns, a person_id against every id
    given, which holds the campaigns' people)."""
    records = {str(one) for one in record_ids or []}
    gone = {"campaigns": {str(one) for one in campaign_ids or []} | records, "persons": records}
    return _apply(model_registry, requester_id, gone, dry_run)


def sweep_orphans(model_registry: Any, requester_id: str, dry_run: bool = True) -> dict[str, int]:
    """The VTT rows whose campaign or person is gone (deleted, or never there), and what references
    them; soft-deleted unless ``dry_run``. {"vtt.<table>": count}."""
    metadata = _metadata(model_registry)
    tables = vtt_tables(metadata)
    gone: dict[str, set[str]] = {}
    session = model_registry.DB.session()
    try:
        for owner_table in set(OWNERS.values()):
            target = metadata.tables.get(owner_table)
            if target is None:
                continue
            live = sa.select(target.c.id).where(target.c.deleted_at.is_(None)) if "deleted_at" in target.c else sa.select(target.c.id)
            for table in tables:
                for column, pointed in _references(table):
                    if pointed != owner_table or OWNERS.get(column.name) != owner_table:
                        continue
                    rows = session.execute(
                        sa.select(column).where(table.c.deleted_at.is_(None), column.is_not(None), column.not_in(live)).distinct()
                    ).scalars()
                    gone.setdefault(owner_table, set()).update(str(one) for one in rows)
    finally:
        session.close()
    return _apply(model_registry, requester_id, gone, dry_run)


def register_remove(model_registry: Any) -> bool:
    """remove_for registered with the wiki's register_remove_hook; False on a wiki without it."""
    from zephyrex.extensions.AbstractExtensionProvider import loaded_ability
    from zephyrex.lib.Environment import env

    register = loaded_ability(model_registry, "rpg_core", "register_remove_hook")
    if register is None:
        return False
    answer = register(model_registry, str(env("ROOT_ID")), remove_for)
    if hasattr(answer, "__await__"):
        from zephyrex.logic.AbstractLogicManager.manager import _cache_sync_run

        _cache_sync_run(answer)
    return True
