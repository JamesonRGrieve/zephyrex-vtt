# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_traits extension definition."""

from typing import ClassVar

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension
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
        ]
    )
