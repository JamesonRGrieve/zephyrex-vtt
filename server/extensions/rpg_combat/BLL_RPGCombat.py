# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_combat: an encounter (a fight in a campaign, perhaps on a scene), its combatants, and the
initiative order it runs in, round by round.

The campaign's GM runs an encounter: they add combatants, roll initiative, start it, pass the turn and
end it. Initiative is rolled on the server under the campaign's rules pack (rpg_dice: its dice plus a
characteristic's bonus); ties go to the higher characteristic, then to a roll-off, as the pack says. A combatant with no stats to roll (an NPC without a sheet) keeps the initiative the GM sets.

The order is read by the GM, and by a player with a character in the campaign; hidden combatants are
the GM's alone. Round, the current combatant and the status are server-written: they change only
through start, next and end, never through an update.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal, Optional, Type

from fastapi import HTTPException
from pydantic import BaseModel as PlainModel
from pydantic import Field
from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager, PersonModel
from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignManager, CampaignModel  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_combat.Attacks import Attack, armor_class, attacks_for, resolve
from zephyrex.extensions.rpg_dice.BLL_RPGDice import DiceManager, InitiativeRequest, live_draw  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import PersonTraitManager, TraitManager  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_scene.BLL_RPGScene import SceneManager, SceneModel, SceneTokenManager, SceneTokenModel  # type: ignore[import-not-found]
from zephyrex.lib.CustomRoute import ExposeIn, custom_route
from zephyrex.lib.Environment import env
from zephyrex.lib.Rooms import room_of
from zephyrex.logic.AbstractLogicManager import (
    AbstractBLLManager,
    ApplicationModel,
    ModelMeta,
    NameMixinModel,
    StringSearchModel,
    UpdateMixinModel,
)
from zephyrex.pydantic2.fastapi import RouterMixin
from zephyrex.pydantic2.registry import BaseModel  # type: ignore[attr-defined]

Status = Literal["setup", "running", "ended"]


class EncounterModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    CampaignModel.Reference.Optional,
    SceneModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["EncounterManager"]] = None
    status: Optional[Status] = Field("setup", description="setup, running or ended (start, end)")
    round: Optional[int] = Field(0, description="The round being fought; 0 before the start")
    current_combatant_id: Optional[str] = Field(None, description="Whose turn it is (next)")
    table_comment: ClassVar[str] = "A fight in a campaign, perhaps on a scene; its GM runs it"

    class Create(BaseModel, CampaignModel.Reference.ID, SceneModel.Reference.ID.Optional):
        name: str = Field("Encounter")

    class Update(BaseModel):
        name: Optional[str] = None

    class Search(ApplicationModel.Search, CampaignModel.Reference.ID.Search, SceneModel.Reference.ID.Search):
        status: Optional[StringSearchModel] = None
        name: Optional[StringSearchModel] = None


class CombatantModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    EncounterModel.Reference.Optional,
    PersonModel.Reference.Optional,
    SceneTokenModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["CombatantManager"]] = None
    initiative: Optional[float] = Field(None, description="Rolled (or set by the GM); highest acts first")
    tiebreak: Optional[float] = Field(None, description="The initiative characteristic, which breaks ties")
    roll_off: Optional[int] = Field(None, description="A d10, for ties the characteristic leaves")
    is_defeated: Optional[bool] = Field(False, description="Out of the fight: skipped when the turn passes")
    is_hidden: Optional[bool] = Field(False, description="The GM's alone (an ambusher not yet seen)")
    hp: Optional[int] = Field(None, description="Hit points now, in this fight; from the sheet when first needed")
    hp_max: Optional[int] = Field(None, description="The hit point maximum, from the sheet")
    reaction_round: Optional[int] = Field(None, description="The round its reaction was used in; free again the next round")
    action_round: Optional[int] = Field(None, description="The round it took its action in, on its turn")
    table_comment: ClassVar[str] = "A character in an encounter, with their initiative"

    class Create(
        BaseModel, EncounterModel.Reference.ID, PersonModel.Reference.ID.Optional, SceneTokenModel.Reference.ID.Optional
    ):
        name: Optional[str] = Field(None, description="Defaults to the character's name")
        initiative: Optional[float] = None
        is_hidden: bool = False

    class Update(BaseModel):
        name: Optional[str] = None
        initiative: Optional[float] = None
        is_defeated: Optional[bool] = None
        is_hidden: Optional[bool] = None

    class Search(ApplicationModel.Search, EncounterModel.Reference.ID.Search, PersonModel.Reference.ID.Search):
        name: Optional[StringSearchModel] = None


