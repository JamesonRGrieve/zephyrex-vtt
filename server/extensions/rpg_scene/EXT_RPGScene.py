# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_scene extension: scenes, tokens and walls, and what a token perceives, as a route
(BLL_RPGScene) and as the ``scene_snapshot`` ability the AI GM calls (A23)."""

from typing import Any, ClassVar

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension, ability
from zephyrex.extensions.rpg_scene.BLL_RPGScene import SceneManager, SnapshotRequest
from zephyrex.lib.Dependencies import Dependencies, EXT_Dependency


class RPGSceneExtension(AbstractStaticExtension):
    name: ClassVar[str] = "rpg_scene"
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = "Scenes, tokens and walls, and what each token perceives"
    dependencies: ClassVar[Dependencies] = Dependencies(
        [
            EXT_Dependency(
                name="rpg_core",
                friendly_name="Rpg Core",
                optional=False,
                reason="A scene belongs to a campaign, and a token stands for one of its characters",
            ),
            EXT_Dependency(
                name="genealogy",
                friendly_name="Genealogy",
                optional=False,
                reason="A token stands for one of genealogy's persons",
            ),
        ]
    )

    @classmethod
    def scenes(cls, requester_id: str) -> SceneManager:
        manager: SceneManager = cls.as_requester(SceneManager, requester_id)
        return manager

    @classmethod
    @ability("scene_snapshot")
    async def scene_snapshot(cls, requester_id: str, scene_id: str, token_id: str) -> dict[str, Any]:
        """What a token perceives in its scene, decided on the server: the tokens it sees (nearest
        first, with their distance in the scene's units) and the doors. Hidden tokens and what walls
        cut off are never included."""
        return cls.scenes(requester_id).snapshot_for(scene_id, SnapshotRequest(token_id=token_id)).model_dump()
