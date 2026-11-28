# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_dice: saved formulas and roll tables (OBJECT_PLAN §4), and the referee's rolls and checks.

``POST /v1/dice/roll`` rolls a formula; ``POST /v1/dice/check`` rolls one for a character, with
``@stat`` references resolved from their traits (Check.py). Both roll on the server with
``secrets.SystemRandom``, so neither a player nor a model can choose a result (docs/DESIGN.md,
Principle 2). Results are returned, not stored: writing them to the wiki's ``rpg_log`` is its own
item (docs/DESIGN.md, Progress).

Who may check is decided once: the campaign's GM, or the character's own player; anyone else gets
the same 404 as a character that doesn't exist. Past that, the stats are read as the system (a
trusted read), so a GM's hidden traits still count in a player's own check. What comes back is what
the requester may see. A player may name the system's stat templates and the campaign traits they can
read; any other name is ``unknown_stat``, the same as one that doesn't exist. Contributions from
records they can't read are folded into one ``hidden`` step with only their net effect, so a check
never reveals a hidden value. Per-record hiding waits for acl_rbac (docs/DESIGN.md, Progress).
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Any, ClassVar, Literal, Optional, Type

from fastapi import HTTPException
from pydantic import BaseModel as PlainModel
from pydantic import Field
from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager
from zephyrex.extensions.rpg_dice.Check import Contribution, Step, check, resolve
from zephyrex.extensions.rpg_dice.Dice import MAX_FORMULA_LENGTH, DiceError, roll
from zephyrex.extensions.rpg_dice.Percentile import TestError
from zephyrex.extensions.rpg_dice.Percentile import test as percentile_test
from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignManager  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_systems.BLL_RPGSystems import GameSystemManager, GameSystemModel  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_systems.Packs import load_pack  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_dice.D20 import d20_test  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_modules.BLL_RPGModules import CampaignModuleManager, ContentModuleManager, ModuleRecordManager  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import (  # type: ignore[import-not-found]
    DerivativeTraitManager,
    PersonTraitManager,
    TraitManager,
)
from zephyrex.extensions.world_inventory.BLL_WorldInventory import (  # type: ignore[import-not-found]
    ItemInstanceManager,
    ItemManager,
)
from zephyrex.extensions.world_spatial.BLL_WorldSpatial import LocationManager  # type: ignore[import-not-found]
from zephyrex.lib.CustomRoute import ExposeIn, custom_route
from zephyrex.lib.Environment import env
from zephyrex.logic.AbstractLogicManager import (
    AbstractBLLManager,
    ApplicationModel,
    DescriptionMixinModel,
    ModelMeta,
    NameMixinModel,
    NumericalSearchModel,
    StringSearchModel,
    UpdateMixinModel,
)
from zephyrex.pydantic2.fastapi import RouterMixin
from zephyrex.pydantic2.fastapi.types import RouteType
from zephyrex.pydantic2.registry import BaseModel  # type: ignore[attr-defined]

_SYSTEM_RANDOM = secrets.SystemRandom()
_STAT_REFERENCE = re.compile(r"@([A-Za-z_][A-Za-z0-9_]*)")
_NOT_A_WORD = re.compile(r"[^a-z0-9]+")
MAX_QUALIFIERS = 20
# Where an item is worn or wielded: a location of these kinds bound to the character.
WORN_LOCATION_KINDS = frozenset({"equipment_slot", "body_part"})


def live_draw(sides: int) -> int:
    """A face from 1 to ``sides`` from the operating system's random source."""
    return _SYSTEM_RANDOM.randint(1, sides)


def stat_name(name: str) -> str:
    """How a trait is named in a formula: ``Sleight of Hand`` is ``@sleight_of_hand``."""
    return _NOT_A_WORD.sub("_", name.strip().lower()).strip("_")


# ---------------------------------------------------------------------------
# Saved formulas and roll tables (OBJECT_PLAN §4 rpg_dice)
# ---------------------------------------------------------------------------


class DiceFormulaModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    DescriptionMixinModel.Optional,
    GameSystemModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["DiceFormulaManager"]] = None
    formula: Optional[str] = Field(None, description="Dice notation (rpg_dice Dice.py)")
    table_comment: ClassVar[str] = "A saved formula, e.g. a system's attack roll; game_system_id NULL = any system"

    class Create(BaseModel, GameSystemModel.Reference.ID.Optional):
        name: str = Field(...)
        formula: str = Field(..., max_length=MAX_FORMULA_LENGTH)
        description: Optional[str] = None

    class Update(BaseModel):
        name: Optional[str] = None
        formula: Optional[str] = Field(None, max_length=MAX_FORMULA_LENGTH)
        description: Optional[str] = None

    class Search(ApplicationModel.Search, GameSystemModel.Reference.ID.Search):
        name: Optional[StringSearchModel] = None


class RollTableModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    DescriptionMixinModel.Optional,
    GameSystemModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["RollTableManager"]] = None
    formula: Optional[str] = Field(None, description="The roll that picks an entry")
    table_comment: ClassVar[str] = "A roll table (random encounters, loot); its entries cover the formula's range"

    class Create(BaseModel, GameSystemModel.Reference.ID.Optional):
        name: str = Field(...)
        formula: str = Field(..., max_length=MAX_FORMULA_LENGTH)
        description: Optional[str] = None

    class Update(BaseModel):
        name: Optional[str] = None
        formula: Optional[str] = Field(None, max_length=MAX_FORMULA_LENGTH)
        description: Optional[str] = None

    class Search(ApplicationModel.Search, GameSystemModel.Reference.ID.Search):
        name: Optional[StringSearchModel] = None


class RollTableEntryModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    RollTableModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["RollTableEntryManager"]] = None
    range_low: Optional[int] = Field(None, description="The lowest roll that picks this entry")
    range_high: Optional[int] = Field(None, description="The highest roll that picks this entry")
    result_text: Optional[str] = Field(None)
    result_entity_type: Optional[str] = Field(None, description="What the entry names, if a record")
    result_entity_id: Optional[str] = Field(None)
    weight: Optional[int] = Field(None, description="Draw weight, for tables rolled by weight")
    table_comment: ClassVar[str] = "One row of a roll table: a range of results and what it gives"

    class Create(BaseModel, RollTableModel.Reference.ID.Optional):
        range_low: int = Field(...)
        range_high: int = Field(...)
        result_text: Optional[str] = None
        result_entity_type: Optional[str] = None
        result_entity_id: Optional[str] = None
        weight: Optional[int] = None

    class Update(BaseModel):
        range_low: Optional[int] = None
        range_high: Optional[int] = None
        result_text: Optional[str] = None
        result_entity_type: Optional[str] = None
        result_entity_id: Optional[str] = None
        weight: Optional[int] = None

    class Search(ApplicationModel.Search, RollTableModel.Reference.ID.Search):
        range_low: Optional[NumericalSearchModel] = None
        range_high: Optional[NumericalSearchModel] = None


class DiceFormulaManager(AbstractBLLManager, RouterMixin):
    _model = DiceFormulaModel


class RollTableManager(AbstractBLLManager, RouterMixin):
    _model = RollTableModel


class RollTableEntryManager(AbstractBLLManager, RouterMixin):
    _model = RollTableEntryModel


DiceFormulaModel.Manager = DiceFormulaManager
RollTableModel.Manager = RollTableManager
RollTableEntryModel.Manager = RollTableEntryManager

ALL_MODELS: list[type] = [DiceFormulaModel, RollTableModel, RollTableEntryModel]


# ---------------------------------------------------------------------------
# Rolls and checks
# ---------------------------------------------------------------------------


class RollRequest(PlainModel):
    formula: str = Field(..., max_length=MAX_FORMULA_LENGTH)


class RollEnvelope(PlainModel):
    roll: RollRequest


class DieOut(PlainModel):
    value: int
    kept: bool
    note: Optional[str] = None


class TermOut(PlainModel):
    notation: str
    dice: list[DieOut]
    value: int


class RollOut(PlainModel):
    formula: str
    total: int
    terms: list[TermOut]
    stats: dict[str, int]


class RollResultEnvelope(PlainModel):
    roll: RollOut


class CheckRequest(PlainModel):
    person_id: str
    formula: str = Field(..., max_length=MAX_FORMULA_LENGTH)
    target: Optional[float] = None
    compare: Literal[">=", "<="] = ">="
    qualifiers: list[str] = Field(default_factory=list, max_length=MAX_QUALIFIERS)


class CheckEnvelope(PlainModel):
    check: CheckRequest


class StepOut(PlainModel):
    id: str
    operation: str
    size: float
    result: float


class StatOut(PlainModel):
    """Why a stat is what it is (V21's breakdown): its base and each contribution in order."""

    name: str
    trait_id: str
    base: float
    value: float
    steps: list[StepOut]


class CheckOut(RollOut):
    person_id: str
    target: Optional[float]
    compare: str
    success: Optional[bool]
    margin: Optional[float]
    resolved: list[StatOut]


class CheckResultEnvelope(PlainModel):
    check: CheckOut


MAX_MODIFIERS = 20


class TestRequest(PlainModel):
    person_id: str
    # A characteristic or skill of the campaign's system pack, by slug (might, repair).
    name: str = Field(..., max_length=100)
    # A difficulty of the pack (a d100 pack: easy … very hard); none is the pack's default.
    difficulty: Optional[str] = Field(None, max_length=40)
    modifiers: list[int] = Field(default_factory=list, max_length=MAX_MODIFIERS)
    # Which specialisation of a specialist skill (Lore: "Stars"); required for those, refused
    # for the rest. Matched case-insensitively against the character's own.
    specialisation: Optional[str] = Field(None, max_length=100)
    # Advantage or Disadvantage, for a pack whose test has them (the 5e SRD: two d20s, the higher or
    # the lower kept); refused for a pack without.
    advantage: Optional[Literal["advantage", "disadvantage"]] = None


class TestEnvelope(PlainModel):
    test: TestRequest


class TestOut(PlainModel):
    person_id: str
    system: str
    name: str
    specialisation: Optional[str] = None
    kind: Literal["characteristic", "skill"]
    characteristic: StatOut
    skill_rank: Optional[int]
    trained: bool
    target: int
    roll: int
    success: bool
    degrees: Optional[int] = Field(
        None, description="Degrees of success or failure, for a system that has them (d100); none for a d20 test (5e has none)"
    )
    natural: Optional[Literal["success", "failure"]]
    steps: list[dict[str, Any]]
    mechanic: Literal["d100-degrees", "d20"] = Field(
        "d100-degrees", description="How the result reads: d100 roll-under with degrees, or a d20 against a DC (no degrees)"
    )
    natural_roll: Optional[int] = Field(
        None, description="A d20 test's natural 20 or 1 (the die as it fell); on a check the SRD gives it no automatic result"
    )
    total: Optional[int] = Field(None, description="A d20 test's roll plus its modifiers (none for d100 roll-under)")
    test_kind: str = Field("d100-under", description="The pack's test: d100-under (percentile) or d20-over (5e)")
    no_sheet: bool = Field(False, description="Rolled for a character with no value for it, as the pack's rules say")
    advantage: Optional[Literal["advantage", "disadvantage"]] = Field(None, description="Rolled with Advantage or Disadvantage")
    rolls: list[int] = Field(default_factory=list, description="Every die rolled for the test; ``roll`` is the one kept")


