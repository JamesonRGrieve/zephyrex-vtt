# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_scene: a scene, its tokens and walls (OBJECT_PLAN §4, the fields A23 needs first), and what a
token perceives there (``POST /v1/scene/{scene_id}/snapshot``, the ``scene_snapshot`` ability).

The server is the referee for sight too (docs/DESIGN.md, Principle 5): Vision.py decides what a
token sees, and only that leaves the server. A snapshot is for the campaign's GM, or the player whose
character the token is; anyone else gets the same 404 as a scene that doesn't exist. Past that, the
scene is read as the system, so every wall and token counts whoever made it.

The map a scene holds is zephyr-cartography's model, shared (operator, 2026-11-21; docs/DESIGN.md,
"zephyr-cartography, native here"): a scene's features are the scene-spec v1 kinds (region, stroke,
path, room, stamp, pin, label, zone, shape, token), kept as they are in ``scene_features``; and the
walls, lights, tiles, notes and regions they generate are records of their own, each naming the
feature that made it, so editing a feature re-syncs only its own records (the module's lifecycle
rule). Hand-placed records have no feature. Art (a background, a tile's image, terrain masks) is the
framework's attachments, not a column. Levels are modelled from the start; play uses one first.

Not yet: fog memory, elevation in sight, and lights in what a token sees.
"""

from __future__ import annotations

import re

from typing import Any, ClassVar, Literal, Optional, Type

from fastapi import HTTPException, Response
from pydantic import BaseModel as PlainModel
from pydantic import Field
from zephyrex.lib.Rooms import room_of
from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager, PersonModel
from zephyrex.extensions.AbstractExtensionProvider import loaded_ability
from zephyrex.extensions.rpg_scene.Scopes import Person as ScopedPerson
from zephyrex.extensions.rpg_scene.Scopes import Place as ScopedPlace
from zephyrex.extensions.rpg_scene.Scopes import party_spot, scope as scope_of
from zephyrex.extensions.rpg_scene.Uvtt import UvttError, read as read_uvtt
from zephyrex.extensions.rpg_scene.Vision import FULL_CIRCLE, Scene, Token, Wall, blocks_move, find_path, in_shape, perceive, shape_box
from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignManager, CampaignModel  # type: ignore[import-not-found]
from zephyrex.extensions.world_spatial.BLL_WorldSpatial import LocationManager, LocationModel  # type: ignore[import-not-found]
from zephyrex.lib.ContentNegotiation import skip_negotiation
from zephyrex.lib.CustomRoute import ExposeIn, custom_route
from zephyrex.lib.Environment import env
from zephyrex.logic.AbstractLogicManager.models import FieldComparison
from zephyrex.logic.AbstractLogicManager import (
    AbstractBLLManager,
    ApplicationModel,
    ModelMeta,
    NameMixinModel,
    StringSearchModel,
    UpdateMixinModel,
)
from zephyrex.pydantic2.fastapi import RouterMixin
from zephyrex.pydantic2.registry import BaseModel  # type: ignore[attr-defined]

DEFAULT_GRID_SIZE = 100.0
DEFAULT_GRID_DISTANCE = 5.0
MAX_WALL_POINTS = 256

Disposition = Literal["friendly", "neutral", "hostile", "secret"]
DoorType = Literal["none", "door", "secret", "window", "gate", "portcullis"]
DoorState = Literal["closed", "open", "locked", "barred", "broken"]
Restriction = Literal["none", "normal", "limited"]
Direction = Literal["both", "left", "right"]
# zephyr-cartography's scene-spec v1 feature kinds (@zephyrex/cartography is their source of truth).
FeatureKind = Literal["region", "stroke", "path", "room", "stamp", "pin", "label", "zone", "shape", "token"]
MAX_FEATURE_KEY = 200
# An uploaded picture's own address (the attachments extension's content route).
ASSET_PATH = re.compile(r"/v1/asset/([^/?#]+)/content")
# A scene's art comes back as its own bytes: out of content negotiation, as the asset route is.
skip_negotiation(r"/v1/scene/[^/]+/background")


class SceneModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    CampaignModel.Reference.Optional,
    LocationModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["SceneManager"]] = None
    width: Optional[int] = Field(None, description="Pixels")
    height: Optional[int] = Field(None, description="Pixels")
    grid_size: Optional[float] = Field(DEFAULT_GRID_SIZE, description="Pixels per grid cell")
    grid_distance: Optional[float] = Field(DEFAULT_GRID_DISTANCE, description="Distance units per cell")
    grid_units: Optional[str] = Field("ft", description="What the distance units are")
    token_vision: Optional[bool] = Field(True, description="Whether tokens see only what their sight allows")
    global_illumination: Optional[bool] = Field(True, description="Lit everywhere, whatever the darkness")
    darkness_level: Optional[float] = Field(0.0, description="0 (day) to 1 (pitch dark)")
    background_color: Optional[str] = Field(None, description="#rrggbb shown where there is no art")
    padding: Optional[float] = Field(0.0, description="Share of width and height around the map")
    splats: Optional[list[dict[str, Any]]] = Field(None, description="Terrain paint layers (cartography); masks are attachments")
    flags: Optional[dict[str, Any]] = Field(None, description="Other systems' data about the place, kept as given")
    entry_x: Optional[float] = Field(None, description="Where arrivals appear, pixels; none = the scene's centre")
    entry_y: Optional[float] = Field(None, description="Where arrivals appear, pixels; none = the scene's centre")
    is_active: Optional[bool] = Field(False, description="The campaign's current scene (one per campaign; activate)")
    background_url: Optional[str] = Field(None, description="The scene's map picture by link (battlemap art, set or generated)")
    table_comment: ClassVar[str] = "A playable area in a campaign: the battlemap a table plays on"

    class Create(BaseModel, CampaignModel.Reference.ID.Optional, LocationModel.Reference.ID.Optional):
        name: str = Field(...)
        width: Optional[int] = Field(None, ge=1)
        height: Optional[int] = Field(None, ge=1)
        grid_size: float = Field(DEFAULT_GRID_SIZE, gt=0)
        grid_distance: float = Field(DEFAULT_GRID_DISTANCE, gt=0)
        grid_units: str = "ft"
        token_vision: bool = True
        global_illumination: bool = True
        darkness_level: float = Field(0.0, ge=0, le=1)
        background_color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
        padding: float = Field(0.0, ge=0, le=1)
        splats: Optional[list[dict[str, Any]]] = None
        flags: Optional[dict[str, Any]] = None
        entry_x: Optional[float] = None
        entry_y: Optional[float] = None
        background_url: Optional[str] = Field(None, max_length=2000)

    class Update(BaseModel):
        location_id: Optional[str] = None
        name: Optional[str] = None
        width: Optional[int] = Field(None, ge=1)
        height: Optional[int] = Field(None, ge=1)
        grid_size: Optional[float] = Field(None, gt=0)
        grid_distance: Optional[float] = Field(None, gt=0)
        grid_units: Optional[str] = None
        token_vision: Optional[bool] = None
        global_illumination: Optional[bool] = None
        darkness_level: Optional[float] = Field(None, ge=0, le=1)
        background_color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
        padding: Optional[float] = Field(None, ge=0, le=1)
        splats: Optional[list[dict[str, Any]]] = None
        flags: Optional[dict[str, Any]] = None
        entry_x: Optional[float] = None
        entry_y: Optional[float] = None
        background_url: Optional[str] = Field(None, max_length=2000)

    class Search(ApplicationModel.Search, CampaignModel.Reference.ID.Search, LocationModel.Reference.ID.Search):
        is_active: Optional[bool] = None
        name: Optional[StringSearchModel] = None


class SceneLevelModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    SceneModel.Reference.Optional,
    metaclass=ModelMeta,
):
    """A floor of a scene, bottom to top by ``sort``, with its height band in the scene's units."""

    Manager: ClassVar[Type["SceneLevelManager"]] = None
    sort: Optional[int] = Field(0, description="Bottom to top")
    bottom: Optional[float] = Field(0.0, description="Floor elevation, distance units")
    top: Optional[float] = Field(None, description="Ceiling elevation, distance units; NULL = open")
    table_comment: ClassVar[str] = "A level (floor) of a scene"

    class Create(BaseModel, SceneModel.Reference.ID):
        name: str = Field(...)
        sort: int = 0
        bottom: float = 0.0
        top: Optional[float] = None

    class Update(BaseModel):
        name: Optional[str] = None
        sort: Optional[int] = None
        bottom: Optional[float] = None
        top: Optional[float] = None

    class Search(ApplicationModel.Search, SceneModel.Reference.ID.Search):
        pass


class SceneFeatureModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    SceneModel.Reference.Optional,
    SceneLevelModel.Reference.Optional,
    metaclass=ModelMeta,
):
    """One authored map feature, as zephyr-cartography's scene spec writes it: ``spec`` is the
    feature itself (its kind's fields), validated by @zephyrex/cartography where it is edited and
    imported. The server keeps it whole, so nothing the module knows is lost."""

    Manager: ClassVar[Type["SceneFeatureManager"]] = None
    kind: Optional[FeatureKind] = Field(None)
    key: Optional[str] = Field(None, description="The name other features use for this one")
    sort: Optional[int] = Field(0, description="Drawing order within its kind")
    spec: Optional[dict[str, Any]] = Field(None, description="The scene-spec v1 feature")
    table_comment: ClassVar[str] = "A map feature in zephyr-cartography's scene-spec model"

    class Create(BaseModel, SceneModel.Reference.ID, SceneLevelModel.Reference.ID.Optional):
        kind: FeatureKind = Field(...)
        key: Optional[str] = Field(None, max_length=MAX_FEATURE_KEY)
        sort: int = 0
        spec: dict[str, Any] = Field(...)

    class Update(BaseModel):
        key: Optional[str] = Field(None, max_length=MAX_FEATURE_KEY)
        sort: Optional[int] = None
        spec: Optional[dict[str, Any]] = None

    class Search(ApplicationModel.Search, SceneModel.Reference.ID.Search, SceneLevelModel.Reference.ID.Search):
        kind: Optional[StringSearchModel] = None


class SceneTokenModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    SceneModel.Reference.Optional,
    SceneLevelModel.Reference.Optional,
    PersonModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["SceneTokenManager"]] = None
    x: Optional[float] = Field(0.0, description="Left edge, pixels")
    y: Optional[float] = Field(0.0, description="Top edge, pixels")
    width: Optional[float] = Field(1.0, description="Grid cells")
    height: Optional[float] = Field(1.0, description="Grid cells")
    elevation: Optional[float] = Field(0.0, description="Distance units (not yet used for sight)")
    rotation: Optional[float] = Field(0.0, description="Degrees clockwise from facing down the screen")
    sight_range: Optional[float] = Field(None, description="Distance units; NULL = unlimited")
    sight_angle: Optional[float] = Field(FULL_CIRCLE, description="Degrees of the sight cone")
    disposition: Optional[Disposition] = Field("neutral")
    is_hidden: Optional[bool] = Field(False, description="Hidden from players: never perceived")
    table_comment: ClassVar[str] = "A token on a scene; person_id is the character it stands for"

    class Create(
        BaseModel, SceneModel.Reference.ID.Optional, SceneLevelModel.Reference.ID.Optional, PersonModel.Reference.ID.Optional
    ):
        name: str = Field(...)
        x: float = 0.0
        y: float = 0.0
        width: float = Field(1.0, gt=0)
        height: float = Field(1.0, gt=0)
        elevation: float = 0.0
        rotation: float = 0.0
        sight_range: Optional[float] = Field(None, ge=0)
        sight_angle: float = Field(FULL_CIRCLE, gt=0, le=FULL_CIRCLE)
        disposition: Disposition = "neutral"
        is_hidden: bool = False

    class Update(BaseModel):
        name: Optional[str] = None
        x: Optional[float] = None
        y: Optional[float] = None
        width: Optional[float] = Field(None, gt=0)
        height: Optional[float] = Field(None, gt=0)
        elevation: Optional[float] = None
        rotation: Optional[float] = None
        sight_range: Optional[float] = Field(None, ge=0)
        sight_angle: Optional[float] = Field(None, gt=0, le=FULL_CIRCLE)
        disposition: Optional[Disposition] = None
        is_hidden: Optional[bool] = None

    class Search(ApplicationModel.Search, SceneModel.Reference.ID.Search, PersonModel.Reference.ID.Search):
        name: Optional[StringSearchModel] = None


class SceneWallModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    SceneModel.Reference.Optional,
    SceneLevelModel.Reference.Optional,
    SceneFeatureModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["SceneWallManager"]] = None
    points: Optional[list[list[float]]] = Field(None, description="[[x, y], ...] pixels, a polyline")
    door_type: Optional[DoorType] = Field("none")
    door_state: Optional[DoorState] = Field("closed")
    sight_restriction: Optional[Restriction] = Field("normal")
    move_restriction: Optional[Restriction] = Field("normal")
    light_restriction: Optional[Restriction] = Field("normal")
    sound_restriction: Optional[Restriction] = Field("normal")
    direction: Optional[Direction] = Field("both", description="One-way walls block one side only")
    table_comment: ClassVar[str] = "A wall or door on a scene, as a polyline; scene_feature_id is the feature that made it"

    class Create(
        BaseModel, SceneModel.Reference.ID.Optional, SceneLevelModel.Reference.ID.Optional, SceneFeatureModel.Reference.ID.Optional
    ):
        points: list[list[float]] = Field(..., min_length=2, max_length=MAX_WALL_POINTS)
        door_type: DoorType = "none"
        door_state: DoorState = "closed"
        sight_restriction: Restriction = "normal"
        move_restriction: Restriction = "normal"
        light_restriction: Restriction = "normal"
        sound_restriction: Restriction = "normal"
        direction: Direction = "both"

    class Update(BaseModel):
        points: Optional[list[list[float]]] = Field(None, min_length=2, max_length=MAX_WALL_POINTS)
        door_type: Optional[DoorType] = None
        door_state: Optional[DoorState] = None
        sight_restriction: Optional[Restriction] = None
        move_restriction: Optional[Restriction] = None
        light_restriction: Optional[Restriction] = None
        sound_restriction: Optional[Restriction] = None
        direction: Optional[Direction] = None

    class Search(ApplicationModel.Search, SceneModel.Reference.ID.Search, SceneFeatureModel.Reference.ID.Search):
        pass


class SceneLightModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    SceneModel.Reference.Optional,
    SceneLevelModel.Reference.Optional,
    SceneFeatureModel.Reference.Optional,
    metaclass=ModelMeta,
):
    """A light, or a darkness source, at a point."""

    Manager: ClassVar[Type["SceneLightManager"]] = None
    x: Optional[float] = Field(0.0, description="Pixels")
    y: Optional[float] = Field(0.0, description="Pixels")
    bright: Optional[float] = Field(0.0, description="Bright radius, distance units")
    dim: Optional[float] = Field(0.0, description="Dim radius, distance units")
    angle: Optional[float] = Field(FULL_CIRCLE, description="Degrees of the cone")
    rotation: Optional[float] = Field(0.0, description="Degrees clockwise")
    color: Optional[str] = Field(None, description="#rrggbb, NULL for white")
    darkness: Optional[bool] = Field(False, description="A darkness source, not a light")
    walls: Optional[bool] = Field(True, description="Walls stop it")
    is_hidden: Optional[bool] = Field(False, description="Switched off")
    table_comment: ClassVar[str] = "A light or darkness source on a scene"

    class Create(
        BaseModel, SceneModel.Reference.ID, SceneLevelModel.Reference.ID.Optional, SceneFeatureModel.Reference.ID.Optional
    ):
        x: float = 0.0
        y: float = 0.0
        bright: float = Field(0.0, ge=0)
        dim: float = Field(0.0, ge=0)
        angle: float = Field(FULL_CIRCLE, gt=0, le=FULL_CIRCLE)
        rotation: float = 0.0
        color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
        darkness: bool = False
        walls: bool = True
        is_hidden: bool = False

    class Update(BaseModel):
        x: Optional[float] = None
        y: Optional[float] = None
        bright: Optional[float] = Field(None, ge=0)
        dim: Optional[float] = Field(None, ge=0)
        angle: Optional[float] = Field(None, gt=0, le=FULL_CIRCLE)
        rotation: Optional[float] = None
        color: Optional[str] = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
        darkness: Optional[bool] = None
        walls: Optional[bool] = None
        is_hidden: Optional[bool] = None

    class Search(ApplicationModel.Search, SceneModel.Reference.ID.Search, SceneFeatureModel.Reference.ID.Search):
        pass


class SceneTileModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    SceneModel.Reference.Optional,
    SceneLevelModel.Reference.Optional,
    SceneFeatureModel.Reference.Optional,
    metaclass=ModelMeta,
):
    """A placed image (a stamp's art, a baked terrain blend); the image is its ``art`` attachment."""

    Manager: ClassVar[Type["SceneTileManager"]] = None
    x: Optional[float] = Field(0.0, description="Left edge, pixels")
    y: Optional[float] = Field(0.0, description="Top edge, pixels")
    width: Optional[float] = Field(None, description="Pixels")
    height: Optional[float] = Field(None, description="Pixels")
    rotation: Optional[float] = Field(0.0, description="Degrees clockwise")
    sort: Optional[int] = Field(0, description="Drawing order")
    mirror_x: Optional[bool] = Field(False)
    mirror_y: Optional[bool] = Field(False)
    alpha: Optional[float] = Field(1.0, description="0 to 1")
    is_hidden: Optional[bool] = Field(False, description="Hidden from players")
    table_comment: ClassVar[str] = "An image placed on a scene"

    class Create(
        BaseModel, SceneModel.Reference.ID, SceneLevelModel.Reference.ID.Optional, SceneFeatureModel.Reference.ID.Optional
    ):
        x: float = 0.0
        y: float = 0.0
        width: float = Field(..., gt=0)
        height: float = Field(..., gt=0)
        rotation: float = 0.0
        sort: int = 0
        mirror_x: bool = False
        mirror_y: bool = False
        alpha: float = Field(1.0, ge=0, le=1)
        is_hidden: bool = False

    class Update(BaseModel):
        x: Optional[float] = None
        y: Optional[float] = None
        width: Optional[float] = Field(None, gt=0)
        height: Optional[float] = Field(None, gt=0)
        rotation: Optional[float] = None
        sort: Optional[int] = None
        mirror_x: Optional[bool] = None
        mirror_y: Optional[bool] = None
        alpha: Optional[float] = Field(None, ge=0, le=1)
        is_hidden: Optional[bool] = None

    class Search(ApplicationModel.Search, SceneModel.Reference.ID.Search, SceneFeatureModel.Reference.ID.Search):
        pass


class SceneNoteModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    SceneModel.Reference.Optional,
    SceneLevelModel.Reference.Optional,
    SceneFeatureModel.Reference.Optional,
    metaclass=ModelMeta,
):
    """A map pin: text, and the wiki entity it opens; a sign is read on hover."""

    Manager: ClassVar[Type["SceneNoteManager"]] = None
    x: Optional[float] = Field(0.0, description="Pixels")
    y: Optional[float] = Field(0.0, description="Pixels")
    text: Optional[str] = Field(None)
    icon: Optional[str] = Field(None)
    size: Optional[float] = Field(None, description="Pixels")
    entity_type: Optional[str] = Field(None, description="The wiki entity the pin opens")
    entity_id: Optional[str] = Field(None)
    is_global: Optional[bool] = Field(False, description="Shown whatever a token can see")
    readable: Optional[bool] = Field(False, description="A sign: players read it on hover")
    is_hidden: Optional[bool] = Field(False, description="Hidden from players")
    table_comment: ClassVar[str] = "A map pin on a scene"

    class Create(
        BaseModel, SceneModel.Reference.ID, SceneLevelModel.Reference.ID.Optional, SceneFeatureModel.Reference.ID.Optional
    ):
        x: float = 0.0
        y: float = 0.0
        text: Optional[str] = None
        icon: Optional[str] = None
        size: Optional[float] = Field(None, gt=0)
        entity_type: Optional[str] = None
        entity_id: Optional[str] = None
        is_global: bool = False
        readable: bool = False
        is_hidden: bool = False

    class Update(BaseModel):
        x: Optional[float] = None
        y: Optional[float] = None
        text: Optional[str] = None
        icon: Optional[str] = None
        size: Optional[float] = Field(None, gt=0)
        entity_type: Optional[str] = None
        entity_id: Optional[str] = None
        is_global: Optional[bool] = None
        readable: Optional[bool] = None
        is_hidden: Optional[bool] = None

    class Search(ApplicationModel.Search, SceneModel.Reference.ID.Search, SceneFeatureModel.Reference.ID.Search):
        pass


class SceneRegionModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    SceneModel.Reference.Optional,
    SceneLevelModel.Reference.Optional,
    SceneFeatureModel.Reference.Optional,
    LocationModel.Reference.Optional,
    metaclass=ModelMeta,
):
    """An area with behaviours: a zone, a hazard, a trap, stairs between levels, a ceiling, terrain
    that slows. ``shapes`` and ``behaviours`` keep the cartography model's form."""

    Manager: ClassVar[Type["SceneRegionManager"]] = None
    shapes: Optional[list[dict[str, Any]]] = Field(None)
    behaviours: Optional[list[dict[str, Any]]] = Field(None)
    is_hidden: Optional[bool] = Field(False, description="Hidden from players, behaviours off")
    table_comment: ClassVar[str] = "An area of a scene with behaviours"

    class Create(
        BaseModel,
        SceneModel.Reference.ID,
        SceneLevelModel.Reference.ID.Optional,
        SceneFeatureModel.Reference.ID.Optional,
        LocationModel.Reference.ID.Optional,
    ):
        name: Optional[str] = None
        shapes: list[dict[str, Any]] = Field(..., min_length=1)
        behaviours: list[dict[str, Any]] = Field(default_factory=list)
        is_hidden: bool = False

    class Update(BaseModel):
        name: Optional[str] = None
        location_id: Optional[str] = None
        shapes: Optional[list[dict[str, Any]]] = Field(None, min_length=1)
        behaviours: Optional[list[dict[str, Any]]] = None
        is_hidden: Optional[bool] = None

    class Search(ApplicationModel.Search, SceneModel.Reference.ID.Search, SceneFeatureModel.Reference.ID.Search):
        pass


class ScopePlaceModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    CampaignModel.Reference.Optional,
    LocationModel.Reference.Optional,
    metaclass=ModelMeta,
):
    """Where a place's marker sits on its parent's map at the scope above it (the town map's
    Halloway house), as fractions of that map. The wiki's places have no coordinates; this is the
    VTT's, pinned by the campaign's GM (place_on_scope)."""

    Manager: ClassVar[Type["ScopePlaceManager"]] = None
    x: Optional[float] = Field(None, description="Across its parent's map, 0 (left) to 1 (right)")
    y: Optional[float] = Field(None, description="Down its parent's map, 0 (top) to 1 (bottom)")
    table_comment: ClassVar[str] = "Where a place's marker sits on its parent's map, at the scope above it"

    class Create(BaseModel, CampaignModel.Reference.ID, LocationModel.Reference.ID):
        x: float = Field(..., ge=0, le=1)
        y: float = Field(..., ge=0, le=1)

    class Update(BaseModel):
        x: Optional[float] = Field(None, ge=0, le=1)
        y: Optional[float] = Field(None, ge=0, le=1)

    class Search(ApplicationModel.Search, CampaignModel.Reference.ID.Search, LocationModel.Reference.ID.Search):
        pass


class MoveRequest(PlainModel):
    x: float
    y: float


class MoveEnvelope(PlainModel):
    move: MoveRequest


class MovedEnvelope(PlainModel):
    scene_token: dict[str, Any]


class PilotOut(PlainModel):
    person_id: str
    # The token, where it stands (its top-left, pixels) and on which scene; none when the target
    # place is on no map, so the character left the maps (its tokens removed).
    token_id: Optional[str] = None
    scene_id: Optional[str] = None
    x: Optional[float] = None
    y: Optional[float] = None
    arrived: bool = True
    # Cells still to walk, in scene units, when max_distance stopped it short.
    remaining: float = 0.0
    removed: int = 0
    location_id: Optional[str] = None


class MoveSceneRequest(PlainModel):
    scene_id: str = Field(description="The scene to move the token to (the same campaign's)")


class MoveSceneEnvelope(PlainModel):
    move_scene: MoveSceneRequest


class SceneTokenManager(AbstractBLLManager, RouterMixin):
    _model = SceneTokenModel

    def _trusted(self, manager: type[Any]) -> Any:
        return manager(requester_id=env("ROOT_ID"), model_registry=self.model_registry)

    def move_for(self, token_id: str, body: MoveRequest) -> dict[str, Any]:
        """Move a token: the campaign's GM moves any token anywhere; a player moves their own
        character's token, never through a wall that blocks movement (a closed door, one-way from
        its closed side). Everyone else gets the same 404 as a missing token."""
        tokens = self._trusted(SceneTokenManager)
        try:
            token = tokens.get(id=token_id)
            scene = self._trusted(SceneManager).get(id=token.scene_id)
        except HTTPException:
            raise _not_found("SceneTokenModel") from None
        requester = str(self.requester.id)
        campaign = None
        if scene.campaign_id is not None:
            try:
                campaign = self._trusted(CampaignManager).get(id=scene.campaign_id)
            except HTTPException:
                campaign = None
        gm = requester in _campaign_gms(campaign)
        player = False
        if not gm and token.person_id is not None:
            try:
                person = self._trusted(PersonManager).get(id=token.person_id)
            except HTTPException:
                person = None
            player = requester in _controllers(self.model_registry, person)
        if not (gm or player):
            raise _not_found("SceneTokenModel")
        if not gm:
            grid = float(scene.grid_size or DEFAULT_GRID_SIZE)
            half_w, half_h = float(token.width or 1) * grid / 2, float(token.height or 1) * grid / 2
            start = (float(token.x or 0) + half_w, float(token.y or 0) + half_h)
            end = (body.x + half_w, body.y + half_h)
            walls = [_wall(row) for row in self._trusted(SceneWallManager).list(scene_id=scene.id)]
            if blocks_move(start, end, walls) is not None:
                raise HTTPException(status_code=422, detail={"message": "A wall is in the way"})
        moved = tokens.update(id=token.id, x=body.x, y=body.y)
        # The person's wiki location follows their token.
        SceneManager(requester_id=str(self.requester.id), model_registry=self.model_registry).sync_location(moved, scene)
        return moved.model_dump(mode="json") if hasattr(moved, "model_dump") else dict(moved)

    @custom_route(
        method="POST",
        path="/{token_id}/move",
        input_model=MoveEnvelope,
        output_model=MovedEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="Move a token: the GM's any token anywhere; a player's own, never through a wall",
    )
    async def move_route(self, token_id: str, body: MoveEnvelope) -> MovedEnvelope:
        return MovedEnvelope(scene_token=self.move_for(token_id, body.move))

    @custom_route(
        method="POST",
        path="/{token_id}/move_scene",
        input_model=MoveSceneEnvelope,
        output_model=PilotOut,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="Move a token to another scene of its campaign, at the entry on a free cell (the campaign's GM)",
    )
    async def move_scene_route(self, token_id: str, body: MoveSceneEnvelope) -> PilotOut:
        scenes = SceneManager(requester_id=str(self.requester.id), model_registry=self.model_registry)
        return scenes.move_token_to_scene_for(token_id, body.move_scene.scene_id)


class SceneWallManager(AbstractBLLManager, RouterMixin):
    _model = SceneWallModel


class SceneLevelManager(AbstractBLLManager, RouterMixin):
    _model = SceneLevelModel


class SceneFeatureManager(AbstractBLLManager, RouterMixin):
    _model = SceneFeatureModel


class SceneLightManager(AbstractBLLManager, RouterMixin):
    _model = SceneLightModel


class SceneTileManager(AbstractBLLManager, RouterMixin):
    _model = SceneTileModel


class SceneNoteManager(AbstractBLLManager, RouterMixin):
    _model = SceneNoteModel


class SceneRegionManager(AbstractBLLManager, RouterMixin):
    _model = SceneRegionModel


class ScopePlaceManager(AbstractBLLManager, RouterMixin):
    _model = ScopePlaceModel


SceneTokenModel.Manager = SceneTokenManager
SceneWallModel.Manager = SceneWallManager
SceneLevelModel.Manager = SceneLevelManager
SceneFeatureModel.Manager = SceneFeatureManager
SceneLightModel.Manager = SceneLightManager
SceneTileModel.Manager = SceneTileManager
SceneNoteModel.Manager = SceneNoteManager
SceneRegionModel.Manager = SceneRegionManager
ScopePlaceModel.Manager = ScopePlaceManager

ALL_MODELS: list[type] = [
    SceneModel,
    SceneLevelModel,
    SceneFeatureModel,
    SceneTokenModel,
    SceneWallModel,
    SceneLightModel,
    SceneTileModel,
    SceneNoteModel,
    SceneRegionModel,
    ScopePlaceModel,
]


# ---------------------------------------------------------------------------
# What a token perceives
# ---------------------------------------------------------------------------


class SnapshotRequest(PlainModel):
    token_id: str


class SnapshotEnvelope(PlainModel):
    snapshot: SnapshotRequest


class SeenToken(PlainModel):
    id: str
    name: Optional[str]
    person_id: Optional[str]
    disposition: Optional[str]
    distance: float


class SeenDoor(PlainModel):
    id: str
    door_type: str
    door_state: str


class SnapshotOut(PlainModel):
    scene_id: str
    viewer: str
    lit: bool
    units: str
    seen: list[SeenToken]
    doors: list[SeenDoor]


class SnapshotResultEnvelope(PlainModel):
    snapshot: SnapshotOut


class ViewRequest(PlainModel):
    # The token a player sees from; none for the GM's whole view, or a player's first own token.
    token_id: Optional[str] = None


class ViewEnvelope(PlainModel):
    view: ViewRequest


class ViewToken(PlainModel):
    id: str
    name: Optional[str]
    person_id: Optional[str]
    disposition: Optional[str]
    x: float
    y: float
    width: float
    height: float
    rotation: float
    is_hidden: bool = False
    mine: bool = False
    picture_url: Optional[str] = None



class ViewWall(PlainModel):
    id: str
    points: list[list[float]]
    door_type: Optional[str]
    door_state: Optional[str]


class ViewOut(PlainModel):
    scene_id: str
    name: Optional[str]
    width: Optional[int]
    height: Optional[int]
    grid_size: float
    grid_distance: float
    grid_units: str
    background_color: Optional[str]
    gm: bool
    viewer: Optional[str]
    lit: bool
    tokens: list[ViewToken]
    walls: list[ViewWall]
    background_url: Optional[str] = None


class ViewResultEnvelope(PlainModel):
    view: ViewOut


class SceneTokenOut(PlainModel):
    token_id: str
    name: Optional[str]
    entity_id: Optional[str]
    hidden: bool


class SceneTokensOut(PlainModel):
    scene_tokens: list[SceneTokenOut]


class ActivateEnvelope(PlainModel):
    # Nothing to say beyond the scene in the path; a POST's typed body all the same.
    activate: dict[str, Any] = Field(default_factory=dict)


class CurrentRequest(PlainModel):
    campaign_id: str


class CurrentEnvelope(PlainModel):
    current: CurrentRequest


class PlaceRequest(PlainModel):
    person_id: str
    near_person_id: Optional[str] = Field(None, description="Beside this person's token on the scene")
    x: Optional[float] = Field(None, description="Or at this point, pixels")
    y: Optional[float] = None


class PlaceEnvelope(PlainModel):
    place: PlaceRequest


class RemoveRequest(PlainModel):
    person_id: str


class RemoveEnvelope(PlainModel):
    remove: RemoveRequest


class RemoveOut(PlainModel):
    scene_id: str
    person_id: str
    removed: bool = Field(description="Whether they had a token on the scene to take off")


class CopyRequest(PlainModel):
    from_campaign_id: str
    to_campaign_id: str
    id_map: dict[str, str] = Field(default_factory=dict, description="Source wiki ids (persons, locations) to the copies'")


class CopyEnvelope(PlainModel):
    copy_scenes: CopyRequest


class CopiedEnvelope(PlainModel):
    scenes: list["SceneSummary"]