def _not_found(model: str) -> HTTPException:
    return HTTPException(
        status_code=404, detail={"message": f"Request searched {model} and could not find the required record."}
    )


def _refuse(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"message": message})


def _live(manager: Any, **filters: Any) -> list[Any]:
    """A trusted manager's rows without soft-deleted ones (ROOT reads include tombstones)."""
    return list(manager.list(filters=[manager.DB.deleted_at.is_(None)], **filters))


def _gms_of(campaign: Any) -> set[str]:
    """A campaign's GM: its owner, or its creator for a campaign made without one."""
    if campaign is None:
        return set()
    return {str(owner) for owner in (campaign.user_id, getattr(campaign, "created_by_user_id", None)) if owner}


def ordered(combatants: list[Any]) -> list[Any]:
    """Initiative order (p. 218): highest initiative first; ties to the higher characteristic, then
    the higher roll-off; combatants with no initiative yet last, by name."""

    def key(one: Any) -> tuple[Any, ...]:
        rolled = one.initiative is not None
        return (
            not rolled,
            -(one.initiative or 0),
            -(one.tiebreak if one.tiebreak is not None else -1),
            -(one.roll_off or 0),
            (one.name or "").casefold(),
            one.id,
        )

    return sorted(combatants, key=key)


class CombatantOut(PlainModel):
    id: str
    name: Optional[str]
    person_id: Optional[str]
    scene_token_id: Optional[str]
    initiative: Optional[float]
    is_defeated: bool
    is_hidden: bool
    controlled: bool = Field(description="The requester's own character, or (for the GM) every combatant")


class Unrolled(PlainModel):
    combatant_id: str
    name: Optional[str]
    reason: str


class OrderOut(PlainModel):
    id: str
    name: Optional[str]
    campaign_id: Optional[str]
    scene_id: Optional[str]
    status: str
    round: int
    current_combatant_id: Optional[str]
    gm: bool
    combatants: list[CombatantOut]
    unrolled: list[Unrolled] = Field(default_factory=list, description="Combatants a roll left without initiative")


class OrderEnvelope(PlainModel):
    encounter: OrderOut


class RollRequest(PlainModel):
    reroll: bool = Field(False, description="Roll again for combatants who already have initiative")


class RollEnvelope(PlainModel):
    roll: RollRequest = Field(default_factory=RollRequest)


class ControlEnvelope(PlainModel):
    # Nothing to say beyond the encounter in the path; a POST's typed body all the same.
    control: dict[str, Any] = Field(default_factory=dict)


class CurrentRequest(PlainModel):
    campaign_id: str


class CurrentEnvelope(PlainModel):
    current: CurrentRequest


class CurrentOut(PlainModel):
    encounter: Optional[OrderOut]


class CombatOptionsRequest(PlainModel):
    person_id: str


class CombatOptionsEnvelope(PlainModel):
    combat_options: CombatOptionsRequest


class ReactionOut(PlainModel):
    available: bool
    trigger: Optional[str] = Field(None, description="What would provoke it; none until triggers are modelled")


class CombatActionOut(PlainModel):
    id: str
    kind: Literal["attack", "spell", "other"]
    name: str
    needs_target: bool
    targets: list[str] = Field(default_factory=list, description="The person ids it may target")
    slot_levels: list[int] = Field(default_factory=list, description="A spell's castable slot levels (spells come later)")
    summary: str


class CombatTargetOut(PlainModel):
    person_id: str
    name: str
    hostile: bool
    hp: Optional[int] = None


class CombatOptionsOut(PlainModel):
    encounter_id: str
    person_id: str
    turn: bool = Field(description="Whether it's this combatant's turn")
    action_available: bool = Field(description="Its turn, and its action not yet taken this round")
    reaction: ReactionOut
    actions: list[CombatActionOut]
    targets: list[CombatTargetOut]
    reach: Literal["unchecked"] = Field("unchecked", description="Distance isn't checked yet: every target is offered")
    hp: Optional[int] = None
    hp_max: Optional[int] = None


class CombatOptionsResultEnvelope(PlainModel):
    combat_options: CombatOptionsOut


