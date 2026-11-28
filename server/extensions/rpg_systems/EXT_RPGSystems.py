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

    @classmethod
    def on_start(cls) -> None:
        """The VTT's rows go with the wiki records they belong to: Removal.remove_for registered with
        the wiki's register_remove_hook (a campaign's delete, and remove_orphaned_records)."""
        from zephyrex.extensions.rpg_systems.Removal import register_remove
        from zephyrex.lib.Logging import logger
        from zephyrex.pydantic2.registry import ModelRegistry

        try:
            registry = ModelRegistry.attached()
            if registry is not None and not register_remove(registry):
                logger.info("rpg_systems: the wiki offers no remove hook; a removed campaign's VTT rows stay")
        except Exception as error:  # the removal is extra: the app boots without it
            logger.warning(f"rpg_systems: no remove hook: {error}")

    @classmethod
    @ability("sweep_orphans")
    async def sweep_orphans(cls, requester_id: str, dry_run: bool = True) -> dict[str, Any]:
        """The VTT rows left behind by a campaign or person already gone (a playthrough deleted
        before the wiki's remove hook): {"vtt.<table>": count}, soft-deleted only when ``dry_run`` is
        false. The server's own accounts only (ROOT, SYSTEM); on prod, the operator runs it."""
        from fastapi import HTTPException

        from zephyrex.extensions.rpg_systems.Removal import sweep_orphans

        if str(requester_id) not in {str(env("ROOT_ID")), str(env("SYSTEM_ID"))}:
            raise HTTPException(status_code=403, detail={"message": "Only the server's own accounts sweep"})
        registry = cls.as_requester(GameSystemManager, requester_id).model_registry
        return {"dry_run": dry_run, "removed": sweep_orphans(registry, str(requester_id), dry_run)}
