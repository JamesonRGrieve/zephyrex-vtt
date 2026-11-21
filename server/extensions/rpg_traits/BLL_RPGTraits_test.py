# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structural tests for rpg_traits (moved from rpg_state's): the unified Trait model (status effects
are a trait kind), DerivativeTrait edges, and per-person values folding status effects."""

import os

import pytest

os.environ.setdefault("JWT_SECRET", "x" * 32)

from zephyrex.extensions.rpg_traits.BLL_RPGTraits import (  # type: ignore[import-not-found]
    ALL_MODELS,
    DerivativeTraitManager,
    DerivativeTraitModel,
    PersonTraitManager,
    PersonTraitModel,
    TraitManager,
    TraitModel,
)


class TestModelManagerWiring:
    """Every owned model must point to its Manager and vice versa."""

    PAIRS = [
        (TraitModel, TraitManager),
        (DerivativeTraitModel, DerivativeTraitManager),
        (PersonTraitModel, PersonTraitManager),
    ]

    def test_each_model_has_its_manager(self):
        for model, manager in self.PAIRS:
            assert model.Manager is manager, f"{model.__name__} → wrong Manager"
            assert manager._model is model, f"{manager.__name__} → wrong _model"

    def test_all_models_listed(self):
        assert set(ALL_MODELS) == {model for model, _ in self.PAIRS}


class TestCreateUpdateSearchPresent:
    def test_nested_classes_exist(self):
        for model in ALL_MODELS:
            assert hasattr(model, "Create"), f"{model.__name__} missing Create"
            assert hasattr(model, "Update"), f"{model.__name__} missing Update"
            assert hasattr(model, "Search"), f"{model.__name__} missing Search"




class TestUnifiedTraitContract:
    """StatusEffect is folded into Trait via kind='status_effect'.
    No separate StatusEffectModel exists."""

    def test_no_status_effect_model(self):
        from zephyrex.extensions.rpg_traits import BLL_RPGTraits

        assert not hasattr(BLL_RPGTraits, "StatusEffectModel")
        assert not hasattr(BLL_RPGTraits, "StatusEffectTraitModel")
        assert not hasattr(BLL_RPGTraits, "PersonStatusEffectModel")

    def test_status_effect_is_a_trait_kind(self):
        bs = TraitModel.Create(
            name="Bull's Strength",
            kind="status_effect",
            default_duration_seconds=600,
        )
        assert bs.kind == "status_effect"
        assert bs.default_duration_seconds == 600

    def test_attribute_trait_has_no_duration(self):
        # default_duration_seconds is meaningful only for status_effect.
        str_attr = TraitModel.Create(name="STR", kind="attribute")
        assert str_attr.default_duration_seconds is None


class TestDerivativeTraitContract:
    """DerivativeTrait carries operation, value, order_index,
    stacking_group, qualifier. source_trait_id NULL = constant.
    operation is locked to a closed enum at the Pydantic layer."""

    def test_static_buff_via_derivative(self):
        # Bull's Strength → STR, +2 always.
        d = DerivativeTraitModel.Create(
            source_trait_id="bulls-strength",
            target_trait_id="str",
            operation="additive",
            value=2.0,
        )
        assert d.source_trait_id == "bulls-strength"
        assert d.target_trait_id == "str"
        assert d.operation == "additive"
        assert d.value == 2.0

    def test_operation_rejects_unknown_value(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            DerivativeTraitModel.Create(
                source_trait_id="x",
                target_trait_id="y",
                operation="not-a-real-op",
                value=1.0,
            )

    def test_item_can_be_source(self):
        # Ring of Protection: source_item_id set, source_trait_id null.
        # Contribution applies while the person wears an ItemInstance
        # of this Item (runtime-resolved).
        d = DerivativeTraitModel.Create(
            source_item_id="ring-of-protection",
            target_trait_id="ac",
            operation="additive",
            value=1.0,
            stacking_group="deflection_bonus",
        )
        assert d.source_item_id == "ring-of-protection"
        assert d.source_trait_id is None
        assert d.target_trait_id == "ac"
        assert d.stacking_group == "deflection_bonus"

    def test_item_consumable_targets_status_effect_trait(self):
        # Potion of Bull's Strength: source_item_id=potion,
        # target_trait_id=BullsStrength (a kind='status_effect' Trait).
        # On consumption, the manager spawns a PersonTrait of
        # BullsStrength on the drinker; this DerivativeTrait edge
        # documents the "this potion grants this Trait when consumed"
        # relationship.
        d = DerivativeTraitModel.Create(
            source_item_id="potion-of-bulls-strength",
            target_trait_id="bulls-strength",
            operation="override",
            value=1.0,
        )
        assert d.source_item_id == "potion-of-bulls-strength"
        assert d.target_trait_id == "bulls-strength"

    def test_constant_contribution_with_both_sources_null(self):
        # Initiative = DEX + 5 — the +5 is a constant edge with both
        # source columns NULL.
        d = DerivativeTraitModel.Create(
            source_trait_id=None,
            source_item_id=None,
            target_trait_id="initiative",
            operation="additive",
            value=5.0,
        )
        assert d.source_trait_id is None
        assert d.source_item_id is None
        assert d.value == 5.0

    def test_signed_value_for_damage(self):
        # Wound → HealthMax, value=-1 multiplier; PersonTrait.value
        # carries the damage magnitude. Or use static -8 here.
        d = DerivativeTraitModel.Create(
            source_trait_id="wound",
            target_trait_id="health-max",
            operation="additive",
            value=-1.0,
        )
        assert d.value == -1.0

    def test_phase_via_operation_and_order_index(self):
        d = DerivativeTraitModel.Create(
            source_trait_id="haste",
            target_trait_id="speed",
            operation="multiplicative",
            value=2.0,
            order_index=1,
        )
        assert d.operation == "multiplicative"
        assert d.order_index == 1

    def test_stacking_group(self):
        d = DerivativeTraitModel.Create(
            source_trait_id="ring-of-protection",
            target_trait_id="ac",
            operation="additive",
            value=1.0,
            stacking_group="deflection_bonus",
        )
        assert d.stacking_group == "deflection_bonus"

    def test_qualifier_for_conditional(self):
        d = DerivativeTraitModel.Create(
            source_trait_id="orcbane",
            target_trait_id="attack-bonus",
            operation="additive",
            value=2.0,
            qualifier="vs orcs",
        )
        assert d.qualifier == "vs orcs"

    def test_clamp_operation_supported(self):
        d = DerivativeTraitModel.Create(
            source_trait_id=None,
            target_trait_id="hp-current",
            operation="clamp",
            value=0.0,  # 0 = lower bound by convention
        )
        assert d.operation == "clamp"


class TestPersonTraitFoldsStatusEffect:
    """PersonTrait carries both durable trait values and applied-effect
    attachments. Status effects are PersonTrait rows with started_at /
    expires_at / source_* set; durable traits leave them NULL."""

    def test_durable_attribute(self):
        pt = PersonTraitModel.Create(
            person_id="bob", trait_id="str", value=16.0
        )
        assert pt.value == 16.0
        assert pt.started_at is None
        assert pt.expires_at is None

    def test_applied_status_effect(self):
        from datetime import datetime

        pt = PersonTraitModel.Create(
            person_id="bob",
            trait_id="bulls-strength",
            started_at=datetime(2026, 1, 1, 12, 0),
            expires_at=datetime(2026, 1, 1, 12, 10),
            source_person_id="wizard",
            source_item_instance_id="ii-potion",
        )
        assert pt.source_person_id == "wizard"
        assert pt.source_item_instance_id == "ii-potion"

    def test_wound_carries_damage_magnitude_on_value(self):
        pt = PersonTraitModel.Create(
            person_id="bob",
            trait_id="wound",
            value=-8.0,
            source_person_id="orc",
        )
        assert pt.value == -8.0
        assert pt.source_person_id == "orc"

    def test_target_location_localises_damage_to_body_part(self):
        # Bob takes 8 damage to his left arm (a body-part Location
        # under his body-root Location, associated_person_id=Bob).
        pt = PersonTraitModel.Create(
            person_id="bob",
            trait_id="wound",
            value=-8.0,
            target_location_id="loc-bob-left-arm",
            source_person_id="orc",
        )
        assert pt.target_location_id == "loc-bob-left-arm"

    def test_target_location_optional_for_full_body_buffs(self):
        # Bull's Strength is whole-body — target_location_id stays NULL.
        pt = PersonTraitModel.Create(
            person_id="bob",
            trait_id="bulls-strength",
        )
        assert pt.target_location_id is None

    def test_person_trait_fully_editable(self):
        from datetime import datetime

        u = PersonTraitModel.Update(
            value=20.0,
            expires_at=datetime(2026, 1, 1, 13, 0),
            source_person_id="caster-X",
            source_item_instance_id="ii-Y",
        )
        assert u.value == 20.0
        assert u.source_person_id == "caster-X"
