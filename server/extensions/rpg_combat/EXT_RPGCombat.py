# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_combat extension: encounters (BLL_RPGCombat), and the abilities the AI GM runs a fight with:
start one (from a scene's tokens, or named characters), roll initiative, pass the turn, end it, and
read the order. The AI GM acts as the campaign's GM, under the same rules as a human one."""

from typing import Any, ClassVar, Optional

from fastapi import HTTPException

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension, ability, backend_selector, loaded_ability
from zephyrex.extensions.rpg_combat.BLL_RPGCombat import (
    CombatActionRequest,
    CombatOptionsRequest,
    CombatantManager,
    EncounterManager,
    RollRequest,
)
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
    @backend_selector
    async def backend_for(cls, ability_name: str, arguments: dict[str, Any]) -> Optional[str]:
        """Which backend serves this call (the operator's framework selector, sf 72f51160): the
        campaign's, as the wiki says (by campaign_id, an encounter's campaign or a person's), for a campaign kept in an external tabletop; None (this
        extension's own) for a native campaign, an unknown one, or a wiki with no campaign_backend.
        Only keyword arguments reach a selector, so a positional campaign stays native."""
        from zephyrex.lib.Environment import env
        from zephyrex.pydantic2.registry import ModelRegistry

        # An fvtt: id is always Foundry's (the wiki's rule): no lookup.
        if any(str(arguments.get(key) or "").startswith("fvtt:") for key in ("campaign_id", "scene_id", "encounter_id", "person_id")):
            return "foundry"
        registry = ModelRegistry.attached()
        ask = None if registry is None else loaded_ability(registry, "rpg_core", "campaign_backend")
        if ask is None:
            return None
        campaign_id = arguments.get("campaign_id")
        if not campaign_id and arguments.get("encounter_id"):
            encounter = EncounterManager(requester_id=str(env("ROOT_ID")), model_registry=registry)._find(EncounterManager, str(arguments["encounter_id"]))
            campaign_id = None if encounter is None else encounter.campaign_id
        person_id = arguments.get("person_id")
        if not campaign_id and not person_id:
            return None
        answer = ask(registry, str(env("SYSTEM_ID")), campaign_id=campaign_id, person_id=person_id)
        if hasattr(answer, "__await__"):
            answer = await answer
        backend = (answer or {}).get("backend")
        return None if backend in (None, "", "native") else str(backend)

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
        dispositions: Optional[dict[str, dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        """Start a fight in a campaign: its combatants are ``person_ids`` (characters of the campaign),
        or else every character with a token on ``scene_id`` (hidden tokens stay hidden combatants).
        Initiative is rolled under the campaign's pack and round 1 begins; a combatant with no stats
        to roll is listed in ``unrolled`` with why, and acts last until the GM sets theirs.
        Who fights whom comes from each combatant's own dispositions in the wiki toward the others
        (toward a person, else toward the party): hostile or enraged is hostile, and hostility runs
        both ways; someone with none on record stays neutral, not an enemy for being present, and is
        returned in ``open_choices`` (with the options to choose from). ``dispositions`` overrides
        a person's stance by person id: {disposition: friendly|neutral|hostile, hostile_to: [person
        ids]}. set_disposition changes it mid-fight.
        The campaign's GM only. Returns the encounter in initiative order."""
        given = {person_id: dict(change or {}) for person_id, change in (dispositions or {}).items()}
        wrong = [one.get("disposition") for one in given.values() if one.get("disposition") not in (None, "friendly", "neutral", "hostile")]
        if wrong:
            raise HTTPException(status_code=422, detail={"message": f"A disposition is friendly, neutral or hostile, not {wrong[0]!r}"})
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
        choices = encounters.assign_stances(encounter, given)
        rolled = encounters.roll_initiative_for(encounter.id, RollRequest())
        rolled.open_choices = choices
        if not rolled.combatants:
            return rolled.model_dump()
        # The fight starts even when some couldn't be rolled (no sheet, no rule to roll them by): they
        # act last and are listed, with why, until the GM sets their initiative.
        started = encounters.start_for(encounter.id)
        started.unrolled = rolled.unrolled
        started.open_choices = choices
        return started.model_dump()

    @classmethod
    @ability("combat_options")
    async def combat_options(cls, requester_id: str, encounter_id: str, person_id: str) -> dict[str, Any]:
        """A combatant's legal choices now, for a decision model to pick among: {turn, action_available,
        reaction: {available, trigger}, actions: [{id, kind, name, needs_target, targets, slot_levels,
        summary}], targets: [{person_id, name, hostile, hp}], reach: "unchecked", hp, hp_max}. Its
        weapon attacks come from its sheet and the system pack; distance isn't checked yet. The
        campaign's GM only."""
        body = CombatOptionsRequest(person_id=person_id)
        return cls.encounters(requester_id).combat_options_for(encounter_id, body).model_dump()

    @classmethod
    @ability("take_combat_action")
    async def take_combat_action(
        cls,
        requester_id: str,
        encounter_id: str,
        person_id: str,
        action_id: str,
        target_ids: Optional[list[str]] = None,
        slot_level: Optional[int] = None,
        use_reaction: bool = False,
    ) -> dict[str, Any]:
        """Take one of combat_options' actions, resolved on the server by the pack's rules (an attack:
        d20 + modifier + Proficiency Bonus against AC, a natural 20 a Critical Hit, the damage taken
        from the target's hit points). Anything combat_options doesn't offer now is refused. Returns
        {hit, critical, roll, total, target_ac, damage, damage_roll, target_hp, target_defeated, steps}.
        The campaign's GM only."""
        body = CombatActionRequest(
            person_id=person_id, action_id=action_id, target_ids=target_ids or [], slot_level=slot_level, use_reaction=use_reaction
        )
        return cls.encounters(requester_id).take_combat_action_for(encounter_id, body).model_dump()

    @classmethod
    @ability("set_disposition")
    async def set_disposition(
        cls,
        requester_id: str,
        encounter_id: str,
        person_id: str,
        disposition: Optional[str] = None,
        hostile_to: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Change a combatant's stance mid-fight: its ``disposition`` toward the party (friendly,
        neutral, hostile) and/or whom it is ``hostile_to`` (person ids; [] is a surrender, the party
        a betrayal). Hostility runs both ways, so this moves both directions at once. Returns the
        encounter in initiative order with each combatant's disposition and hostile_to, and any
        open choices left. The campaign's GM only."""
        return cls.encounters(requester_id).set_disposition_for(encounter_id, person_id, disposition, hostile_to).model_dump()

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

    @classmethod
    @ability("rest")
    async def rest(
        cls, requester_id: str, campaign_id: str, person_ids: list[str], kind: str, hit_dice: Optional[int] = None
    ) -> dict[str, Any]:
        """A rest for characters of the campaign, as its rules pack says (srd-5e: ``short`` or
        ``long``). A Short Rest spends Hit Point Dice (each rolled plus the Constitution modifier, at
        least 1) one at a time until the character is whole or its dice, or ``hit_dice`` at most, run
        out; a Long Rest restores all hit points and Hit Point Dice and takes one Exhaustion level
        off. A character below the hit points a rest needs is listed with ``refused``. Refused while
        a fight is running (Initiative interrupts a rest) or when the pack has no rest rules.
        Returns {kind, rested: [{person_id, name, hp_before, hp, hp_max, hit_dice, exhaustion,
        conditions, rolls, refused?}]}. The campaign's GM only."""
        from zephyrex.extensions.rpg_combat.Recovery import recovery_for

        registry = cls.encounters(requester_id).model_registry
        recovery = recovery_for(registry, requester_id, campaign_id)
        strangers = [one for one in person_ids if _campaign_of(registry, one) != str(campaign_id)]
        if strangers:
            raise HTTPException(status_code=422, detail={"message": "Every character resting must be the campaign's"})
        return recovery.rest_all(list(person_ids), kind, hit_dice)

    @classmethod
    @ability("set_condition")
    async def set_condition(cls, requester_id: str, person_id: str, condition: str, present: bool = True) -> dict[str, Any]:
        """Give a character a condition (``present``), or take it off: the pack's conditions (srd-5e:
        Blinded … Unconscious), named in any case. Exhaustion goes up or down one level instead, ends
        at 0, and ``dies`` is true at its last. Returns the character's state: {person_id, condition,
        present, dies, hp, hp_max, hit_dice, exhaustion, conditions}. The campaign's GM only;
        character_sheet shows the state too."""
        from zephyrex.extensions.rpg_combat.Recovery import campaign_of_person, recovery_for

        registry = cls.encounters(requester_id).model_registry
        return recovery_for(registry, requester_id, campaign_of_person(registry, person_id)).set_condition(person_id, condition, present)

    @classmethod
    @ability("use_item")
    async def use_item(cls, requester_id: str, person_id: str, item_instance_id: str, quantity: int = 1) -> dict[str, Any]:
        """A character uses ``quantity`` of an item they carry (items_carried's item_instance_id). A
        consumable the rules pack knows does what it says, once per unit (srd-5e: a Potion of
        Healing heals 2d4+2, up to the maximum, and ends Unconscious), and is spent (the wiki's
        spend_item); another consumable is just spent; anything else is refused (422: narrate it, or
        test it). 409 when they don't carry it. Returns {person_id, item_instance_id, name, used,
        effect: {healing, rolled} | null, spent, left, hp, hp_max, hit_dice, exhaustion,
        conditions}. The campaign's GM only."""
        from zephyrex.extensions.rpg_combat.Recovery import campaign_of_person, recovery_for

        registry = cls.encounters(requester_id).model_registry
        return recovery_for(registry, requester_id, campaign_of_person(registry, person_id)).use_item(person_id, item_instance_id, quantity)


def _campaign_of(registry: Any, person_id: str) -> Optional[str]:
    from zephyrex.extensions.rpg_combat.Recovery import campaign_of_person

    try:
        return campaign_of_person(registry, person_id)
    except HTTPException:
        return None
