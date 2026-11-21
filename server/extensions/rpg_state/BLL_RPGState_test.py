# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structural tests for what's left of rpg_state until the wiki takes it: the Hook DAG (Quest and
Objective folded into Hook; HookDependency carries the edges) and the faction endpoints on
genealogy's relationships."""

import os

import pytest

os.environ.setdefault("JWT_SECRET", "x" * 32)

from zephyrex.extensions.rpg_state.BLL_RPGState import (
    ALL_MODELS,
    FactionHookManager,
    FactionHookModel,
    HookDependencyManager,
    HookDependencyModel,
    HookManager,
    HookModel,
    PersonHookManager,
    PersonHookModel,
    RPG_RelationshipModel,
)


class TestModelManagerWiring:
    """Every owned model must point to its Manager and vice versa."""

    PAIRS = [
        (HookModel, HookManager),
        (HookDependencyModel, HookDependencyManager),
        (PersonHookModel, PersonHookManager),
        (FactionHookModel, FactionHookManager),
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




class TestRelationshipFactionInjection:
    def test_subject_faction_endpoint(self):
        rr = RPG_RelationshipModel(faction_id="f-guild")
        assert rr.faction_id == "f-guild"
        assert rr.target_faction_id is None

    def test_target_faction_endpoint(self):
        rr = RPG_RelationshipModel(target_faction_id="f-thieves")
        assert rr.target_faction_id == "f-thieves"

    def test_both_faction_endpoints(self):
        rr = RPG_RelationshipModel(
            faction_id="f-guild", target_faction_id="f-thieves"
        )
        assert rr.faction_id == "f-guild"
        assert rr.target_faction_id == "f-thieves"




class TestHookDAG:
    """Quest+Objective fold into Hook with a kind discriminator. The
    DAG of dependencies lives in HookDependency; presence of a row IS
    the dependency, the reason string explains it."""

    def test_no_quest_or_objective_models(self):
        from zephyrex.extensions.rpg_state import BLL_RPGState

        assert not hasattr(BLL_RPGState, "QuestModel")
        assert not hasattr(BLL_RPGState, "ObjectiveModel")
        assert not hasattr(BLL_RPGState, "PersonQuestModel")
        assert not hasattr(BLL_RPGState, "PersonObjectiveModel")
        assert not hasattr(BLL_RPGState, "FactionQuestModel")

    def test_hook_is_kind_discriminated(self):
        major = HookModel.Create(
            name="Slay the dragon",
            kind="major_quest",
            campaign_id="c1",
            giver_faction_id="f-king",
        )
        thread = HookModel.Create(
            name="The cursed amulet rumor",
            kind="rumor",
            campaign_id="c1",
        )
        assert major.kind == "major_quest"
        assert thread.kind == "rumor"

    def test_hook_kind_rejects_unknown_value(self):
        # kind is locked to the closed HookKind Literal.
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            HookModel.Create(name="X", kind="invented_kind")

    def test_dependency_is_presence_plus_reason(self):
        d = HookDependencyModel.Create(
            parent_hook_id="hook-find-dragon",
            child_hook_id="hook-slay-dragon",
            reason="must locate the dragon's lair before the assault",
        )
        assert d.parent_hook_id == "hook-find-dragon"
        assert d.child_hook_id == "hook-slay-dragon"
        assert "lair" in d.reason

    def test_no_dependency_kind_enum(self):
        # The HookDependency model has no `kind` or `dependency_kind`
        # field — presence of the row IS the dependency, period.
        for cls in (
            HookDependencyModel.Create,
            HookDependencyModel.Update,
        ):
            assert "kind" not in cls.model_fields
            assert "dependency_kind" not in cls.model_fields

    def test_person_hook_progress(self):
        ph = PersonHookModel.Create(
            person_id="bob",
            hook_id="hook-slay-wolves",
            status="active",
            progress=3.0,  # 3 of 5 wolves slain
        )
        assert ph.status == "active"
        assert ph.progress == 3.0

    def test_faction_hook_progress(self):
        fh = FactionHookModel.Create(
            faction_id="f-guild",
            hook_id="hook-recover-relic",
            status="active",
            progress=0.5,
        )
        assert fh.status == "active"
        assert fh.progress == 0.5




class TestCycleGuardHookRegistered:
    """The HookDependency cycle guard is registered at import time (the faction and location guards
    went with their models to the wiki)."""

    def test_cycle_guard_hook_callable_present(self):
        from zephyrex.extensions.rpg_state import BLL_RPGState

        assert hasattr(BLL_RPGState, "_hook_dependency_no_cycle")
