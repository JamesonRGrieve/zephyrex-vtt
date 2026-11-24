# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_systems: the game systems a campaign runs on (the VTT's half of OBJECT_PLAN's rpg_core; the
wiki's rpg_core keeps campaigns and the character fields). It also gives the wiki's campaigns and
items the game system they belong to (``game_system_id``), which its migration adds to their tables.
Split from rpg_state (operator, 2026-11-20).

A game system belongs to a setting (the wiki's settings), which is the wiki's (rpg_core's
SettingModel, the wiki's S6; docs/SUITE.md: the wiki owns campaigns, world and canon, vtt owns
systems and mechanics). The wiki sits above vtt, so ``setting_id`` is a reference by id, not a
foreign key. The systems the operator named are seeded by name (game-systems.json, migration 003);
their mechanics come per system pack.
"""

from __future__ import annotations

import re
from typing import ClassVar, List, Optional, Type

from pydantic import Field, model_validator

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


SLUG_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"


def slugify(name: str) -> str:
    """A name as a slug: lower case, words joined by hyphens ("Fifth Edition SRD" → "fifth-edition-srd")."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unnamed"


class GameSystemModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    DescriptionMixinModel.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["GameSystemManager"]] = None
    slug: Optional[str] = Field(None, description="Stable name (srd-5e); from the name when not given")
    setting_id: Optional[str] = Field(None, description="The wiki's setting it belongs to (a reference, no FK)")
    table_comment: ClassVar[str] = (
        "Reference catalog of supported RPG systems (DnD 5e, Pathfinder 2e, ...)"
    )

    class Create(BaseModel):
        name: str = Field(..., description="Display name of the system")
        description: Optional[str] = Field(None)
        slug: Optional[str] = Field(None, pattern=SLUG_PATTERN)
        setting_id: Optional[str] = None

        @model_validator(mode="after")
        def _slug_from_name(self) -> "GameSystemModel.Create":
            if self.slug is None:
                self.slug = slugify(self.name)
            return self

    class Update(BaseModel):
        name: Optional[str] = None
        description: Optional[str] = None
        slug: Optional[str] = Field(None, pattern=SLUG_PATTERN)
        setting_id: Optional[str] = None

    class Search(ApplicationModel.Search):
        name: Optional[StringSearchModel] = None
        slug: Optional[StringSearchModel] = None
        setting_id: Optional[StringSearchModel] = None


class GameSystemManager(AbstractBLLManager, RouterMixin):
    _model = GameSystemModel


# ---------------------------------------------------------------------------
# 2. The game system a wiki campaign or item belongs to
# ---------------------------------------------------------------------------


# The highest starting level any pack could state; each pack's own maximum is checked where it's used.
MAX_STARTING_LEVEL = 30


@extension_model(CampaignModel)
class RPG_CampaignSystemModel(BaseModel):
    """The game system a campaign runs on, added to the wiki's campaigns."""

    game_system_id: Optional[str] = Field(None, description="FK → game_systems.id; the rules it runs on")
    starting_level: Optional[int] = Field(
        None, description="The level its characters start at (a scenario's pregens are built to it); none is the pack's first"
    )

    class Create(BaseModel):
        game_system_id: Optional[str] = None
        starting_level: Optional[int] = Field(None, ge=1, le=MAX_STARTING_LEVEL)

    class Update(BaseModel):
        game_system_id: Optional[str] = None
        starting_level: Optional[int] = Field(None, ge=1, le=MAX_STARTING_LEVEL)

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