class TestResultEnvelope(PlainModel):
    test: TestOut


class TestOptionsRequest(PlainModel):
    person_id: str


class TestOptionsEnvelope(PlainModel):
    options: TestOptionsRequest


class TestOptionOut(PlainModel):
    slug: str
    name: str
    short: Optional[str] = None
    characteristic: Optional[str] = None
    untrainable: bool = False
    # A specialist skill's specialisations this character holds (rank 1+), for a tray to offer.
    specialisations: list[str] = Field(default_factory=list)


class DifficultyOut(PlainModel):
    slug: str
    modifier: int
    dc: Optional[int] = None


class TestOptionsOut(PlainModel):
    person_id: str
    system: str
    characteristics: list[TestOptionOut]
    skills: list[TestOptionOut]
    difficulties: list[DifficultyOut]
    default_difficulty: str
    # Whether the character has a sheet under this pack (any of its characteristics set); without one
    # a tray offers formulas only.
    has_sheet: bool = True
    test_kind: str = Field("d100-under", description="The pack's test: d100-under (percentile) or d20-over (5e)")


class TestOptionsResultEnvelope(PlainModel):
    options: TestOptionsOut


class SheetRequest(PlainModel):
    person_id: str


class SheetEnvelope(PlainModel):
    sheet: SheetRequest


class SheetEntry(PlainModel):
    trait_id: str
    slug: Optional[str]
    name: str
    kind: Optional[str]
    value: Optional[float] = None
    rank: Optional[int] = None
    specialisation: Optional[str] = None


class SheetItem(PlainModel):
    id: str
    item_id: Optional[str]
    name: Optional[str]
    quantity: int = 1


class SheetOut(PlainModel):
    person_id: str
    name: Optional[str]
    system: Optional[str]
    has_sheet: bool
    characteristics: list[SheetEntry]
    skills: list[SheetEntry]
    resources: list[SheetEntry]
    origins: list[SheetEntry]
    abilities: list[SheetEntry]
    gear: list[SheetItem]
    state: Optional[dict[str, Any]] = Field(
        None,
        description="What fights, rests and potions left (rpg_combat): hp and hp_max, hit_dice {die, total, spent, left}, "
        "exhaustion, conditions; none without rpg_combat",
    )


class SheetResultEnvelope(PlainModel):
    sheet: SheetOut


class InitiativeRequest(PlainModel):
    person_id: str


class InitiativeEnvelope(PlainModel):
    initiative: InitiativeRequest


class InitiativeOut(PlainModel):
    person_id: str
    system: str
    dice: str
    roll: int
    characteristic: str
    value: float
    bonus: int
    total: int


class InitiativeResultEnvelope(PlainModel):
    initiative: InitiativeOut


def initiative_bonus(value: float, kind: str) -> int:
    """A characteristic's initiative bonus by the pack's rule: ``tens``, its tens digit (a percentile
    lines' characteristic bonus); ``modifier``, (value − 10) / 2 rounded down (d20 ability modifiers)."""
    if kind == "tens":
        return int(value) // 10
    if kind == "modifier":
        return (int(value) - 10) // 2
    raise ValueError(f"unknown initiative bonus {kind!r}")


# A sheet's sections by trait kind; any other kind is an ability (talents, traits, powers, feats…).
SHEET_CHARACTERISTICS = frozenset({"characteristic", "attribute"})
SHEET_ORIGINS = frozenset({"homeworld", "background", "role", "elite-advance", "divination", "origin", "class", "subclass", "species"})


def _refused(error: DiceError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"message": error.message, "code": "dice_formula", "errors": [{"type": error.code, "loc": ["formula"]}]},
    )


def _not_found(model: str) -> HTTPException:
    return HTTPException(
        status_code=404, detail={"message": f"Request searched {model} and could not find the required record."}
    )


def _now_like(moment: datetime) -> datetime:
    now = datetime.now(timezone.utc)
    return now if moment.tzinfo is not None else now.replace(tzinfo=None)


def _same(text: Optional[str]) -> str:
    """A specialisation as compared: trimmed and case-folded, "" for none."""
    return (text or "").strip().casefold()


def _live(row: Any) -> bool:
    """A trait value still in force: no expiry, or one still ahead."""
    expires = getattr(row, "expires_at", None)
    return expires is None or expires > _now_like(expires)


HIDDEN_STEP = "hidden"


def fold_hidden(base: float, steps: list[Step], visible: set[str]) -> list[StepOut]:
    """The steps a requester may see: each run of steps from records they can't read becomes one
    ``hidden`` step carrying only the net change, so no hidden value can be read back out."""
    shown: list[StepOut] = []
    before = base
    for step in steps:
        if step.id in visible:
            shown.append(StepOut(**step.as_dict()))
        elif shown and shown[-1].id == HIDDEN_STEP:
            shown[-1] = StepOut(
                id=HIDDEN_STEP, operation=HIDDEN_STEP, size=step.result - (before - shown[-1].size), result=step.result
            )
        else:
            shown.append(StepOut(id=HIDDEN_STEP, operation=HIDDEN_STEP, size=step.result - before, result=step.result))
        before = step.result
    return shown


