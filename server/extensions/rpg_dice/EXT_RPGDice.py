# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_dice extension: the referee's dice, as routes (BLL_RPGDice) and as abilities a framework agent
calls (the AI GM's ``roll`` and ``check``, A21): mechanics come from here, never from a model."""

from typing import Any, ClassVar, Optional

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension, ability
from zephyrex.extensions.rpg_dice.BLL_RPGDice import CheckRequest, DiceManager
from zephyrex.lib.Dependencies import Dependencies, EXT_Dependency


class RPGDiceExtension(AbstractStaticExtension):
    name: ClassVar[str] = "rpg_dice"
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = "Dice notation, roll tables, and rolls and checks made on the server"
    dependencies: ClassVar[Dependencies] = Dependencies(
        [
            EXT_Dependency(
                name="rpg_traits",
                friendly_name="Rpg Traits",
                optional=False,
                reason="Checks resolve a character's stats from their traits",
            ),
            EXT_Dependency(
                name="rpg_core",
                friendly_name="Rpg Core",
                optional=False,
                reason="A check's access rule reads the campaign's GM and the character's player",
            ),
            EXT_Dependency(
                name="world_inventory",
                friendly_name="World Inventory",
                optional=False,
                reason="Items a character wears count toward their stats",
            ),
            EXT_Dependency(
                name="world_spatial",
                friendly_name="World Spatial",
                optional=False,
                reason="A worn item sits in a character's equipment-slot or body-part location",
            ),
        ]
    )

    @classmethod
    def dice(cls, requester_id: str) -> DiceManager:
        manager: DiceManager = cls.as_requester(DiceManager, requester_id)
        return manager

    @classmethod
    @ability("roll")
    async def roll(cls, requester_id: str, formula: str) -> dict[str, Any]:
        """Roll dice notation on the server (e.g. ``2d20kh1 + 3``): the total and every die."""
        return cls.dice(requester_id).roll_formula(formula).model_dump()

    @classmethod
    @ability("check")
    async def check(
        cls,
        requester_id: str,
        person_id: str,
        formula: str,
        target: Optional[float] = None,
        compare: str = ">=",
        qualifiers: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Roll a check for a character: ``@stat`` in the formula is their resolved trait (e.g.
        ``1d20 + @dexterity`` against 15, or ``1d100`` at or under ``@weapon_skill`` with ``<=``).
        The result says whether it succeeded, by how much, and why each stat is what it is."""
        body = CheckRequest(
            person_id=person_id, formula=formula, target=target, compare=compare, qualifiers=qualifiers or []
        )
        return cls.dice(requester_id).check_for(body).model_dump()
