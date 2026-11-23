# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_builder extension: character creation by the rules as written (BLL_RPGBuilder), as routes and
as abilities an agent calls: read a character's options, roll their ability scores, set them."""

from typing import Any, ClassVar, Optional

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension, ability
from zephyrex.extensions.rpg_builder.BLL_RPGBuilder import ApplyRequest, BuilderManager, ChooseRequest, NpcSheetRequest, RollRequest
from zephyrex.lib.Dependencies import Dependencies, EXT_Dependency


class RPGBuilderExtension(AbstractStaticExtension):
    name: ClassVar[str] = "rpg_builder"
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = "Character creation by the rules as written: ability scores by the pack's own methods"
    dependencies: ClassVar[Dependencies] = Dependencies(
        [
            EXT_Dependency(
                name="rpg_dice",
                friendly_name="Rpg Dice",
                optional=False,
                reason="The pack, the character's access rule and their stats come from rpg_dice",
            ),
            EXT_Dependency(
                name="rpg_traits",
                friendly_name="Rpg Traits",
                optional=False,
                reason="Scores are written as the character's trait values",
            ),
            EXT_Dependency(
                name="genealogy",
                friendly_name="Genealogy",
                optional=False,
                reason="A roll belongs to one of genealogy's persons",
            ),
        ]
    )

    @classmethod
    def builder(cls, requester_id: str) -> BuilderManager:
        manager: BuilderManager = cls.as_requester(BuilderManager, requester_id)
        return manager

    @classmethod
    @ability("builder_options")
    async def builder_options(cls, requester_id: str, person_id: str) -> dict[str, Any]:
        """A character's ability score methods under the campaign's pack (the 5e SRD: standard array,
        point buy with its costs and pool, 4d6 keep 3 six times), their current scores, any kept
        roll, and whether the requester may set them now."""
        return cls.builder(requester_id).options_for(person_id).model_dump()

    @classmethod
    @ability("roll_abilities")
    async def roll_abilities(cls, requester_id: str, person_id: str, again: bool = False) -> dict[str, Any]:
        """Roll a character's ability scores by the pack's random generation, on the server, and keep
        the roll (one per character for a player; ``again`` lets the GM roll a new set)."""
        return cls.builder(requester_id).roll_for(RollRequest(person_id=person_id, again=again)).model_dump()

    @classmethod
    @ability("set_abilities")
    async def set_abilities(cls, requester_id: str, person_id: str, method: str, scores: dict[str, int]) -> dict[str, Any]:
        """Set a character's ability scores by ``method`` (standard_array, point_buy, or roll: their
        kept roll), one score per ability slug, checked against the method's rule."""
        body = ApplyRequest(person_id=person_id, method=method, scores=scores)  # type: ignore[arg-type]
        return cls.builder(requester_id).apply_for(body).model_dump()

    @classmethod
    @ability("builder_choices")
    async def builder_choices(cls, requester_id: str, person_id: str) -> dict[str, Any]:
        """A character's creation steps under the pack (the 5e SRD: class; origin's background and
        species; ability scores…), each choice's options and what the character has chosen."""
        return cls.builder(requester_id).choices_for(person_id).model_dump()

    @classmethod
    @ability("choose")
    async def choose(cls, requester_id: str, person_id: str, kind: str, trait_id: str) -> dict[str, Any]:
        """Record a creation choice: ``kind`` one the steps name (class, background, species) and
        ``trait_id`` one of its options. A player chooses once; the GM may change it."""
        return cls.builder(requester_id).choose_for(ChooseRequest(person_id=person_id, kind=kind, trait_id=trait_id)).model_dump()

    @classmethod
    @ability("npc_sheet")
    async def npc_sheet(
        cls, requester_id: str, person_id: str, role: str, hint: str = "", replace: bool = False
    ) -> dict[str, Any]:
        """Give an NPC a sheet from the closest compendium stat block of the campaign's pack (srd-5e:
        the SRD's humanoids, by ``role`` and the ``hint`` line about them), or the pack's generic
        block (the Commoner): its ability scores and skill proficiencies become the NPC's, nothing
        invented. Returns {sheet: {person_id, system, source: compendium | template, entry_name,
        has_sheet, hp, ac, cr}, sheet_id, source_name}; a 422 when the pack has no blocks. The GM only."""
        body = NpcSheetRequest(person_id=person_id, role=role, hint=hint, replace=replace)
        return cls.builder(requester_id).npc_sheet_for(body).model_dump()

    @classmethod
    @ability("sheet_for_npc")
    async def sheet_for_npc(
        cls, requester_id: str, person_id: str, role: str, campaign_id: Optional[str] = None, hint: str = ""
    ) -> dict[str, Any]:
        """The same as npc_sheet, with the campaign checked against the person's."""
        body = NpcSheetRequest(person_id=person_id, role=role, hint=hint, campaign_id=campaign_id)
        return cls.builder(requester_id).npc_sheet_for(body).model_dump()
