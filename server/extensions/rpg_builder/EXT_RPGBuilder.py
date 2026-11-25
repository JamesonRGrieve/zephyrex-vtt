# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_builder extension: character creation by the rules as written (BLL_RPGBuilder), as routes and
as abilities an agent calls: read a character's options, roll their ability scores, set them."""

from typing import Any, ClassVar, Optional

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension, ability, backend_selector, loaded_ability
from zephyrex.extensions.rpg_builder.BLL_RPGBuilder import (
    ApplyRequest,
    BuilderManager,
    ChooseRequest,
    LevelsRequest,
    NpcOptionsRequest,
    NpcSheetRequest,
    PregenRequest,
    PregensRequest,
    RollRequest,
)
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
    @backend_selector
    async def backend_for(cls, ability_name: str, arguments: dict[str, Any]) -> Optional[str]:
        """Which backend serves this call (the operator's framework selector, sf 72f51160): the
        campaign's, as the wiki says (by campaign_id or a person's), for a campaign kept in an external tabletop; None (this
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
        person_id = arguments.get("person_id")
        if not campaign_id and not person_id:
            return None
        answer = ask(registry, str(env("SYSTEM_ID")), campaign_id=campaign_id, person_id=person_id)
        if hasattr(answer, "__await__"):
            answer = await answer
        backend = (answer or {}).get("backend")
        return None if backend in (None, "", "native") else str(backend)

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
    @ability("starting_levels")
    async def starting_levels(cls, requester_id: str, campaign_id: str) -> dict[str, Any]:
        """The levels a campaign's characters can start at, for a slider: {campaign_id, system,
        max_level, starting_level_max, starting_level}. max_level is the pack's (20 for srd-5e; 1 with
        no pack); starting_level_max is the campaign's own cap within it (``starting_level_max``, a
        one-shot's 4), else max_level, and starting_level stays within it. Set the level through the
        campaign's ``starting_level``. The campaign's GM only."""
        return cls.builder(requester_id).levels_for(LevelsRequest(campaign_id=campaign_id)).model_dump()

    @classmethod
    @ability("build_campaign_pregens")
    async def build_campaign_pregens(cls, requester_id: str, campaign_id: str, level: Optional[int] = None) -> dict[str, Any]:
        """Build a campaign's (a scenario's) pregens to its starting level, as a starting-level slider
        commits: ``level`` sets the campaign's starting level first (within the pack's maximum), then
        every player character with a builder line is built or re-levelled to it. Returns
        {campaign_id, starting_level, results: [build_pregen's report each], skipped: [{person_id,
        name, reason}]}; each result's gaps are its open choices. The campaign's GM only."""
        return cls.builder(requester_id).campaign_pregens_for(PregensRequest(campaign_id=campaign_id, level=level)).model_dump()

    @classmethod
    @ability("build_pregen")
    async def build_pregen(
        cls, requester_id: str, person_id: str, replace: bool = False, dry_run: bool = False, level: Optional[int] = None
    ) -> dict[str, Any]:
        """Give a pregen its starting sheet by the SRD's creation rules (a setting's pc with no campaign,
        for its owner; or a campaign's character, a scenario's pregen, for the campaign's GM),
        from its own line ("Level 1 Dragonborn Cleric, Acolyte background (SRD 5.2.1)") and the srd5e
        module: its class, background and species, the standard array as the SRD places it for the
        class, the skills and features granted outright. Every choice the rules leave open and its data
        doesn't settle is a gap, reported and not guessed. Returns {pregen: {built, written, abilities,
        saves, skills, features, hp, gaps: [{what, detail}], ...}}. ``dry_run`` writes nothing; a sheet
        already there is refused unless ``replace``. It is built to ``level``, else its campaign's
        ``starting_level``, else 1: each level after the first adds the class's fixed hit points, and
        the features, subclass, ability increases and spells it brings are granted or reported open."""
        body = PregenRequest(person_id=person_id, replace=replace, dry_run=dry_run, level=level)
        return {"pregen": cls.builder(requester_id).build_pregen_for(body).model_dump()}

    @classmethod
    @ability("npc_sheet_options")
    async def npc_sheet_options(cls, requester_id: str, campaign_id: str) -> dict[str, Any]:
        """What the campaign's pack can build an NPC from, for a caller to choose among (a decision
        model picks by each option's summary) and pass to npc_sheet as option_id: {system, options:
        [{id, name, level_or_cr, class, subclass, summary}]}. srd-5e offers the SRD's humanoid stat
        blocks; empty when the pack has nothing to build NPCs from. The campaign's GM only."""
        body = NpcOptionsRequest(campaign_id=campaign_id)
        return cls.builder(requester_id).npc_options_for(body).model_dump(by_alias=True)

    @classmethod
    @ability("npc_sheet")
    async def npc_sheet(
        cls, requester_id: str, person_id: str, role: str, hint: str = "", replace: bool = False, option_id: Optional[str] = None
    ) -> dict[str, Any]:
        """Give an NPC a sheet from the closest compendium stat block of the campaign's pack (srd-5e:
        the SRD's humanoids, by ``role`` and the ``hint`` line about them), or the pack's generic
        block (the Commoner): its ability scores and skill proficiencies become the NPC's, nothing
        invented. Returns {sheet: {person_id, system, source: compendium | template, entry_name,
        has_sheet, hp, ac, cr}, sheet_id, source_name}; a 422 when the pack has no blocks. ``option_id``
        (one of npc_sheet_options' ids) builds from that option instead of the closest. The GM only."""
        body = NpcSheetRequest(person_id=person_id, role=role, hint=hint, replace=replace, option_id=option_id)
        return cls.builder(requester_id).npc_sheet_for(body).model_dump()

    @classmethod
    @ability("sheet_for_npc")
    async def sheet_for_npc(
        cls, requester_id: str, person_id: str, role: str, campaign_id: Optional[str] = None, hint: str = ""
    ) -> dict[str, Any]:
        """The same as npc_sheet, with the campaign checked against the person's."""
        body = NpcSheetRequest(person_id=person_id, role=role, hint=hint, campaign_id=campaign_id)
        return cls.builder(requester_id).npc_sheet_for(body).model_dump()
