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
from zephyrex.extensions.rpg_dice.BLL_RPGDice import DiceManager, stat_name  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import PersonTraitManager  # type: ignore[import-not-found]
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
        rows = [row for row in self._trusted(AbilityRollManager).list(person_id=person_id) if not getattr(row, "deleted_at", None)]
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
            live = [row for row in rows.list(person_id=person.id, trait_id=trait.id) if not getattr(row, "deleted_at", None)]
            if live:
                rows.update_trusted(id=live[0].id, value=value)
            else:
                rows.create(person_id=person.id, trait_id=trait.id, value=value)
        if rolled is not None:
            self._trusted(AbilityRollManager).update_trusted(id=rolled.id, is_used=True)
        return self.options_for(person.id)

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
