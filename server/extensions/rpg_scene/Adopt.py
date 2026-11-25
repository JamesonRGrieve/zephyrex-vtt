# SPDX-License-Identifier: AGPL-3.0-or-later
"""The scenes of a setting made system level (operator, 2026-11-25: "The out of the box scenarios,
pregens, everything with the SRD should also be system level down to campaigns which are user
level"): the wiki's system_adopt (wiki ed56c11) makes its own rows SYSTEM's, then calls each
registered adopt hook with (model_registry, setting_id, scenario_ids, id_map, dry_run). This is
rpg_scene's:

- every live scene of those scenarios, its levels, features, walls, lights, tiles, notes, regions
  and tokens, and the scenarios' scope pins, are made SYSTEM's (every account reads them; a start
  still copies them as the starter's own);
- a merged duplicate's (id_map: its ids → the system copy's): its scenes move onto the system
  scenario with every reference turned (a token's person, a scene's or region's place), unless the
  system scenario already has a scene of the same name, when the duplicate's is removed with its
  parts; a pin whose place the system scenario already pins likewise.

The wiki turns references only in its own tables; these are VTT's. A dry run counts and writes
nothing. Returned lines go into the wiki's report.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

PART_MANAGERS = (
    "SceneLevelManager",
    "SceneFeatureManager",
    "SceneWallManager",
    "SceneLightManager",
    "SceneTileManager",
    "SceneNoteManager",
    "SceneRegionManager",
    "SceneTokenManager",
)
# The columns of VTT's scene rows that name a wiki record (turned through a merge's id map).
REFERENCES = ("campaign_id", "location_id", "person_id")


def _table(model_registry: Any, manager: Any) -> Any:
    from zephyrex.lib.Environment import env

    return manager(requester_id=env("ROOT_ID"), model_registry=model_registry).DB.__table__


def adopt_scenes(model_registry: Any, setting_id: str, scenario_ids: list[str], id_map: dict[str, str], dry_run: bool) -> list[str]:
    from zephyrex.extensions.rpg_scene import BLL_RPGScene as scene_bll
    from zephyrex.lib.Environment import env

    system = str(env("SYSTEM_ID"))
    targets = {str(one) for one in scenario_ids}
    mapped = {str(key): str(value) for key, value in (id_map or {}).items()}
    sources = sorted(targets | {key for key, value in mapped.items() if value in targets})
    if not sources:
        return []
    scenes = _table(model_registry, scene_bll.SceneManager)
    pins = _table(model_registry, scene_bll.ScopePlaceManager)
    parts = [_table(model_registry, getattr(scene_bll, name)) for name in PART_MANAGERS]
    counts = {"scenes": 0, "parts": 0, "pins": 0, "removed scenes": 0, "removed pins": 0}
    session = model_registry.DB.session()
    touched: set[str] = set()
    try:
        live = scenes.c.deleted_at.is_(None)
        found = session.execute(select(scenes).where(scenes.c.campaign_id.in_(sources) & live)).mappings().all()
        names = {
            (str(row["campaign_id"]), row["name"])
            for row in found
            if str(row["campaign_id"]) in targets
        }
        kept: list[str] = []
        dropped: list[str] = []
        for row in found:
            campaign = str(row["campaign_id"])
            target = mapped.get(campaign, campaign)
            if target != campaign and (target, row["name"]) in names:
                dropped.append(str(row["id"]))
                continue
            names.add((target, row["name"]))
            kept.append(str(row["id"]))
            if not dry_run:
                session.execute(scenes.update().where(scenes.c.id == row["id"]).values(**_turned(row, scenes, mapped, system)))
        counts["scenes"] += len(kept)
        counts["removed scenes"] += len(dropped)
        for part in parts:
            for row in session.execute(select(part).where(part.c.scene_id.in_(kept) & part.c.deleted_at.is_(None))).mappings().all() if kept else []:
                counts["parts"] += 1
                if not dry_run:
                    session.execute(part.update().where(part.c.id == row["id"]).values(**_turned(row, part, mapped, system)))
            if dropped and not dry_run:
                session.execute(part.update().where(part.c.scene_id.in_(dropped) & part.c.deleted_at.is_(None)).values(deleted_at=func.now()))
            touched.add(part.name)
        if dropped and not dry_run:
            session.execute(scenes.update().where(scenes.c.id.in_(dropped)).values(deleted_at=func.now()))
        touched.add(scenes.name)

        placed = session.execute(select(pins).where(pins.c.campaign_id.in_(sources) & pins.c.deleted_at.is_(None))).mappings().all()
        pinned = {(str(row["campaign_id"]), str(row["location_id"])) for row in placed if str(row["campaign_id"]) in targets}
        for row in placed:
            campaign = str(row["campaign_id"])
            target = mapped.get(campaign, campaign)
            place = mapped.get(str(row["location_id"]), str(row["location_id"]))
            if target != campaign and (target, place) in pinned:
                counts["removed pins"] += 1
                if not dry_run:
                    session.execute(pins.update().where(pins.c.id == row["id"]).values(deleted_at=func.now()))
                continue
            pinned.add((target, place))
            counts["pins"] += 1
            if not dry_run:
                session.execute(pins.update().where(pins.c.id == row["id"]).values(**_turned(row, pins, mapped, system)))
        touched.add(pins.name)
        if not dry_run:
            session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
    if not dry_run:
        _clear_cache(touched)
    said = ", ".join(f"{count} {what}" for what, count in counts.items() if count) or "nothing"
    return [f"rpg_scene: made SYSTEM's{' (dry run)' if dry_run else ''}: {said}"]


def _turned(row: Any, table: Any, mapped: dict[str, str], system: str) -> dict[str, Any]:
    """A row's new values: SYSTEM as its author, and each wiki reference turned through the map."""
    values: dict[str, Any] = {"created_by_user_id": system}
    for name in REFERENCES:
        if name in table.c and row[name] is not None and str(row[name]) in mapped:
            values[name] = mapped[str(row[name])]
    return values


def _clear_cache(touched: set[str]) -> None:
    try:
        from zephyrex.logic.AbstractLogicManager.manager import _cache_sync_run, get_entity_cache
    except ImportError:
        return
    cache = get_entity_cache()
    if cache is None:
        return
    for table in sorted(touched):
        try:
            _cache_sync_run(cache.invalidate_table(table))
        except Exception:  # noqa: BLE001 - a stale entry expires; the rows are right
            continue


def register_adopt(model_registry: Any) -> bool:
    """adopt_scenes registered with the wiki's register_adopt_hook (wiki ed56c11+); False on an
    older wiki, which has no system_adopt to call it."""
    from zephyrex.extensions.AbstractExtensionProvider import loaded_ability
    from zephyrex.lib.Environment import env

    register = loaded_ability(model_registry, "rpg_core", "register_adopt_hook")
    if register is None:
        return False
    register(model_registry, str(env("ROOT_ID")), adopt_scenes)
    return True
