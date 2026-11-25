# SPDX-License-Identifier: AGPL-3.0-or-later
"""The traits and sheets of a setting made system level (operator, 2026-11-25: "The out of the box
scenarios, pregens, everything with the SRD should also be system level down to campaigns which
are user level"): rpg_traits' hook for the wiki's system_adopt (wiki ed56c11), called with
(model_registry, setting_id, scenario_ids, id_map, dry_run) after the wiki's own rows are SYSTEM's.

- the scenarios' own trait definitions (a campaign's traits) are made SYSTEM's;
- every live sheet row (person_trait) of a person of those scenarios, or of the setting's canon (a
  setting pregen: no campaign), is made SYSTEM's, so every account reads the pregens' sheets; a
  start still copies them as the player's own;
- a merged duplicate's (id_map: its ids → the system copy's): its traits move onto the system
  scenario unless it has one of the same kind and slug (then the duplicate's is removed and its
  sheet rows point at the system one); its people's sheet rows move to the system person unless
  that person already has a sheet (then they're removed).

The wiki turns references only in its own tables; these are VTT's. A dry run counts and writes
nothing. Returned lines go into the wiki's report.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_, func, or_, select


def _table(model_registry: Any, manager: Any) -> Any:
    from zephyrex.lib.Environment import env

    return manager(requester_id=env("ROOT_ID"), model_registry=model_registry).DB.__table__


def adopt_traits(model_registry: Any, setting_id: str, scenario_ids: list[str], id_map: dict[str, str], dry_run: bool) -> list[str]:
    from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager
    from zephyrex.extensions.rpg_traits.BLL_RPGTraits import PersonTraitManager, TraitManager
    from zephyrex.lib.Environment import env

    system = str(env("SYSTEM_ID"))
    targets = {str(one) for one in scenario_ids}
    mapped = {str(key): str(value) for key, value in (id_map or {}).items()}
    sources = sorted(targets | {key for key, value in mapped.items() if value in targets})
    traits = _table(model_registry, TraitManager)
    sheets = _table(model_registry, PersonTraitManager)
    persons = _table(model_registry, PersonManager)
    counts = {"traits": 0, "sheet rows": 0, "removed traits": 0, "removed sheet rows": 0}
    session = model_registry.DB.session()
    try:
        # The scenarios' own trait definitions; a duplicate's matched by (kind, slug).
        trait_map: dict[str, str] = {}
        if sources:
            found = session.execute(select(traits).where(traits.c.campaign_id.in_(sources) & traits.c.deleted_at.is_(None))).mappings().all()
            held = {(str(row["campaign_id"]), row["kind"], row["slug"]): str(row["id"]) for row in found if str(row["campaign_id"]) in targets}
            for row in found:
                campaign = str(row["campaign_id"])
                target = mapped.get(campaign, campaign)
                key = (target, row["kind"], row["slug"])
                if target != campaign and key in held:
                    trait_map[str(row["id"])] = held[key]
                    counts["removed traits"] += 1
                    if not dry_run:
                        session.execute(traits.update().where(traits.c.id == row["id"]).values(deleted_at=func.now()))
                    continue
                held[key] = str(row["id"])
                counts["traits"] += 1
                if not dry_run:
                    session.execute(traits.update().where(traits.c.id == row["id"]).values(created_by_user_id=system, campaign_id=target))

        # Whose sheets: the scenarios' people and the setting's canon people (its pregens), and a
        # merged duplicate's people (id_map keys; the wiki has removed them, their sheets remain).
        live = persons.c.deleted_at.is_(None)
        people_of = [persons.c.campaign_id.in_(sources)] if sources else []
        if "setting_id" in persons.c:
            people_of.append(and_(persons.c.setting_id == str(setting_id), persons.c.campaign_id.is_(None)))
        people = {str(one) for one in session.execute(select(persons.c.id).where(live & or_(*people_of))).scalars()} if people_of else set()
        wanted = sorted(people | set(mapped))
        rows = session.execute(select(sheets).where(sheets.c.person_id.in_(wanted) & sheets.c.deleted_at.is_(None))).mappings().all() if wanted else []
        has_sheet = {str(row["person_id"]) for row in rows if str(row["person_id"]) in people and str(row["person_id"]) not in mapped}
        for row in rows:
            person = str(row["person_id"])
            target = mapped.get(person, person)
            if target != person and target in has_sheet:
                counts["removed sheet rows"] += 1
                if not dry_run:
                    session.execute(sheets.update().where(sheets.c.id == row["id"]).values(deleted_at=func.now()))
                continue
            counts["sheet rows"] += 1
            if not dry_run:
                values: dict[str, Any] = {"created_by_user_id": system, "person_id": target}
                if row["trait_id"] is not None and str(row["trait_id"]) in trait_map:
                    values["trait_id"] = trait_map[str(row["trait_id"])]
                session.execute(sheets.update().where(sheets.c.id == row["id"]).values(**values))
        # A sheet row still pointing at a removed duplicate trait (someone else's person) follows it.
        if trait_map and not dry_run:
            for old, new in trait_map.items():
                session.execute(sheets.update().where(sheets.c.trait_id == old).values(trait_id=new))
        if not dry_run:
            session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
    if not dry_run:
        _clear_cache({traits.name, sheets.name})
    said = ", ".join(f"{count} {what}" for what, count in counts.items() if count) or "nothing"
    return [f"rpg_traits: made SYSTEM's{' (dry run)' if dry_run else ''}: {said}"]


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
    """adopt_traits registered with the wiki's register_adopt_hook (wiki ed56c11+); False on an
    older wiki, which has no system_adopt to call it."""
    from zephyrex.extensions.AbstractExtensionProvider import loaded_ability
    from zephyrex.lib.Environment import env

    register = loaded_ability(model_registry, "rpg_core", "register_adopt_hook")
    if register is None:
        return False
    register(model_registry, str(env("ROOT_ID")), adopt_traits)
    return True
