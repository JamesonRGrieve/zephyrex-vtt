# SPDX-License-Identifier: AGPL-3.0-or-later
"""A character's lasting state (CharacterStateModel): hit points that outlast a fight, rests, healing
and conditions, under the campaign's rules pack (Zephyrex RPG, 2026-11-28: "the story follows the
game's state"). The pack says what a rest does (``rest``), which conditions there are
(``conditions``), each class's Hit Point Die (``leveling.hit_die``) and what a healing consumable
heals (``consumables``); a system whose pack doesn't say has no rest and accepts any condition name.

A character with no state row is at its sheet's maximum, nothing spent, no condition. Every write is
the server's own (ROOT), made after the caller's GM check."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from fastapi import HTTPException
from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager
from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignManager  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_dice.BLL_RPGDice import DiceManager, live_draw  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_dice.Dice import roll
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import PersonTraitManager, TraitManager  # type: ignore[import-not-found]
from zephyrex.lib.Environment import env

Draw = Callable[[int], int]


def _refuse(message: str) -> HTTPException:
    return HTTPException(status_code=422, detail={"message": message})


def _not_found(model: str) -> HTTPException:
    return HTTPException(status_code=404, detail={"message": f"Request searched {model} and could not find the required record."})


def _live(manager: Any, **filters: Any) -> list[Any]:
    return list(manager.list(filters=[manager.DB.deleted_at.is_(None)], **filters))


def _modifier(score: Optional[float]) -> int:
    """A d20 pack's ability modifier: (score − 10) / 2, rounded down; 0 without a score."""
    return 0 if score is None else (int(score) - 10) // 2


