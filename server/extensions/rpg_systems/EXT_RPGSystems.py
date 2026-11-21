# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_systems extension definition."""

from typing import ClassVar

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension
from zephyrex.lib.Dependencies import Dependencies, EXT_Dependency


class RPGSystemsExtension(AbstractStaticExtension):
    name: ClassVar[str] = "rpg_systems"
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = "Game systems, and the game system of the wiki's campaigns and items"
    dependencies: ClassVar[Dependencies] = Dependencies(
        [
            EXT_Dependency(
                name="rpg_core",
                friendly_name="Rpg Core",
                optional=False,
                reason="It adds game_system_id to the wiki's campaigns",
            ),
            EXT_Dependency(
                name="world_inventory",
                friendly_name="World Inventory",
                optional=False,
                reason="It adds game_system_id to the wiki's items",
            ),
        ]
    )
