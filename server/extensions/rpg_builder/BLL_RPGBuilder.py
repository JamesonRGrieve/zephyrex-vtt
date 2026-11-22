# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_builder: character creation by the rules as written, under the campaign's system pack.

Ability scores first (the pack's ``ability_methods``; [redacted]: standard array, point buy, or 4d6
keep the highest three, six times). The server rolls, keeps the roll, and checks the scores applied
against the chosen method, then writes them as the character's ability values. The campaign's GM, or
the character's own player (rpg_dice's access rule). A player sets a character's scores once and
uses one roll per character; the GM may roll again or redo them.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal, Optional, Type

from fastapi import HTTPException
from pydantic import BaseModel as PlainModel
from pydantic import Field
from zephyrex.extensions.genealogy.BLL_Genealogy import PersonModel
from zephyrex.extensions.rpg_builder.Abilities import AbilityError, check_scores
from zephyrex.extensions.rpg_builder.Npcs import pick
from zephyrex.extensions.rpg_dice.BLL_RPGDice import DiceManager, stat_name  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_modules.BLL_RPGModules import CampaignModuleManager, ModuleRecordManager  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import PersonTraitManager, TraitManager  # type: ignore[import-not-found]
from zephyrex.lib.CustomRoute import ExposeIn, custom_route
from zephyrex.lib.Environment import env
from zephyrex.logic.AbstractLogicManager import AbstractBLLManager, ApplicationModel, ModelMeta, UpdateMixinModel
from zephyrex.pydantic2.fastapi import RouterMixin
from zephyrex.pydantic2.fastapi.types import RouteType
from zephyrex.pydantic2.registry import BaseModel  # type: ignore[attr-defined]

Method = Literal["standard_array", "point_buy", "roll"]


class AbilityRollModel(ApplicationModel.Optional, UpdateMixinModel.Optional, PersonModel.Reference.Optional, metaclass=ModelMeta):
    Manager: ClassVar[Type["AbilityRollManager"]] = None
    scores: Optional[list[int]] = Field(None, description="The six totals rolled, in order")
    dice: Optional[list[list[int]]] = Field(None, description="Every die of each roll, kept and dropped")
    is_used: Optional[bool] = Field(False, description="Applied to the character's scores")
    table_comment: ClassVar[str] = "Ability scores the server rolled for a character (character creation)"

    class Create(BaseModel, PersonModel.Reference.ID.Optional):
        scores: Optional[list[int]] = None
        dice: Optional[list[list[int]]] = None

    class Update(BaseModel):
        pass

    class Search(ApplicationModel.Search, PersonModel.Reference.ID.Search):
        pass


class AbilityRollManager(AbstractBLLManager, RouterMixin):
    """Server-written only: no client routes."""

    _model = AbilityRollModel
    routes_to_register: ClassVar[list[RouteType] | None] = []


AbilityRollModel.Manager = AbilityRollManager


class PersonEnvelopeRequest(PlainModel):
    person_id: str


class OptionsEnvelope(PlainModel):
    options: PersonEnvelopeRequest


class RollRequest(PlainModel):
    person_id: str
    again: bool = Field(False, description="Roll a new set (the GM only)")


class RollEnvelope(PlainModel):
    roll: RollRequest


class ApplyRequest(PlainModel):
    person_id: str
    method: Method
    scores: dict[str, int] = Field(description="A score per ability slug")


class ApplyEnvelope(PlainModel):
    abilities: ApplyRequest


class AbilityOut(PlainModel):
    slug: str
    name: str
    short: Optional[str] = None
    score: Optional[float] = None


class RolledOut(PlainModel):
    scores: list[int]
    dice: list[list[int]]
    used: bool


class BuilderOptionsOut(PlainModel):
    person_id: str
    system: str
    gm: bool
    abilities: list[AbilityOut]
    methods: dict[str, Any]
    rolled: Optional[RolledOut]
    can_set: bool = Field(description="Whether the requester may set the scores now")


class BuilderOptionsEnvelope(PlainModel):
    builder: BuilderOptionsOut


class ChoicesEnvelope(PlainModel):
    choices: PersonEnvelopeRequest


