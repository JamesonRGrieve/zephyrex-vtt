"""Extension-level tests for rpg_state."""

import os

os.environ.setdefault("JWT_SECRET", "x" * 32)
os.environ.setdefault("PYTEST_CURRENT_TEST", "rpg_state_ext_test")

from zephyrex.extensions.rpg_state.BLL_RPGState import ALL_MODELS
from zephyrex.extensions.rpg_state.EXT_RPGState import RPGStateExtension


class TestExtensionMetadata:
    def test_name_and_description(self):
        assert RPGStateExtension.name == "rpg_state"
        assert "RPG" in RPGStateExtension.description

    def test_depends_on_genealogy(self):
        # Hard dependency: rpg_state widens genealogy.PersonModel and
        # genealogy.RelationshipModel via @extension_model. Declared as the
        # framework reads it, so loading rpg_state loads genealogy.
        declared = {(d.name, d.optional) for d in RPGStateExtension.dependencies.ext}
        assert declared == {("genealogy", False), ("acl_rbac", True)}

    def test_discovered_models_are_the_roster(self):
        assert RPGStateExtension.models == set(ALL_MODELS)
        assert len(ALL_MODELS) == 13  # bump when adding owned tables.