class SceneSummary(PlainModel):
    id: str
    name: Optional[str]
    campaign_id: Optional[str]
    location_id: Optional[str]
    width: Optional[int]
    height: Optional[int]
    grid_size: float
    background_url: Optional[str] = Field(None, description="What the map draws under its grid: the scene's own picture, else its place's")



class CurrentOut(PlainModel):
    scene: Optional[SceneSummary]


CopiedEnvelope.model_rebuild()


class ScopeRequest(PlainModel):
    campaign_id: str
    location_id: Optional[str] = Field(None, description="The place to show; none is the current scene's, else the party's")


class ScopeEnvelope(PlainModel):
    scope: ScopeRequest


class ScopePerson(PlainModel):
    person_id: str
    name: str
    picture: Optional[str] = Field(None, description="Their portrait (the wiki's picture: a link, else their newest upload)")


class ScopePlace(PlainModel):
    id: str
    name: str
    kind: Optional[str] = Field(None, description="The wiki's location kind: region, city, building, room…")
    picture: Optional[str] = Field(None, description="The place's illustration (a thumbnail; never its map)")


class ScopeMarker(PlainModel):
    location_id: str
    name: str
    kind: Optional[str]
    picture: Optional[str]
    x: float = Field(description="Across the scope's map, 0 to 1")
    y: float = Field(description="Down the scope's map, 0 to 1")
    placed: bool = Field(description="Pinned by the GM or from a region of the map; false is an even layout")
    people: list[ScopePerson] = Field(description="The NPCs in it, however deep (the parlour's count for the house)")
    count: int


class ScopeParty(PlainModel):
    location_id: str = Field(description="The place inside the scope they are in, or the scope's own")
    x: float
    y: float
    people: list[ScopePerson]


class ScopeBackground(PlainModel):
    url: Optional[str] = Field(None, description="The map art: the scope's scene's picture; none draws a labelled placeholder")
    scene_id: Optional[str] = Field(None, description="The campaign's scene of this place, to play on")
    label: str = Field(description="The place's name, for the placeholder and the map's corner")


class ScopeOut(PlainModel):
    campaign_id: str
    location: ScopePlace
    scope: Optional[str] = Field(None, description="The place's kind: the level shown")
    parent: Optional[ScopePlace] = Field(None, description="Scoping out shows this; none at the top")
    path: list[ScopePlace] = Field(description="The top place down to this one")
    background: ScopeBackground
    markers: list[ScopeMarker] = Field(description="Each place inside it that NPCs are in, their group token")
    parties: list[ScopeParty] = Field(default_factory=list, description="The party's group(s) where they are (a split party is several)")
    here: list[ScopePerson] = Field(description="NPCs at this place itself, in no place inside it")


class PlaceOnScopeRequest(PlainModel):
    campaign_id: str
    location_id: str = Field(description="The place whose marker moves (on its parent's map)")
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class PlaceOnScopeEnvelope(PlainModel):
    place_on_scope: PlaceOnScopeRequest


class UvttRequest(PlainModel):
    uvtt: dict[str, Any] = Field(description="A Universal VTT map's JSON (.uvtt / .dd2vtt); its embedded image is ignored")
    replace: bool = Field(True, description="Take off the scene's hand-placed and imported walls and lights first")


class UvttEnvelope(PlainModel):
    import_uvtt: UvttRequest


class UvttOut(PlainModel):
    scene_id: str
    level: Optional[str] = Field(None, description="The file's level name, e.g. Ground floor")
    width: int
    height: int
    grid_size: float
    walls: int
    doors: int
    lights: int
    removed: int = Field(description="Walls and lights taken off first")


def _summary(scene: Any) -> SceneSummary:
    return SceneSummary(
        id=scene.id,
        name=scene.name,
        campaign_id=scene.campaign_id,
        location_id=getattr(scene, "location_id", None),
        width=scene.width,
        height=scene.height,
        grid_size=float(scene.grid_size or DEFAULT_GRID_SIZE),
    )


def _live(manager: Any, **filters: Any) -> list[Any]:
    """A trusted manager's rows, without soft-deleted ones. The framework surfaces tombstones to
    ROOT (an audit read), and the rows don't carry deleted_at, so the filter goes in the query."""
    return list(manager.list(filters=[manager.DB.deleted_at.is_(None)], **filters))


def _campaign_gms(campaign: Any) -> set[str]:
    """A campaign's GM: its owner, or its creator for a campaign made without one."""
    if campaign is None:
        return set()
    return {str(owner) for owner in (campaign.user_id, getattr(campaign, "created_by_user_id", None)) if owner}


def _controllers(model_registry: Any, person: Any) -> set[str]:
    """Who plays a character: the person's own player (user_id), and whoever holds a seat for them
    at a table (rpg_table's controller_id; a playthrough's copied pregens are played through seats)."""
    if person is None:
        return set()
    found = {str(person.user_id)} if getattr(person, "user_id", None) else set()
    try:
        from zephyrex.extensions.rpg_table.BLL_RPGTable import TableSeatManager  # type: ignore[import-not-found]
    except ImportError:
        return found
    seats = TableSeatManager(requester_id=env("ROOT_ID"), model_registry=model_registry)
    for seat in _live(seats, person_id=person.id):
        if getattr(seat, "controller_id", None):
            found.add(str(seat.controller_id))
    return found


def _not_found(model: str) -> HTTPException:
    return HTTPException(
        status_code=404, detail={"message": f"Request searched {model} and could not find the required record."}
    )


def _token(row: Any) -> Token:
    return Token(
        id=row.id,
        x=float(row.x or 0),
        y=float(row.y or 0),
        width=float(row.width or 1),
        height=float(row.height or 1),
        rotation=float(row.rotation or 0),
        sight_range=None if row.sight_range is None else float(row.sight_range),
        sight_angle=float(row.sight_angle if row.sight_angle is not None else FULL_CIRCLE),
        is_hidden=bool(row.is_hidden),
    )


def _wall(row: Any) -> Wall:
    return Wall(
        id=row.id,
        points=row.points or [],
        door_type=row.door_type or "none",
        door_state=row.door_state or "closed",
        sight_restriction=row.sight_restriction or "normal",
        direction=row.direction or "both",
        move_restriction=row.move_restriction or "normal",
    )


