# SPDX-License-Identifier: AGPL-3.0-or-later
"""A campaign's spells, by name, for the AI GM to say what a spell does when it's cast (the operator,
2026-11-26: "Just pull the spell details and highlight in the question 'x casts y (spell effects) on
z'"). The spell traits of the campaign's own game system only: names collide across systems (Sacred
Flame is a 5e spell and a 40k talent). Its own spells (campaign_id set) over the system's templates
of the same slug."""

from typing import Any

from fastapi import HTTPException
from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager
from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignManager  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import TraitManager
from zephyrex.lib.Environment import env


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404, detail={"message": "Request searched CampaignModel and could not find the required record."}
    )


def _system_id(model_registry: Any, campaign: Any) -> str | None:
    """The campaign's game system, as its dice tray reads it (its own, else its setting's one packed
    system); just its own when rpg_dice isn't loaded."""
    try:
        from zephyrex.extensions.rpg_dice.BLL_RPGDice import DiceManager  # type: ignore[import-not-found]
    except ImportError:
        own = getattr(campaign, "game_system_id", None)
        return None if own is None else str(own)
    return DiceManager(requester_id=env("ROOT_ID"), model_registry=model_registry).system_id_of(campaign)


def _may_read(model_registry: Any, requester_id: str, campaign: Any) -> bool:
    """The campaign's GM, one of its players (a character's own, or a seat's controller), anyone for
    the instance's shared copy (TEMPLATE's or SYSTEM's: a scenario's start screen comes before it's
    theirs), and the server's own accounts."""
    requester = str(requester_id)
    if requester in {str(env("ROOT_ID")), str(env("SYSTEM_ID"))}:
        return True
    owners = {str(owner) for owner in (campaign.user_id, getattr(campaign, "created_by_user_id", None)) if owner}
    if requester in owners or owners & {str(env("TEMPLATE_ID")), str(env("SYSTEM_ID"))}:
        return True
    people = PersonManager(requester_id=env("ROOT_ID"), model_registry=model_registry)
    characters = [one for one in people.list(campaign_id=campaign.id) if getattr(one, "deleted_at", None) is None]
    if any(requester == str(getattr(one, "user_id", None) or "") for one in characters):
        return True
    try:
        from zephyrex.extensions.rpg_table.BLL_RPGTable import TableSeatManager  # type: ignore[import-not-found]
    except ImportError:
        return False
    seats = TableSeatManager(requester_id=env("ROOT_ID"), model_registry=model_registry)
    ids = {str(one.id) for one in characters}
    return any(
        str(getattr(seat, "person_id", "") or "") in ids and requester == str(getattr(seat, "controller_id", "") or "")
        for seat in seats.list(filters=[seats.DB.deleted_at.is_(None)], controller_id=requester)
    )


def spells_for_campaign(model_registry: Any, requester_id: str, campaign_id: str) -> dict[str, Any]:
    """``{"spells": [{"name", "slug", "description"}]}``, sorted by name, descriptions as stored."""
    try:
        campaign = CampaignManager(requester_id=env("ROOT_ID"), model_registry=model_registry).get(id=campaign_id)
    except HTTPException as error:
        raise _not_found() from error
    if getattr(campaign, "deleted_at", None) is not None or not _may_read(model_registry, requester_id, campaign):
        raise _not_found()
    system_id = _system_id(model_registry, campaign)
    if system_id is None:
        return {"spells": []}
    traits = TraitManager(requester_id=env("ROOT_ID"), model_registry=model_registry)
    live = [traits.DB.deleted_at.is_(None)]
    rows = traits.list(filters=live, game_system_id=system_id, kind="spell")
    chosen: dict[str, Any] = {}
    for row in rows:
        own = getattr(row, "campaign_id", None)
        if own is not None and str(own) != str(campaign.id):
            continue
        key = str(row.slug or row.name or row.id)
        if key not in chosen or (own is not None and getattr(chosen[key], "campaign_id", None) is None):
            chosen[key] = row
    spells = [
        {"name": str(row.name or ""), "slug": row.slug, "description": row.description}
        for row in chosen.values()
    ]
    return {"spells": sorted(spells, key=lambda one: (one["name"].casefold(), str(one["slug"] or "")))}