class CombatActionRequest(PlainModel):
    person_id: str
    action_id: str
    target_ids: list[str] = Field(default_factory=list, max_length=1)
    slot_level: Optional[int] = None
    use_reaction: bool = Field(False, description="Take it as the combatant's reaction, off its turn")


class CombatActionEnvelope(PlainModel):
    combat_action: CombatActionRequest


class CombatActionResultOut(PlainModel):
    encounter_id: str
    person_id: str
    action_id: str
    name: str
    target_id: Optional[str] = None
    hit: bool
    critical: bool
    roll: int
    total: int
    target_ac: int
    damage: int
    damage_roll: Optional[dict[str, Any]] = None
    target_hp: Optional[int] = Field(None, description="The target's hit points after the damage")
    target_defeated: bool = False
    steps: list[dict[str, Any]] = Field(default_factory=list)


class CombatActionResultEnvelope(PlainModel):
    combat_action: CombatActionResultOut


class _Combat:
    """Reads as the system once a rule has passed, and who the campaign's GM is."""

    model_registry: Any
    requester: Any

    def _trusted(self, manager: type[Any]) -> Any:
        return manager(requester_id=env("ROOT_ID"), model_registry=self.model_registry)

    def _find(self, manager: type[Any], record_id: Optional[str]) -> Any | None:
        if record_id is None:
            return None
        try:
            found = self._trusted(manager).get(id=record_id)
        except HTTPException:
            return None
        return None if getattr(found, "deleted_at", None) else found

    def _campaign_of(self, encounter: Any) -> Any | None:
        return self._find(CampaignManager, encounter.campaign_id)

    def _is_gm(self, campaign: Any) -> bool:
        return str(self.requester.id) in _gms_of(campaign)

    def _gm_encounter(self, encounter_id: str) -> tuple[Any, Any]:
        """The encounter and its campaign, for the campaign's GM; anyone else gets a 404."""
        encounter = self._find(EncounterManager, encounter_id)
        campaign = None if encounter is None else self._campaign_of(encounter)
        if encounter is None or not self._is_gm(campaign):
            raise _not_found("EncounterModel")
        return encounter, campaign