class SceneManager(AbstractBLLManager, RouterMixin):
    """Scenes, and what a token perceives in one."""

    _model = SceneModel

    def _trusted(self, manager: type[Any]) -> Any:
        """A manager reading as the system, once the access rule has passed."""
        return manager(requester_id=env("ROOT_ID"), model_registry=self.model_registry)

    def _get(self, manager: type[Any], record_id: str) -> Any | None:
        try:
            return self._trusted(manager).get(id=record_id)
        except HTTPException:
            return None

    def snapshot_for(self, scene_id: str, body: SnapshotRequest) -> SnapshotOut:
        scene = self._get(SceneManager, scene_id)
        viewer = self._get(SceneTokenManager, body.token_id)
        if scene is None or viewer is None or viewer.scene_id != scene.id:
            raise _not_found("SceneTokenModel")
        requester = str(self.requester.id)
        campaign = None if scene.campaign_id is None else self._get(CampaignManager, scene.campaign_id)
        person = None if viewer.person_id is None else self._get(PersonManager, viewer.person_id)
        gm = requester in _campaign_gms(campaign)
        player = requester in _controllers(self.model_registry, person)
        if not (gm or player):
            # The same answer as a scene or token that isn't there.
            raise _not_found("SceneTokenModel")
        rows = list(_live(self._trusted(SceneTokenManager), scene_id=scene.id))
        walls = list(self._trusted(SceneWallManager).list(scene_id=scene.id))
        perceived = perceive(
            Scene(
                grid_size=float(scene.grid_size or DEFAULT_GRID_SIZE),
                grid_distance=float(scene.grid_distance or DEFAULT_GRID_DISTANCE),
                global_illumination=bool(scene.global_illumination),
                darkness_level=float(scene.darkness_level or 0),
            ),
            _token(viewer),
            [_token(row) for row in rows],
            [_wall(row) for row in walls],
        )
        by_id = {row.id: row for row in rows}
        walls_by_id = {row.id: row for row in walls}
        return SnapshotOut(
            scene_id=scene.id,
            viewer=viewer.id,
            lit=perceived.lit,
            units=scene.grid_units or "ft",
            seen=[
                SeenToken(
                    id=one["id"],
                    name=by_id[one["id"]].name,
                    person_id=by_id[one["id"]].person_id,
                    disposition=by_id[one["id"]].disposition,
                    distance=one["distance"],
                )
                for one in perceived.seen
            ],
            doors=[
                SeenDoor(
                    id=door,
                    door_type=walls_by_id[door].door_type,
                    door_state=walls_by_id[door].door_state,
                )
                for door in perceived.doors
            ],
        )

    def view_for(self, scene_id: str, body: ViewRequest) -> ViewOut:
        """What to draw of a scene for the requester, decided on the server (the scene view's data).

        The campaign's GM sees everything: every token (hidden ones flagged) and every wall and
        door. A player sees from one of their own tokens (the one named, or their first on the
        scene): their own tokens, and what that token perceives (perceive: sight, walls, light),
        with only the doors it sees. Hidden tokens and other walls never reach a player.
        """
        scene = self._get(SceneManager, scene_id)
        if scene is None:
            raise _not_found("SceneModel")
        requester = str(self.requester.id)
        campaign = None if scene.campaign_id is None else self._get(CampaignManager, scene.campaign_id)
        gm = requester in _campaign_gms(campaign)
        rows = list(_live(self._trusted(SceneTokenManager), scene_id=scene.id))
        walls = list(_live(self._trusted(SceneWallManager), scene_id=scene.id))
        people: dict[str, Any] = {}

        pictures: dict[str, Optional[str]] = {}

        def plays(row: Any) -> bool:
            if row.person_id is None:
                return False
            if row.person_id not in people:
                person = self._get(PersonManager, row.person_id)
                people[row.person_id] = _controllers(self.model_registry, person)
                pictures[row.person_id] = getattr(person, "picture_url", None) if person is not None else None
            return requester in people[row.person_id]

        mine = {row.id for row in rows if plays(row)}
        pictures.update(self._portraits(sorted({row.person_id for row in rows if row.person_id})))
        viewer = None
        if body.token_id is not None:
            viewer = next((row for row in rows if row.id == body.token_id), None)
            if viewer is None or not (gm or viewer.id in mine):
                raise _not_found("SceneTokenModel")
        elif not gm:
            viewer = next((row for row in rows if row.id in mine), None)
            if viewer is None:
                # A player of the campaign with no token here sees the map and nothing on it; anyone
                # else gets the same answer as a scene that isn't there.
                if campaign is None or not self._is_member(campaign):
                    raise _not_found("SceneModel")
                return ViewOut(**self._empty_view(scene))

        def drawn(row: Any) -> ViewToken:
            return ViewToken(
                id=row.id,
                name=row.name,
                person_id=row.person_id,
                disposition=row.disposition,
                x=float(row.x or 0),
                y=float(row.y or 0),
                width=float(row.width or 1),
                height=float(row.height or 1),
                rotation=float(row.rotation or 0),
                is_hidden=bool(row.is_hidden),
                mine=row.id in mine,
                picture_url=pictures.get(row.person_id) if row.person_id else None,
            )

        def wall(row: Any) -> ViewWall:
            return ViewWall(id=row.id, points=row.points or [], door_type=row.door_type, door_state=row.door_state)

        lit = True
        if viewer is None:
            tokens, shown = [drawn(row) for row in rows], [wall(row) for row in walls]
        else:
            perceived = perceive(
                Scene(
                    grid_size=float(scene.grid_size or DEFAULT_GRID_SIZE),
                    grid_distance=float(scene.grid_distance or DEFAULT_GRID_DISTANCE),
                    global_illumination=bool(scene.global_illumination),
                    darkness_level=float(scene.darkness_level or 0),
                ),
                _token(viewer),
                [_token(row) for row in rows],
                [_wall(row) for row in walls],
            )
            lit = perceived.lit
            seen = {one["id"] for one in perceived.seen} | mine | {viewer.id}
            hidden_ok = gm
            tokens = [drawn(row) for row in rows if row.id in seen and (hidden_ok or not row.is_hidden or row.id in mine)]
            doors = set(perceived.doors)
            shown = [wall(row) for row in walls if row.id in doors] if not gm else [wall(row) for row in walls]
        return ViewOut(
            scene_id=scene.id,
            name=scene.name,
            width=scene.width,
            height=scene.height,
            grid_size=float(scene.grid_size or DEFAULT_GRID_SIZE),
            grid_distance=float(scene.grid_distance or DEFAULT_GRID_DISTANCE),
            grid_units=scene.grid_units or "ft",
            background_color=scene.background_color,
            gm=gm,
            viewer=None if viewer is None else viewer.id,
            lit=lit,
            tokens=tokens,
            walls=shown,
            background_url=self._drawn_background(scene),
        )

    def _portraits(self, person_ids: list[str]) -> dict[str, Optional[str]]:
        """Each person's portrait as the wiki gives it (world_entities_by_id: their picture link,
        else their newest uploaded picture), as the requester; someone it doesn't return keeps their
        link. Nothing where the wiki's ability isn't loaded."""
        by_id = loaded_ability(self.model_registry, "rpg_core", "world_entities_by_id")
        if by_id is None or not person_ids:
            return {}
        found = by_id(self.model_registry, str(self.requester.id), person_ids).get("world_entities") or []
        return {str(one["id"]): one.get("picture") for one in found if one.get("kind") == "person" and one.get("picture")}

    def import_uvtt_for(self, scene_id: str, body: UvttRequest) -> UvttOut:
        """A Universal VTT map's walls, doors and lights onto a scene (rpg_scene.Uvtt), which takes
        the map's size and grid: the picture alone isn't a scene (Cartography's exports, Dungeondraft).
        Replacing takes off the walls and lights no feature made (hand-placed or imported) first; a
        feature's own records stay. Made as the requester, the campaign's GM only."""
        scene = self._get(SceneManager, scene_id)
        campaign = None if scene is None or scene.campaign_id is None else self._get(CampaignManager, scene.campaign_id)
        if scene is None or str(self.requester.id) not in self._gms_of(campaign):
            raise _not_found("SceneModel")
        try:
            found = read_uvtt(body.uvtt, float(scene.grid_distance or DEFAULT_GRID_DISTANCE))
        except (UvttError, TypeError, ValueError) as error:
            raise HTTPException(status_code=422, detail={"message": f"Not a Universal VTT map this reads: {error}"}) from error
        mine = lambda manager: manager(requester_id=str(self.requester.id), model_registry=self.model_registry)  # noqa: E731
        removed = 0
        if body.replace:
            for manager in (SceneWallManager, SceneLightManager):
                for row in _live(self._trusted(manager), scene_id=scene.id):
                    if getattr(row, "scene_feature_id", None) is None:
                        self._trusted(manager).delete(id=row.id)
                        removed += 1
        self._trusted(SceneManager).update(id=scene.id, width=found.width, height=found.height, grid_size=found.grid_size)
        walls = mine(SceneWallManager)
        for points in found.walls:
            walls.create(scene_id=scene.id, points=points)
        for door in found.doors:
            walls.create(scene_id=scene.id, points=door["points"], door_type="door", door_state=door["door_state"])
        lights = mine(SceneLightManager)
        for light in found.lights:
            lights.create(scene_id=scene.id, **light)
        return UvttOut(
            scene_id=scene.id,
            level=found.level,
            width=found.width,
            height=found.height,
            grid_size=found.grid_size,
            walls=len(found.walls),
            doors=len(found.doors),
            lights=len(found.lights),
            removed=removed,
        )

    def _summarize(self, scene: Any) -> SceneSummary:
        """A scene's summary with what its map draws under the grid (_background_of)."""
        summary = _summary(scene)
        summary.background_url = self._background_of(scene)
        return summary

    def set_background_for(self, scene_id: str, background_url: Optional[str]) -> SceneSummary:
        """Set (or, with None, clear) a scene's own map picture: a generated battlemap's link. The
        campaign's GM only."""
        scene = self._get(SceneManager, scene_id)
        campaign = None if scene is None or scene.campaign_id is None else self._get(CampaignManager, scene.campaign_id)
        if scene is None or str(self.requester.id) not in self._gms_of(campaign):
            raise _not_found("SceneModel")
        if background_url is not None and len(background_url) > 2000:
            raise HTTPException(status_code=422, detail={"message": "That link is longer than 2000 characters"})
        return self._summarize(self._trusted(SceneManager).update(id=scene.id, background_url=background_url))

    def _background_of(self, scene: Any) -> Optional[str]:
        """What to draw under the grid: the scene's own map picture (background_url: battlemap art the
        GM set or rpg-ai generated), else nothing (the grid on its ground). Never its place's wiki
        picture: that's an illustration (a ship's mast), not a top-down map (the operator, 2026-11-22)."""
        return str(scene.background_url) if getattr(scene, "background_url", None) else None

    def _drawn_background(self, scene: Any) -> Optional[str]:
        """The map art's address to draw from: an uploaded picture (/v1/asset/{id}/content) is served
        by the scene's own background route, which lets the campaign's players load it (the asset's
        own route serves only its uploader and viewers of a record it's attached to, and players
        can't view the GM's rows); a link elsewhere is drawn as it is."""
        stored = self._background_of(scene)
        if stored and ASSET_PATH.fullmatch(stored):
            return f"/v1/scene/{scene.id}/background"
        return stored

    async def background_for(self, scene_id: str) -> Response:
        """A scene's uploaded map art, for its campaign's GM and players: the asset its background
        names, read as the system once membership is checked. A scene whose art is a link elsewhere,
        or has none, has nothing here (404), as does anyone outside the campaign."""
        scene = self._get(SceneManager, scene_id)
        campaign = None if scene is None or scene.campaign_id is None else self._get(CampaignManager, scene.campaign_id)
        if scene is None or campaign is None or not self._is_member(campaign):
            raise _not_found("SceneModel")
        found = ASSET_PATH.fullmatch(self._background_of(scene) or "")
        if found is None:
            raise _not_found("SceneModel")
        from zephyrex.extensions.attachments.BLL_Attachments import AssetManager  # type: ignore[import-not-found]
        from zephyrex.extensions.cloud.EXT_Cloud import EXT_Cloud  # type: ignore[import-not-found]

        try:
            asset = AssetManager(requester_id=env("SYSTEM_ID"), model_registry=self.model_registry).get(id=found.group(1))
        except HTTPException:
            raise _not_found("SceneModel") from None
        content = await EXT_Cloud.download_file(asset.provider, asset.path)
        return Response(
            content=content,
            media_type=asset.content_type,
            headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
        )

    def _empty_view(self, scene: Any) -> dict[str, Any]:
        """A scene's map with nothing on it: for a player of the campaign with no token there."""
        return {
            "scene_id": scene.id,
            "name": scene.name,
            "width": scene.width,
            "height": scene.height,
            "grid_size": float(scene.grid_size or DEFAULT_GRID_SIZE),
            "grid_distance": float(scene.grid_distance or DEFAULT_GRID_DISTANCE),
            "grid_units": scene.grid_units or "ft",
            "background_color": scene.background_color,
            "gm": False,
            "viewer": None,
            "lit": False,
            "tokens": [],
            "walls": [],
            "background_url": self._drawn_background(scene),
        }

    def _gms_of(self, campaign: Any) -> set[str]:
        """Who is a campaign's GM: its owner, or its creator for a campaign made without one."""
        return _campaign_gms(campaign)

    def activate_scene_for(self, scene_id: str) -> SceneSummary:
        """Make a scene its campaign's current scene, and no other: the campaign's GM only."""
        scene = self._get(SceneManager, scene_id)
        campaign = None if scene is None or scene.campaign_id is None else self._get(CampaignManager, scene.campaign_id)
        if scene is None or str(self.requester.id) not in self._gms_of(campaign):
            raise _not_found("SceneModel")
        scenes = self._trusted(SceneManager)
        for other in scenes.list(campaign_id=scene.campaign_id):
            if other.id != scene.id and other.is_active:
                # is_active is server-written (activate only): out of the client's Update schema.
                scenes.update_trusted(id=other.id, is_active=False)
        return self._summarize(scenes.update_trusted(id=scene.id, is_active=True))

    def _is_member(self, campaign: Any) -> bool:
        """The campaign's GM, or a player with a character in it."""
        requester = str(self.requester.id)
        if requester in self._gms_of(campaign):
            return True
        return any(
            requester in _controllers(self.model_registry, person)
            for person in _live(self._trusted(PersonManager), campaign_id=campaign.id)
        )

    def current_scene_for(self, campaign_id: str) -> Optional[SceneSummary]:
        """A campaign's current scene, for its GM and its players (scenes are the GM's rows, so a
        player's own read would miss them: membership is checked here and the scene read as the
        system). With none active, its first scene becomes current; with no scene at all, a default
        one is made where the party is (default_scene_for), so the map is never empty."""
        campaign = self._get(CampaignManager, campaign_id)
        if campaign is None or not self._is_member(campaign):
            return None
        scenes = sorted(
            _live(self._trusted(SceneManager), campaign_id=campaign.id),
            key=lambda one: one.created_at.timestamp() if one.created_at else 0,
        )
        for scene in scenes:
            if scene.is_active:
                return self._summarize(scene)
        if scenes:
            return self._summarize(self._trusted(SceneManager).update_trusted(id=scenes[0].id, is_active=True))
        made = self.default_scene_for(campaign)
        return None if made is None else self._summarize(made)

    def _world(self, campaign: Any, gm: bool) -> tuple[dict[str, ScopedPlace], list[ScopedPerson]]:
        """The campaign's places (its setting's canon too: a scenario's house can sit in a canon
        town) and its people, through the wiki's world_entities. Read as the campaign's GM: the
        caller is a member (checked), and a player can't read the GM's campaign row the wiki checks
        first; a GM-only record is then left out for anyone but the GM."""
        campaign_id = campaign.id
        reader = str(self.requester.id) if gm else str(campaign.user_id or campaign.created_by_user_id)
        world_entities = loaded_ability(self.model_registry, "rpg_core", "world_entities")
        if world_entities is None:
            raise HTTPException(status_code=503, detail={"message": "The wiki's world_entities isn't loaded"})
        found: list[dict[str, Any]] = []
        after: Optional[str] = None
        while True:
            page = world_entities(
                self.model_registry, reader, campaign_id, kinds=["location", "person"], after=after, limit=100, include_setting=True
            )
            found.extend(page.get("world_entities") or [])
            after = page.get("next")
            if not after:
                break
        shown = [one for one in found if not one.get("deleted") and (gm or not one.get("gm_only"))]
        kinds = {person.id: getattr(person, "kind", None) for person in _live(self._trusted(PersonManager), campaign_id=campaign_id)}
        place_ids = sorted({one["id"] for one in shown if one.get("kind") == "location"})
        locations = self._trusted(LocationManager)
        # A place's kind (city, building, room) isn't in world_entities: one read for them all.
        place_kinds = (
            {str(row.id): getattr(row, "kind", None) for row in locations.list(filters=[FieldComparison(locations.Model, "id", "in", place_ids)]) or []}
            if place_ids
            else {}
        )
        places = {
            one["id"]: ScopedPlace(one["id"], one.get("name") or "", place_kinds.get(one["id"]), one.get("parent_id"), one.get("picture"))
            for one in shown
            if one.get("kind") == "location"
        }
        people = [
            ScopedPerson(one["id"], one.get("name") or "", one.get("location_id"), kinds.get(one["id"]) == "pc", one.get("picture"))
            for one in shown
            if one.get("kind") == "person" and not one.get("canon")
        ]
        return places, people

    def scope_for(self, body: ScopeRequest) -> ScopeOut:
        """A place at its scope, for the campaign's GM and players (operator, 2026-11-24: a
        scope-out mode, "the town instead of the house, with a group token for each group of notable
        NPCs if multiple occupy the same building"). Its markers are the places directly inside it
        that NPCs are in, however deep, each a group; the party is its own group where it is. With no
        place named: the current scene's, else the party's. See rpg_scene.Scopes."""
        campaign = self._get(CampaignManager, body.campaign_id)
        if campaign is None or not self._is_member(campaign):
            raise _not_found("CampaignModel")
        gm = str(self.requester.id) in self._gms_of(campaign)
        places, people = self._world(campaign, gm)
        scenes = sorted(
            _live(self._trusted(SceneManager), campaign_id=campaign.id),
            key=lambda one: (not one.is_active, one.created_at.timestamp() if one.created_at else 0),
        )
        location_id = body.location_id
        if location_id is None:
            location_id = next((one.location_id for one in scenes if one.is_active and getattr(one, "location_id", None)), None)
        if location_id is None:
            location_id = next((one.location_id for one in people if one.is_pc and one.location_id), None)
        if location_id is None or location_id not in places:
            raise HTTPException(status_code=422, detail={"message": "No place to show: name one of the campaign's places"})
        scene = next((one for one in scenes if getattr(one, "location_id", None) == location_id), None)
        positions: dict[str, tuple[float, float]] = {}
        if scene is not None and scene.width and scene.height:
            for region in _live(self._trusted(SceneRegionManager), scene_id=scene.id):
                boxes = [box for box in (shape_box(shape) for shape in region.shapes or []) if box]
                if getattr(region, "location_id", None) and boxes:
                    left, top, right, bottom = boxes[0]
                    positions[region.location_id] = ((left + right) / 2 / float(scene.width), (top + bottom) / 2 / float(scene.height))
        gms = self._gms_of(campaign)
        for pinned in _live(self._trusted(ScopePlaceManager), campaign_id=campaign.id):
            # Only the GM's pins count: the table is open to REST like the rest, but the map is theirs.
            if str(getattr(pinned, "created_by_user_id", "")) in gms and pinned.x is not None and pinned.y is not None:
                positions[pinned.location_id] = (float(pinned.x), float(pinned.y))
        scoped = scope_of(places, people, location_id, positions)

        def person(one: ScopedPerson) -> ScopePerson:
            return ScopePerson(person_id=one.id, name=one.name, picture=one.picture)

        def place(one: ScopedPlace) -> ScopePlace:
            return ScopePlace(id=one.id, name=one.name, kind=one.kind, picture=one.picture)

        markers = [
            ScopeMarker(
                location_id=group.place.id,
                name=group.place.name,
                kind=group.place.kind,
                picture=group.place.picture,
                x=group.x,
                y=group.y,
                placed=group.placed,
                people=[person(one) for one in group.npcs],
                count=len(group.npcs),
            )
            for group in scoped.groups
            if group.npcs
        ]
        parties = [
            ScopeParty(location_id=group.place.id, x=party_spot(group)[0], y=party_spot(group)[1], people=[person(one) for one in group.party])
            for group in scoped.groups
            if group.party
        ]
        if scoped.here_party:
            parties.append(ScopeParty(location_id=location_id, x=0.5, y=0.5, people=[person(one) for one in scoped.here_party]))
        return ScopeOut(
            campaign_id=campaign.id,
            location=place(scoped.place),
            scope=scoped.place.kind,
            parent=None if scoped.parent is None else place(scoped.parent),
            path=[place(one) for one in scoped.path],
            background=ScopeBackground(
                url=None if scene is None else self._drawn_background(scene),
                scene_id=None if scene is None else scene.id,
                label=scoped.place.name,
            ),
            markers=markers,
            parties=parties,
            here=[person(one) for one in scoped.here_npcs],
        )

    def place_on_scope_for(self, body: PlaceOnScopeRequest) -> ScopeOut:
        """Pin a place's marker on its parent's map (the GM drags the Halloway house to where it
        stands on the town map); returns the parent's scope. The campaign's GM only."""
        campaign = self._get(CampaignManager, body.campaign_id)
        if campaign is None or str(self.requester.id) not in self._gms_of(campaign):
            raise _not_found("CampaignModel")
        places, _ = self._world(campaign, True)
        place = places.get(body.location_id)
        if place is None or not place.parent_id or place.parent_id not in places:
            raise HTTPException(status_code=422, detail={"message": "That place has no parent map to sit on"})
        mine = ScopePlaceManager(requester_id=str(self.requester.id), model_registry=self.model_registry)
        held = [one for one in _live(mine, campaign_id=campaign.id, location_id=place.id)]
        if held:
            mine.update(id=held[0].id, x=body.x, y=body.y)
            for extra in held[1:]:
                mine.delete(id=extra.id)
        else:
            mine.create(campaign_id=campaign.id, location_id=place.id, x=body.x, y=body.y)
        return self.scope_for(ScopeRequest(campaign_id=campaign.id, location_id=place.parent_id))

    def default_scene_for(self, campaign: Any) -> Any | None:
        """A plain grid scene for a campaign with none, made as its GM and made current: at the
        players' characters' wiki location (named after it, as its map), with a token for each
        character there, placed from the centre outward; with no location, the players' characters.
        None for a campaign without a GM."""
        gm = next(iter(sorted(self._gms_of(campaign))), None)
        if gm is None:
            return None
        persons = _live(self._trusted(PersonManager), campaign_id=campaign.id)
        players = [one for one in persons if _controllers(self.model_registry, one)]
        place = next((one.location_id for one in players if getattr(one, "location_id", None)), None)
        if place is None:
            place = next((one.location_id for one in persons if getattr(one, "location_id", None)), None)
        present = [one for one in persons if place is not None and getattr(one, "location_id", None) == place] or players
        location = None if place is None else self._get(LocationManager, place)
        as_gm = lambda manager: manager(requester_id=gm, model_registry=self.model_registry)  # noqa: E731
        grid = DEFAULT_GRID_SIZE
        scene = as_gm(SceneManager).create(
            name=(getattr(location, "name", None) or getattr(campaign, "name", None) or "The table"),
            campaign_id=campaign.id,
            location_id=place,
            width=int(20 * grid),
            height=int(15 * grid),
        )
        taken: set[tuple[int, int]] = set()
        tokens = as_gm(SceneTokenManager)
        for person in present:
            x, y = self._free_cell(scene, self._arrival_point(scene), taken, gap=1)
            taken.add((int(x // grid), int(y // grid)))
            tokens.create(
                name=person.name or "Character",
                scene_id=scene.id,
                person_id=person.id,
                x=x,
                y=y,
                disposition="friendly" if person in players else "neutral",
            )
        return self._trusted(SceneManager).update_trusted(id=scene.id, is_active=True)

    def copy_scenes_for(self, from_campaign_id: str, to_campaign_id: str, id_map: dict[str, str]) -> list[SceneSummary]:
        """Copy a campaign's scenes, with everything on them (art link, walls and doors, lights,
        regions, tokens), and its GM's marker pins into another campaign: a scenario's maps into a
        playthrough started from it. ``id_map`` maps the source's wiki ids (persons, locations)
        to the copies' (the wiki's instantiate); ids not in it are kept. The source scene that was
        current is current in the copy (else the first). For the target campaign's GM, who can read
        the source campaign."""
        target = self._get(CampaignManager, to_campaign_id)
        if target is None or str(self.requester.id) not in self._gms_of(target):
            raise _not_found("CampaignModel")
        try:
            CampaignManager(requester_id=str(self.requester.id), model_registry=self.model_registry).get(id=from_campaign_id)
        except HTTPException:
            raise _not_found("CampaignModel") from None
        gm = str(self.requester.id)
        mapped = dict(id_map)
        skip = {"id", "created_at", "updated_at", "created_by_user_id", "updated_by_user_id", "deleted_at", "deleted_by_user_id"}

        def copy(manager: type[Any], row: Any, **overrides: Any) -> Any:
            creatable = set(manager._model.Create.model_fields)
            # A column left null is the Create's default, not a null it may refuse (a region's
            # behaviours stored as null failed the whole copy).
            fields = {key: value for key, value in row.model_dump().items() if key in creatable and key not in skip and value is not None}
            for key in ("person_id", "location_id", "scene_level_id", "scene_feature_id"):
                if fields.get(key) is not None:
                    fields[key] = mapped.get(fields[key], fields[key])
            fields.update(overrides)
            made = manager(requester_id=gm, model_registry=self.model_registry).create(**fields)
            mapped[row.id] = made.id
            return made

        copied: list[tuple[Any, Any]] = []
        sources = sorted(
            _live(self._trusted(SceneManager), campaign_id=from_campaign_id),
            key=lambda one: one.created_at.timestamp() if one.created_at else 0,
        )
        for source in sources:
            scene = copy(SceneManager, source, campaign_id=to_campaign_id)
            for part in (SceneLevelManager, SceneFeatureManager, SceneWallManager, SceneLightManager,
                         SceneTileManager, SceneNoteManager, SceneRegionManager, SceneTokenManager):
                for row in _live(self._trusted(part), scene_id=source.id):
                    copy(part, row, scene_id=scene.id)
            copied.append((source, scene))
        # The GM's marker pins on the scope maps (scope_places), onto the copied places. Only the
        # source GM's count there (scope_for), so only theirs come across.
        source_gms = self._gms_of(self._get(CampaignManager, from_campaign_id))
        for pin in _live(self._trusted(ScopePlaceManager), campaign_id=from_campaign_id):
            if str(getattr(pin, "created_by_user_id", "")) in source_gms and pin.x is not None and pin.y is not None:
                copy(ScopePlaceManager, pin, campaign_id=to_campaign_id)
        if not copied:
            return []
        current = next((scene for source, scene in copied if source.is_active), copied[0][1])
        scenes = self._trusted(SceneManager)
        for other in _live(scenes, campaign_id=to_campaign_id):
            if other.is_active and other.id != current.id:
                scenes.update_trusted(id=other.id, is_active=False)
        scenes.update_trusted(id=current.id, is_active=True)
        return [self._summarize(self._get(SceneManager, scene.id) or scene) for _, scene in copied]

    def _arrival_point(self, scene: Any) -> tuple[float, float]:
        """Where arrivals appear: the scene's entry point, else its centre."""
        grid = float(scene.grid_size or DEFAULT_GRID_SIZE)
        width = float(scene.width or 40 * grid)
        height = float(scene.height or 30 * grid)
        x = scene.entry_x if getattr(scene, "entry_x", None) is not None else width / 2
        y = scene.entry_y if getattr(scene, "entry_y", None) is not None else height / 2
        return (float(x), float(y))

    def _place_of(self, campaign_id: str, location_id: str) -> tuple[Any, tuple[float, float]] | None:
        """The scene and point a wiki location is on: a region of a campaign scene whose location it
        is (its centre), else a campaign scene whose location it is (its entry), else the same for the
        location's parents, nearest first. None when no map shows it."""
        scenes = list(self._trusted(SceneManager).list(campaign_id=campaign_id))
        by_id = {scene.id: scene for scene in scenes}
        regions = self._trusted(SceneRegionManager)
        locations = self._trusted(LocationManager)
        seen: set[str] = set()
        current: Optional[str] = location_id
        while current and current not in seen:
            seen.add(current)
            for region in regions.list(location_id=current):
                scene = by_id.get(region.scene_id)
                boxes = [box for box in (shape_box(shape) for shape in region.shapes or []) if box]
                if scene is not None and boxes:
                    left, top, right, bottom = boxes[0]
                    return scene, ((left + right) / 2, (top + bottom) / 2)
            for scene in scenes:
                if getattr(scene, "location_id", None) == current:
                    return scene, self._arrival_point(scene)
            try:
                current = getattr(locations.get(id=current), "parent_id", None)
            except HTTPException:
                current = None
        return None

    def location_at(self, scene: Any, x: float, y: float) -> Optional[str]:
        """The wiki location a point on a scene stands in: the smallest region with a location that
        holds it, else the scene's own location."""
        best: tuple[float, str] | None = None
        for region in self._trusted(SceneRegionManager).list(scene_id=scene.id):
            if not getattr(region, "location_id", None):
                continue
            for shape in region.shapes or []:
                box = shape_box(shape)
                if box and in_shape((x, y), shape):
                    area = (box[2] - box[0]) * (box[3] - box[1])
                    if best is None or area < best[0]:
                        best = (area, region.location_id)
        return best[1] if best else getattr(scene, "location_id", None)

    def sync_location(self, token: Any, scene: Any) -> Optional[str]:
        """The person's wiki location follows their token: the location under its centre. Written as
        the system once the move itself was allowed (a player may move their token without being
        allowed to edit their person record)."""
        if token.person_id is None:
            return None
        grid = float(scene.grid_size or DEFAULT_GRID_SIZE)
        centre_x = float(token.x or 0) + float(token.width or 1) * grid / 2
        centre_y = float(token.y or 0) + float(token.height or 1) * grid / 2
        location = self.location_at(scene, centre_x, centre_y)
        if location:
            person = self._get(PersonManager, token.person_id)
            if person is not None and getattr(person, "location_id", None) != location:
                self._trusted(PersonManager).update(
                    id=token.person_id, location_id=location
                )
        return location

    def _free_cell(self, scene: Any, point: tuple[float, float], taken: set[tuple[int, int]], gap: int = 0) -> tuple[float, float]:
        """The top-left of the free cell nearest a point, inside the scene, spiralling outward. With
        ``gap``, a cell is free only with that many empty cells between it and anyone else, so a crowd
        arriving together spreads out rather than packing into a block (operator, 2026-11-24)."""

        def free(at: tuple[int, int]) -> bool:
            if gap <= 0:
                return at not in taken
            return not any(max(abs(at[0] - one[0]), abs(at[1] - one[1])) <= gap for one in taken)

        grid = float(scene.grid_size or DEFAULT_GRID_SIZE)
        columns = max(1, int(float(scene.width or 40 * grid) // grid))
        rows = max(1, int(float(scene.height or 30 * grid) // grid))
        cx = min(columns - 1, max(0, int(point[0] // grid)))
        cy = min(rows - 1, max(0, int(point[1] // grid)))
        for ring in range(max(columns, rows)):
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    if max(abs(dx), abs(dy)) != ring:
                        continue
                    at = (cx + dx, cy + dy)
                    if 0 <= at[0] < columns and 0 <= at[1] < rows and free(at):
                        return (at[0] * grid, at[1] * grid)
        # No spaced cell left: the nearest free one at all.
        return self._free_cell(scene, point, taken) if gap > 0 else (cx * grid, cy * grid)

    def pilot_for(
        self,
        person_id: str,
        location_id: Optional[str] = None,
        scene_id: Optional[str] = None,
        x: Optional[float] = None,
        y: Optional[float] = None,
        max_distance: Optional[float] = None,
    ) -> PilotOut:
        """The GM (agent) moves a character to a wiki location, or to a point on a scene. On the
        same scene the token walks a path round walls (find_path: the player-move wall rule, within
        the scene), at most ``max_distance`` scene units when given; on another scene it leaves its
        old one and appears at the target's region centre or entry, on the nearest free cell. A place
        on no map takes the character off the maps (their tokens removed). The person's location
        follows. The campaign's GM only."""
        person = self._get(PersonManager, person_id)
        campaign_id = None if person is None else getattr(person, "campaign_id", None)
        campaign = None if campaign_id is None else self._get(CampaignManager, campaign_id)
        if person is None or str(self.requester.id) not in self._gms_of(campaign):
            raise _not_found("PersonModel")
        if (location_id is None) == (scene_id is None):
            raise HTTPException(status_code=422, detail={"message": "Give either a location or a scene"})
        tokens = self._trusted(SceneTokenManager)
        scenes = {scene.id: scene for scene in self._trusted(SceneManager).list(campaign_id=campaign_id)}
        held = [token for token in _live(tokens, person_id=person_id) if token.scene_id in scenes]
        if scene_id is not None:
            scene = scenes.get(scene_id)
            if scene is None:
                raise _not_found("SceneModel")
            point = (float(x), float(y)) if x is not None and y is not None else self._arrival_point(scene)
        else:
            found = self._place_of(campaign_id, location_id or "")
            if found is None:
                for token in held:
                    tokens.delete(id=token.id)
                if location_id and getattr(person, "location_id", None) != location_id:
                    self._trusted(PersonManager).update(
                        id=person_id, location_id=location_id
                    )
                return PilotOut(person_id=person_id, removed=len(held), location_id=location_id)
            scene, point = found
        grid = float(scene.grid_size or DEFAULT_GRID_SIZE)
        here = next((token for token in held if token.scene_id == scene.id), None)
        removed = 0
        for token in held:
            if token is not here:
                tokens.delete(id=token.id)
                removed += 1
        others = {
            (int(float(token.x or 0) // grid), int(float(token.y or 0) // grid))
            for token in _live(tokens, scene_id=scene.id)
            if token.person_id != person_id
        }
        if here is None:
            # A point asked for (beside someone, where the GM tapped) is kept close; an arrival at
            # a place or an entry keeps a cell between people, so a crowd spreads out.
            spot = self._free_cell(scene, point, others, gap=0 if x is not None and y is not None else 1)
            # Made as the requester (the campaign's GM, checked above), not the system: a token the
            # system owns is one the GM's own list and edits can't see.
            mine = SceneTokenManager(requester_id=str(self.requester.id), model_registry=self.model_registry)
            token = mine.create(name=getattr(person, "name", None) or "Token", scene_id=scene.id, person_id=person_id, x=spot[0], y=spot[1])
            location = self.sync_location(token, scene)
            return PilotOut(person_id=person_id, token_id=token.id, scene_id=scene.id, x=spot[0], y=spot[1], removed=removed, location_id=location)
        start = (float(here.x or 0) + grid / 2, float(here.y or 0) + grid / 2)
        bounds = (float(scene.width or 40 * grid), float(scene.height or 30 * grid))
        walls = [_wall(row) for row in self._trusted(SceneWallManager).list(scene_id=scene.id)]
        path = find_path(start, point, grid, bounds, walls)
        if path is None:
            raise HTTPException(status_code=422, detail={"message": "There's no way through to there"})
        steps = len(path) - 1
        allowed = steps
        if max_distance is not None:
            allowed = min(steps, int(max(0.0, max_distance) // float(scene.grid_distance or DEFAULT_GRID_DISTANCE)))
        stop = path[allowed]
        target = (stop[0] - grid / 2, stop[1] - grid / 2)
        moved = tokens.update(id=here.id, x=target[0], y=target[1])
        location = self.sync_location(moved, scene)
        return PilotOut(
            person_id=person_id,
            token_id=here.id,
            scene_id=scene.id,
            x=target[0],
            y=target[1],
            arrived=allowed == steps,
            remaining=(steps - allowed) * float(scene.grid_distance or DEFAULT_GRID_DISTANCE),
            removed=removed,
            location_id=location,
        )

    def move_token_to_scene_for(self, token_id: str, scene_id: str) -> PilotOut:
        """Move a token to another scene of its campaign (someone leaves the docks for the tavern):
        off this scene, onto the target at its entry, on the nearest free cell. A character's token
        goes as pilot_token moves them (one token per person, their wiki location following); a
        token with no character moves as it is. The campaign's GM only."""
        token = self._get(SceneTokenManager, token_id)
        here = None if token is None else self._get(SceneManager, token.scene_id)
        there = self._get(SceneManager, scene_id)
        campaign = None if here is None or here.campaign_id is None else self._get(CampaignManager, here.campaign_id)
        if token is None or here is None or str(self.requester.id) not in self._gms_of(campaign):
            raise _not_found("SceneTokenModel")
        if there is None or there.campaign_id != here.campaign_id:
            raise _not_found("SceneModel")
        if token.person_id is not None:
            return self.pilot_for(token.person_id, scene_id=there.id)
        grid = float(there.grid_size or DEFAULT_GRID_SIZE)
        taken = {
            (int(float(one.x or 0) // grid), int(float(one.y or 0) // grid))
            for one in _live(self._trusted(SceneTokenManager), scene_id=there.id)
        }
        x, y = self._free_cell(there, self._arrival_point(there), taken, gap=1)
        self._trusted(SceneTokenManager).update_trusted(id=token.id, scene_id=there.id, scene_level_id=None, x=x, y=y)
        return PilotOut(person_id="", token_id=token.id, scene_id=there.id, x=x, y=y)

    def remove_person_for(self, scene_id: str, body: RemoveRequest) -> RemoveOut:
        """Take a person's token off a scene (someone leaves, the story not saying where): their wiki
        location is left as it is. False when they had no token there. The campaign's GM only."""
        scene = self._get(SceneManager, scene_id)
        campaign = None if scene is None or scene.campaign_id is None else self._get(CampaignManager, scene.campaign_id)
        if scene is None or str(self.requester.id) not in self._gms_of(campaign):
            raise _not_found("SceneModel")
        tokens = self._trusted(SceneTokenManager)
        held = _live(tokens, scene_id=scene.id, person_id=body.person_id)
        for token in held:
            tokens.delete(id=token.id)
        return RemoveOut(scene_id=scene.id, person_id=body.person_id, removed=bool(held))

    def place_person_for(self, scene_id: str, body: PlaceRequest) -> PilotOut:
        """Put a person of the campaign on a scene (an NPC the GM just authored): on the nearest free
        cell beside ``near_person_id``'s token there, else at the point given, else at the scene's
        entry. One token per person, as pilot_token keeps it (off any other scene); their wiki
        location follows the scene. The campaign's GM only."""
        scene = self._get(SceneManager, scene_id)
        if scene is None:
            raise _not_found("SceneModel")
        x, y = body.x, body.y
        if body.near_person_id is not None:
            beside = next(iter(_live(self._trusted(SceneTokenManager), scene_id=scene.id, person_id=body.near_person_id)), None)
            if beside is not None:
                grid = float(scene.grid_size or DEFAULT_GRID_SIZE)
                x = float(beside.x or 0) + float(beside.width or 1) * grid / 2
                y = float(beside.y or 0) + float(beside.height or 1) * grid / 2
        return self.pilot_for(body.person_id, scene_id=scene.id, x=x, y=y)

    def tokens_for(self, scene_id: str) -> list[SceneTokenOut]:
        """Who is on a scene: each token and the wiki person it stands for. The campaign's GM gets
        every token, hidden ones flagged (a GM-side decision may count them); a member of the
        campaign gets the ones not hidden; anyone else the same 404 as a missing scene."""
        scene = self._get(SceneManager, scene_id)
        if scene is None:
            raise _not_found("SceneModel")
        requester = str(self.requester.id)
        campaign = None if scene.campaign_id is None else self._get(CampaignManager, scene.campaign_id)
        gm = requester in _campaign_gms(campaign)
        rows = list(_live(self._trusted(SceneTokenManager), scene_id=scene.id))
        if not gm and (campaign is None or not self._is_member(campaign)):
            raise _not_found("SceneModel")
        return [
            SceneTokenOut(token_id=row.id, name=row.name, entity_id=row.person_id, hidden=bool(row.is_hidden))
            for row in rows
            if gm or not row.is_hidden
        ]

    @custom_route(
        method="POST",
        path="/{scene_id}/activate",
        input_model=ActivateEnvelope,
        output_model=SceneSummary,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="Make a scene its campaign's current scene (the campaign's GM)",
    )
    async def activate_route(self, scene_id: str, body: ActivateEnvelope) -> SceneSummary:
        return self.activate_scene_for(scene_id)

    @custom_route(
        method="POST",
        path="/{scene_id}/import_uvtt",
        input_model=UvttEnvelope,
        output_model=UvttOut,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="A Universal VTT map's walls, doors and lights onto a scene, which takes its size and grid (the campaign's GM)",
    )
    async def import_uvtt_route(self, scene_id: str, body: UvttEnvelope) -> UvttOut:
        return self.import_uvtt_for(scene_id, body.import_uvtt)

    @custom_route(
        method="GET",
        path="/{scene_id}/background",
        authentication_type="jwt",
        response_class=Response,
        openapi_tags=("Scenes",),
        summary="A scene's uploaded map art, for its campaign's GM and players",
        expose_in=(ExposeIn.REST,),
    )
    async def background_route(self, scene_id: str) -> Response:
        return await self.background_for(scene_id)

    @custom_route(
        method="POST",
        path="/scope",
        input_model=ScopeEnvelope,
        output_model=ScopeOut,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="A place at its scope: the places inside it that people are in, as group markers, and the party",
    )
    async def scope_route(self, body: ScopeEnvelope) -> ScopeOut:
        return self.scope_for(body.scope)

    @custom_route(
        method="POST",
        path="/place_on_scope",
        input_model=PlaceOnScopeEnvelope,
        output_model=ScopeOut,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="Pin a place's marker on its parent's map (the campaign's GM); returns the parent's scope",
    )
    async def place_on_scope_route(self, body: PlaceOnScopeEnvelope) -> ScopeOut:
        return self.place_on_scope_for(body.place_on_scope)

    @custom_route(
        method="POST",
        path="/current",
        input_model=CurrentEnvelope,
        output_model=CurrentOut,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="A campaign's current scene, or none",
    )
    async def current_route(self, body: CurrentEnvelope) -> CurrentOut:
        return CurrentOut(scene=self.current_scene_for(body.current.campaign_id))

    @custom_route(
        method="POST",
        path="/{scene_id}/place",
        input_model=PlaceEnvelope,
        output_model=PilotOut,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="Put a person on a scene beside another's token, at a point, or at the entry (the campaign's GM)",
    )
    async def place_route(self, scene_id: str, body: PlaceEnvelope) -> PilotOut:
        return self.place_person_for(scene_id, body.place)

    @custom_route(
        method="POST",
        path="/{scene_id}/remove",
        input_model=RemoveEnvelope,
        output_model=RemoveOut,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="Take a person's token off a scene, their wiki location left as it is (the campaign's GM)",
    )
    async def remove_route(self, scene_id: str, body: RemoveEnvelope) -> RemoveOut:
        return self.remove_person_for(scene_id, body.remove)

    @custom_route(
        method="POST",
        path="/copy",
        input_model=CopyEnvelope,
        output_model=CopiedEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="Copy a campaign's scenes into another (a scenario's maps into its playthrough; the target's GM)",
    )
    async def copy_route(self, body: CopyEnvelope) -> CopiedEnvelope:
        request = body.copy_scenes
        return CopiedEnvelope(scenes=self.copy_scenes_for(request.from_campaign_id, request.to_campaign_id, request.id_map))

    @custom_route(
        method="GET",
        path="/{scene_id}/tokens",
        output_model=SceneTokensOut,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="Who is on a scene: tokens and the wiki persons they stand for (hidden ones for the GM, flagged)",
    )
    async def tokens_route(self, scene_id: str) -> SceneTokensOut:
        return SceneTokensOut(scene_tokens=self.tokens_for(scene_id))

    @custom_route(
        method="POST",
        path="/{scene_id}/view",
        input_model=ViewEnvelope,
        output_model=ViewResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="What to draw of a scene for the requester: the GM's whole view, or a player's token's sight",
    )
    async def view_route(self, scene_id: str, body: ViewEnvelope) -> ViewResultEnvelope:
        return ViewResultEnvelope(view=self.view_for(scene_id, body.view))

    @custom_route(
        method="POST",
        path="/{scene_id}/snapshot",
        input_model=SnapshotEnvelope,
        output_model=SnapshotResultEnvelope,
        authentication_type="jwt",
        expose_in=(ExposeIn.REST,),
        openapi_tags=("Scenes",),
        summary="What a token perceives in its scene, decided on the server (A23)",
    )
    async def snapshot_route(self, scene_id: str, body: SnapshotEnvelope) -> SnapshotResultEnvelope:
        return SnapshotResultEnvelope(snapshot=self.snapshot_for(scene_id, body.snapshot))


SceneModel.Manager = SceneManager

# Live rooms (server-framework `rooms`; inert when the app doesn't load it): everything on a scene
# changes in that scene's room. Changes carry no record data, so a hidden token's move never leaks;
# viewers refetch through scene_snapshot, the one place sight is decided.
# A scene is also news in its campaign's room (list-level: a scene added, renamed, removed); what's
# on it stays in the scene's own room, so a campaign page doesn't hear every token move.
room_of(
    SceneManager,
    lambda scene: [("scene", scene.id)] + ([("campaign", scene.campaign_id)] if scene.campaign_id else []),
)
for _part in (
    SceneLevelManager,
    SceneFeatureManager,
    SceneTokenManager,
    SceneWallManager,
    SceneLightManager,
    SceneTileManager,
    SceneNoteManager,
    SceneRegionManager,
):
    room_of(_part, lambda record: ("scene", record.scene_id) if record.scene_id else None)


def _copy_on_instantiate(model_registry: Any, requester_id: str, source_id: str, made_id: str, id_map: dict[str, str]) -> None:
    """The wiki's instantiate (a playthrough started from a scenario) copies the scenario's scenes,
    tokens remapped to the copied characters, when the wiki offers the AFTER_INSTANTIATE callbacks."""
    SceneManager(requester_id=requester_id, model_registry=model_registry).copy_scenes_for(source_id, made_id, id_map)


def register_copy(model_registry: Any) -> bool:
    """The copy above registered with the wiki through its published ability
    (register_instantiate_hook, wiki b289c56), so any backend offering it serves; an older wiki
    without it still takes the copy on its AFTER_INSTANTIATE list. Registering twice is a no-op.
    False when neither is there."""
    from zephyrex.extensions.AbstractExtensionProvider import loaded_ability
    from zephyrex.lib.Environment import env

    register = loaded_ability(model_registry, "rpg_core", "register_instantiate_hook")
    if register is not None:
        register(model_registry, str(env("ROOT_ID")), _copy_on_instantiate)
        return True
    try:
        from zephyrex.extensions.rpg_core.BLL_RPGCore import AFTER_INSTANTIATE  # type: ignore[import-not-found,attr-defined]
    except ImportError:
        return False
    if _copy_on_instantiate not in AFTER_INSTANTIATE:
        AFTER_INSTANTIATE.append(_copy_on_instantiate)
    return True
