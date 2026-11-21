"""Extension-level tests for what's left of rpg_state."""

import os

os.environ.setdefault("JWT_SECRET", "x" * 32)
os.environ.setdefault("PYTEST_CURRENT_TEST", "rpg_state_ext_test")

from zephyrex.extensions.rpg_state.BLL_RPGState import ALL_MODELS
from zephyrex.extensions.rpg_state.EXT_RPGState import RPGStateExtension


class TestExtensionMetadata:
    def test_name(self):
        assert RPGStateExtension.name == "rpg_state"

    def test_depends_on_genealogy_and_the_wikis_campaigns_and_factions(self):
        # It widens genealogy's relationships, and its hooks name the wiki's campaigns and factions.
        declared = {(d.name, d.optional) for d in RPGStateExtension.dependencies.ext}
        assert declared == {("genealogy", False), ("rpg_core", False), ("world_social", False)}

    def test_discovered_models_are_the_roster(self):
        assert RPGStateExtension.models == set(ALL_MODELS)
        assert len(ALL_MODELS) == 4  # the hook tables, until the wiki's world_narrative takes them
