# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_modules: private rules and content modules (operator, 2026-11-21).

The six [redacted] [redacted] lines come in from the redacted Foundry system's compendiums through the bridge
(tools/foundry-bridge: extract.mjs writes a line's bundle, Install.py installs it). The content is
private:
- a module and everything installed from it belong to the account that installed it, never the
  framework's SYSTEM user, so on a hosted instance no other account sees them;
- a campaign plays with the modules its GM enables (CampaignModule).

ModuleRecord maps each source document, keyed (module, Foundry _id), to the vtt record made from it,
with the document's content hash and its materialized data. So a re-install updates in place,
removes what the source dropped, and keeps what vtt's own models don't hold (a talent's
prerequisites and modifiers, an origin step's grants) for the later phases.
"""

from __future__ import annotations

from typing import Any, ClassVar, Optional, Type

from pydantic import Field
from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignModel  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_systems.BLL_RPGSystems import GameSystemModel  # type: ignore[import-not-found]
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


class ContentModuleModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    GameSystemModel.Reference.Optional,
    metaclass=ModelMeta,
):
    """One line's rules and content, as one account installed it."""

    Manager: ClassVar[Type["ContentModuleManager"]] = None
    slug: Optional[str] = Field(None, description="redacted-dh2, redacted-rt…")
    line: Optional[str] = Field(None, description="The source's line key (dh2, rt…)")
    system_ref: Optional[str] = Field(None, description="The redacted system commit it was read with")
    content_ref: Optional[str] = Field(None, description="The content repository commit it was read from")
    document_count: Optional[int] = Field(None, description="Source documents installed")
    rules: Optional[dict[str, Any]] = Field(None, description="The line's test rules (characteristics, ranks, difficulties…)")
    table_comment: ClassVar[str] = "A private rules/content module, owned by the account that installed it"

    class Create(BaseModel, GameSystemModel.Reference.ID.Optional):
        name: str = Field(...)
        slug: str = Field(..., max_length=100)
        line: str = Field(..., max_length=20)
        system_ref: Optional[str] = None
        content_ref: Optional[str] = None
        document_count: Optional[int] = None
        rules: Optional[dict[str, Any]] = None

    class Update(BaseModel):
        name: Optional[str] = None
        system_ref: Optional[str] = None
        content_ref: Optional[str] = None
        document_count: Optional[int] = None
        rules: Optional[dict[str, Any]] = None

    class Search(ApplicationModel.Search, GameSystemModel.Reference.ID.Search):
        slug: Optional[StringSearchModel] = None
        line: Optional[StringSearchModel] = None


class ModuleRecordModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    ContentModuleModel.Reference.Optional,
    metaclass=ModelMeta,
):
    """A source document of a module and the vtt record made from it."""

    Manager: ClassVar[Type["ModuleRecordManager"]] = None
    source_id: Optional[str] = Field(None, description="The Foundry document's _id")
    source_type: Optional[str] = Field(None, description="Its Foundry type (talent, skill, originPath…)")
    entity_type: Optional[str] = Field(None, description="The vtt record it became (trait…)")
    entity_id: Optional[str] = Field(None, description="That record's id")
    content_hash: Optional[str] = Field(None)
    homebrew: Optional[bool] = Field(False)
    conversion: Optional[bool] = Field(False, description="Another line's document, ported to this one")
    provenance: Optional[str] = Field(None, description="raw, homebrew… as the source labels it for the line")
    book: Optional[str] = Field(None)
    page: Optional[str] = Field(None)
    data: Optional[dict[str, Any]] = Field(None, description="The document's system data, materialized for the line")
    table_comment: ClassVar[str] = "A source document of a module, and the vtt record it became"

    class Create(BaseModel, ContentModuleModel.Reference.ID):
        source_id: str = Field(..., max_length=64)
        source_type: Optional[str] = None
        entity_type: Optional[str] = None
        entity_id: Optional[str] = None
        content_hash: Optional[str] = None
        homebrew: bool = False
        conversion: bool = False
        provenance: Optional[str] = None
        book: Optional[str] = None
        page: Optional[str] = None
        data: Optional[dict[str, Any]] = None

    class Update(BaseModel):
        source_type: Optional[str] = None
        entity_type: Optional[str] = None
        entity_id: Optional[str] = None
        content_hash: Optional[str] = None
        homebrew: Optional[bool] = None
        conversion: Optional[bool] = None
        provenance: Optional[str] = None
        book: Optional[str] = None
        page: Optional[str] = None
        data: Optional[dict[str, Any]] = None

    class Search(ApplicationModel.Search, ContentModuleModel.Reference.ID.Search):
        source_id: Optional[StringSearchModel] = None
        source_type: Optional[StringSearchModel] = None


class CampaignModuleModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    CampaignModel.Reference.Optional,
    ContentModuleModel.Reference.Optional,
    metaclass=ModelMeta,
):
    """A module a campaign plays with, enabled by its GM."""

    Manager: ClassVar[Type["CampaignModuleManager"]] = None
    table_comment: ClassVar[str] = "A module enabled for a campaign"

    class Create(BaseModel, CampaignModel.Reference.ID, ContentModuleModel.Reference.ID):
        pass

    class Update(BaseModel):
        pass

    class Search(ApplicationModel.Search, CampaignModel.Reference.ID.Search, ContentModuleModel.Reference.ID.Search):
        pass


class ContentModuleManager(AbstractBLLManager, RouterMixin):
    _model = ContentModuleModel


class ModuleRecordManager(AbstractBLLManager, RouterMixin):
    _model = ModuleRecordModel


class CampaignModuleManager(AbstractBLLManager, RouterMixin):
    _model = CampaignModuleModel


ContentModuleModel.Manager = ContentModuleManager
ModuleRecordModel.Manager = ModuleRecordManager
CampaignModuleModel.Manager = CampaignModuleManager

ALL_MODELS: list[type] = [ContentModuleModel, ModuleRecordModel, CampaignModuleModel]
