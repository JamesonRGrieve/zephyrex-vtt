# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_combat extension: encounters (BLL_RPGCombat), and the abilities the AI GM runs a fight with:
start one (from a scene's tokens, or named characters), roll initiative, pass the turn, end it, and
read the order. The AI GM acts as the campaign's GM, under the same rules as a human one."""

from typing import Any, ClassVar, Optional

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension, ability
from zephyrex.extensions.rpg_combat.BLL_RPGCombat import CombatantManager, EncounterManager, RollRequest
from zephyrex.extensions.rpg_scene.BLL_RPGScene import SceneManager  # type: ignore[import-not-found]
from zephyrex.lib.Dependencies import Dependencies, EXT_Dependency


class RPGCombatExtension(AbstractStaticExtension):
    name: ClassVar[str] = "rpg_combat"
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = "Encounters: combatants in initiative order, rounds and turns, run by the campaign's GM"
    dependencies: ClassVar[Dependencies] = Dependencies(
        [
            EXT_Dependency(
                name="rpg_core",
                friendly_name="Rpg Core",
                optional=False,
                reason="An encounter belongs to a campaign, whose GM runs it",
            ),
            EXT_Dependency(
                name="rpg_dice",
                friendly_name="Rpg Dice",
                optional=False,
                reason="Initiative is rolled under the campaign's rules pack",
            ),
            EXT_Dependency(
                name="rpg_scene",
                friendly_name="Rpg Scene",
                optional=False,
                reason="An encounter may be fought on a scene, its combatants the scene's tokens",
            ),
            EXT_Dependency(
                name="genealogy",
                friendly_name="Genealogy",
                optional=False,
                reason="A combatant is one of genealogy's persons",
            ),
        ]
    )

    @classmethod
    def encounters(cls, requester_id: str) -> EncounterManager:
        manager: EncounterManager = cls.as_requester(EncounterManager, requester_id)
        return manager

    @classmethod
    @ability("start_encounter")
    async def start_encounter(
        cls,
        requester_id: str,
        campaign_id: str,
        scene_id: Optional[str] = None,
        person_ids: Optional[list[str]] = None,
        name: Optional[str] = None,
        hidden_person_ids: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Start a fight in a campaign: its combatants are ``person_ids`` (characters of the campaign),
        or else every character with a token on ``scene_id`` (hidden tokens stay hidden combatants).
        Initiative is rolled under the campaign's pack and round 1 begins; a combatant with no stats
        to roll is listed in ``unrolled`` and the fight waits in setup until the GM sets theirs.
        The campaign's GM only. Returns the encounter in initiative order."""
        encounters = cls.encounters(requester_id)
        combatants = cls.as_requester(CombatantManager, requester_id)
        encounter = encounters.create(campaign_id=campaign_id, scene_id=scene_id, name=name or "Encounter")
        hidden = set(hidden_person_ids or [])
        if person_ids:
            for person_id in person_ids:
                combatants.create(encounter_id=encounter.id, person_id=person_id, is_hidden=person_id in hidden)
        elif scene_id is not None:
            for token in cls.as_requester(SceneManager, requester_id).tokens_for(scene_id):
                if token.entity_id:
                    combatants.create(
                        encounter_id=encounter.id,
                        person_id=token.entity_id,
                        scene_token_id=token.token_id,
                        is_hidden=token.hidden or token.entity_id in hidden,
                    )
        rolled = encounters.roll_initiative_for(encounter.id, RollRequest())
        if rolled.unrolled or not rolled.combatants:
            return rolled.model_dump()
        return encounters.start_for(encounter.id).model_dump()

    @classmethod
    @ability("roll_initiative")
    async def roll_initiative(cls, requester_id: str, encounter_id: str, reroll: bool = False) -> dict[str, Any]:
        """Roll initiative for an encounter's combatants who have none (everyone with ``reroll``),
        under the campaign's pack. The campaign's GM only. Returns the order, and who couldn't roll."""
        return cls.encounters(requester_id).roll_initiative_for(encounter_id, RollRequest(reroll=reroll)).model_dump()

    @classmethod
    @ability("start_combat")
    async def start_combat(cls, requester_id: str, encounter_id: str) -> dict[str, Any]:
        """Begin an encounter in setup: round 1, the first in initiative order to act."""
        return cls.encounters(requester_id).start_for(encounter_id).model_dump()

    @classmethod
    @ability("next_turn")
    async def next_turn(cls, requester_id: str, encounter_id: str) -> dict[str, Any]:
        """Pass the turn to the next combatant still fighting; after the last, a new round begins.
        Returns the order with ``current_combatant_id`` and ``round``."""
        return cls.encounters(requester_id).next_turn_for(encounter_id).model_dump()

    @classmethod
    @ability("end_encounter")
    async def end_encounter(cls, requester_id: str, encounter_id: str) -> dict[str, Any]:
        """End an encounter. The campaign's GM only."""
        return cls.encounters(requester_id).end_for(encounter_id).model_dump()

    @classmethod
    @ability("encounter_order")
    async def encounter_order(cls, requester_id: str, encounter_id: str) -> dict[str, Any]:
        """An encounter in initiative order: round, whose turn it is, each combatant's initiative and
        whether they're defeated (hidden ones for the GM only)."""
        return cls.encounters(requester_id).order_for(encounter_id).model_dump()

    @classmethod
    @ability("current_encounter")
    async def current_encounter(cls, requester_id: str, campaign_id: str) -> Optional[dict[str, Any]]:
        """A campaign's fight in progress in initiative order, or None."""
        found = cls.encounters(requester_id).current_for(campaign_id)
        return None if found is None else found.model_dump()
