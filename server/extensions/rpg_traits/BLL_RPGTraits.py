# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_traits: the unified trait catalog (stats, skills, spells, resources, status effects), how
traits derive from one another, and each character's values (OBJECT_PLAN §4). Split from rpg_state
(operator, 2026-11-20); the resolution pipeline its docs describe is rpg_dice's Check.py.

Characters are genealogy's persons with the wiki's rpg_core fields; campaigns are the wiki's; game
systems are rpg_systems'.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, List, Literal, Optional, Type

from pydantic import Field, model_validator

from zephyrex.pydantic2.registry import BaseModel
from zephyrex.pydantic2.fastapi import RouterMixin
from zephyrex.logic.AbstractLogicManager import (
    AbstractBLLManager,
    ApplicationModel,
    DateSearchModel,
    DescriptionMixinModel,
    ModelMeta,
    NameMixinModel,
    NumericalSearchModel,
    StringSearchModel,
    UpdateMixinModel,
)

from zephyrex.extensions.genealogy.BLL_Genealogy import PersonModel
from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignModel  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_systems.BLL_RPGSystems import SLUG_PATTERN, GameSystemModel, slugify  # type: ignore[import-not-found]


DerivativeOperation = Literal["override", "additive", "multiplicative", "clamp"]
"""Closed set of derivation operations for ``DerivativeTraitModel``.

Doubles as the resolution-pipeline phase: override → additive →
multiplicative → clamp. Within each phase, ``order_index`` orders ties.
"""


# ---------------------------------------------------------------------------
# 3. Trait — unified property catalog (incl. status effects)
# ---------------------------------------------------------------------------


class TraitModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    DescriptionMixinModel.Optional,
    GameSystemModel.Reference.Optional,
    CampaignModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["TraitManager"]] = None
    # Conventional `kind` values (free-form so systems may extend):
    #   attribute  — STR, DEX, CHA, ...
    #   skill      — Stealth, Persuasion, Athletics, ...
    #   spell      — Fireball (a spell IS a Trait so CombatActionLog.trait_id
    #                reaches it directly).
    #   talent / feat / ability / language — durable learnings.
    #   resource   — HP, mana, spell_slot_1, stress, wounds, dice pools;
    #                PersonTrait.value carries current value.
    #   progression — level, experience, spent_experience, milestones,
    #                 advancement_points. By convention named 'level',
    #                 'experience', 'spent_experience'.
    #   status_effect — Bull's Strength, Wound, Bleed, Marked, Slowed.
    #                   Applied to a person via PersonTrait with timing
    #                   (started_at / expires_at) and source attribution.
    kind: Optional[str] = Field(
        None,
        description=(
            "attribute|skill|spell|talent|feat|ability|language|resource|"
            "progression|status_effect|... (free-form)"
        ),
    )
    default_duration_seconds: Optional[int] = Field(
        None,
        description=(
            "Default lifetime when applied. Only meaningful when "
            "kind='status_effect'; NULL = persists until manually removed."
        ),
    )
    slug: Optional[str] = Field(
        None,
        description=(
            "The option's stable name within its kind ([redacted], [redacted]): what a plot hook's "
            "character check names (contract/requirement-cases.json). From the name when not given."
        ),
    )
    table_comment: ClassVar[str] = (
        "Unified property catalog: stats, skills, spells, talents, feats, "
        "abilities, languages, resources, progression, and status effects. "
        "campaign_id=NULL = globally-shared template; set = "
        "campaign-scoped override. default_duration_seconds is meaningful "
        "only for kind='status_effect'."
    )

    class Create(
        BaseModel,
        GameSystemModel.Reference.ID.Optional,
        CampaignModel.Reference.ID.Optional,
    ):
        name: str = Field(...)
        description: Optional[str] = None
        kind: Optional[str] = None
        default_duration_seconds: Optional[int] = None
        slug: Optional[str] = Field(None, pattern=SLUG_PATTERN)

        @model_validator(mode="after")
        def _slug_from_name(self) -> "TraitModel.Create":
            if self.slug is None:
                self.slug = slugify(self.name)
            return self

    class Update(BaseModel):
        name: Optional[str] = None
        description: Optional[str] = None
        kind: Optional[str] = None
        default_duration_seconds: Optional[int] = None
        slug: Optional[str] = Field(None, pattern=SLUG_PATTERN)

    class Search(
        ApplicationModel.Search,
        GameSystemModel.Reference.ID.Search,
        CampaignModel.Reference.ID.Search,
    ):
        name: Optional[StringSearchModel] = None
        kind: Optional[StringSearchModel] = None
        slug: Optional[StringSearchModel] = None


