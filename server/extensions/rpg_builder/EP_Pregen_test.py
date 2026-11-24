# SPDX-License-Identifier: AGPL-3.0-or-later
"""build_pregen against a real server: a setting pregen (a pc with no campaign) gets its starting
sheet from its own line and an installed srd5e-shaped module, open choices are reported, and only
its owner may build it. The bundle is a few cut-down documents of the open fifth-edition system's own
(SRD 5.2.1, CC-BY-4.0)."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_modules.Install import install
from zephyrex.extensions.rpg_systems.BLL_RPGSystems import GameSystemManager
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import PersonTraitManager, TraitManager
from zephyrex.lib.Environment import env
from zephyrex.testing.factories import create_user

from vtt_app import create

KINDS = {
    "types": {"race": "species", "background": "background", "class": "class", "subclass": "subclass", "spell": "spell"},
    "fields": {"feat": {"path": ["type", "value"], "map": {"class": "class-feature", "race": "species-trait", "feat": "feat"}, "default": "feat"}},
}
FIGHTER = "Compendium.dnd5e.classes24.Item.phbftrFighter000"


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    with TestClient(create()) as client:
        yield client


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _create(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = server.post(f"/v1/{resource}", json={resource: fields}, headers=_headers(user))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()[resource]
    return created


def _document(uuid: str, name: str, kind: str, system: dict[str, Any]) -> dict[str, Any]:
    return {
        "line": "srd5e", "id": uuid, "foundry_id": uuid.rsplit(".", 1)[-1], "name": name, "foundry_class": "Item",
        "type": kind, "pack": "classes24", "category": "classes24", "homebrew": False, "conversion": False, "img": None,
        "source": {"provenance": "srd", "book": "SRD 5.2.1", "page": None}, "system": system, "items": [], "hash": f"h-{uuid}",
    }


def _bundle() -> dict[str, Any]:
    documents = [
        _document(FIGHTER, "Fighter", "class", {
            "hd": {"denomination": "d10"},
            "advancement": [
                {"type": "Trait", "level": 1, "title": "Saving Throw Proficiencies", "configuration": {"grants": ["saves:str", "saves:con"], "choices": []}},
                {"type": "Trait", "level": 1, "title": "Skill Proficiencies", "configuration": {"grants": [], "choices": [{"count": 2, "pool": ["skills:ath", "skills:prc"]}]}},
                {"type": "ItemGrant", "level": 1, "title": "Class Features", "configuration": {"items": [{"uuid": "Compendium.dnd5e.classes24.Item.phbftrSecondWind", "optional": False}]}},
            ],
            "startingEquipment": [{"type": "OR", "group": ""}],
        }),
        _document("Compendium.dnd5e.classes24.Item.phbftrSecondWind", "Second Wind", "feat", {"type": {"value": "class"}}),
        _document("Compendium.dnd5e.origins24.Item.phbbgAcolyte0000", "Acolyte", "background", {
            "advancement": [
                {"type": "AbilityScoreImprovement", "level": 0, "title": "Background Ability Score Improvement", "configuration": {"points": 3, "cap": 2, "locked": ["str", "dex", "con"]}},
                {"type": "Trait", "level": 0, "title": "Background Proficiencies", "configuration": {"grants": ["skills:ins", "skills:rel"], "choices": []}},
                {"type": "ItemGrant", "level": 0, "title": "Background Feat", "configuration": {"items": [{"uuid": "Compendium.dnd5e.feats24.Item.phbftMagicInitia", "optional": False}]}},
            ],
            "startingEquipment": [{"type": "AND", "group": ""}],
            "wealth": "50",
        }),
        _document("Compendium.dnd5e.feats24.Item.phbftMagicInitia", "Magic Initiate", "feat", {"type": {"value": "feat"}}),
        _document("Compendium.dnd5e.origins24.Item.phbspHuman000000", "Human", "race", {
            "advancement": [{"type": "Size", "level": 0, "configuration": {"sizes": ["sm", "med"]}}],
        }),
    ]
    return {"line": "srd5e", "system": "srd-5e", "name": "SRD 5.2 content", "slug": "srd5e", "kinds": KINDS, "documents": documents, "problems": []}


@pytest.fixture(scope="module")
def world(server: TestClient) -> dict[str, Any]:
    """The operator's setting on the srd-5e system, the srd5e module installed, and two pregens."""
    owner = create_user(server)
    setting = _create(server, owner, "setting", name="The Coast", slug="the-coast")
    registry = server.app.state.model_registry  # type: ignore[attr-defined]
    systems = GameSystemManager(requester_id=env("ROOT_ID"), model_registry=registry)
    fifth = next(one for one in systems.list(slug="srd-5e"))
    systems.update(id=fifth.id, setting_id=setting["id"])
    install(registry, str(owner.id), _bundle())
    on = {"kind": "pc", "setting_id": setting["id"]}
    current = _create(server, owner, "person", name="Bran", description="Level 1 Human Fighter, Acolyte background (SRD 5.2.1). A temple guard.", **on)
    older = _create(server, owner, "person", name="Bran (2014)", description="Level 1 Human Fighter, Acolyte background (SRD 5.1).", **on)
    return {"owner": owner, "current": current, "older": older, "registry": registry}


