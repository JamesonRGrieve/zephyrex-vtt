# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_state extension definition."""

from typing import ClassVar

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension
from zephyrex.lib.Dependencies import Dependencies, EXT_Dependency


class RPGStateExtension(AbstractStaticExtension):
    name: ClassVar[str] = "rpg_state"
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = "Narrative hooks and faction endpoints on relationships, until the wiki takes them"
    dependencies: ClassVar[Dependencies] = Dependencies(
        [
            EXT_Dependency(
                name="genealogy",
                friendly_name="Genealogy",
                optional=False,
                reason="It widens genealogy's relationships with faction endpoints",
            ),
            EXT_Dependency(
                name="rpg_core",
                friendly_name="Rpg Core",
                optional=False,
                reason="A hook belongs to a campaign",
            ),
            EXT_Dependency(
                name="world_social",
                friendly_name="World Social",
                optional=False,
                reason="Faction hooks and endpoints name the wiki's factions",
            ),
        ]
    )
