# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_state, what's left of it after the suite split (operator, 2026-11-20; OBJECT_PLAN §6): the
narrative hooks and the faction endpoints on genealogy's relationships, kept here only until the
wiki's world_narrative (S3) and world_social relationships (S4) take them. Everything else moved:

- game systems → rpg_systems; traits, derivative traits, person traits → rpg_traits (both here);
- campaigns and the character fields on persons → the wiki's rpg_core; locations → world_spatial;
  factions → world_social; items and item instances → world_inventory.

Hook DAG
--------
There is **no** separate Quest / Objective hierarchy. Both fold into ``HookModel``: a campaign-scoped
narrative element with a free-form ``kind``. Dependencies between hooks live in
``HookDependencyModel(parent_hook_id, child_hook_id, reason)``; per-actor progress in
``PersonHookModel`` and ``FactionHookModel``.

This extension ships no migration: its hook tables come from the framework's create_all, and the
faction endpoint columns on ``relationships`` (a migrated table) are not added to the database until
the wiki's world_social owns them, so they are not usable meanwhile.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, List, Literal, Optional, Type

from pydantic import Field

from zephyrex.extensions.genealogy.BLL_Genealogy import PersonModel, RelationshipModel
from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignModel  # type: ignore[import-not-found]
from zephyrex.extensions.world_social.BLL_WorldSocial import FactionModel  # type: ignore[import-not-found]
from zephyrex.lib.CycleGuard import CycleGuardError, would_create_dag_cycle
from zephyrex.logic.AbstractLogicManager import (
    AbstractBLLManager,
    ApplicationModel,
    DescriptionMixinModel,
    HookContext,
    HookTiming,
    ModelMeta,
    NameMixinModel,
    NumericalSearchModel,
    StringSearchModel,
    UpdateMixinModel,
    hook_bll,
)
from zephyrex.pydantic2.fastapi import RouterMixin
from zephyrex.pydantic2.registry import BaseModel
from zephyrex.pydantic2.sqlalchemy import extension_model

HookKind = Literal[
    "major_quest",
    "side_quest",
    "objective",
    "plot_thread",
    "mystery",
    "rumor",
    "obligation",
    "foreshadowing",
    "hint",
    "background",
]
"""Closed set of Hook narrative kinds for ``HookModel``."""


# ---------------------------------------------------------------------------
# 9. Hooks — narrative DAG (replaces Quest+Objective)
# ---------------------------------------------------------------------------


class HookModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    DescriptionMixinModel.Optional,
    CampaignModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["HookManager"]] = None
    kind: Optional[HookKind] = Field(
        None,
        description=(
            "Closed enum: major_quest|side_quest|objective|plot_thread|"
            "mystery|rumor|obligation|foreshadowing|hint|background. "
            "Validated by Pydantic Literal and enforced in DDL by a "
            "CHECK constraint in the migration."
        ),
    )
    giver_faction_id: Optional[str] = Field(
        None,
        description="Faction that issued the hook (FK → factions.id).",
    )
    table_comment: ClassVar[str] = (
        "Narrative element. Replaces Quest+Objective with a single "
        "table; hierarchy and prerequisite relationships move to "
        "HookDependency. Per-actor progress lives in PersonHook / "
        "FactionHook."
    )

    class Create(BaseModel, CampaignModel.Reference.ID.Optional):
        name: str = Field(...)
        description: Optional[str] = None
        kind: Optional[HookKind] = None
        giver_faction_id: Optional[str] = None

    class Update(BaseModel):
        name: Optional[str] = None
        description: Optional[str] = None
        kind: Optional[HookKind] = None
        giver_faction_id: Optional[str] = None

    class Search(ApplicationModel.Search, CampaignModel.Reference.ID.Search):
        name: Optional[StringSearchModel] = None
        kind: Optional[StringSearchModel] = None


class HookManager(AbstractBLLManager, RouterMixin):
    _model = HookModel


HookModel.Manager = HookManager


class HookDependencyModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["HookDependencyManager"]] = None
    # Both endpoints reference hooks.id; manual columns since
    # HookModel.Reference would generate one hook_id and collide on the
    # second.
    parent_hook_id: Optional[str] = Field(
        None,
        description="The prerequisite Hook (FK → hooks.id).",
    )
    child_hook_id: Optional[str] = Field(
        None,
        description="The dependent Hook (FK → hooks.id).",
    )
    reason: Optional[str] = Field(
        None,
        description=(
            "Free-form explanation of why the dependency exists "
            "('requires the dragon to be slain first', "
            "'alternative path via diplomacy', "
            "'blocked while the curse is active'). The presence of the "
            "row IS the dependency; reason explains it."
        ),
    )
    table_comment: ClassVar[str] = (
        "DAG edge between two Hooks. Presence of a row IS the "
        "dependency; the reason string explains it. No dependency-kind "
        "enum: complete/fail/unlock/block/alternative-path semantics "
        "are described in the reason text. Manager-layer cycle guard "
        "rejects edits that would close a cycle."
    )

    class Create(BaseModel):
        parent_hook_id: Optional[str] = None
        child_hook_id: Optional[str] = None
        reason: Optional[str] = None

    class Update(BaseModel):
        reason: Optional[str] = None

    class Search(ApplicationModel.Search):
        parent_hook_id: Optional[StringSearchModel] = None
        child_hook_id: Optional[StringSearchModel] = None
        reason: Optional[StringSearchModel] = None


class HookDependencyManager(AbstractBLLManager, RouterMixin):
    _model = HookDependencyModel


HookDependencyModel.Manager = HookDependencyManager


class PersonHookModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    PersonModel.Reference.Optional,
    HookModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["PersonHookManager"]] = None
    status: Optional[str] = Field(
        None,
        description=(
            "available|active|completed|failed|abandoned|superseded|... "
            "(free-form; non-quest Hooks may use 'unresolved' / "
            "'resolved' instead)"
        ),
    )
    accepted_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)
    progress: Optional[float] = Field(
        None,
        description=(
            "Numeric progress for incremental hooks (3 of 5 wolves "
            "slain). NULL for atomic hooks."
        ),
    )
    table_comment: ClassVar[str] = (
        "Per-person hook progress. Replaces both PersonQuest and "
        "PersonObjective."
    )

    class Create(
        BaseModel,
        PersonModel.Reference.ID.Optional,
        HookModel.Reference.ID.Optional,
    ):
        status: Optional[str] = None
        accepted_at: Optional[datetime] = None
        completed_at: Optional[datetime] = None
        progress: Optional[float] = None

    class Update(BaseModel):
        status: Optional[str] = None
        accepted_at: Optional[datetime] = None
        completed_at: Optional[datetime] = None
        progress: Optional[float] = None

    class Search(
        ApplicationModel.Search,
        PersonModel.Reference.ID.Search,
        HookModel.Reference.ID.Search,
    ):
        status: Optional[StringSearchModel] = None
        progress: Optional[NumericalSearchModel] = None


class PersonHookManager(AbstractBLLManager, RouterMixin):
    _model = PersonHookModel


PersonHookModel.Manager = PersonHookManager


class FactionHookModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    FactionModel.Reference.Optional,
    HookModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["FactionHookManager"]] = None
    status: Optional[str] = Field(None, description="See PersonHookModel.status")
    accepted_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)
    progress: Optional[float] = Field(None)
    table_comment: ClassVar[str] = "Per-faction hook progress."

    class Create(
        BaseModel,
        FactionModel.Reference.ID.Optional,
        HookModel.Reference.ID.Optional,
    ):
        status: Optional[str] = None
        accepted_at: Optional[datetime] = None
        completed_at: Optional[datetime] = None
        progress: Optional[float] = None

    class Update(BaseModel):
        status: Optional[str] = None
        accepted_at: Optional[datetime] = None
        completed_at: Optional[datetime] = None
        progress: Optional[float] = None

    class Search(
        ApplicationModel.Search,
        FactionModel.Reference.ID.Search,
        HookModel.Reference.ID.Search,
    ):
        status: Optional[StringSearchModel] = None
        progress: Optional[NumericalSearchModel] = None


class FactionHookManager(AbstractBLLManager, RouterMixin):
    _model = FactionHookModel


FactionHookModel.Manager = FactionHookManager


# ---------------------------------------------------------------------------
# 10. Inject Faction endpoints onto genealogy.RelationshipModel
# ---------------------------------------------------------------------------


@extension_model(RelationshipModel)
class RPG_RelationshipModel(BaseModel):
    """RPG Faction endpoints injected onto ``genealogy.RelationshipModel``.

    Genealogy ships ``person_id`` (subject) and ``target_person_id``
    (object). RPG widens the table with ``faction_id`` (subject) and
    ``target_faction_id`` (object). The migration adds the endpoint-XOR
    CHECK: exactly one of (``person_id``, ``faction_id``) per row, same
    for the target side.

    Examples (kind, discriminator) → endpoints:
        ('member_of', 'leader')      → person → faction
        ('affiliated_with', 'allied') → faction → faction
        ('social', 'rival')          → person → person (unchanged)
    """

    faction_id: Optional[str] = Field(
        None,
        description=(
            "Subject-side Faction endpoint. XOR with person_id "
            "(enforced by migration CHECK)."
        ),
    )
    target_faction_id: Optional[str] = Field(
        None,
        description=(
            "Object-side Faction endpoint. XOR with target_person_id "
            "(enforced by migration CHECK)."
        ),
    )

    class Create(BaseModel):
        faction_id: Optional[str] = None
        target_faction_id: Optional[str] = None

    class Update(BaseModel):
        faction_id: Optional[str] = None
        target_faction_id: Optional[str] = None

    class Search(BaseModel):
        faction_id: Optional[StringSearchModel] = None
        target_faction_id: Optional[StringSearchModel] = None




# ---------------------------------------------------------------------------
# Cycle guard — HookDependency
# ---------------------------------------------------------------------------


def _hook_parents_lookup(manager: AbstractBLLManager):
    """Return a function that yields the parent_hook_ids of a given child."""

    def _get(child_hook_id: str):
        try:
            edges = manager.list(child_hook_id=child_hook_id) or []
        except Exception:
            return ()
        return [
            getattr(edge, "parent_hook_id", None)
            for edge in edges
            if getattr(edge, "parent_hook_id", None)
        ]

    return _get



@hook_bll(HookDependencyManager, timing=HookTiming.BEFORE, priority=10)
def _hook_dependency_no_cycle(context: HookContext) -> None:
    if context.method_name not in ("create", "update"):
        return
    parent_id = context.kwarg("parent_hook_id", default=None)
    child_id = context.kwarg("child_hook_id", default=None)
    if not parent_id or not child_id:
        return
    if would_create_dag_cycle(
        parent_id, child_id, _hook_parents_lookup(context.manager)
    ):
        raise CycleGuardError(
            f"HookDependency parent={parent_id} → child={child_id} would close a cycle."
        )



# ---------------------------------------------------------------------------
# Public roster
# ---------------------------------------------------------------------------


ALL_MODELS: List[type] = [HookModel, HookDependencyModel, PersonHookModel, FactionHookModel]

__all__ = [
    "HookModel",
    "HookManager",
    "HookDependencyModel",
    "HookDependencyManager",
    "PersonHookModel",
    "PersonHookManager",
    "FactionHookModel",
    "FactionHookManager",
    "RPG_RelationshipModel",
    "ALL_MODELS",
]