class Recovery:
    """One campaign's characters' lasting state, for a requester already known to be its GM (or the
    server)."""

    def __init__(self, model_registry: Any, campaign: Any, draw: Draw = live_draw) -> None:
        self.model_registry = model_registry
        self.campaign = campaign
        self.draw = draw
        self.dice = DiceManager(requester_id=env("ROOT_ID"), model_registry=model_registry)
        system_id = self.dice.system_id_of(campaign)
        self.system_id = None if system_id is None else str(system_id)
        try:
            self.pack: dict[str, Any] = self.dice._pack_for(campaign)
        except HTTPException:
            self.pack = {}

    def _trusted(self, manager: type[Any]) -> Any:
        return manager(requester_id=env("ROOT_ID"), model_registry=self.model_registry)

    # The record.

    def row(self, person_id: str) -> Any | None:
        from zephyrex.extensions.rpg_combat.BLL_RPGCombat import CharacterStateManager

        found = _live(self._trusted(CharacterStateManager), person_id=person_id)
        return found[0] if found else None

    def write(self, person_id: str, **values: Any) -> Any:
        from zephyrex.extensions.rpg_combat.BLL_RPGCombat import CharacterStateManager

        states = self._trusted(CharacterStateManager)
        if "conditions" in values and isinstance(values["conditions"], list):
            values["conditions"] = json.dumps(values["conditions"]) if values["conditions"] else None
        row = self.row(person_id)
        if row is None:
            return states.create(person_id=person_id, **values)
        return states.update(id=row.id, **values)

    def sheet(self, person_id: str) -> tuple[dict[str, float], dict[str, float], list[str]]:
        """The character's characteristics and resources by slug, and its classes' names."""
        traits = self._trusted(TraitManager)
        scores: dict[str, float] = {}
        resources: dict[str, float] = {}
        classes: list[str] = []
        for value in _live(self._trusted(PersonTraitManager), person_id=person_id):
            try:
                trait = traits.get(id=value.trait_id)
            except HTTPException:
                continue
            if getattr(trait, "deleted_at", None) is not None or not trait.slug:
                continue
            if self.system_id is not None and str(getattr(trait, "game_system_id", "") or "") not in ("", self.system_id):
                continue
            if trait.kind == "characteristic" and value.value is not None:
                scores[trait.slug] = float(value.value)
            elif trait.kind == "resource" and value.value is not None:
                resources[trait.slug] = float(value.value)
            elif trait.kind == "class" and trait.name:
                classes.append(str(trait.name))
        return scores, resources, classes

    def state(self, person_id: str) -> dict[str, Any]:
        """The character's state as character_sheet and the abilities report it: hit points now and
        their maximum, its Hit Point Dice (die, total, spent, left), Exhaustion and conditions."""
        row = self.row(person_id)
        scores, resources, classes = self.sheet(person_id)
        hp_max = None if resources.get("hit-points") is None else int(resources["hit-points"])
        hp = getattr(row, "hp", None)
        hit_die = next((int(die) for name, die in ((self.pack.get("leveling") or {}).get("hit_die") or {}).items() if name in classes), None)
        level = self.dice._level(person_id, self.campaign, True) if hit_die is not None else None
        total = int(level or 0) if hit_die is not None else 0
        spent = int(getattr(row, "hit_dice_spent", 0) or 0)
        return {
            "hp": hp_max if hp is None else int(hp),
            "hp_max": hp_max,
            "hit_dice": None if hit_die is None else {"die": f"d{hit_die}", "total": total, "spent": spent, "left": max(0, total - spent)},
            "exhaustion": int(getattr(row, "exhaustion", 0) or 0),
            "conditions": self.conditions(row),
        }

    @staticmethod
    def conditions(row: Any) -> list[str]:
        raw = getattr(row, "conditions", None)
        if not raw:
            return []
        try:
            found = json.loads(raw)
        except ValueError:
            return []
        return [str(one) for one in found] if isinstance(found, list) else []

    # Hit points.

    def set_hp(self, person_id: str, hp: int) -> dict[str, Any]:
        """Hit points now (a hit in a fight, a heal): kept between 0 and the maximum; at 0 a character
        gains the pack's at-zero condition (Unconscious), and regaining any ends it."""
        state = self.state(person_id)
        hp_max = state["hp_max"]
        hp = max(0, hp if hp_max is None else min(hp, hp_max))
        conditions = list(state["conditions"])
        at_zero = (self.pack.get("conditions") or {}).get("at_zero_hit_points")
        person = self._trusted(PersonManager).get(id=person_id)
        if at_zero and getattr(person, "kind", None) == "pc":
            if hp == 0 and at_zero not in conditions:
                conditions.append(at_zero)
            elif hp > 0 and state["hp"] == 0 and at_zero in conditions:
                conditions.remove(at_zero)
        self.write(person_id, hp=hp, conditions=conditions)
        self._sync_fights(person_id, hp)
        return self.state(person_id)

    def _sync_fights(self, person_id: str, hp: int) -> None:
        """A heal mid-fight shows in the fight: the character's combatant in a running encounter."""
        from zephyrex.extensions.rpg_combat.BLL_RPGCombat import CombatantManager, EncounterManager

        encounters = self._trusted(EncounterManager)
        combatants = self._trusted(CombatantManager)
        for one in _live(combatants, person_id=person_id):
            try:
                encounter = encounters.get(id=one.encounter_id)
            except HTTPException:
                continue
            if encounter.status != "ended" and one.hp_max is not None:
                combatants.update_trusted(id=one.id, hp=hp, is_defeated=hp == 0)

    def heal(self, person_id: str, formula: str) -> dict[str, Any]:
        rolled = roll(formula, self.draw)
        before = self.state(person_id)
        after = self.set_hp(person_id, int(before["hp"] or 0) + int(rolled.total))
        return {"formula": formula, "rolled": int(rolled.total), "hp_before": before["hp"], **after}

    # Rest.

    def _fighting(self) -> bool:
        from zephyrex.extensions.rpg_combat.BLL_RPGCombat import EncounterManager

        return any(one.status == "running" for one in _live(self._trusted(EncounterManager), campaign_id=self.campaign.id))

    def rest(self, person_id: str, kind: str, hit_dice: Optional[int] = None) -> dict[str, Any]:
        """One character's rest of ``kind`` (the pack's: short or long), as the pack's rest rules say.
        A Short Rest spends Hit Point Dice, each rolled plus the Constitution modifier (at least the
        minimum), one at a time until the character is whole or the dice (or ``hit_dice``, at most)
        run out; a Long Rest restores all hit points and Hit Point Dice and takes Exhaustion levels
        off. A character below the hit points a rest needs to start gets none of it (``refused``)."""
        rules = (self.pack.get("rest") or {}).get(kind)
        before = self.state(person_id)
        person = self._trusted(PersonManager).get(id=person_id)
        out: dict[str, Any] = {"person_id": person_id, "name": getattr(person, "name", None), "hp_before": before["hp"]}
        needs = int(rules.get("needs_hit_points") or 0) if rules else 0
        if before["hp"] is not None and before["hp"] < needs:
            return {**out, **before, "refused": f"A {kind} rest needs at least {needs} Hit Point{'s' if needs != 1 else ''} to start"}
        conditions = list(before["conditions"])
        if kind == "long":
            exhaustion = max(0, before["exhaustion"] + int(rules.get("exhaustion") or 0))
            if exhaustion == 0 and "Exhaustion" in conditions:
                conditions.remove("Exhaustion")
            self.write(person_id, hp=before["hp_max"], hit_dice_spent=0, exhaustion=exhaustion, conditions=conditions)
            if before["hp_max"] is not None:
                self._sync_fights(person_id, int(before["hp_max"]))
            return {**out, **self.state(person_id), "rolls": []}
        dice = before["hit_dice"]
        rolls: list[dict[str, Any]] = []
        hp = before["hp"]
        if dice is not None and hp is not None and before["hp_max"] is not None:
            scores, _, _ = self.sheet(person_id)
            spend = rules.get("hit_dice") or {}
            bonus = _modifier(scores.get(str(spend.get("characteristic") or "constitution")))
            least = int(spend.get("minimum") or 1)
            sides = int(dice["die"][1:])
            budget = dice["left"] if hit_dice is None else min(dice["left"], max(0, int(hit_dice)))
            while budget > 0 and hp < before["hp_max"]:
                face = int(self.draw(sides))
                gained = max(least, face + bonus)
                hp = min(before["hp_max"], hp + gained)
                rolls.append({"die": dice["die"], "roll": face, "modifier": bonus, "regained": gained})
                budget -= 1
            if rolls:
                self.write(person_id, hit_dice_spent=dice["spent"] + len(rolls))
                self.set_hp(person_id, hp)
        return {**out, **self.state(person_id), "rolls": rolls}

    def rest_all(self, person_ids: list[str], kind: str, hit_dice: Optional[int] = None) -> dict[str, Any]:
        kinds = [one for one in (self.pack.get("rest") or {}) if one != "cite"]
        if not kinds:
            raise _refuse(f"{self.pack.get('system') or 'This system'}'s rules pack has no rest rules")
        if kind not in kinds:
            raise _refuse(f"A rest is {' or '.join(kinds)}, not {kind!r}")
        if self._fighting():
            raise _refuse("Rolling Initiative interrupts a rest: end the fight first")
        return {"kind": kind, "rested": [self.rest(person_id, kind, hit_dice) for person_id in person_ids]}

    # Conditions.

    def set_condition(self, person_id: str, condition: str, present: bool = True) -> dict[str, Any]:
        """Give a character a condition, or take one off. The pack's conditions only, where it lists
        them (by name, any case); a levelled condition (Exhaustion) goes up or down a level instead,
        and ends at 0; ``dies`` says when its last level is reached."""
        table = self.pack.get("conditions") or {}
        names = list(table.get("names") or [])
        name = next((one for one in names if one.casefold() == condition.strip().casefold()), None) if names else condition.strip()
        if not name:
            raise _refuse(f"{condition!r} isn't a condition here: {', '.join(names)}" if names else "Name the condition")
        state = self.state(person_id)
        conditions = list(state["conditions"])
        levelled = (table.get("levelled") or {}).get(name)
        dies = False
        if levelled is not None:
            level = max(0, state["exhaustion"] + (int(levelled.get("per") or 1) * (1 if present else -1)))
            dies = level >= int(levelled.get("dies_at") or 10**6)
            if level > 0 and name not in conditions:
                conditions.append(name)
            if level == 0 and name in conditions:
                conditions.remove(name)
            self.write(person_id, exhaustion=level, conditions=conditions)
        else:
            if present and name not in conditions:
                conditions.append(name)
            if not present and name in conditions:
                conditions.remove(name)
            self.write(person_id, conditions=conditions)
        return {"person_id": person_id, "condition": name, "present": name in self.state(person_id)["conditions"], "dies": dies, **self.state(person_id)}

    # Items.

    def consumable(self, item: Any) -> Optional[dict[str, Any]]:
        """The pack's consumable an item is: by its compendium source, else by its name's slug."""
        source = str(getattr(item, "compendium_source", "") or "")
        name = str(getattr(item, "name", "") or "")
        slug = "-".join("".join(ch if ch.isalnum() else " " for ch in name.lower()).split())
        for one in self.pack.get("consumables") or []:
            if source and source in (one.get("uuids") or []):
                return dict(one)
        return next((dict(one) for one in self.pack.get("consumables") or [] if one.get("slug") == slug), None)


def recovery_for(model_registry: Any, requester_id: str, campaign_id: str, draw: Draw = live_draw) -> Recovery:
    """The campaign's Recovery, for its GM (or the server); anyone else a 404."""
    try:
        campaign = CampaignManager(requester_id=env("ROOT_ID"), model_registry=model_registry).get(id=campaign_id)
    except HTTPException as error:
        raise _not_found("CampaignModel") from error
    owners = {str(one) for one in (campaign.user_id, getattr(campaign, "created_by_user_id", None)) if one}
    if getattr(campaign, "deleted_at", None) is not None or (
        str(requester_id) not in owners and str(requester_id) not in {str(env("ROOT_ID")), str(env("SYSTEM_ID"))}
    ):
        raise _not_found("CampaignModel")
    return Recovery(model_registry, campaign, draw)


def campaign_of_person(model_registry: Any, person_id: str) -> str:
    try:
        person = PersonManager(requester_id=env("ROOT_ID"), model_registry=model_registry).get(id=person_id)
    except HTTPException as error:
        raise _not_found("PersonModel") from error
    if getattr(person, "deleted_at", None) is not None or not getattr(person, "campaign_id", None):
        raise _not_found("PersonModel")
    return str(person.campaign_id)
