# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_builder: character creation by the rules as written, under the campaign's system pack.

Ability scores first (the pack's ``ability_methods``; the 5e SRD: standard array, point buy, or 4d6
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
from zephyrex.extensions.rpg_builder.Pregen import Document, Gap, name_key, parse_line, plan
from zephyrex.extensions.rpg_dice.BLL_RPGDice import CampaignManager, DiceManager, stat_name  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_dice.D20 import proficiency_bonus  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_modules.BLL_RPGModules import CampaignModuleManager, ModuleRecordManager  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_systems.BLL_RPGSystems import GameSystemManager  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_systems.Packs import load_pack  # type: ignore[import-not-found]
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
    kind: str = Field(description="A choice the pack's creation steps name (the 5e SRD: class, background, species)")
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
    option_id: Optional[str] = Field(None, description="The option to build from (npc_sheet_options); none picks the closest by role")


class NpcSheetEnvelope(PlainModel):
    npc: NpcSheetRequest


class NpcOptionsRequest(PlainModel):
    campaign_id: str


class NpcOptionsEnvelope(PlainModel):
    npc_options: NpcOptionsRequest


class NpcOptionOut(PlainModel):
    """One thing the campaign's pack can build an NPC from: a stat block (srd-5e) for now."""

    id: str
    name: str
    level_or_cr: Optional[float] = Field(None, description="Its challenge rating (a stat block) or level (a class build)")
    class_name: Optional[str] = Field(None, serialization_alias="class", description="A class build's class; none for a stat block")
    subclass: Optional[str] = None
    summary: str = Field(description="What it is, for a model choosing among options: its numbers and what it's good at")


class NpcOptionsOut(PlainModel):
    system: Optional[str] = Field(None, description="The campaign's game system; none when it has no rules pack")
    options: list[NpcOptionOut] = Field(default_factory=list, description="Empty when the pack has nothing to build NPCs from")


class NpcOptionsResultEnvelope(PlainModel):
    npc_options: NpcOptionsOut


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


class PregenRequest(PlainModel):
    person_id: str
    replace: bool = Field(False, description="Overwrite a sheet the pregen already has")
    dry_run: bool = Field(False, description="Report what would be built and what stays open; write nothing")


class PregenEnvelope(PlainModel):
    pregen: PregenRequest


class PregenGapOut(PlainModel):
    what: str = Field(description="What is open: line, edition, level, class, background, species, abilities, equipment")
    detail: str


class PregenOut(PlainModel):
    person_id: str
    name: Optional[str] = None
    system: Optional[str] = None
    level: Optional[int] = None
    class_name: Optional[str] = None
    background: Optional[str] = None
    species: Optional[str] = None
    edition: Optional[str] = None
    has_sheet: bool = Field(description="Whether the pregen had sheet rows before this call")
    built: bool = Field(description="Whether a sheet was (or, in a dry run, would be) written")
    written: int = 0
    abilities: dict[str, int] = Field(default_factory=dict, description="The standard array as the SRD places it for the class")
    saves: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list, description="Skills granted outright (proficient)")
    features: list[str] = Field(default_factory=list, description="The granted features and spells, by name")
    hp: Optional[int] = Field(None, description="Level-1 hit points from these scores (before any open ability increase)")
    gaps: list[PregenGapOut] = Field(default_factory=list, description="Choices the rules leave open that the pregen's data doesn't settle")