class DiceManager(AbstractBLLManager[Any], RouterMixin):
    """The referee's rolls; no table of its own."""

    prefix: ClassVar[str | None] = "/v1/dice"
    tags: ClassVar[list[str] | None] = ["Dice"]
    routes_to_register: ClassVar[list[RouteType] | None] = []

    def _manager(self, manager: type[Any]) -> Any:
        """A manager as the requester sees records."""
        return manager(requester_id=str(self.requester.id), model_registry=self.model_registry)

    def _trusted(self, manager: type[Any]) -> Any:
        """A manager reading as the system, once the access rule has passed (as update_trusted)."""
        return manager(requester_id=env("ROOT_ID"), model_registry=self.model_registry)

    def _readable(self, manager: type[Any], record_id: str) -> bool:
        """Whether the requester could read this record themselves."""
        try:
            self._manager(manager).get(id=record_id)
        except HTTPException:
            return False
        return True

    def roll_formula(self, formula: str) -> RollOut:
        try:
            return RollOut(**roll(formula, live_draw).as_dict())
        except DiceError as error:
            raise _refused(error) from error

    def _get(self, manager: type[Any], model: str, record_id: str) -> Any:
        try:
            return self._trusted(manager).get(id=record_id)
        except HTTPException as error:
            raise _not_found(model) from error

    def _person_values(self, person_id: str, trait_id: str) -> list[float]:
        rows = self._trusted(PersonTraitManager).list(person_id=person_id, trait_id=trait_id)
        return [float(row.value) for row in rows if row.value is not None and _live(row)]

    def _trait_for(self, name: str, campaign: Any, gm: bool) -> Any:
        """The trait ``@name`` means in this campaign: the campaign's own over its system's template.

        A system's templates (``campaign_id`` NULL: Dexterity, Strength, the stats the rules define)
        are public to every member of the campaign. A campaign's own traits are nameable by a player
        only if they can read them, so a GM's secret (a Curse not yet discovered) answers exactly as
        a name that doesn't exist. Per-record hiding of templates waits for acl_rbac.
        """
        traits = self._trusted(TraitManager)
        named = [
            trait
            for trait in traits.list(campaign_id=campaign.id)
            if stat_name(trait.name or "") == name and (gm or self._readable(TraitManager, trait.id))
        ]
        if not named and self.system_id_of(campaign) is not None:
            named = self._system_trait(name, campaign)
        if not named:
            raise _refused(DiceError("unknown_stat", f"There is no stat called @{name}"))
        if len(named) > 1:
            raise _refused(DiceError("ambiguous_stat", f"More than one trait is called @{name}"))
        return named[0]

    def _system_trait(self, name: str, campaign: Any) -> list[Any]:
        """The system-level traits (``campaign_id`` NULL) ``@name`` can mean in this campaign. A trait
        installed by a content module (a private line: its owner's own) counts only when that module is
        enabled on the campaign (CampaignModule), and then it wins over the system's templates;
        another account's private module is never one of them, though a trusted read lists it."""
        candidates = [
            trait
            for trait in self._trusted(TraitManager).list(game_system_id=self.system_id_of(campaign))
            if trait.campaign_id is None and stat_name(trait.name or "") == name
        ]
        if not candidates:
            return []
        enabled = {row.content_module_id for row in self._trusted(CampaignModuleManager).list(campaign_id=campaign.id)}
        records = self._trusted(ModuleRecordManager)
        from_modules, templates = [], []
        for trait in candidates:
            modules = {row.content_module_id for row in records.list(entity_type="trait", entity_id=trait.id)}
            if not modules:
                templates.append(trait)
            elif modules & enabled:
                from_modules.append(trait)
        return from_modules or templates

    def _worn_items(self, person_id: str) -> set[str]:
        """The items the person wears or wields: instances placed in one of their equipment slots or
        body parts (a world_spatial location of that kind bound to them, OBJECT_PLAN §4). An item in
        a pack, or only carried, doesn't count."""
        slots = {
            location.id
            for location in self._trusted(LocationManager).list(associated_person_id=person_id)
            if location.kind in WORN_LOCATION_KINDS
        }
        if not slots:
            return set()
        instances = self._trusted(ItemInstanceManager).list()
        return {instance.item_id for instance in instances if instance.location_id in slots}

    def _resolve(self, person_id: str, trait: Any, qualifiers: list[str], worn: set[str], gm: bool) -> StatOut:
        contributions = []
        visible: set[str] = set()
        for row in self._trusted(DerivativeTraitManager).list(target_trait_id=trait.id):
            if row.operation is None or row.value is None:
                continue
            if row.source_trait_id is not None:
                own = self._person_values(person_id, row.source_trait_id)
                source: Literal["trait", "item", "constant"] = "trait"
                source_value = sum(own) if own else None
            elif row.source_item_id is not None:
                source, source_value = "item", None
            else:
                source, source_value = "constant", None
            if gm or (
                self._readable(DerivativeTraitManager, row.id)
                and (row.source_trait_id is None or self._readable(TraitManager, row.source_trait_id))
            ):
                visible.add(row.id)
            contributions.append(
                Contribution(
                    id=row.id,
                    operation=row.operation,
                    value=float(row.value),
                    order_index=row.order_index or 0,
                    stacking_group=row.stacking_group,
                    qualifier=row.qualifier,
                    source=source,
                    source_value=source_value,
                    item_active=row.source_item_id in worn,
                )
            )
        resolved = resolve(self._person_values(person_id, trait.id), contributions, qualifiers)
        return StatOut(
            name=stat_name(trait.name or ""),
            trait_id=trait.id,
            base=resolved.base,
            value=resolved.value,
            steps=fold_hidden(resolved.base, list(resolved.steps), visible),
        )

    def _players_of(self, person: Any) -> set[str]:
        """Who plays a character: the person's own player (user_id), and whoever holds a seat for
        them at a table (rpg_table's controller_id: a playthrough's copied pregens are played
        through seats). rpg_table builds on rpg_dice, so it's read only when it's loaded."""
        found = {str(person.user_id)} if getattr(person, "user_id", None) else set()
        try:
            from zephyrex.extensions.rpg_table.BLL_RPGTable import TableSeatManager  # type: ignore[import-not-found]
        except ImportError:
            return found
        seats = self._trusted(TableSeatManager)
        for seat in seats.list(filters=[seats.DB.deleted_at.is_(None)], person_id=person.id):
            if getattr(seat, "controller_id", None):
                found.add(str(seat.controller_id))
        return found

    def _character(self, person_id: str) -> tuple[Any, Any, bool]:
        """The character, their campaign, and whether the requester is its GM. Only the campaign's
        GM and the character's player (their own, or their seat's) get past; anyone else gets the same answer as a
        character that isn't there, so nobody learns which ids exist."""
        person = self._get(PersonManager, "PersonModel", person_id)
        requester = str(self.requester.id)
        campaign_id = getattr(person, "campaign_id", None)
        campaign = None if campaign_id is None else self._get(CampaignManager, "CampaignModel", campaign_id)
        # The campaign's owner (user_id) or, for a campaign created without one (an import), its creator.
        gm = campaign is not None and requester in {
            str(owner) for owner in (campaign.user_id, getattr(campaign, "created_by_user_id", None)) if owner
        }
        if not gm and requester not in self._players_of(person):
            raise _not_found("PersonModel")
        if campaign is None:
            raise HTTPException(
                status_code=422,
                detail={"message": "This character isn't in a campaign, so they have no stats to check"},
            )
        return person, campaign, gm

    def check_for(self, body: CheckRequest) -> CheckOut:
        person, campaign, gm = self._character(body.person_id)
        worn = self._worn_items(person.id)
        names = list(dict.fromkeys(_STAT_REFERENCE.findall(body.formula)))
        traits = [self._trait_for(name, campaign, gm) for name in names]
        resolved = [self._resolve(person.id, trait, body.qualifiers, worn, gm) for trait in traits]
        try:
            checked = check(
                body.formula, live_draw, {stat.name: stat.value for stat in resolved}, body.target, body.compare
            )
        except DiceError as error:
            raise _refused(error) from error
        return CheckOut(**checked.as_dict(), person_id=person.id, resolved=resolved)

    def _skill_rows(self, person_id: str, skill: Any, campaign: Any, gm: bool) -> list[Any]:
        """The character's live, ranked rows of a skill (one per specialisation for specialist skills)."""
        try:
            trait = self._trait_for(stat_name(skill["name"]), campaign, gm)
        except HTTPException:
            return []
        rows = self._trusted(PersonTraitManager).list(person_id=person_id, trait_id=trait.id)
        return [row for row in rows if row.rank is not None and _live(row)]

    def _skill_rank(
        self, person_id: str, skill: Any, campaign: Any, gm: bool, specialisation: Optional[str] = None
    ) -> Optional[int]:
        """The rank (1–4) the character holds in a skill (of a specialist skill: in that
        specialisation), or None when they hold it untrained."""
        rows = self._skill_rows(person_id, skill, campaign, gm)
        if skill["specialist"]:
            wanted = _same(specialisation)
            rows = [row for row in rows if _same(getattr(row, "specialisation", None)) == wanted]
        ranks = [int(row.rank) for row in rows]
        return max(ranks) if ranks else None

    def system_id_of(self, campaign: Any) -> Optional[str]:
        """The campaign's game system: its own, else (a vault-imported scenario or its playthrough,
        made with a setting but no system) the one system of its setting that has a rules pack.
        None when neither says (no setting, or a setting whose systems have several packs or none)."""
        own = getattr(campaign, "game_system_id", None)
        if own is not None:
            return str(own)
        setting_id = getattr(campaign, "setting_id", None)
        if setting_id is None:
            return None
        systems = self._trusted(GameSystemManager).list(setting_id=setting_id)
        packed = [system for system in systems if system.slug and load_pack(system.slug) is not None]
        return str(packed[0].id) if len(packed) == 1 else None

    def _module_pack(self, campaign: Any, system: Any) -> Optional[dict[str, Any]]:
        """A system with no committed pack (a private instance's lines) runs by the rules of a content
        module enabled on the campaign for that system: the Foundry bridge's rules step writes them in
        a pack's shape (test, skill ranks, difficulties, characteristics, skills, and character
        creation). None when no enabled module of the system has rules."""
        modules = self._trusted(ContentModuleManager)
        for link in self._trusted(CampaignModuleManager).list(campaign_id=campaign.id):
            try:
                module = modules.get(id=link.content_module_id)
            except HTTPException:
                continue
            rules = getattr(module, "rules", None)
            if rules and str(getattr(module, "game_system_id", "") or "") == str(system.id) and rules.get("test"):
                return {**rules, "system": system.slug}
        return None

    def _pack_for(self, campaign: Any) -> dict[str, Any]:
        """The rules pack of the campaign's game system, or a 422 saying it has none."""
        system_id = self.system_id_of(campaign)
        system = None if system_id is None else self._get(GameSystemManager, "GameSystemModel", system_id)
        pack = None if system is None or not system.slug else load_pack(system.slug)
        if pack is None and system is not None:
            pack = self._module_pack(campaign, system)
        if pack is None:
            raise HTTPException(
                status_code=422,
                detail={"message": "This campaign's game system has no rules pack yet; use a check instead"},
            )
        return pack

    def test_options_for(self, body: TestOptionsRequest) -> TestOptionsOut:
        """What a test can name for this character: the pack's characteristics, skills (with
        whether each can be attempted untrained) and difficulties, for a dice tray to offer."""
        person, campaign, gm = self._character(body.person_id)
        pack = self._pack_for(campaign)
        difficulties = pack["difficulties"]
        return TestOptionsOut(
            person_id=person.id,
            system=pack["system"],
            characteristics=[
                TestOptionOut(slug=one["slug"], name=one["name"], short=one.get("short"))
                for one in pack["characteristics"]
            ],
            skills=[
                TestOptionOut(
                    slug=one["slug"],
                    name=one["name"],
                    characteristic=one["characteristic"],
                    untrainable=bool(one.get("specialist")),
                    specialisations=(
                        sorted(
                            {
                                row.specialisation.strip()
                                for row in self._skill_rows(person.id, one, campaign, gm)
                                if getattr(row, "specialisation", None)
                            },
                            key=str.casefold,
                        )
                        if one.get("specialist")
                        else []
                    ),
                )
                for one in pack["skills"]
            ],
            difficulties=[
                DifficultyOut(slug=slug, modifier=0, dc=value)
                if pack["test"]["kind"] == "d20-over"
                else DifficultyOut(slug=slug, modifier=value)
                for slug, value in difficulties.items()
                if slug not in ("default", "cite")
            ],
            default_difficulty=difficulties["default"],
            has_sheet=self._has_sheet(person.id, pack, campaign, gm),
            test_kind=str(pack["test"].get("kind", "d100-under")),
        )

    def sheet_for(self, body: SheetRequest) -> SheetOut:
        """A character's sheet, read-only: their characteristics, skills (rank and specialisation),
        resources (wounds, fate…), origin steps, other abilities (talents, traits, powers, feats) and
        owned gear. For the campaign's GM or the character's own player; a player never sees a trait
        they couldn't read themselves (a GM's secret)."""
        person, campaign, gm = self._character(body.person_id)
        system_id = self.system_id_of(campaign)
        system = None if system_id is None else self._get(GameSystemManager, "GameSystemModel", system_id)
        traits = self._trusted(TraitManager)
        sections: dict[str, list[SheetEntry]] = {"characteristics": [], "skills": [], "resources": [], "origins": [], "abilities": []}
        for row in self._trusted(PersonTraitManager).list(person_id=person.id):
            if not _live(row) or row.trait_id is None:
                continue
            try:
                trait = traits.get(id=row.trait_id)
            except HTTPException:
                continue
            if not gm and getattr(trait, "campaign_id", None) is not None and not self._readable(TraitManager, trait.id):
                continue
            kind = trait.kind or ""
            entry = SheetEntry(
                trait_id=trait.id,
                slug=trait.slug,
                name=trait.name or "",
                kind=kind or None,
                value=None if row.value is None else float(row.value),
                rank=None if row.rank is None else int(row.rank),
                specialisation=getattr(row, "specialisation", None),
            )
            section = (
                "characteristics"
                if kind in SHEET_CHARACTERISTICS
                else "skills"
                if kind == "skill"
                else "resources"
                if kind == "resource"
                else "origins"
                if kind in SHEET_ORIGINS
                else "abilities"
            )
            sections[section].append(entry)
        for entries in sections.values():
            entries.sort(key=lambda one: (one.name.casefold(), (one.specialisation or "").casefold()))
        gear = self._gear(person.id)
        state = None
        try:
            from zephyrex.extensions.rpg_combat.Recovery import Recovery  # type: ignore[import-not-found]
        except ImportError:
            pass  # no rpg_combat: no lasting state to show
        else:
            state = Recovery(self.model_registry, campaign).state(person.id)
        return SheetOut(
            person_id=person.id,
            name=getattr(person, "name", None),
            system=None if system is None else system.slug,
            has_sheet=any(one.value is not None for one in sections["characteristics"]),
            gear=gear,
            state=state,
            **sections,
        )

    def _gear(self, person_id: str) -> list[SheetItem]:
        """What the character carries: the wiki's items_carried (its carry rows, and gear owned that
        lies nowhere), else, on a wiki without it, the instances they own."""
        from zephyrex.extensions.AbstractExtensionProvider import loaded_ability

        call = loaded_ability(self.model_registry, "rpg_core", "items_carried")
        if call is not None:
            answer = call(self.model_registry, str(env("SYSTEM_ID")), person_ids=[str(person_id)])
            if hasattr(answer, "__await__"):
                from zephyrex.logic.AbstractLogicManager.manager import _cache_sync_run

                answer = _cache_sync_run(answer)
            return [
                SheetItem(id=str(one["item_instance_id"]), item_id=one.get("item_id"), name=one.get("name") or None, quantity=int(one.get("quantity") or 1))
                for one in ((answer or {}).get("items") or {}).get(str(person_id), [])
            ]
        items = self._trusted(ItemManager)
        gear = []
        for instance in self._trusted(ItemInstanceManager).list(owner_person_id=person_id):
            try:
                item_name = None if instance.item_id is None else items.get(id=instance.item_id).name
            except HTTPException:
                item_name = None
            gear.append(SheetItem(id=instance.id, item_id=instance.item_id, name=item_name, quantity=int(instance.quantity or 1)))
        return gear

    def _has_sheet(self, person_id: str, pack: dict[str, Any], campaign: Any, gm: bool) -> bool:
        """Whether the character holds a value for any of the pack's characteristics."""
        rows = self._trusted(PersonTraitManager)
        for one in pack["characteristics"]:
            try:
                trait = self._trait_for(stat_name(one["name"]), campaign, gm)
            except HTTPException:
                continue
            if any(row.value is not None and _live(row) for row in rows.list(person_id=person_id, trait_id=trait.id)):
                return True
        return False

    def _level(self, person_id: str, campaign: Any, gm: bool) -> Optional[int]:
        """The character's level (a Level trait), for a d20 pack's Proficiency Bonus; none without one."""
        try:
            trait = self._trait_for(stat_name("Level"), campaign, gm)
        except HTTPException:
            return None
        values = self._person_values(person_id, trait.id)
        return int(max(values)) if values else None

    def _d20_test(
        self, body: TestRequest, person: Any, campaign: Any, gm: bool, pack: dict[str, Any],
        skill: Optional[dict[str, Any]], trait: Any, rank: Optional[int], no_sheet: bool,
    ) -> TestOut:
        """A D20 Test (a d20-over pack: the 5e SRD): ability modifier, Proficiency Bonus by level when
        proficient, against the difficulty's DC; a character with no score tests at the pack's human
        average, flagged no_sheet."""
        if no_sheet:
            score = float(pack["test"]["no_sheet_score"])
            stat = StatOut(name=stat_name(trait.name or ""), trait_id=trait.id, base=score, value=score, steps=[])
        else:
            stat = self._resolve(person.id, trait, [], self._worn_items(person.id), gm)
        die = int(pack["test"].get("die", 20))
        rolls = [live_draw(die)]
        if body.advantage is not None:
            rule = pack["test"].get("advantage")
            if not rule:
                raise HTTPException(status_code=422, detail={"message": f"{pack['system']}'s test has no {body.advantage}"})
            rolls = [live_draw(die) for _ in range(int(rule["dice"]))]
        kept = rolls[0]
        if body.advantage is not None:
            kept = max(rolls) if pack["test"]["advantage"][body.advantage] == "higher" else min(rolls)
        try:
            outcome = d20_test(
                pack,
                score=None if no_sheet else stat.value,
                roll=kept,
                skill_rank=rank,
                level=self._level(person.id, campaign, gm) if rank else None,
                difficulty=body.difficulty,
                modifiers=body.modifiers,
            )
        except TestError as error:
            raise HTTPException(status_code=422, detail={"message": str(error)}) from error
        return TestOut(
            person_id=person.id,
            system=pack["system"],
            name=body.name,
            specialisation=None,
            kind="skill" if skill else "characteristic",
            characteristic=stat,
            skill_rank=rank,
            trained=skill is None or rank is not None,
            target=outcome.target,
            roll=outcome.roll,
            success=outcome.success,
            degrees=None,
            natural=None,
            steps=outcome.steps,
            mechanic="d20",
            natural_roll=kept if kept in (1, die) else None,
            total=outcome.total,
            test_kind="d20-over",
            no_sheet=no_sheet,
            advantage=body.advantage,
            rolls=rolls,
        )

    def test_for(self, body: TestRequest) -> TestOut:
        """A test under the campaign's system pack (d100 roll-under with degrees, or a d20-over test),
        rolled on the server: the characteristic resolved as a check resolves a stat, plus the
        skill's rank, the difficulty and the modifiers."""
        person, campaign, gm = self._character(body.person_id)
        pack = self._pack_for(campaign)
        skills = {one["slug"]: one for one in pack["skills"]}
        characteristics = {one["slug"]: one for one in pack["characteristics"]}
        skill = skills.get(body.name)
        characteristic = characteristics.get(skill["characteristic"] if skill else body.name)
        if characteristic is None:
            raise HTTPException(
                status_code=422, detail={"message": f"{pack['system']} has no characteristic or skill {body.name!r}"}
            )
        specialist = bool(skill and skill["specialist"])
        if specialist and not _same(body.specialisation):
            raise HTTPException(
                status_code=422,
                detail={"message": f"Name which {skill['name']} this is, e.g. {skill['name']} (Stars)"},
            )
        if not specialist and body.specialisation:
            raise HTTPException(status_code=422, detail={"message": f"{body.name} has no specialisations"})
        trait = self._trait_for(stat_name(characteristic["name"]), campaign, gm)
        rank = None if skill is None else self._skill_rank(person.id, skill, campaign, gm, body.specialisation)
        no_sheet = not self._person_values(person.id, trait.id)
        if pack["test"]["kind"] == "d20-over":
            return self._d20_test(body, person, campaign, gm, pack, skill, trait, rank, no_sheet)
        if body.advantage is not None:
            raise HTTPException(status_code=422, detail={"message": f"{pack['system']}'s test has no {body.advantage}"})
        if no_sheet and pack["test"].get("no_sheet_score") is None:
            # The pack's rulebook states no average to test a sheetless character at (not every rulebook does):
            # a value is needed, never a made-up number.
            raise HTTPException(
                status_code=422,
                detail={
                    "message": f"{person.name or 'This character'} has no {characteristic['name']}, and "
                    f"{pack['system']} states no average to test at: give them a {characteristic['name']} value"
                },
            )
        stat = self._resolve(person.id, trait, [], self._worn_items(person.id), gm)
        trained = skill is None or rank is not None
        try:
            outcome = percentile_test(
                pack,
                characteristic=round(stat.value),
                roll=live_draw(100),
                skill_rank=rank,
                trained=trained,
                specialist=specialist,
                difficulty=body.difficulty,
                modifiers=body.modifiers,
            )
        except TestError as error:
            raise HTTPException(status_code=422, detail={"message": str(error)}) from error
        return TestOut(
            person_id=person.id,
            system=pack["system"],
            name=body.name,
            specialisation=body.specialisation.strip() if specialist and body.specialisation else None,
            kind="skill" if skill else "characteristic",
            characteristic=stat,
            skill_rank=rank,
            trained=trained,
            target=outcome.target,
            roll=outcome.roll,
            success=outcome.success,
            degrees=outcome.degrees,
            natural=outcome.natural,
            steps=outcome.steps,
            rolls=[outcome.roll],
        )

    def initiative_for(self, body: InitiativeRequest) -> InitiativeOut:
        """A character's initiative under the campaign's system pack, rolled on the server: the
        pack's dice plus the bonus of its characteristic (a percentile pack: 1d10 + a characteristic's
        tens). ``value`` is the characteristic itself, which breaks ties."""
        person, campaign, gm = self._character(body.person_id)
        pack = self._pack_for(campaign)
        rule = pack.get("initiative")
        if rule is None:
            raise HTTPException(
                status_code=422, detail={"message": f"{pack['system']}'s pack has no initiative rule yet"}
            )
        names = {one["slug"]: one["name"] for one in pack["characteristics"]}
        trait = self._trait_for(stat_name(names[rule["characteristic"]]), campaign, gm)
        if not self._person_values(person.id, trait.id):
            average = pack["test"].get("no_sheet_score")
            if average is None:
                # No value to read a bonus from, and no average the rulebook states: the GM sets it.
                raise HTTPException(
                    status_code=422,
                    detail={"message": f"{person.name or 'This character'} has no {names[rule['characteristic']]} to roll initiative with"},
                )
            stat = StatOut(name=stat_name(trait.name or ""), trait_id=trait.id, base=float(average), value=float(average), steps=[])
        else:
            stat = self._resolve(person.id, trait, [], self._worn_items(person.id), gm)
        rolled = self.roll_formula(rule["dice"])
        bonus = initiative_bonus(stat.value, rule["bonus"])
        return InitiativeOut(
            person_id=person.id,
            system=pack["system"],
            dice=rule["dice"],
            roll=int(rolled.total),
            characteristic=rule["characteristic"],
            value=stat.value,
            bonus=bonus,
            total=int(rolled.total) + bonus,
        )

    @custom_route(
        method="POST",
        path="/roll",
        input_model=RollEnvelope,
        output_model=RollResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Dice",),
        summary="Roll a formula on the server (A21)",
    )
    async def roll_route(self, body: RollEnvelope) -> RollResultEnvelope:
        return RollResultEnvelope(roll=self.roll_formula(body.roll.formula))

    @custom_route(
        method="POST",
        path="/check",
        input_model=CheckEnvelope,
        output_model=CheckResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Dice",),
        summary="Roll a check for a character, their @stats resolved from their traits (A21)",
    )
    async def check_route(self, body: CheckEnvelope) -> CheckResultEnvelope:
        return CheckResultEnvelope(check=self.check_for(body.check))

    @custom_route(
        method="POST",
        path="/test",
        input_model=TestEnvelope,
        output_model=TestResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Dice",),
        summary="Roll a test under the campaign's system pack (d100 with degrees, or a d20 test)",
    )
    async def test_route(self, body: TestEnvelope) -> TestResultEnvelope:
        return TestResultEnvelope(test=self.test_for(body.test))

    @custom_route(
        method="POST",
        path="/sheet",
        input_model=SheetEnvelope,
        output_model=SheetResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Dice",),
        summary="A character's sheet, read-only: characteristics, skills, resources, origins, abilities and gear",
    )
    async def sheet_route(self, body: SheetEnvelope) -> SheetResultEnvelope:
        return SheetResultEnvelope(sheet=self.sheet_for(body.sheet))

    @custom_route(
        method="POST",
        path="/test-options",
        input_model=TestOptionsEnvelope,
        output_model=TestOptionsResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Dice",),
        summary="What a test can name for a character under the campaign's system pack (a dice tray's choices)",
    )
    async def test_options_route(self, body: TestOptionsEnvelope) -> TestOptionsResultEnvelope:
        return TestOptionsResultEnvelope(options=self.test_options_for(body.options))

    @custom_route(
        method="POST",
        path="/initiative",
        input_model=InitiativeEnvelope,
        output_model=InitiativeResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Dice",),
        summary="Roll a character's initiative under the campaign's system pack (its dice plus a characteristic's bonus)",
    )
    async def initiative_route(self, body: InitiativeEnvelope) -> InitiativeResultEnvelope:
        return InitiativeResultEnvelope(initiative=self.initiative_for(body.initiative))
