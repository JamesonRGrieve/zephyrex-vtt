# SPDX-License-Identifier: AGPL-3.0-or-later
"""build_pregen's planning, pure: a pregen's line, and what the SRD's creation rules fix or leave open.
The documents are cut-down shapes of the open fifth-edition system's own (SRD 5.2.1, CC-BY-4.0)."""

from typing import Any

from zephyrex.extensions.rpg_builder.Pregen import Document, name_key, parse_line, plan

FIGHTER = "Compendium.dnd5e.classes24.Item.phbftrFighter000"
PACK: dict[str, Any] = {
    "characteristics": [
        {"slug": slug, "name": slug.title(), "short": slug[:3].upper()}
        for slug in ("strength", "dexterity", "constitution", "intelligence", "wisdom", "charisma")
    ],
    "skills": [{"slug": "insight", "key": "ins"}, {"slug": "religion", "key": "rel"}, {"slug": "athletics", "key": "ath"}],
    "leveling": {"max_level": 20, "fixed_hit_points": {"Fighter": 6}, "minimum_per_level": 1},
    "ability_methods": {
        "standard_array_by_class": {
            FIGHTER: {"name": "Fighter", "scores": {"strength": 15, "dexterity": 14, "constitution": 13, "intelligence": 8, "wisdom": 10, "charisma": 12}}
        }
    },
}


def _catalog() -> dict[str, dict[str, Document]]:
    fighter = Document("t-fighter", FIGHTER, "Fighter", {
        "hd": {"denomination": "d10"},
        "advancement": [
            {"type": "Trait", "level": 1, "title": "Saving Throw Proficiencies", "configuration": {"grants": ["saves:str", "saves:con"], "choices": []}},
            {"type": "Trait", "level": 1, "title": "Skill Proficiencies", "configuration": {"grants": [], "choices": [{"count": 2, "pool": ["skills:ath", "skills:ins"]}]}},
            {"type": "Trait", "level": 1, "title": "Armor Training", "classRestriction": "secondary", "configuration": {"grants": ["skills:rel"]}},
            {"type": "ItemGrant", "level": 1, "title": "Class Features", "configuration": {"items": [{"uuid": "F-second-wind", "optional": False}]}},
            {"type": "ItemGrant", "level": 2, "title": "Class Features", "configuration": {"items": [{"uuid": "F-action-surge", "optional": False}]}},
            {"type": "ItemChoice", "title": "Fighting Style", "configuration": {"choices": {"1": {"count": 1}}}},
            {"type": "Subclass", "level": 3, "configuration": {}},
            {"type": "AbilityScoreImprovement", "level": 4, "configuration": {"points": 2}},
        ],
        "startingEquipment": [{"type": "OR", "group": ""}],
    })
    acolyte = Document("t-acolyte", "B-acolyte", "Acolyte", {
        "advancement": [
            {"type": "AbilityScoreImprovement", "level": 0, "title": "Background Ability Score Improvement",
             "configuration": {"points": 3, "cap": 2, "locked": ["str", "dex", "con"]}},
            {"type": "Trait", "level": 0, "title": "Background Proficiencies", "configuration": {"grants": ["tool:art:calligrapher", "skills:ins", "skills:rel"], "choices": []}},
            {"type": "ItemGrant", "level": 0, "title": "Background Feat", "configuration": {"items": [{"uuid": "F-magic-initiate", "optional": False}]}},
        ],
        "startingEquipment": [{"type": "AND", "group": ""}],
        "wealth": "50",
    })
    elf = Document("t-elf", "S-elf-high", "Elf, High", {
        "advancement": [
            {"type": "Size", "level": 0, "configuration": {"sizes": ["med"]}},
            {"type": "ItemGrant", "level": 0, "title": "Elf Traits", "configuration": {"items": [{"uuid": "F-darkvision", "optional": False}]}},
        ],
    })
    return {"class": {"fighter": fighter}, "background": {"acolyte": acolyte}, "species": {name_key("Elf, High"): elf}}


def test_a_pregen_line_names_level_species_class_background_and_edition() -> None:
    line = parse_line("Level 1 High Elf Fighter, Acolyte background (SRD 5.2.1). Raised in a temple.", ["Fighter", "Cleric"])
    assert line is not None
    assert (line.level, line.species, line.klass, line.background, line.edition) == (1, "High Elf", "Fighter", "Acolyte", "5.2.1")
    assert parse_line("A gruff sellsword.", ["Fighter"]) is None


def test_names_compare_with_their_comma_turned() -> None:
    assert name_key("Elf, High") == name_key("High Elf") == "high elf"


def test_the_rules_fix_scores_saves_skills_features_and_hp_and_report_every_open_choice() -> None:
    line = parse_line("Level 1 High Elf Fighter, Acolyte background (SRD 5.2.1).", ["Fighter"])
    got = plan(line, _catalog(), PACK)
    assert got.buildable
    assert got.origins == {"class": "t-fighter", "background": "t-acolyte", "species": "t-elf"}
    assert got.abilities["strength"] == 15 and got.abilities["intelligence"] == 8
    assert got.saves == ["strength", "constitution"]
    # The background's skills outright; the multiclass-only set is not the character's.
    assert got.skills == ["insight", "religion"]
    # Level-1 grants only (Action Surge is level 2).
    assert got.features == ["F-second-wind", "F-magic-initiate", "F-darkvision"]
    assert got.hp == 10 + 1  # d10 + the Constitution modifier of 13
    open_choices = [gap.detail for gap in got.gaps]
    assert any("Skill Proficiencies: choose 2" in one for one in open_choices)
    assert any("Fighting Style" in one for one in open_choices)
    assert any("3 points among intelligence, wisdom, charisma, at most +2 each" in one for one in open_choices)
    assert any("Fighter's starting equipment" in one for one in open_choices)
    assert any("Acolyte's starting equipment: choose its option, or 50 GP instead" in one for one in open_choices)
    # A one-size species and later-level advancements open nothing.
    assert not any("size" in one or "subclass" in one for one in open_choices)


