# SPDX-License-Identifier: AGPL-3.0-or-later
"""A plot hook's state for its campaign's party: the wiki's requirement rule with its character
checks decided here (Requirements.py), against the options the party's characters hold.

The party is the campaign's player characters (persons of kind ``pc``). A character holds an option
when it has a current trait (no expiry, or one still ahead) whose ``kind`` is the check's dimension
and whose ``slug`` is one of its values. The wiki reports such hooks as needs_check and never calls
the VTT; the AI GM and the VTT's own board ask here (the ``check_requirements`` ability).

Who may ask: the campaign's GM, or a player with a character in it. Anyone else gets the same 404 as
a hook that isn't there. Past that the campaign is read as the system, so every trait counts
whoever recorded it.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager
from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignManager  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import PersonTraitManager, TraitManager
from zephyrex.extensions.rpg_traits.Requirements import RequirementError, evaluate
from zephyrex.extensions.world_narrative.BLL_WorldNarrative import HookManager  # type: ignore[import-not-found]
from zephyrex.lib.Environment import env

PLAYER_CHARACTER = "pc"


def _not_found() -> HTTPException:
    return HTTPException(
        status_code=404, detail={"message": "Request searched HookModel and could not find the required record."}
    )


def _current(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return True
    now = datetime.now(timezone.utc) if expires_at.tzinfo else datetime.now(timezone.utc).replace(tzinfo=None)
    return expires_at > now


class PartyChecks:
    """Reads a campaign as the system, once the access rule has passed."""

    def __init__(self, model_registry: Any, requester_id: str) -> None:
        self.model_registry = model_registry
        self.requester_id = str(requester_id)

    def _trusted(self, manager: type[Any]) -> Any:
        return manager(requester_id=env("ROOT_ID"), model_registry=self.model_registry)

    def _get(self, manager: type[Any], record_id: str) -> Any | None:
        try:
            return self._trusted(manager).get(id=record_id)
        except HTTPException:
            return None

    def _held(self, person_id: str, traits: dict[str, Any]) -> dict[str, list[str]]:
        """A character's held options: dimension (trait kind) → slugs."""
        held: dict[str, list[str]] = {}
        for row in self._trusted(PersonTraitManager).list(person_id=person_id):
            if not _current(row.expires_at) or row.trait_id is None:
                continue
            if row.trait_id not in traits:
                traits[row.trait_id] = self._get(TraitManager, row.trait_id)
            trait = traits[row.trait_id]
            if trait is not None and trait.kind and trait.slug:
                held.setdefault(trait.kind, []).append(trait.slug)
        return held

    def check(self, campaign_id: str, hook_id: str) -> dict[str, Any]:
        campaign = self._get(CampaignManager, campaign_id)
        hook = self._get(HookManager, hook_id)
        if campaign is None or hook is None or getattr(hook, "campaign_id", None) != campaign.id:
            raise _not_found()
        characters = [
            person
            for person in self._trusted(PersonManager).list(campaign_id=campaign.id)
            if getattr(person, "kind", None) == PLAYER_CHARACTER
        ]
        gm = self.requester_id == str(campaign.user_id)
        player = any(self.requester_id == str(getattr(person, "user_id", None)) for person in characters)
        if not (gm or player):
            raise _not_found()
        resolved = [row.id for row in self._trusted(HookManager).list(campaign_id=campaign.id) if row.resolved_at]
        traits: dict[str, Any] = {}
        party = [self._held(person.id, traits) for person in characters]
        try:
            requires = json.loads(hook.requires) if hook.requires else None
            outcome = evaluate(requires, resolved, party=party, self_resolved=hook.resolved_at is not None)
        except (RequirementError, ValueError) as error:
            raise HTTPException(status_code=422, detail={"message": f"The hook's requirement can't be read: {error}"}) from error
        return {"hook_id": hook.id, "state": outcome.state, "unmet_checks": outcome.unmet_checks}
