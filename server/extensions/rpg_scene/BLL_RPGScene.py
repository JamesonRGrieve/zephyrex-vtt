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

from typing import Any, ClassVar, Literal, Optional, Type

from fastapi import HTTPException
from pydantic import BaseModel as PlainModel
from pydantic import Field
from zephyrex.lib.Rooms import room_of
from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager, PersonModel
from zephyrex.extensions.rpg_scene.Vision import FULL_CIRCLE, Scene, Token, Wall, blocks_move, perceive
from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignManager, CampaignModel  # type: ignore[import-not-found]
from zephyrex.lib.CustomRoute import ExposeIn, custom_route
from zephyrex.lib.Environment import env
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


class SceneModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    CampaignModel.Reference.Optional,
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
    table_comment: ClassVar[str] = "A playable area in a campaign: the battlemap a table plays on"

    class Create(BaseModel, CampaignModel.Reference.ID.Optional):
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

    class Update(BaseModel):
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

    class Search(ApplicationModel.Search, CampaignModel.Reference.ID.Search):
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
        BaseModel, SceneModel.Reference.ID, SceneLevelModel.Reference.ID.Optional, SceneFeatureModel.Reference.ID.Optional
    ):
        name: Optional[str] = None
        shapes: list[dict[str, Any]] = Field(..., min_length=1)
        behaviours: list[dict[str, Any]] = Field(default_factory=list)
        is_hidden: bool = False

    class Update(BaseModel):
        name: Optional[str] = None
        shapes: Optional[list[dict[str, Any]]] = Field(None, min_length=1)
        behaviours: Optional[list[dict[str, Any]]] = None
        is_hidden: Optional[bool] = None

    class Search(ApplicationModel.Search, SceneModel.Reference.ID.Search, SceneFeatureModel.Reference.ID.Search):
        pass


class MoveRequest(PlainModel):
    x: float
    y: float


class MoveEnvelope(PlainModel):
    move: MoveRequest


class MovedEnvelope(PlainModel):
    scene_token: dict[str, Any]


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
        gm = campaign is not None and requester == campaign.user_id
        player = False
        if not gm and token.person_id is not None:
            try:
                player = getattr(self._trusted(PersonManager).get(id=token.person_id), "user_id", None) == requester
            except HTTPException:
                player = False
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


SceneTokenModel.Manager = SceneTokenManager
SceneWallModel.Manager = SceneWallManager
SceneLevelModel.Manager = SceneLevelManager
SceneFeatureModel.Manager = SceneFeatureManager
SceneLightModel.Manager = SceneLightManager
SceneTileModel.Manager = SceneTileManager
SceneNoteModel.Manager = SceneNoteManager
SceneRegionModel.Manager = SceneRegionManager

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


class ViewResultEnvelope(PlainModel):
    view: ViewOut


class SceneTokenOut(PlainModel):
    token_id: str
    name: Optional[str]
    entity_id: Optional[str]
    hidden: bool


class SceneTokensOut(PlainModel):
    scene_tokens: list[SceneTokenOut]


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
        gm = campaign is not None and requester == campaign.user_id
        player = person is not None and requester == getattr(person, "user_id", None)
        if not (gm or player):
            # The same answer as a scene or token that isn't there.
            raise _not_found("SceneTokenModel")
        rows = list(self._trusted(SceneTokenManager).list(scene_id=scene.id))
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
        gm = campaign is not None and requester == campaign.user_id
        rows = list(self._trusted(SceneTokenManager).list(scene_id=scene.id))
        walls = list(self._trusted(SceneWallManager).list(scene_id=scene.id))
        people: dict[str, Any] = {}

        def owner(row: Any) -> Optional[str]:
            if row.person_id is None:
                return None
            if row.person_id not in people:
                people[row.person_id] = self._get(PersonManager, row.person_id)
            person = people[row.person_id]
            return None if person is None else getattr(person, "user_id", None)

        mine = {row.id for row in rows if owner(row) == requester}
        viewer = None
        if body.token_id is not None:
            viewer = next((row for row in rows if row.id == body.token_id), None)
            if viewer is None or not (gm or viewer.id in mine):
                raise _not_found("SceneTokenModel")
        elif not gm:
            viewer = next((row for row in rows if row.id in mine), None)
            if viewer is None:
                raise _not_found("SceneModel")

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
        )

    def tokens_for(self, scene_id: str) -> list[SceneTokenOut]:
        """Who is on a scene: each token and the wiki person it stands for. The campaign's GM gets
        every token, hidden ones flagged (a GM-side decision may count them); a member of the
        campaign gets the ones not hidden; anyone else the same 404 as a missing scene."""
        scene = self._get(SceneManager, scene_id)
        if scene is None:
            raise _not_found("SceneModel")
        requester = str(self.requester.id)
        campaign = None if scene.campaign_id is None else self._get(CampaignManager, scene.campaign_id)
        owners = set() if campaign is None else {
            str(owner) for owner in (campaign.user_id, getattr(campaign, "created_by_user_id", None)) if owner
        }
        gm = requester in owners
        rows = list(self._trusted(SceneTokenManager).list(scene_id=scene.id))
        if not gm:
            member = False
            for row in rows:
                person = None if row.person_id is None else self._get(PersonManager, row.person_id)
                if person is not None and getattr(person, "user_id", None) == requester:
                    member = True
                    break
            if not member:
                raise _not_found("SceneModel")
        return [
            SceneTokenOut(token_id=row.id, name=row.name, entity_id=row.person_id, hidden=bool(row.is_hidden))
            for row in rows
            if gm or not row.is_hidden
        ]

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