class PregenResultEnvelope(PlainModel):
    pregen: PregenOut


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
        """Roll the pack's random generation (the 5e SRD: 4d6 keep the highest three, six times) and keep
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

    def npc_options_for(self, body: NpcOptionsRequest) -> NpcOptionsOut:
        """What the campaign's pack can build an NPC from (srd-5e: the SRD's humanoid stat blocks), for
        a caller to choose among and pass to npc_sheet as option_id. Empty when the pack has none, or
        the campaign's system has no pack. The campaign's GM only."""
        dice = self._dice()
        campaign = dice._get(CampaignManager, "CampaignModel", body.campaign_id)
        requester = str(self.requester.id)
        if requester not in {str(owner) for owner in (campaign.user_id, getattr(campaign, "created_by_user_id", None)) if owner}:
            raise HTTPException(status_code=404, detail={"message": "Request searched CampaignModel and could not find the required record."})
        try:
            pack = dice._pack_for(campaign)
        except HTTPException:
            return NpcOptionsOut()
        names = {skill["slug"]: skill["name"] for skill in pack.get("skills", [])}
        options = []
        for block in (pack.get("npcs") or {}).get("blocks") or []:
            skilled = ", ".join(names.get(slug, slug) for slug in block.get("skills") or {})
            parts = [f"CR {block['cr']:g}" if block.get("cr") is not None else None, f"{block['hp']} HP" if block.get("hp") else None,
                     f"AC {block['ac']}" if block.get("ac") else None, f"skilled in {skilled}" if skilled else None]
            options.append(NpcOptionOut(
                id=block["slug"], name=block["name"], level_or_cr=block.get("cr"), summary="; ".join(one for one in parts if one),
            ))
        return NpcOptionsOut(system=pack["system"], options=options)

    def npc_sheet_for(self, body: NpcSheetRequest) -> NpcSheetResultEnvelope:
        """An NPC's sheet from the closest compendium stat block of the campaign's pack (srd-5e: the
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
        if body.option_id is not None:
            named = [one for one in npcs["blocks"] if one["slug"] == body.option_id]
            if not named:
                raise _refuse(f"{pack['system']} has no NPC option {body.option_id!r}; npc_sheet_options lists them")
            block, source = named[0], "compendium"
        else:
            block, source = pick(npcs["blocks"], npcs["generic"], body.role, body.hint)
        rows = self._trusted(PersonTraitManager)
        # The rows are made as the requester (the campaign's GM, checked above), so the GM's own list
        # and edits see the sheet; one the system made earlier is replaced, not updated in place.
        mine = PersonTraitManager(requester_id=str(self.requester.id), model_registry=self.model_registry)

        def write(trait_id: str, **values: Any) -> None:
            for row in self._live(rows, person_id=person.id, trait_id=trait_id):
                rows.delete(id=row.id)
            mine.create(person_id=person.id, trait_id=trait_id, **values)

        for one, trait, _ in abilities:
            write(trait.id, value=float(block["abilities"][one["slug"]]))
        names = {skill["slug"]: skill["name"] for skill in pack["skills"]}
        for slug, rank in (block.get("skills") or {}).items():
            if slug in names:
                write(dice._trait_for(stat_name(names[slug]), campaign, gm).id, rank=int(rank))
        # What combat reads (rpg_combat): the block's weapons, its hit points and AC, and its
        # Proficiency Bonus by its CR. A system without those templates (no 006 seed) skips them.
        templates = {
            (trait.kind, trait.slug): trait.id
            for trait in self._live(self._trusted(TraitManager), game_system_id=dice.system_id_of(campaign))
            if trait.campaign_id is None and trait.slug and trait.kind in ("weapon", "resource")
        }
        weapons = {one["name"].casefold(): one["slug"] for one in pack.get("weapons") or []}
        for attack in block.get("attacks") or []:
            slug = weapons.get(attack["name"].casefold())
            if slug and ("weapon", slug) in templates:
                write(templates[("weapon", slug)])
        held = {"hit-points": block.get("hp"), "armor-class": block.get("ac")}
        if block.get("cr") is not None:
            held["proficiency-bonus"] = proficiency_bonus(pack, max(1, int(block["cr"])))
        for slug, value in held.items():
            if value is not None and ("resource", slug) in templates:
                write(templates[("resource", slug)], value=float(value))
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

    def _catalog(self, system_id: str) -> dict[str, dict[str, Document]]:
        """The system's class, background and species traits that came from a module, each with its
        record's source data (Foundry's system), by name_key."""
        traits = self._trusted(TraitManager)
        records = self._trusted(ModuleRecordManager)
        catalog: dict[str, dict[str, Document]] = {}
        for kind in ("class", "background", "species"):
            found: dict[str, Document] = {}
            for trait in self._live(traits, game_system_id=system_id, kind=kind):
                if trait.campaign_id is not None:
                    continue
                for record in records.list(entity_type="trait", entity_id=trait.id):
                    found[name_key(trait.name or "")] = Document(trait.id, record.source_id, trait.name or "", record.data or {})
                    break
            catalog[kind] = found
        return catalog

    def build_pregen_for(self, body: PregenRequest) -> PregenOut:
        """A setting pregen's starting sheet by the SRD's creation rules (rpg_builder.Pregen): what
        its own line and the rules settle is written, every open choice is reported, nothing is
        guessed. The pregen's owner only; refused when it has a sheet, unless replace."""
        from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager

        persons = self._trusted(PersonManager)
        person = next(iter(self._live(persons, id=body.person_id)), None)
        requester = str(self.requester.id)
        if person is None or requester not in {
            str(owner) for owner in (getattr(person, "user_id", None), getattr(person, "created_by_user_id", None)) if owner
        }:
            raise HTTPException(status_code=404, detail={"message": "Request searched PersonModel and could not find the required record."})
        if getattr(person, "campaign_id", None) is not None:
            raise _refuse("build_pregen is for a setting's pregen; a campaign's characters use the builder's steps")
        system_id = self._dice().system_id_of(person)
        system = None if system_id is None else self._trusted(GameSystemManager).get(id=system_id)
        pack = None if system is None or not system.slug else load_pack(system.slug)
        if pack is None:
            raise _refuse("This pregen's setting has no game system with a rules pack")
        catalog = self._catalog(str(system.id))
        # Its line is in its description (genealogy's), or its entry (the wiki's Plate value, as JSON text).
        text = " ".join(str(getattr(person, name, None) or "") for name in ("description", "summary", "entry"))
        line = parse_line(text, [document.name for document in catalog["class"].values()])
        result = plan(line, catalog, pack)

        records = self._trusted(ModuleRecordManager)
        traits = self._trusted(TraitManager)
        feature_ids: list[tuple[str, str]] = []
        for source_id in result.features:
            record = next((row for row in records.list(source_id=source_id, entity_type="trait") if row.entity_id), None)
            trait = None if record is None else next(iter(self._live(traits, id=record.entity_id)), None)
            if trait is None:
                result.gaps.append(Gap("feature", f"{source_id} isn't a trait in the module"))
                continue
            feature_ids.append((trait.id, trait.name or ""))
        by_slug = {
            (trait.kind, trait.slug): trait.id
            for trait in self._live(traits, game_system_id=system.id)
            if trait.campaign_id is None and trait.kind in ("characteristic", "skill", "resource") and trait.slug
        }
        rows = self._trusted(PersonTraitManager)
        existing = self._live(rows, person_id=person.id)
        if existing and not body.replace and not body.dry_run:
            raise _refuse(f"{person.name or 'This pregen'} already has a sheet; pass replace to overwrite it")

        wanted: list[dict[str, Any]] = [{"trait_id": trait_id} for trait_id in result.origins.values()]
        wanted += [{"trait_id": trait_id} for trait_id, _ in feature_ids]
        for slug, score in result.abilities.items():
            if ("characteristic", slug) in by_slug:
                wanted.append({"trait_id": by_slug[("characteristic", slug)], "value": float(score)})
        for slug in result.skills:
            if ("skill", slug) in by_slug:
                wanted.append({"trait_id": by_slug[("skill", slug)], "rank": 1})
        # Combat reads these (rpg_combat): level-1 hit points, and the Proficiency Bonus at level 1.
        resources = {"hit-points": result.hp, "proficiency-bonus": proficiency_bonus(pack, 1) if pack.get("proficiency") else None}
        for slug, value in resources.items():
            if value is not None and ("resource", slug) in by_slug:
                wanted.append({"trait_id": by_slug[("resource", slug)], "value": float(value)})
        wanted = list({row["trait_id"]: row for row in wanted}.values())

        written = 0
        if result.buildable and not body.dry_run:
            for row in existing:
                rows.delete(id=row.id)
            # Made as the requester (the pregen's owner, checked above), so their own list sees the sheet.
            mine = PersonTraitManager(requester_id=str(self.requester.id), model_registry=self.model_registry)
            for row in wanted:
                mine.create(person_id=person.id, **row)
            written = len(wanted)
        return PregenOut(
            person_id=person.id,
            name=person.name,
            system=pack["system"],
            level=line.level if line else None,
            class_name=line.klass if line else None,
            background=line.background if line else None,
            species=line.species if line else None,
            edition=line.edition if line else None,
            has_sheet=bool(existing),
            built=result.buildable,
            written=written,
            abilities=result.abilities,
            saves=result.saves,
            skills=result.skills,
            features=[name for _, name in feature_ids],
            hp=result.hp,
            gaps=[PregenGapOut(what=gap.what, detail=gap.detail) for gap in result.gaps],
        )

    @custom_route(
        method="POST",
        path="/pregen",
        input_model=PregenEnvelope,
        output_model=PregenResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Builder",),
        summary="A setting pregen's starting sheet by the SRD's creation rules; open choices reported (its owner)",
    )
    async def pregen_route(self, body: PregenEnvelope) -> PregenResultEnvelope:
        builder = BuilderManager(requester_id=str(self.requester.id), model_registry=self.model_registry)
        return PregenResultEnvelope(pregen=builder.build_pregen_for(body.pregen))

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
        path="/npc-options",
        input_model=NpcOptionsEnvelope,
        output_model=NpcOptionsResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Builder",),
        summary="What the campaign's pack can build an NPC from, to choose among for npc-sheet (the campaign's GM)",
    )
    async def npc_options_route(self, body: NpcOptionsEnvelope) -> NpcOptionsResultEnvelope:
        builder = BuilderManager(requester_id=str(self.requester.id), model_registry=self.model_registry)
        return NpcOptionsResultEnvelope(npc_options=builder.npc_options_for(body.npc_options))

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
        summary="Record a creation choice (the 5e SRD: a class, background or species)",
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