def _build(server: TestClient, user: Any, person_id: str, **flags: Any) -> Any:
    return server.post("/v1/builder/pregen", json={"pregen": {"person_id": person_id, **flags}}, headers=_headers(user))


def test_a_dry_run_reports_the_sheet_and_every_open_choice_and_writes_nothing(server: TestClient, world: dict[str, Any]) -> None:
    response = _build(server, world["owner"], world["current"]["id"], dry_run=True)
    assert response.status_code == 200, response.text
    got = response.json()["pregen"]
    assert (got["class_name"], got["background"], got["species"], got["level"]) == ("Fighter", "Acolyte", "Human", 1)
    assert got["built"] and got["written"] == 0 and not got["has_sheet"]
    assert got["abilities"] == {"strength": 15, "dexterity": 14, "constitution": 13, "intelligence": 8, "wisdom": 10, "charisma": 12}
    assert got["saves"] == ["strength", "constitution"] and got["skills"] == ["insight", "religion"]
    assert sorted(got["features"]) == ["Magic Initiate", "Second Wind"] and got["hp"] == 11
    assert {gap["what"] for gap in got["gaps"]} == {"class", "background", "species", "equipment"}
    rows = PersonTraitManager(requester_id=env("ROOT_ID"), model_registry=world["registry"])
    assert not list(rows.list(person_id=world["current"]["id"]))


def test_a_build_writes_the_sheet_once_and_a_rebuild_needs_replace(server: TestClient, world: dict[str, Any]) -> None:
    first = _build(server, world["owner"], world["current"]["id"])
    assert first.status_code == 200, first.text
    assert first.json()["pregen"]["written"] == 3 + 2 + 6 + 2 + 2  # origins, features, abilities, skills, HP and PB
    registry = world["registry"]
    rows = PersonTraitManager(requester_id=env("ROOT_ID"), model_registry=registry)
    traits = TraitManager(requester_id=env("ROOT_ID"), model_registry=registry)
    live = [rows.DB.deleted_at.is_(None)]
    held = {traits.get(id=row.trait_id).slug: row for row in rows.list(filters=live, person_id=world["current"]["id"])}
    # The pregen's owner lists the sheet through the generic route: the rows are theirs, not the system's.
    own = server.get("/v1/person_trait", params={"person_id": world["current"]["id"], "limit": 50}, headers=_headers(world["owner"]))
    assert own.status_code == 200 and len(own.json()["person_traits"]) == 15, own.text
    assert held["strength"].value == 15 and held["religion"].rank == 1 and "fighter" in held

    again = _build(server, world["owner"], world["current"]["id"])
    assert again.status_code == 422 and "already has a sheet" in again.text
    replaced = _build(server, world["owner"], world["current"]["id"], replace=True)
    assert replaced.status_code == 200 and replaced.json()["pregen"]["has_sheet"]
    assert len(list(rows.list(filters=live, person_id=world["current"]["id"]))) == 15


def test_another_edition_is_reported_not_built(server: TestClient, world: dict[str, Any]) -> None:
    got = _build(server, world["owner"], world["older"]["id"]).json()["pregen"]
    assert not got["built"] and got["written"] == 0
    assert [gap["what"] for gap in got["gaps"]] == ["edition"]


def test_only_the_pregens_owner_builds_it(server: TestClient, world: dict[str, Any]) -> None:
    stranger = create_user(server)
    response = _build(server, stranger, world["current"]["id"], dry_run=True)
    assert response.status_code == 404 and "could not find" in response.text