class ChooseRequest(PlainModel):
    person_id: str
    kind: str = Field(description="A choice the pack's creation steps name ([redacted]: class, background, species)")
    trait_id: str


class ChooseEnvelope(PlainModel):
    choose: ChooseRequest


class ChoiceOptionOut(PlainModel):
    trait_id: str
    name: str
    description: Optional[str] = None


class ChoiceOut(PlainModel):
    kind: str
    chosen: Optional[ChoiceOptionOut]
    options: list[ChoiceOptionOut]


class StepOut(PlainModel):
    step: int
    name: str
    choices: list[ChoiceOut] = Field(default_factory=list)


class ChoicesOut(PlainModel):
    person_id: str
    system: str
    gm: bool
    steps: list[StepOut]


class ChoicesResultEnvelope(PlainModel):
    builder: ChoicesOut


class NpcSheetRequest(PlainModel):
    person_id: str
    role: str = Field(description="What the NPC is in the story: barkeeper, guard, cult leader…")
    hint: str = Field("", description="A line about them, to help choose (\"a gruff tavern keeper\")")
    campaign_id: Optional[str] = Field(None, description="Checked against the person's campaign when given")
    replace: bool = Field(False, description="Overwrite a sheet the NPC already has")


class NpcSheetEnvelope(PlainModel):
    npc: NpcSheetRequest


class NpcSheetOut(PlainModel):
    person_id: str
    system: str
    source: Literal["compendium", "template"]
    entry_name: str
    entry_uuid: Optional[str] = None
    has_sheet: bool
    hp: Optional[int] = Field(None, description="The block's hit points (the pack has no resource traits yet)")
    ac: Optional[int] = None
    cr: Optional[float] = None


class NpcSheetResultEnvelope(PlainModel):
    sheet: NpcSheetOut
    sheet_id: str = Field(description="The person whose sheet it is")
    source_name: str


def _refuse(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"message": message})