def test_an_other_edition_or_level_or_unknown_origin_builds_nothing() -> None:
    older = plan(parse_line("Level 1 High Elf Fighter, Acolyte background (SRD 5.1).", ["Fighter"]), _catalog(), PACK)
    assert not older.buildable and [gap.what for gap in older.gaps] == ["edition"]
    higher = plan(parse_line("Level 3 High Elf Fighter, Acolyte background (SRD 5.2.1).", ["Fighter"]), _catalog(), PACK)
    assert not higher.buildable and [gap.what for gap in higher.gaps] == ["level"]
    unknown = plan(parse_line("Level 1 High Elf Fighter, Recluse background (SRD 5.2.1).", ["Fighter"]), _catalog(), PACK)
    assert not unknown.buildable and any(gap.what == "background" and "Recluse" in gap.detail for gap in unknown.gaps)


def test_a_pregen_is_advanced_to_the_starting_level_with_fixed_hit_points() -> None:
    line = parse_line("Level 1 High Elf Fighter, Acolyte background (SRD 5.2.1).", ["Fighter"])
    got = plan(line, _catalog(), PACK, level=4)
    assert got.buildable and got.level == 4
    assert got.hp == (10 + 1) + 3 * (6 + 1), "level 1's d10 + Con, then the fixed 6 + Con at each of levels 2 to 4"
    assert "F-action-surge" in got.features, "level 2's feature comes in"
    open_choices = [gap.detail for gap in got.gaps]
    assert any("choose a subclass" in one for one in open_choices), "a subclass at level 3 is the player's"
    assert any("2 points among" in one for one in open_choices), "level 4's ability increase is the player's"


def test_a_level_past_the_packs_last_or_an_unknown_species() -> None:
    line = parse_line("Level 1 High Elf Fighter, Acolyte background (SRD 5.2.1).", ["Fighter"])
    beyond = plan(line, _catalog(), PACK, level=21)
    assert not beyond.buildable and [gap.what for gap in beyond.gaps] == ["level"]
    unknown = plan(parse_line("Level 1 Unknown Fighter, Acolyte background (SRD 5.2.1).", ["Fighter"]), _catalog(), PACK)
    assert unknown.buildable and "species" not in unknown.origins
    assert not any(gap.what == "species" for gap in unknown.gaps)


def test_advancements_stored_as_an_object_keyed_by_id_build_the_same() -> None:
    """Newer dnd5e data keeps a document's advancements as {id: advancement}: iterating it gave the
    keys, strings, and build_campaign_pregens 500'd at level 4 (The Haunted Manor, Goblin Ambush)."""
    catalog = _catalog()
    fighter = catalog["class"]["fighter"]
    keyed = {f"adv{index}": one for index, one in enumerate(fighter.data["advancement"])}
    keyed["stray"] = "not an advancement"
    catalog["class"]["fighter"] = Document(fighter.trait_id, fighter.source_id, fighter.name, {**fighter.data, "advancement": keyed})
    line = parse_line("Level 1 High Elf Fighter, Acolyte background (SRD 5.2.1).", ["Fighter"])
    as_object = plan(line, catalog, PACK, level=4)
    as_list = plan(line, _catalog(), PACK, level=4)
    assert as_object.buildable and as_object.features == as_list.features and as_object.hp == as_list.hp
    assert sorted(gap.detail for gap in as_object.gaps) == sorted(gap.detail for gap in as_list.gaps)


def test_a_species_named_alone_with_several_lineages_builds_with_the_lineage_open() -> None:
    """The srd5e module holds Gnome only as "Gnome, Forest" and "Gnome, Rock" (and Tiefling as three
    legacies): "Level 1 Gnome Wizard" matched nothing and built nothing (Nix Copperpot, Kestrel Vane).
    The lineage is the player's choice, never guessed; the rest builds."""
    catalog = _catalog()
    for lineage in ("Gnome, Forest", "Gnome, Rock"):
        catalog["species"][name_key(lineage)] = Document(f"t-{lineage}", f"S-{lineage}", lineage, {"advancement": []})
    got = plan(parse_line("Level 1 Gnome Fighter, Acolyte background (SRD 5.2.1).", ["Fighter"]), catalog, PACK)
    assert got.buildable and "species" not in got.origins and got.hp is not None
    assert [gap.detail for gap in got.gaps if gap.what == "species"] == ["Gnome: choose a lineage: Forest Gnome or Rock Gnome"]
    # A species the module holds as one lineage only is that lineage: nothing to choose.
    only = plan(parse_line("Level 1 Elf Fighter, Acolyte background (SRD 5.2.1).", ["Fighter"]), _catalog(), PACK)
    assert only.buildable and only.origins["species"] == "t-elf"