class TraitManager(AbstractBLLManager, RouterMixin):
    _model = TraitModel


# ---------------------------------------------------------------------------
# 4. DerivativeTrait — edges defining how Traits derive from each other
# ---------------------------------------------------------------------------


class DerivativeTraitModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["DerivativeTraitManager"]] = None
    # Source endpoints. Two flavours, mutually exclusive at the row
    # level (enforced by ck_derivative_traits_source_xor in DDL): a
    # row's contribution comes from either a Trait OR an Item, never
    # both. Both NULL = constant contribution (the row's `value` is
    # added unconditionally).
    source_trait_id: Optional[str] = Field(
        None,
        description=(
            "FK → traits.id. When set, contribution scales with the "
            "source's PersonTrait.value (or 1.0 if null). Mutually "
            "exclusive with source_item_id."
        ),
    )
    source_item_id: Optional[str] = Field(
        None,
        description=(
            "FK → items.id. When set, contribution applies while the "
            "person carries an ItemInstance of this Item in an active "
            "configuration (equipped / held / in an equipment slot "
            "associated with the person — runtime-resolved, not part "
            "of this row). Mutually exclusive with source_trait_id."
        ),
    )
    target_trait_id: Optional[str] = Field(
        None,
        description="FK → traits.id. The trait being modified.",
    )
    operation: Optional[DerivativeOperation] = Field(
        None,
        description=(
            "Closed enum: override|additive|multiplicative|clamp. Also "
            "identifies the resolution phase: override → additive → "
            "multiplicative → clamp. Within each phase, order_index "
            "sequences ties. Validated by Pydantic Literal and enforced "
            "in DDL by a CHECK constraint in the migration."
        ),
    )
    value: Optional[float] = Field(
        None,
        description=(
            "Magnitude. Signed. For additive: the contribution; for "
            "multiplicative: the multiplier; for override: the new value; "
            "for clamp: positive = upper bound, negative = lower bound."
        ),
    )
    order_index: Optional[int] = Field(
        None,
        description="Tie-breaker within phase (lower runs first; default 0).",
    )
    stacking_group: Optional[str] = Field(
        None,
        description=(
            "NULL = always stacks (sum). Non-NULL = within group, only "
            "the max-abs contribution wins. Used to model 'doesn't stack "
            "with itself' / typed-bonus stacking rules."
        ),
    )
    qualifier: Optional[str] = Field(
        None,
        description=(
            "Conditional context. NULL = always applies; non-NULL = "
            "conditional ('vs orcs', 'while prone', 'in moonlight'). UI "
            "surfaces non-NULL qualifiers as toggles."
        ),
    )
    table_comment: ClassVar[str] = (
        "Edges defining how one Trait contributes to another. Replaces "
        "the prior StatusEffectTrait; subsumes arithmetic derivations "
        "(Initiative ← DEX + 5), applied-effect modifiers (Bull's "
        "Strength → STR +2), and item effects (Ring of Protection → AC "
        "+1 while worn). Resolution pipeline: override → additive → "
        "multiplicative → clamp; order_index sequences within phase; "
        "stacking_group de-duplicates by max-abs. Source mutual "
        "exclusion: source_trait_id XOR source_item_id (at most one); "
        "both NULL = constant contribution. Activation for source_item "
        "rows is runtime-resolved against the person's worn / held "
        "ItemInstances."
    )

    class Create(BaseModel):
        source_trait_id: Optional[str] = None
        source_item_id: Optional[str] = None
        target_trait_id: Optional[str] = None
        operation: Optional[DerivativeOperation] = None
        value: Optional[float] = None
        order_index: Optional[int] = None
        stacking_group: Optional[str] = None
        qualifier: Optional[str] = None

    class Update(BaseModel):
        operation: Optional[DerivativeOperation] = None
        value: Optional[float] = None
        order_index: Optional[int] = None
        stacking_group: Optional[str] = None
        qualifier: Optional[str] = None

    class Search(ApplicationModel.Search):
        source_trait_id: Optional[StringSearchModel] = None
        source_item_id: Optional[StringSearchModel] = None
        target_trait_id: Optional[StringSearchModel] = None
        operation: Optional[StringSearchModel] = None
        value: Optional[NumericalSearchModel] = None
        stacking_group: Optional[StringSearchModel] = None
        qualifier: Optional[StringSearchModel] = None