class BuilderManager(AbstractBLLManager[Any], RouterMixin):
    """Character creation's steps; no table of its own."""

    prefix: ClassVar[str | None] = "/v1/builder"
    tags: ClassVar[list[str] | None] = ["Builder"]
    routes_to_register: ClassVar[list[RouteType] | None] = []

    def _trusted(self, manager: type[Any]) -> Any:
        return manager(requester_id=env("ROOT_ID"), model_registry=self.model_registry)

    def _dice(self) -> DiceManager:
        return DiceManager(requester_id=str(self.requester.id), model_registry=self.model_registry)

    def _context(self, person_id: str) -> tuple[Any, Any, bool, dict[str, Any], dict[str, Any]]:
        """The character, campaign, GM flag, pack and its ability methods; a 422 when the pack has none."""
        dice = self._dice()
        person, campaign, gm = dice._character(person_id)
        pack = dice._pack_for(campaign)
        methods = pack.get("ability_methods")
        if methods is None:
            raise _refuse(f"{pack['system']}'s pack has no ability score methods yet")
        return person, campaign, gm, pack, methods

    def _abilities(self, person_id: str, campaign: Any, gm: bool, pack: dict[str, Any]) -> list[tuple[dict[str, Any], Any, Optional[float]]]:
        dice = self._dice()
        found = []
        for one in pack["characteristics"]:
            trait = dice._trait_for(stat_name(one["name"]), campaign, gm)
            values = dice._person_values(person_id, trait.id)
            found.append((one, trait, max(values) if values else None))
        return found

    def _roll_of(self, person_id: str) -> Any | None:
        rolls = self._trusted(AbilityRollManager)
        rows = list(rolls.list(filters=[rolls.DB.deleted_at.is_(None)], person_id=person_id))
        rows.sort(key=lambda row: row.created_at.timestamp() if row.created_at else 0)
        return rows[-1] if rows else None

    def options_for(self, person_id: str) -> BuilderOptionsOut:
        person, campaign, gm, pack, methods = self._context(person_id)
        abilities = self._abilities(person.id, campaign, gm, pack)
        rolled = self._roll_of(person.id)
        return BuilderOptionsOut(
            person_id=person.id,
            system=pack["system"],
            gm=gm,
            abilities=[AbilityOut(slug=one["slug"], name=one["name"], short=one.get("short"), score=score) for one, _, score in abilities],
            methods=methods,
            rolled=None if rolled is None else RolledOut(scores=rolled.scores or [], dice=rolled.dice or [], used=bool(rolled.is_used)),
            can_set=gm or all(score is None for _, _, score in abilities),
        )

    def roll_for(self, body: RollRequest) -> RolledOut:
        """Roll the pack's random generation ([redacted]: 4d6 keep the highest three, six times) and keep
        it. A player gets one roll per character; the GM may roll again."""
        person, _, gm, _, methods = self._context(body.person_id)
        existing = self._roll_of(person.id)
        if existing is not None and not (gm and body.again):
            return RolledOut(scores=existing.scores or [], dice=existing.dice or [], used=bool(existing.is_used))
        spec = methods["roll"]
        dice = self._dice()
        scores, every = [], []
        for _ in range(int(spec["count"])):
            rolled = dice.roll_formula(spec["formula"])
            scores.append(int(rolled.total))
            every.append([int(die.value) for term in rolled.terms for die in (term.dice or [])])
        self._trusted(AbilityRollManager).create(person_id=person.id, scores=scores, dice=every)
        return RolledOut(scores=scores, dice=every, used=False)

    def apply_for(self, body: ApplyRequest) -> BuilderOptionsOut:
        """Set the character's ability scores by a method, checked against it, and write them."""
        person, campaign, gm, pack, methods = self._context(body.person_id)
        abilities = self._abilities(person.id, campaign, gm, pack)
        if not gm and any(score is not None for _, _, score in abilities):
            raise _refuse("These scores are already set; the GM can redo them")
        rolled = self._roll_of(person.id) if body.method == "roll" else None
        if rolled is not None and rolled.is_used and not gm:
            raise _refuse("That roll has been used; the GM can roll again")
        try:
            check_scores(methods, [one["slug"] for one, _, _ in abilities], body.method, body.scores, (rolled.scores or []) if rolled else [])
        except AbilityError as error:
            raise _refuse(str(error)) from error
        # Server-written once the rules and the access rule have passed: the scores are the method's.
        rows = self._trusted(PersonTraitManager)
        for one, trait, _ in abilities:
            value = float(body.scores[one["slug"]])
            live = list(rows.list(filters=[rows.DB.deleted_at.is_(None)], person_id=person.id, trait_id=trait.id))
            if live:
                rows.update_trusted(id=live[0].id, value=value)
            else:
                rows.create(person_id=person.id, trait_id=trait.id, value=value)
        if rolled is not None:
            self._trusted(AbilityRollManager).update_trusted(id=rolled.id, is_used=True)
        return self.options_for(person.id)

    def _live(self, manager: Any, **filters: Any) -> list[Any]:
        """A trusted manager's rows without soft-deleted ones: ROOT reads include tombstones and the
        rows don't carry deleted_at, so the filter goes in the query."""
        return list(manager.list(filters=[manager.DB.deleted_at.is_(None)], **filters))

    def _available(self, campaign: Any, kind: str) -> list[Any]:
        """The traits of a kind a character in this campaign may choose: the campaign's own, then the
        system's (a content module's only while that module is enabled on the campaign)."""
        traits = self._trusted(TraitManager)
        own = self._live(traits, campaign_id=campaign.id, kind=kind)
        enabled = {row.content_module_id for row in self._trusted(CampaignModuleManager).list(campaign_id=campaign.id)}
        records = self._trusted(ModuleRecordManager)
        system = []
        for trait in self._live(traits, game_system_id=self._dice().system_id_of(campaign), kind=kind):
            if trait.campaign_id is not None:
                continue
            modules = {row.content_module_id for row in records.list(entity_type="trait", entity_id=trait.id)}
            if not modules or modules & enabled:
                system.append(trait)
        return sorted(own + system, key=lambda one: (one.name or "").casefold())

    def _chosen(self, person_id: str, kind: str) -> list[tuple[Any, Any]]:
        """The character's live rows of a kind, each with its trait."""
        found = []
        for row in self._live(self._trusted(PersonTraitManager), person_id=person_id):
            trait = self._trusted(TraitManager).get(id=row.trait_id) if row.trait_id else None
            if trait is not None and trait.kind == kind:
                found.append((row, trait))
        return found

    def _steps(self, pack: dict[str, Any]) -> list[dict[str, Any]]:
        creation = pack.get("creation")
        if creation is None:
            raise _refuse(f"{pack['system']}'s pack has no creation steps yet")
        return list(creation["steps"])

    def choices_for(self, person_id: str) -> ChoicesOut:
        """The pack's creation steps with each choice's options and what the character has chosen."""
        dice = self._dice()
        person, campaign, gm = dice._character(person_id)
        pack = dice._pack_for(campaign)

        def option(trait: Any) -> ChoiceOptionOut:
            return ChoiceOptionOut(trait_id=trait.id, name=trait.name or "Unnamed", description=getattr(trait, "description", None))

        steps = []
        for step in self._steps(pack):
            choices = []
            for kind in step.get("choices", []):
                chosen = self._chosen(person.id, kind)
                choices.append(
                    ChoiceOut(
                        kind=kind,
                        chosen=option(chosen[0][1]) if chosen else None,
                        options=[option(trait) for trait in self._available(campaign, kind)],
                    )
                )
            steps.append(StepOut(step=int(step["step"]), name=step["name"], choices=choices))
        return ChoicesOut(person_id=person.id, system=pack["system"], gm=gm, steps=steps)

    def choose_for(self, body: ChooseRequest) -> ChoicesOut:
        """Record a creation choice (a class, background or species): one per kind; a player chooses
        once, the GM may change it."""
        dice = self._dice()
        person, campaign, gm = dice._character(body.person_id)
        pack = dice._pack_for(campaign)
        kinds = {kind for step in self._steps(pack) for kind in step.get("choices", [])}
        if body.kind not in kinds:
            raise _refuse(f"{pack['system']}'s creation has no {body.kind!r} choice")
        if body.trait_id not in {trait.id for trait in self._available(campaign, body.kind)}:
            raise _refuse(f"That isn't a {body.kind} this campaign offers")
        chosen = self._chosen(person.id, body.kind)
        if chosen and not gm:
            raise _refuse(f"The {body.kind} is already chosen; the GM can change it")
        rows = self._trusted(PersonTraitManager)
        for row, _ in chosen:
            rows.delete(id=row.id)
        rows.create(person_id=person.id, trait_id=body.trait_id)
        return self.choices_for(person.id)

    def npc_sheet_for(self, body: NpcSheetRequest) -> NpcSheetResultEnvelope:
        """An NPC's sheet from the closest compendium stat block of the campaign's pack (dnd-5e: the
        SRD's humanoids) by role and hint, or the pack's generic block: its ability scores and skill
        proficiencies written as the NPC's, nothing invented. The campaign's GM only."""
        dice = self._dice()
        person, campaign, gm = dice._character(body.person_id)
        if not gm:
            raise HTTPException(status_code=404, detail={"message": "Request searched PersonModel and could not find the required record."})
        if body.campaign_id is not None and body.campaign_id != str(campaign.id):
            raise _refuse("That character isn't in this campaign")
        pack = dice._pack_for(campaign)
        npcs = pack.get("npcs")
        if not npcs:
            raise _refuse(f"{pack['system']}'s pack has no NPC stat blocks yet")
        abilities = self._abilities(person.id, campaign, gm, pack)
        if any(score is not None for _, _, score in abilities) and not body.replace:
            raise _refuse(f"{person.name or 'This character'} already has a sheet; pass replace to overwrite it")
        block, source = pick(npcs["blocks"], npcs["generic"], body.role, body.hint)
        rows = self._trusted(PersonTraitManager)

        def write(trait_id: str, **values: Any) -> None:
            live = self._live(rows, person_id=person.id, trait_id=trait_id)
            if live:
                rows.update_trusted(id=live[0].id, **values)
            else:
                rows.create(person_id=person.id, trait_id=trait_id, **values)

        for one, trait, _ in abilities:
            write(trait.id, value=float(block["abilities"][one["slug"]]))
        names = {skill["slug"]: skill["name"] for skill in pack["skills"]}
        for slug, rank in (block.get("skills") or {}).items():
            if slug in names:
                write(dice._trait_for(stat_name(names[slug]), campaign, gm).id, rank=int(rank))
        sheet = NpcSheetOut(
            person_id=person.id,
            system=pack["system"],
            source=source,
            entry_name=block["name"],
            entry_uuid=block.get("uuid"),
            has_sheet=True,
            hp=block.get("hp"),
            ac=block.get("ac"),
            cr=block.get("cr"),
        )
        return NpcSheetResultEnvelope(sheet=sheet, sheet_id=person.id, source_name=block["name"])

    @custom_route(
        method="POST",
        path="/npc-sheet",
        input_model=NpcSheetEnvelope,
        output_model=NpcSheetResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Builder",),
        summary="An NPC's sheet from the closest compendium stat block by role (the campaign's GM)",
    )
    async def npc_sheet_route(self, body: NpcSheetEnvelope) -> NpcSheetResultEnvelope:
        return self.npc_sheet_for(body.npc)

    @custom_route(
        method="POST",
        path="/choices",
        input_model=ChoicesEnvelope,
        output_model=ChoicesResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Builder",),
        summary="A character's creation steps under the pack, each choice's options and what's chosen",
    )
    async def choices_route(self, body: ChoicesEnvelope) -> ChoicesResultEnvelope:
        return ChoicesResultEnvelope(builder=self.choices_for(body.choices.person_id))

    @custom_route(
        method="POST",
        path="/choose",
        input_model=ChooseEnvelope,
        output_model=ChoicesResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Builder",),
        summary="Record a creation choice ([redacted]: a class, background or species)",
    )
    async def choose_route(self, body: ChooseEnvelope) -> ChoicesResultEnvelope:
        return ChoicesResultEnvelope(builder=self.choose_for(body.choose))

    @custom_route(
        method="POST",
        path="/options",
        input_model=OptionsEnvelope,
        output_model=BuilderOptionsEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Builder",),
        summary="A character's ability score methods under the pack, their scores and any kept roll",
    )
    async def options_route(self, body: OptionsEnvelope) -> BuilderOptionsEnvelope:
        return BuilderOptionsEnvelope(builder=self.options_for(body.options.person_id))

    @custom_route(
        method="POST",
        path="/ability-roll",
        input_model=RollEnvelope,
        output_model=RolledOut,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Builder",),
        summary="Roll a character's ability scores by the pack's random generation, kept on the server",
    )
    async def roll_route(self, body: RollEnvelope) -> RolledOut:
        return self.roll_for(body.roll)

    @custom_route(
        method="POST",
        path="/abilities",
        input_model=ApplyEnvelope,
        output_model=BuilderOptionsEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Builder",),
        summary="Set a character's ability scores by a method (standard array, point buy, or their roll)",
    )
    async def abilities_route(self, body: ApplyEnvelope) -> BuilderOptionsEnvelope:
        return BuilderOptionsEnvelope(builder=self.apply_for(body.abilities))


class NpcSheetManager(AbstractBLLManager[Any], RouterMixin):
    """POST /v1/sheet/npc: the same as /v1/builder/npc-sheet, at the path rpg-ai's lite edition calls."""

    prefix: ClassVar[str | None] = "/v1/sheet"
    tags: ClassVar[list[str] | None] = ["Builder"]
    routes_to_register: ClassVar[list[RouteType] | None] = []

    @custom_route(
        method="POST",
        path="/npc",
        input_model=NpcSheetEnvelope,
        output_model=NpcSheetResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Builder",),
        summary="An NPC's sheet from the closest compendium stat block by role (the campaign's GM)",
    )
    async def npc_route(self, body: NpcSheetEnvelope) -> NpcSheetResultEnvelope:
        builder = BuilderManager(requester_id=str(self.requester.id), model_registry=self.model_registry)
        return builder.npc_sheet_for(body.npc)
