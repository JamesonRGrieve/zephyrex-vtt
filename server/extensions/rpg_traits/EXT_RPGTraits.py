# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_traits extension definition: traits, and the ``check_requirements`` ability (a plot hook's
state for the campaign's party, its character checks decided by the traits they hold)."""

from typing import Any, ClassVar

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension, ability
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import PersonTraitManager
from zephyrex.extensions.rpg_traits.Party import PartyChecks
from zephyrex.lib.Dependencies import Dependencies, EXT_Dependency


class RPGTraitsExtension(AbstractStaticExtension):
    name: ClassVar[str] = "rpg_traits"
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = "Traits, how they derive from one another, and each character's values"
    dependencies: ClassVar[Dependencies] = Dependencies(
        [
            EXT_Dependency(
                name="rpg_systems",
                friendly_name="Rpg Systems",
                optional=False,
                reason="A trait belongs to a game system",
            ),
            EXT_Dependency(
                name="rpg_core",
                friendly_name="Rpg Core",
                optional=False,
                reason="A trait may belong to a campaign, and its values to a character",
            ),
            EXT_Dependency(
                name="genealogy",
                friendly_name="Genealogy",
                optional=False,
                reason="A character's values are on genealogy's persons",
            ),
            EXT_Dependency(
                name="world_narrative",
                friendly_name="World Narrative",
                optional=False,
                reason="Plot hooks, whose character checks the party's traits decide",
            ),
        ]
    )

    @classmethod
    @ability("check_requirements")
    async def check_requirements(cls, requester_id: str, campaign_id: str, hook_id: str) -> dict[str, Any]:
        """A plot hook's state for the campaign's party: resolved, available or blocked, with the
        character checks it fails (``unmet_checks``). A check gates whether the party may attempt the
        hook, never a roll's outcome. For the campaign's GM or one of its players."""
        manager: PersonTraitManager = cls.as_requester(PersonTraitManager, requester_id)
        return PartyChecks(manager.model_registry, requester_id).check(campaign_id, hook_id)
