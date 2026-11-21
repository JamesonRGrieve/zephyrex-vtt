# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_modules extension definition: private rules and content modules (BLL_RPGModules), installed
server-side from the Foundry bridge (Install.py; tools/foundry-bridge/install.py)."""

from typing import ClassVar

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension
from zephyrex.lib.Dependencies import Dependencies, EXT_Dependency


class RPGModulesExtension(AbstractStaticExtension):
    name: ClassVar[str] = "rpg_modules"
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = "Private rules and content modules, owned by the account that installs them"
    dependencies: ClassVar[Dependencies] = Dependencies(
        [
            EXT_Dependency(
                name="rpg_systems",
                friendly_name="Rpg Systems",
                optional=False,
                reason="A module is a game system's rules and content",
            ),
            EXT_Dependency(
                name="rpg_traits",
                friendly_name="Rpg Traits",
                optional=False,
                reason="A module's characteristics, skills, talents and the like are traits",
            ),
            EXT_Dependency(
                name="rpg_core",
                friendly_name="Rpg Core",
                optional=False,
                reason="A campaign enables the modules it plays with",
            ),
        ]
    )
