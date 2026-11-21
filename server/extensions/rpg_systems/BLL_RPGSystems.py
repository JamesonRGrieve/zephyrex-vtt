# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_systems: the game systems a campaign runs on (the VTT's half of OBJECT_PLAN's rpg_core; the
wiki's rpg_core keeps campaigns and the character fields). It also gives the wiki's campaigns and
items the game system they belong to (``game_system_id``), which its migration adds to their tables.
Split from rpg_state (operator, 2026-11-20).
"""

from __future__ import annotations

from typing import ClassVar, List, Optional, Type

from pydantic import Field

from zephyrex.pydantic2.registry import BaseModel
from zephyrex.pydantic2.fastapi import RouterMixin
from zephyrex.pydantic2.sqlalchemy import extension_model
from zephyrex.logic.AbstractLogicManager import (
    AbstractBLLManager,
    ApplicationModel,
    DescriptionMixinModel,
    ModelMeta,
    NameMixinModel,
    StringSearchModel,
    UpdateMixinModel,
)

from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignModel  # type: ignore[import-not-found]
from zephyrex.extensions.world_inventory.BLL_WorldInventory import ItemModel  # type: ignore[import-not-found]


# ---------------------------------------------------------------------------
# 1. GameSystem — reference catalog
# ---------------------------------------------------------------------------


class GameSystemModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    DescriptionMixinModel.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["GameSystemManager"]] = None
    table_comment: ClassVar[str] = (
        "Reference catalog of supported RPG systems (DnD 5e, Pathfinder 2e, ...)"
    )

    class Create(BaseModel):
        name: str = Field(..., description="Display name of the system")
        description: Optional[str] = Field(None)

    class Update(BaseModel):
        name: Optional[str] = None
        description: Optional[str] = None

    class Search(ApplicationModel.Search):
        name: Optional[StringSearchModel] = None


class GameSystemManager(AbstractBLLManager, RouterMixin):
    _model = GameSystemModel


# ---------------------------------------------------------------------------
# 2. The game system a wiki campaign or item belongs to
# ---------------------------------------------------------------------------


@extension_model(CampaignModel)
class RPG_CampaignSystemModel(BaseModel):
    """The game system a campaign runs on, added to the wiki's campaigns."""

    game_system_id: Optional[str] = Field(None, description="FK → game_systems.id; the rules it runs on")

    class Create(BaseModel):
        game_system_id: Optional[str] = None

    class Update(BaseModel):
        game_system_id: Optional[str] = None

    class Search(BaseModel):
        game_system_id: Optional[StringSearchModel] = None


@extension_model(ItemModel)
class RPG_ItemSystemModel(BaseModel):
    """The game system an item's stats belong to, added to the wiki's items."""

    game_system_id: Optional[str] = Field(None, description="FK → game_systems.id; none = any system")

    class Create(BaseModel):
        game_system_id: Optional[str] = None

    class Update(BaseModel):
        game_system_id: Optional[str] = None

    class Search(BaseModel):
        game_system_id: Optional[StringSearchModel] = None


GameSystemModel.Manager = GameSystemManager

ALL_MODELS: List[type] = [GameSystemModel]
