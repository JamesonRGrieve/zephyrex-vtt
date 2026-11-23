# SPDX-License-Identifier: AGPL-3.0-or-later
"""Choosing an NPC's stat block from the srd-5e pack's SRD humanoids by role and hint."""

import pytest
from zephyrex.extensions.rpg_builder.Npcs import pick
from zephyrex.extensions.rpg_systems.Packs import load_pack

NPCS = (load_pack("srd-5e") or {})["npcs"]


def _pick(role: str, hint: str = "") -> tuple[str, str]:
    block, source = pick(NPCS["blocks"], NPCS["generic"], role, hint)
    return block["slug"], source


@pytest.mark.parametrize(
    ("role", "hint", "expected"),
    [
        ("guard", "", "guard"),
        ("guard captain", "", "guard-captain"),
        ("town watchman", "", "guard"),
        ("bandit", "", "bandit"),
        ("noble", "a scheming duchess", "noble"),
        ("barkeeper", "a gruff tavern keeper", "commoner"),
        ("cult leader", "", "cultist"),
        ("bouncer", "", "tough"),
    ],
)
def test_a_role_finds_its_block(role: str, hint: str, expected: str) -> None:
    assert _pick(role, hint) == (expected, "compendium")


def test_no_match_is_the_generic_template() -> None:
    assert _pick("astronomer", "studies comets") == ("commoner", "template")


def test_the_blocks_are_the_srds() -> None:
    by_slug = {block["slug"]: block for block in NPCS["blocks"]}
    assert by_slug["commoner"]["abilities"] == dict.fromkeys(
        ["strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma"], 10
    )
    assert by_slug["guard"]["skills"] == {"perception": 1} and by_slug["guard"]["hp"] == 11