class EncounterManager(_Combat, AbstractBLLManager, RouterMixin):
    """Encounters, and running one: initiative, start, the turn, the end."""

    _model = EncounterModel

    def create(self, **kwargs: Any) -> Any:
        campaign = self._find(CampaignManager, kwargs.get("campaign_id"))
        if campaign is None or not self._is_gm(campaign):
            raise _not_found("CampaignModel")
        scene_id = kwargs.get("scene_id")
        if scene_id is not None:
            scene = self._find(SceneManager, scene_id)
            if scene is None or scene.campaign_id != campaign.id:
                raise _refuse("That scene isn't in this campaign")
        return super().create(**kwargs)

    def _members(self, encounter: Any) -> list[Any]:
        return _live(self._trusted(CombatantManager), encounter_id=encounter.id)

    def order_for(self, encounter_id: str, unrolled: Optional[list[Unrolled]] = None) -> OrderOut:
        """The encounter in initiative order, as the requester may see it: the GM every combatant,
        a player with a character in the campaign those not hidden; anyone else a 404."""
        encounter = self._find(EncounterManager, encounter_id)
        campaign = None if encounter is None else self._campaign_of(encounter)
        if encounter is None or campaign is None:
            raise _not_found("EncounterModel")
        requester = str(self.requester.id)
        gm = self._is_gm(campaign)
        if not gm:
            players = {getattr(one, "user_id", None) for one in _live(self._trusted(PersonManager), campaign_id=campaign.id)}
            if requester not in players:
                raise _not_found("EncounterModel")
        owners: dict[str, Optional[str]] = {}
        shown = []
        for one in ordered(self._members(encounter)):
            if one.is_hidden and not gm:
                continue
            if one.person_id and one.person_id not in owners:
                person = self._find(PersonManager, one.person_id)
                owners[one.person_id] = None if person is None else getattr(person, "user_id", None)
            shown.append(
                CombatantOut(
                    id=one.id,
                    name=one.name,
                    person_id=one.person_id,
                    scene_token_id=one.scene_token_id,
                    initiative=one.initiative,
                    is_defeated=bool(one.is_defeated),
                    is_hidden=bool(one.is_hidden),
                    controlled=gm or (one.person_id is not None and owners.get(one.person_id) == requester),
                )
            )
        current = encounter.current_combatant_id
        if current is not None and not any(one.id == current for one in shown):
            current = None  # a hidden combatant's turn: players see no one's
        return OrderOut(
            id=encounter.id,
            name=encounter.name,
            campaign_id=encounter.campaign_id,
            scene_id=encounter.scene_id,
            status=encounter.status or "setup",
            round=int(encounter.round or 0),
            current_combatant_id=current,
            gm=gm,
            combatants=shown,
            unrolled=unrolled or [],
        )

    def roll_initiative_for(self, encounter_id: str, body: RollRequest) -> OrderOut:
        """Roll initiative for the combatants who have none (all of them with ``reroll``) under the
        campaign's pack; those with no stats to roll keep what the GM set, and are listed."""
        encounter, _ = self._gm_encounter(encounter_id)
        dice = DiceManager(requester_id=str(self.requester.id), model_registry=self.model_registry)
        combatants = self._trusted(CombatantManager)
        unrolled: list[Unrolled] = []
        for one in self._members(encounter):
            if one.initiative is not None and not body.reroll:
                continue
            if one.person_id is None:
                unrolled.append(Unrolled(combatant_id=one.id, name=one.name, reason="No character to roll for"))
                continue
            try:
                rolled = dice.initiative_for(InitiativeRequest(person_id=one.person_id))
            except HTTPException as error:
                detail = error.detail if isinstance(error.detail, dict) else {}
                unrolled.append(
                    Unrolled(combatant_id=one.id, name=one.name, reason=str(detail.get("message", "No stats to roll")))
                )
                continue
            # Server-written (a roll, never a client's value): update_trusted, outside the Update schema.
            combatants.update_trusted(
                id=one.id, initiative=float(rolled.total), tiebreak=float(rolled.value), roll_off=live_draw(10)
            )
        return self.order_for(encounter.id, unrolled)

    def start_for(self, encounter_id: str) -> OrderOut:
        """Start the fight: round 1, the first in the order to act. A combatant with no initiative yet
        (nothing on their sheet to roll, the GM's number not set) doesn't hold the fight up: they act
        after everyone who has one, in name order, and are listed as waiting until the GM sets it.
        Nothing is rolled for them that the pack doesn't state (operator: fights start before every
        sheet is built)."""
        encounter, _ = self._gm_encounter(encounter_id)
        if encounter.status == "ended":
            raise _refuse("This encounter has ended")
        members = ordered(self._members(encounter))
        acting = [one for one in members if not one.is_defeated]
        if not acting:
            raise _refuse("No one is left to fight")
        self._trusted(EncounterManager).update_trusted(
            id=encounter.id, status="running", round=1, current_combatant_id=acting[0].id
        )
        waiting = [
            Unrolled(combatant_id=one.id, name=one.name, reason="No initiative yet: acts last until the GM sets it")
            for one in members
            if one.initiative is None
        ]
        return self.order_for(encounter.id, waiting)

    def next_turn_for(self, encounter_id: str) -> OrderOut:
        """Pass the turn to the next combatant still fighting; after the last, a new round begins."""
        encounter, _ = self._gm_encounter(encounter_id)
        if encounter.status != "running":
            raise _refuse("This encounter isn't running")
        members = ordered(self._members(encounter))
        acting = [one for one in members if not one.is_defeated]
        if not acting:
            raise _refuse("No one is left to fight")
        ids = [one.id for one in members]
        at = ids.index(encounter.current_combatant_id) if encounter.current_combatant_id in ids else -1
        round_ = int(encounter.round or 1)
        following = [one for one in members[at + 1 :] if not one.is_defeated]
        if following:
            upcoming = following[0]
        else:
            upcoming, round_ = acting[0], round_ + 1
        self._trusted(EncounterManager).update_trusted(id=encounter.id, round=round_, current_combatant_id=upcoming.id)
        return self.order_for(encounter.id)

    def end_for(self, encounter_id: str) -> OrderOut:
        encounter, _ = self._gm_encounter(encounter_id)
        self._trusted(EncounterManager).update_trusted(id=encounter.id, status="ended", current_combatant_id=None)
        return self.order_for(encounter.id)

    def current_for(self, campaign_id: str) -> Optional[OrderOut]:
        """A campaign's fight in progress (running, else the newest still in setup), for anyone who
        may read it; none when there is none."""
        found = [one for one in _live(self._trusted(EncounterManager), campaign_id=campaign_id) if one.status != "ended"]
        if not found:
            return None
        found.sort(key=lambda one: (one.status != "running", -(one.created_at.timestamp() if one.created_at else 0)))
        try:
            return self.order_for(found[0].id)
        except HTTPException:
            return None

    # Combat choices (rpg-ai's decision models pick only among these) and their resolution.

    def _sheet(self, person: Any, system_id: str) -> tuple[dict[str, float], dict[str, float], list[str]]:
        """The person's ability scores and resources by slug, and the weapons on their sheet."""
        traits = {trait.id: trait for trait in _live(self._trusted(TraitManager), game_system_id=system_id) if trait.campaign_id is None}
        scores: dict[str, float] = {}
        resources: dict[str, float] = {}
        weapons: list[str] = []
        for row in _live(self._trusted(PersonTraitManager), person_id=person.id):
            trait = traits.get(row.trait_id)
            if trait is None or not trait.slug:
                continue
            if trait.kind == "characteristic" and row.value is not None:
                scores[trait.slug] = float(row.value)
            elif trait.kind == "resource" and row.value is not None:
                resources[trait.slug] = float(row.value)
            elif trait.kind == "weapon":
                weapons.append(trait.slug)
        return scores, resources, weapons

    def _fighter(self, encounter: Any, campaign: Any, person_id: str) -> tuple[Any, Any, dict[str, Any], list[Attack], int]:
        """A combatant's row, person, pack, attacks and AC, its hit points filled from the sheet."""
        combatant = next(
            (one for one in _live(self._trusted(CombatantManager), encounter_id=encounter.id) if one.person_id == person_id), None
        )
        if combatant is None:
            raise _refuse("That character isn't in this encounter")
        dice = DiceManager(requester_id=env("ROOT_ID"), model_registry=self.model_registry)
        pack = dice._pack_for(campaign)
        if not pack.get("attack"):
            raise _refuse(f"{pack['system']}'s pack has no attack rules yet")
        person = self._find(PersonManager, person_id)
        scores, resources, carried = self._sheet(person, str(dice.system_id_of(campaign)))
        by_slug = {one["slug"]: one for one in pack.get("weapons") or []}
        weapons = [by_slug[slug] for slug in carried if slug in by_slug]
        # The Proficiency Bonus on the sheet (an NPC's, by its CR), else by the character's Level.
        bonus = resources.get("proficiency-bonus")
        level = None if bonus is not None else dice._level(person_id, campaign, True)
        attacks = attacks_for(pack, weapons, scores, proficient=True, level=level)
        if bonus is not None:
            for one in attacks:
                one.to_hit += int(bonus)
                one.steps = [
                    step if step["step"] != "proficiency" else {"step": "proficiency", "value": int(bonus)} for step in one.steps
                ]
        if combatant.hp_max is None and resources.get("hit-points") is not None:
            hp = int(resources["hit-points"])
            self._trusted(CombatantManager).update_trusted(id=combatant.id, hp=hp, hp_max=hp)
            combatant = self._find(CombatantManager, combatant.id)
        return combatant, person, pack, attacks, armor_class(pack, scores, resources.get("armor-class"))

    def _side(self, combatant: Any, person: Any) -> str:
        """Whose side a combatant fights on: its token's disposition, else a player character friendly
        and anyone else hostile."""
        token = self._find(SceneTokenManager, getattr(combatant, "scene_token_id", None))
        if token is not None and getattr(token, "disposition", None):
            return str(token.disposition)
        return "friendly" if getattr(person, "kind", None) == "pc" else "hostile"

    def combat_options_for(self, encounter_id: str, body: CombatOptionsRequest) -> CombatOptionsOut:
        """A combatant's legal choices now, from its sheet and the system pack: whether it's its turn
        and its action is free, its reaction, its weapon attacks, and the other combatants it may
        target (distance isn't checked yet). The campaign's GM only."""
        encounter, campaign = self._gm_encounter(encounter_id)
        combatant, person, _, attacks, _ = self._fighter(encounter, campaign, body.person_id)
        side = self._side(combatant, person)
        round_now = int(encounter.round or 0)
        targets = []
        for other in _live(self._trusted(CombatantManager), encounter_id=encounter.id):
            if other.id == combatant.id or other.is_defeated or other.person_id is None:
                continue
            who = self._find(PersonManager, other.person_id)
            if who is None:
                continue
            theirs = self._side(other, who)
            hostile = "neutral" not in (side, theirs) and theirs != side
            targets.append(CombatTargetOut(person_id=who.id, name=other.name or who.name or "", hostile=hostile, hp=other.hp))
        turn = encounter.status == "running" and encounter.current_combatant_id == combatant.id
        ids = [one.person_id for one in targets]
        return CombatOptionsOut(
            encounter_id=encounter.id,
            person_id=body.person_id,
            turn=turn,
            action_available=turn and combatant.action_round != round_now,
            reaction=ReactionOut(available=encounter.status == "running" and combatant.reaction_round != round_now),
            actions=[
                CombatActionOut(id=one.id, kind="attack", name=one.name, needs_target=True, targets=ids, summary=one.summary())
                for one in attacks
            ],
            targets=targets,
            hp=combatant.hp,
            hp_max=combatant.hp_max,
        )

    def take_combat_action_for(self, encounter_id: str, body: CombatActionRequest) -> CombatActionResultOut:
        """Resolve one of combat_options' actions by the pack's rules, on the server: an attack roll
        against the target's AC and, on a hit, the damage taken from its hit points (at 0 it's
        defeated). Refused when the choice isn't one combat_options offers now. The GM only."""
        encounter, campaign = self._gm_encounter(encounter_id)
        options = self.combat_options_for(encounter_id, CombatOptionsRequest(person_id=body.person_id))
        action = next((one for one in options.actions if one.id == body.action_id), None)
        if action is None:
            raise _refuse("That isn't one of this combatant's actions now; combat_options lists them")
        if body.use_reaction:
            if not options.reaction.available:
                raise _refuse("Its reaction is already used this round")
        elif not options.action_available:
            raise _refuse("It isn't this combatant's turn, or its action is already taken this round")
        if body.slot_level is not None:
            raise _refuse("A weapon attack takes no spell slot")
        if len(body.target_ids) != 1 or body.target_ids[0] not in action.targets:
            raise _refuse("Name one target from the action's targets")
        combatant, _, pack, attacks, _ = self._fighter(encounter, campaign, body.person_id)
        attack = next(one for one in attacks if one.id == body.action_id)
        target, _, _, _, target_ac = self._fighter(encounter, campaign, body.target_ids[0])
        outcome = resolve(pack, attack, target_ac, live_draw)
        round_now = int(encounter.round or 0)
        combatants = self._trusted(CombatantManager)
        combatants.update_trusted(id=combatant.id, **({"reaction_round": round_now} if body.use_reaction else {"action_round": round_now}))
        hp = target.hp
        defeated = bool(target.is_defeated)
        if outcome.hit and hp is not None:
            hp = max(0, hp - outcome.damage)
            defeated = hp == 0
            combatants.update_trusted(id=target.id, hp=hp, is_defeated=defeated)
        return CombatActionResultOut(
            encounter_id=encounter.id,
            person_id=body.person_id,
            action_id=action.id,
            name=action.name,
            target_id=body.target_ids[0],
            hit=outcome.hit,
            critical=outcome.critical,
            roll=outcome.roll,
            total=outcome.total,
            target_ac=target_ac,
            damage=outcome.damage,
            damage_roll=outcome.damage_roll,
            target_hp=hp,
            target_defeated=defeated,
            steps=outcome.steps,
        )

    @custom_route(
        method="POST",
        path="/{encounter_id}/options",
        input_model=CombatOptionsEnvelope,
        output_model=CombatOptionsResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Combat",),
        summary="A combatant's legal choices now: its turn, reaction, attacks and targets (the campaign's GM)",
    )
    async def options_route(self, encounter_id: str, body: CombatOptionsEnvelope) -> CombatOptionsResultEnvelope:
        return CombatOptionsResultEnvelope(combat_options=self.combat_options_for(encounter_id, body.combat_options))

    @custom_route(
        method="POST",
        path="/{encounter_id}/action",
        input_model=CombatActionEnvelope,
        output_model=CombatActionResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Combat",),
        summary="Take one of combat_options' actions, resolved by the pack's rules on the server (the campaign's GM)",
    )
    async def action_route(self, encounter_id: str, body: CombatActionEnvelope) -> CombatActionResultEnvelope:
        return CombatActionResultEnvelope(combat_action=self.take_combat_action_for(encounter_id, body.combat_action))

    @custom_route(
        method="GET",
        path="/{encounter_id}/order",
        output_model=OrderEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Combat",),
        summary="An encounter in initiative order, as the requester may see it",
    )
    async def order_route(self, encounter_id: str) -> OrderEnvelope:
        return OrderEnvelope(encounter=self.order_for(encounter_id))

    @custom_route(
        method="POST",
        path="/{encounter_id}/initiative",
        input_model=RollEnvelope,
        output_model=OrderEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Combat",),
        summary="Roll initiative under the campaign's pack (the campaign's GM)",
    )
    async def initiative_route(self, encounter_id: str, body: RollEnvelope) -> OrderEnvelope:
        return OrderEnvelope(encounter=self.roll_initiative_for(encounter_id, body.roll))

    @custom_route(
        method="POST",
        path="/{encounter_id}/start",
        input_model=ControlEnvelope,
        output_model=OrderEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Combat",),
        summary="Start an encounter: round 1, the first in the order to act (the campaign's GM)",
    )
    async def start_route(self, encounter_id: str, body: ControlEnvelope) -> OrderEnvelope:
        return OrderEnvelope(encounter=self.start_for(encounter_id))

    @custom_route(
        method="POST",
        path="/{encounter_id}/next",
        input_model=ControlEnvelope,
        output_model=OrderEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Combat",),
        summary="Pass the turn; after the last combatant a new round begins (the campaign's GM)",
    )
    async def next_route(self, encounter_id: str, body: ControlEnvelope) -> OrderEnvelope:
        return OrderEnvelope(encounter=self.next_turn_for(encounter_id))

    @custom_route(
        method="POST",
        path="/{encounter_id}/end",
        input_model=ControlEnvelope,
        output_model=OrderEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Combat",),
        summary="End an encounter (the campaign's GM)",
    )
    async def end_route(self, encounter_id: str, body: ControlEnvelope) -> OrderEnvelope:
        return OrderEnvelope(encounter=self.end_for(encounter_id))

    @custom_route(
        method="POST",
        path="/current",
        input_model=CurrentEnvelope,
        output_model=CurrentOut,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Combat",),
        summary="A campaign's fight in progress, in initiative order, or none",
    )
    async def current_route(self, body: CurrentEnvelope) -> CurrentOut:
        return CurrentOut(encounter=self.current_for(body.current.campaign_id))


