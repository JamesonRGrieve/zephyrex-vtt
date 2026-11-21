# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_systems extension definition: game systems, and the ``game_systems`` ability (the catalog,
optionally for one of the wiki's settings)."""

from typing import Any, ClassVar, Optional

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension, ability
from zephyrex.extensions.rpg_systems.BLL_RPGSystems import GameSystemManager
from zephyrex.lib.Environment import env
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

    @classmethod
    @ability("game_systems")
    async def game_systems(cls, requester_id: str, setting_id: Optional[str] = None) -> list[dict[str, Any]]:
        """The game systems vtt knows, by name, optionally only those of one of the wiki's settings:
        [{id, slug, name, setting_id}]. The catalog is the rules, public to anyone signed in, so it is
        read as the system. A campaign's system is its game_system_id; checks run under it through
        the character's traits (rpg_dice ``check``)."""
        registry = cls.as_requester(GameSystemManager, requester_id).model_registry
        catalog = GameSystemManager(requester_id=env("ROOT_ID"), model_registry=registry)
        rows = catalog.list(setting_id=setting_id) if setting_id else catalog.list()
        systems = [{"id": row.id, "slug": row.slug, "name": row.name, "setting_id": row.setting_id} for row in rows]
        return sorted(systems, key=lambda one: (one["name"] or "").lower())
