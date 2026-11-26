# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_scene extension: scenes, tokens and walls, and what a token perceives, as a route
(BLL_RPGScene) and as the ``scene_snapshot`` ability the AI GM calls (A23)."""

from typing import Any, ClassVar, Optional

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension, ability, backend_selector, loaded_ability
from zephyrex.extensions.rpg_scene.BLL_RPGScene import PlaceOnScopeRequest, SceneManager, ScopeRequest, SnapshotRequest, UvttRequest
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
                name="world_spatial",
                friendly_name="World Spatial",
                optional=False,
                reason="A scene and its regions are the wiki's locations on a map",
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
    def on_start(cls) -> None:
        """A playthrough started from a scenario gets the scenario's scenes and tokens: the copy registered with
        the wiki's register_instantiate_hook (BLL_RPGScene.register_copy)."""
        from zephyrex.extensions.rpg_scene.BLL_RPGScene import register_copy
        from zephyrex.lib.Logging import logger
        from zephyrex.pydantic2.registry import ModelRegistry

        try:
            registry = ModelRegistry.attached()
            if registry is not None and not register_copy(registry):
                logger.warning("rpg_scene: the wiki offers no instantiate hook; scenes and tokens aren't copied on start")
        except Exception as error:  # the copy is extra: the app boots without it
            logger.warning(f"rpg_scene: no copy on instantiate: {error}")
        try:
            # A setting made system level (the wiki's system_adopt, ed56c11+) takes its scenes and tokens too.
            from zephyrex.extensions.rpg_scene.Adopt import register_adopt

            registry = ModelRegistry.attached()
            if registry is not None and not register_adopt(registry):
                logger.info("rpg_scene: the wiki offers no adopt hook; system_adopt leaves its scenes and tokens as they are")
        except Exception as error:  # the adoption is extra: the app boots without it
            logger.warning(f"rpg_scene: no adopt hook: {error}")

    @classmethod
    @backend_selector
    async def backend_for(cls, ability_name: str, arguments: dict[str, Any]) -> Optional[str]:
        """Which backend serves this call (the operator's framework selector, sf 72f51160): the
        campaign's, as the wiki says (by campaign_id, a scene's campaign or a person's), for a campaign kept in an external tabletop; None (this
        extension's own) for a native campaign, an unknown one, or a wiki with no campaign_backend.
        Only keyword arguments reach a selector, so a positional campaign stays native."""
        from zephyrex.lib.Environment import env
        from zephyrex.pydantic2.registry import ModelRegistry

        # An fvtt: id is always Foundry's (the wiki's rule): no lookup.
        if any(str(arguments.get(key) or "").startswith("fvtt:") for key in ("campaign_id", "scene_id", "encounter_id", "person_id")):
            return "foundry"
        registry = ModelRegistry.attached()
        ask = None if registry is None else loaded_ability(registry, "rpg_core", "campaign_backend")
        if ask is None:
            return None
        campaign_id = arguments.get("campaign_id")
        if not campaign_id and arguments.get("scene_id"):
            scene = SceneManager(requester_id=str(env("ROOT_ID")), model_registry=registry)._get(SceneManager, str(arguments["scene_id"]))
            campaign_id = None if scene is None else scene.campaign_id
        person_id = arguments.get("person_id")
        if not campaign_id and not person_id:
            return None
        answer = ask(registry, str(env("SYSTEM_ID")), campaign_id=campaign_id, person_id=person_id)
        if hasattr(answer, "__await__"):
            answer = await answer
        backend = (answer or {}).get("backend")
        return None if backend in (None, "", "native") else str(backend)

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

    @classmethod
    @ability("import_uvtt")
    async def import_uvtt(cls, requester_id: str, scene_id: str, uvtt: dict[str, Any], replace: bool = True) -> dict[str, Any]:
        """A Universal VTT map's (.uvtt / .dd2vtt JSON) walls, doors and lights onto a scene, which
        takes the map's size and grid: {scene_id, level, width, height, grid_size, walls, doors,
        lights, removed}. replace takes off the scene's hand-placed and imported walls and lights
        first. The art is the scene's background, set apart (set_scene_background). The campaign's
        GM only."""
        return cls.scenes(requester_id).import_uvtt_for(scene_id, UvttRequest(uvtt=uvtt, replace=replace)).model_dump()

    @classmethod
    @ability("map_location")
    async def map_location(
        cls,
        requester_id: str,
        location_id: str,
        uvtt: Optional[dict[str, Any]] = None,
        image_base64: Optional[str] = None,
        image_name: Optional[str] = None,
        name: Optional[str] = None,
        grid_size: Optional[float] = None,
        floor: int = 0,
        asset_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """A place's map made into its scene (the vault's map beside a location note: a picture, a
        .dd2vtt/.uvtt, or both): the campaign's (a scenario's) scene bound to that place, made if it
        has none, takes the UVTT's walls, doors, lights, size and grid and the picture (given, else
        the UVTT's embedded art) as its background, uploaded and attached to the place as its map.
        A large picture goes up first (POST /v1/asset/upload, its raw bytes) and comes here as its
        ``asset_id``, used as the art (base64 in the request would exceed a body's limit).
        ``floor`` names which floor of the place (0, the one it opens on; then 1, 2…): each floor is
        its own scene, named "<place> (level N)" unless ``name`` says. Returns {scene_id, floor,
        created, name, width, height, grid_size, background_url, asset_id, walls, doors, lights}.
        Again with the same file and floor it updates the same scene; a start copies them all.
        The campaign's GM only (wiki's vault_import as the importer)."""
        from zephyrex.extensions.rpg_scene.BLL_RPGScene import LocationMapRequest

        body = LocationMapRequest(
            location_id=location_id, uvtt=uvtt, image_base64=image_base64, image_name=image_name, name=name, grid_size=grid_size, floor=floor,
            asset_id=asset_id,
        )
        return (await cls.scenes(requester_id).map_location_for(body)).model_dump()

    @classmethod
    @ability("scene_scope")
    async def scene_scope(cls, requester_id: str, campaign_id: str, location_id: Optional[str] = None) -> dict[str, Any]:
        """The map at a place's scope (a building, its town, the region): {campaign_id, location,
        scope (its kind), parent (scope out to it; none at the top), path (top down), background
        {url, scene_id, label}, markers [{location_id, name, kind, picture, x, y (0 to 1 across
        and down the map), placed, people [{person_id, name, picture}], count}] (each place inside
        it that NPCs are in, however deep, as one group), parties [{location_id, x, y, people}]
        (the player characters, their own group where they are), here [NPCs at the place itself]}.
        No location: the current scene's place, else the party's. The campaign's GM and players;
        GM-only records are the GM's alone."""
        return cls.scenes(requester_id).scope_for(ScopeRequest(campaign_id=campaign_id, location_id=location_id)).model_dump()

    @classmethod
    @ability("place_on_scope")
    async def place_on_scope(cls, requester_id: str, campaign_id: str, location_id: str, x: float, y: float) -> dict[str, Any]:
        """Pin a place's marker on its parent's map (x and y 0 to 1 across and down it); returns the
        parent's scope, as scene_scope. The campaign's GM only."""
        body = PlaceOnScopeRequest(campaign_id=campaign_id, location_id=location_id, x=x, y=y)
        return cls.scenes(requester_id).place_on_scope_for(body).model_dump()

    @classmethod
    @ability("scene_tokens")
    async def scene_tokens(cls, requester_id: str, scene_id: str) -> list[dict[str, Any]]:
        """Who is on a scene: each token (token_id, name) and the wiki person it stands for
        (entity_id, or none). The campaign's GM gets every token, hidden ones flagged (hidden: true);
        a player of the campaign gets only the ones not hidden."""
        return [one.model_dump() for one in cls.scenes(requester_id).tokens_for(scene_id)]

    @classmethod
    @ability("current_scene")
    async def current_scene(cls, requester_id: str, campaign_id: str) -> dict[str, Any] | None:
        """A campaign's current scene ({id, name, campaign_id, location_id, width, height,
        grid_size}) for its GM or players: the active one, else its first, else a default grid scene
        made at the party's wiki location with their tokens; None only for a non-member. A chat on a split party may override it with its
        own scene; otherwise the table plays here."""
        found = cls.scenes(requester_id).current_scene_for(campaign_id)
        return None if found is None else found.model_dump()

    @classmethod
    @ability("set_scene_background")
    async def set_scene_background(cls, requester_id: str, scene_id: str, background_url: str | None) -> dict[str, Any]:
        """Set a scene's own map picture (a generated battlemap's link, e.g. /v1/asset/{id}/content),
        drawn under its grid over its place's picture; None clears it. Returns the scene's summary,
        background_url included. The campaign's GM."""
        return cls.scenes(requester_id).set_background_for(scene_id, background_url).model_dump()

    @classmethod
    @ability("move_token_to_scene")
    async def move_token_to_scene(cls, requester_id: str, token_id: str, scene_id: str) -> dict[str, Any]:
        """Move a token to another scene of its campaign (the story moves someone): off this scene, at
        the target's entry on the nearest free cell; a character's token moves as pilot_token moves
        them (one token per person, their wiki location following). The campaign's GM."""
        return cls.scenes(requester_id).move_token_to_scene_for(token_id, scene_id).model_dump()

    @classmethod
    @ability("place_person")
    async def place_person(
        cls,
        requester_id: str,
        scene_id: str,
        person_id: str,
        near_person_id: str | None = None,
        x: float | None = None,
        y: float | None = None,
    ) -> dict[str, Any]:
        """Put a person of the campaign on a scene (an NPC just authored mid-play): beside
        ``near_person_id``'s token (the seat's character), else at a point, else at the entry, on the
        nearest free cell; one token per person. Returns the token's place. The campaign's GM."""
        from zephyrex.extensions.rpg_scene.BLL_RPGScene import PlaceRequest

        body = PlaceRequest(person_id=person_id, near_person_id=near_person_id, x=x, y=y)
        return cls.scenes(requester_id).place_person_for(scene_id, body).model_dump()

    @classmethod
    @ability("remove_person_from_scene")
    async def remove_person_from_scene(cls, requester_id: str, scene_id: str, person_id: str) -> dict[str, Any]:
        """Take a person's token off a scene (they left, the story not saying where): their wiki
        location is left as it is. Returns {scene_id, person_id, removed}; removed is false when they
        had no token there. The campaign's GM only."""
        from zephyrex.extensions.rpg_scene.BLL_RPGScene import RemoveRequest

        return cls.scenes(requester_id).remove_person_for(scene_id, RemoveRequest(person_id=person_id)).model_dump()

    @classmethod
    @ability("copy_scenes")
    async def copy_scenes(
        cls, requester_id: str, from_campaign_id: str, to_campaign_id: str, id_map: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        """Copy a campaign's scenes with everything on them into another campaign (a scenario's maps
        into a playthrough started from it), remapping wiki ids by ``id_map`` (source → copy: persons,
        locations); the source's current scene is current in the copy. The target campaign's GM."""
        found = cls.scenes(requester_id).copy_scenes_for(from_campaign_id, to_campaign_id, id_map or {})
        return [one.model_dump() for one in found]

    @classmethod
    @ability("activate_scene")
    async def activate_scene(cls, requester_id: str, scene_id: str) -> dict[str, Any]:
        """Make a scene its campaign's current scene, and no other (the campaign's GM)."""
        return cls.scenes(requester_id).activate_scene_for(scene_id).model_dump()

    @classmethod
    @ability("pilot_token")
    async def pilot_token(
        cls,
        requester_id: str,
        person_id: str,
        location_id: str | None = None,
        scene_id: str | None = None,
        x: float | None = None,
        y: float | None = None,
        max_distance: float | None = None,
    ) -> dict[str, Any]:
        """The GM moves a character, for routines as time advances: to a wiki ``location_id`` (vtt
        finds the map: a region of that place, a scene of it, or a parent's), or to ``scene_id`` at
        (x, y) or its entry point. On the same scene the token walks round walls within the scene,
        at most ``max_distance`` scene units if given ({arrived: false, remaining} when stopped short);
        on another scene it moves there, on the nearest free cell. A place no map shows takes the
        character off the maps (tokens removed, {removed}). The person's wiki location follows.
        422 when there's no way through. Returns {person_id, token_id, scene_id, x, y, arrived,
        remaining, removed, location_id}. The campaign's GM only."""
        return cls.scenes(requester_id).pilot_for(person_id, location_id, scene_id, x, y, max_distance).model_dump()