class DerivativeTraitManager(AbstractBLLManager, RouterMixin):
    _model = DerivativeTraitModel


# ---------------------------------------------------------------------------
# 6. PersonTrait — per-person trait values + applied-effect attachments
# ---------------------------------------------------------------------------


class PersonTraitModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    PersonModel.Reference.Optional,
    TraitModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["PersonTraitManager"]] = None
    value: Optional[float] = Field(
        None,
        description=(
            "Per-instance magnitude. For attribute traits: STR=16. For "
            "resource traits: current HP. For status-effect applications: "
            "the magnitude carried by this stack (e.g. -8 for a Wound). "
            "Effective contribution to derived traits = "
            "DerivativeTrait.value × (this value or 1.0)."
        ),
    )
    rank: Optional[int] = Field(
        None,
        description="Optional discrete rank (e.g. proficiency tier)",
    )
    started_at: Optional[datetime] = Field(
        None,
        description=(
            "Application start. NULL = persistent (durable trait). "
            "Set for transient applications (status effects, buffs, "
            "wounds)."
        ),
    )
    expires_at: Optional[datetime] = Field(
        None,
        description=(
            "Application end. NULL = persists until manually removed. "
            "For active filtering, use ``expires_at IS NULL OR "
            "expires_at > now()``."
        ),
    )
    # Source attribution for applied effects. Manual columns since
    # PersonModel.Reference is already used for the affected person and
    # ItemInstance.Reference would create a cycle.
    source_person_id: Optional[str] = Field(
        None, description="The caster / applier (FK → persons.id)"
    )
    source_item_instance_id: Optional[str] = Field(
        None,
        description="Item consumed to apply the effect (FK → item_instances.id)",
    )
    # Target localisation: where on the person (or, more generally,
    # which Location) does this trait/effect apply? Wounds use this to
    # target a body part sub-Location ("Bob's left arm"); buffs that
    # are full-body leave it NULL.
    target_location_id: Optional[str] = Field(
        None,
        description=(
            "FK → locations.id. Where this trait/effect is localised. "
            "For Wounds and similar damage applications: a body-part "
            "sub-Location. NULL = whole-body / location-agnostic."
        ),
    )
    notes: Optional[str] = Field(None)
    table_comment: ClassVar[str] = (
        "Per-person trait instances. Multiple rows per (person, trait) "
        "are allowed (e.g. several Wound stacks at different body "
        "parts). Durable traits leave started_at/expires_at NULL; "
        "transient applications fill them. target_location_id "
        "localises the application (e.g. damage to a specific limb). "
        "The full effective value of a derived target trait is computed "
        "by walking DerivativeTrait edges into it from active source "
        "Traits the person carries."
    )

    class Create(
        BaseModel,
        PersonModel.Reference.ID.Optional,
        TraitModel.Reference.ID.Optional,
    ):
        value: Optional[float] = None
        rank: Optional[int] = None
        started_at: Optional[datetime] = None
        expires_at: Optional[datetime] = None
        source_person_id: Optional[str] = None
        source_item_instance_id: Optional[str] = None
        target_location_id: Optional[str] = None
        notes: Optional[str] = None

    class Update(BaseModel):
        # Fully editable so GMs can retcon any aspect.
        value: Optional[float] = None
        rank: Optional[int] = None
        started_at: Optional[datetime] = None
        expires_at: Optional[datetime] = None
        source_person_id: Optional[str] = None
        source_item_instance_id: Optional[str] = None
        target_location_id: Optional[str] = None
        notes: Optional[str] = None

    class Search(
        ApplicationModel.Search,
        PersonModel.Reference.ID.Search,
        TraitModel.Reference.ID.Search,
    ):
        value: Optional[NumericalSearchModel] = None
        rank: Optional[NumericalSearchModel] = None
        started_at: Optional[DateSearchModel] = None
        expires_at: Optional[DateSearchModel] = None
        target_location_id: Optional[StringSearchModel] = None


class PersonTraitManager(AbstractBLLManager, RouterMixin):
    _model = PersonTraitModel


TraitModel.Manager = TraitManager
DerivativeTraitModel.Manager = DerivativeTraitManager
PersonTraitModel.Manager = PersonTraitManager

ALL_MODELS: List[type] = [TraitModel, DerivativeTraitModel, PersonTraitModel]