class CombatantManager(_Combat, AbstractBLLManager, RouterMixin):
    """An encounter's combatants: the campaign's GM adds, edits and removes them."""

    _model = CombatantModel

    def create(self, **kwargs: Any) -> Any:
        encounter = self._find(EncounterManager, kwargs.get("encounter_id"))
        campaign = None if encounter is None else self._campaign_of(encounter)
        if encounter is None or not self._is_gm(campaign):
            raise _not_found("EncounterModel")
        person = self._find(PersonManager, kwargs.get("person_id"))
        if kwargs.get("person_id") is not None and (person is None or person.campaign_id != campaign.id):
            raise _refuse("That character isn't in this campaign")
        token = self._find(SceneTokenManager, kwargs.get("scene_token_id"))
        if kwargs.get("scene_token_id") is not None and (token is None or token.scene_id != encounter.scene_id):
            raise _refuse("That token isn't on this encounter's scene")
        if not kwargs.get("name"):
            kwargs["name"] = (person.name if person is not None else None) or (token.name if token is not None else None)
        if not kwargs.get("name"):
            raise _refuse("Name the combatant, or give the character it is")
        return super().create(**kwargs)


EncounterModel.Manager = EncounterManager
CombatantModel.Manager = CombatantManager

# Live rooms (server-framework `rooms`; inert when the app doesn't load it): an encounter and its
# combatants change in the encounter's room; an encounter is also news in its campaign's room (a
# fight started, ended), so a play screen hears of a new one. Changes carry no record data, so a
# hidden combatant never leaks: viewers refetch the order, which decides what each may see.
room_of(
    EncounterManager,
    lambda one: [("encounter", one.id)] + ([("campaign", one.campaign_id)] if one.campaign_id else []),
)
room_of(CombatantManager, lambda one: ("encounter", one.encounter_id) if one.encounter_id else None)