def test_a_scenarios_pregen_is_built_by_the_campaigns_gm_under_its_system(server: TestClient, world: dict[str, Any]) -> None:
    """A scenario's pregen is a character of the scenario's campaign: its GM builds it, under the
    campaign's own system; anyone else is told it isn't there."""
    owner = world["owner"]
    registry = world["registry"]
    fifth = next(one for one in GameSystemManager(requester_id=env("ROOT_ID"), model_registry=registry).list(slug="srd-5e"))
    scenario = _create(server, owner, "campaign", name="Through the Old Woods", user_id=owner.id, game_system_id=fifth.id)
    rowan = _create(
        server, owner, "person", name="Rowan Hale", kind="pc", campaign_id=scenario["id"],
        description="Level 1 Human Fighter, Acolyte background (SRD 5.2.1). A woodcutter's son.",
    )
    got = _build(server, owner, rowan["id"], dry_run=True).json()["pregen"]
    assert got["built"] and (got["class_name"], got["species"]) == ("Fighter", "Human")
    stranger = create_user(server)
    refused = _build(server, stranger, rowan["id"], dry_run=True)
    assert refused.status_code == 404 and "could not find" in refused.text


def test_a_scenario_builds_its_pregens_to_its_starting_level(server: TestClient, world: dict[str, Any]) -> None:
    owner = world["owner"]
    registry = world["registry"]
    fifth = next(one for one in GameSystemManager(requester_id=env("ROOT_ID"), model_registry=registry).list(slug="srd-5e"))
    antler = _create(server, owner, "campaign", name="The Split Antler", user_id=owner.id, game_system_id=fifth.id, starting_level=10)
    levels = server.post("/v1/builder/levels", json={"levels": {"campaign_id": antler["id"]}}, headers=_headers(owner))
    assert levels.status_code == 200, levels.text
    assert levels.json()["levels"] == {"campaign_id": antler["id"], "system": "srd-5e", "max_level": 20, "starting_level": 10}
    dingus = _create(
        server, owner, "person", name="Dingus McQuingus the Eighteenth", kind="pc", campaign_id=antler["id"],
        description="Level 1 Unknown Fighter, Acolyte background (SRD 5.2.1). His race is canonically unknown.",
    )
    got = _build(server, owner, dingus["id"], dry_run=True).json()["pregen"]
    assert got["built"] and got["level"] == 10 and got["species"] == "Unknown"
    assert got["hp"] == (10 + 1) + 9 * (6 + 1), "the fixed 6 + Con at each level from 2 to 10"


def test_the_slider_rebuilds_a_scenarios_pregens_to_its_new_level(server: TestClient, world: dict[str, Any]) -> None:
    owner = world["owner"]
    registry = world["registry"]
    fifth = next(one for one in GameSystemManager(requester_id=env("ROOT_ID"), model_registry=registry).list(slug="srd-5e"))
    woods = _create(server, owner, "campaign", name="Through the Old Woods", user_id=owner.id, game_system_id=fifth.id)
    rowan = _create(
        server, owner, "person", name="Rowan Hale", kind="pc", campaign_id=woods["id"],
        description="Level 1 Human Fighter, Acolyte background (SRD 5.2.1).",
    )
    _create(server, owner, "person", name="Kestrel Vane", kind="pc", campaign_id=woods["id"], description="A ranger, built by hand.")

    def commit(user: Any, **body: Any) -> Any:
        return server.post("/v1/builder/pregens", json={"pregens": {"campaign_id": woods["id"], **body}}, headers=_headers(user))

    moved = commit(owner, level=4)
    assert moved.status_code == 200, moved.text
    got = moved.json()["pregens"]
    assert got["starting_level"] == 4
    assert [(one["name"], one["level"], one["built"]) for one in got["results"]] == [("Rowan Hale", 4, True)]
    assert got["results"][0]["written"] > 0 and got["results"][0]["hp"] == (10 + 1) + 3 * (6 + 1)
    assert [one["name"] for one in got["skipped"]] == ["Kestrel Vane"], "no builder line: left as it is"
    levels = server.post("/v1/builder/levels", json={"levels": {"campaign_id": woods["id"]}}, headers=_headers(owner))
    assert levels.json()["levels"]["starting_level"] == 4
    # Moving it again re-levels the sheet already there.
    again = commit(owner, level=2).json()["pregens"]
    assert again["results"][0]["level"] == 2 and again["results"][0]["has_sheet"]
    assert commit(owner, level=25).status_code == 422
    assert commit(create_user(server), level=3).status_code == 404
    assert rowan["id"] == got["results"][0]["person_id"]
