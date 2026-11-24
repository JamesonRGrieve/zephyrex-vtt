# SPDX-License-Identifier: AGPL-3.0-or-later
"""The operator's framework selector (sf 72f51160): each VTT extension's backend_selector says which
backend serves a call, from the call's campaign as the wiki's campaign_backend says, resolving a
scene's, an encounter's or a person's campaign; with no campaign_backend in the wiki, every call is
the VTT's own."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_builder import EXT_RPGBuilder
from zephyrex.extensions.rpg_combat import EXT_RPGCombat
from zephyrex.extensions.rpg_dice import EXT_RPGDice
from zephyrex.extensions.rpg_scene import EXT_RPGScene
from zephyrex.testing.factories import create_user

from vtt_app import create

MODULES = (EXT_RPGScene, EXT_RPGCombat, EXT_RPGDice, EXT_RPGBuilder)


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


@pytest.fixture(scope="module")
def table(server: TestClient) -> dict[str, Any]:
    gm, player = create_user(server), create_user(server)
    kept = {}
    for label in ("foundry", "native"):
        campaign = _create(server, gm, "campaign", name=f"A {label} table", user_id=gm.id)
        pc = _create(server, gm, "person", name=f"{label} hero", kind="pc", user_id=player.id, campaign_id=campaign["id"])
        scene = _create(server, gm, "scene", name=f"{label} map", campaign_id=campaign["id"])
        encounter = asyncio.run(EXT_RPGCombat.RPGCombatExtension.start_encounter(str(gm.id), campaign["id"], person_ids=[pc["id"]]))
        kept[label] = {"campaign": campaign["id"], "person": pc["id"], "scene": scene["id"], "encounter": encounter["id"]}
    return kept


@pytest.fixture
def wiki_says(monkeypatch: pytest.MonkeyPatch, table: dict[str, Any]) -> list[dict[str, Any]]:
    """A wiki whose campaign_backend keeps the "foundry" campaign (and its people) in Foundry."""
    asked: list[dict[str, Any]] = []
    foundry = table["foundry"]

    def campaign_backend(model_registry: Any, requester_id: str, campaign_id: Any = None, person_id: Any = None) -> dict[str, Any]:
        asked.append({"campaign_id": campaign_id, "person_id": person_id})
        there = campaign_id == foundry["campaign"] or person_id == foundry["person"]
        return {"backend": "foundry" if there else "native", "instance_id": "world-1" if there else None}

    for module in MODULES:
        real = module.loaded_ability

        def fake(registry: Any, extension: str, ability: str, _real: Any = real) -> Any:
            return campaign_backend if (extension, ability) == ("rpg_core", "campaign_backend") else _real(registry, extension, ability)

        monkeypatch.setattr(module, "loaded_ability", fake)
    return asked


def _select(extension: Any, ability: str, **arguments: Any) -> Any:
    return asyncio.run(extension.backend_for(ability, arguments))


def test_each_extension_routes_a_foundry_campaigns_calls_and_keeps_its_own(table: dict[str, Any], wiki_says: list[dict[str, Any]]) -> None:
    foundry, native = table["foundry"], table["native"]
    scene, combat = EXT_RPGScene.RPGSceneExtension, EXT_RPGCombat.RPGCombatExtension
    dice, builder = EXT_RPGDice.RPGDiceExtension, EXT_RPGBuilder.RPGBuilderExtension
    assert _select(scene, "current_scene", requester_id="u", campaign_id=foundry["campaign"]) == "foundry"
    assert _select(scene, "scene_tokens", requester_id="u", scene_id=foundry["scene"]) == "foundry"
    assert _select(scene, "scene_tokens", requester_id="u", scene_id=native["scene"]) is None
    assert _select(combat, "next_turn", requester_id="u", encounter_id=foundry["encounter"]) == "foundry"
    assert _select(combat, "next_turn", requester_id="u", encounter_id=native["encounter"]) is None
    assert _select(dice, "test_options", requester_id="u", person_id=foundry["person"]) == "foundry"
    assert _select(builder, "npc_sheet_options", requester_id="u", campaign_id=native["campaign"]) is None
    # The encounter was resolved to its campaign before the wiki was asked.
    assert {"campaign_id": foundry["campaign"], "person_id": None} in wiki_says


def test_a_call_naming_no_campaign_or_an_unknown_scene_is_the_vtts_own(table: dict[str, Any], wiki_says: list[dict[str, Any]]) -> None:
    scene = EXT_RPGScene.RPGSceneExtension
    assert _select(scene, "scene_tokens", requester_id="u") is None
    assert _select(scene, "scene_tokens", requester_id="u", scene_id="no-such-scene") is None
    assert wiki_says == [], "nothing to ask about"


def test_a_foundry_id_is_foundrys_without_asking(table: dict[str, Any], wiki_says: list[dict[str, Any]]) -> None:
    assert _select(EXT_RPGScene.RPGSceneExtension, "scene_tokens", requester_id="u", scene_id="fvtt:Scene.abc") == "foundry"
    assert _select(EXT_RPGDice.RPGDiceExtension, "test_options", requester_id="u", person_id="fvtt:Actor.xyz") == "foundry"
    assert wiki_says == []


def test_a_campaign_the_wiki_keeps_native_stays_the_vtts(table: dict[str, Any]) -> None:
    # The wiki's own campaign_backend: neither table was moved to Foundry.
    assert _select(EXT_RPGScene.RPGSceneExtension, "current_scene", requester_id="u", campaign_id=table["foundry"]["campaign"]) is None
    assert _select(EXT_RPGCombat.RPGCombatExtension, "next_turn", requester_id="u", encounter_id=table["foundry"]["encounter"]) is None


def test_the_wikis_own_campaign_backend_routes_a_campaign_the_gm_moved_to_foundry(server: TestClient) -> None:
    """Against the real thing (wiki 8f8c910, rpg_core 021): the GM sets a campaign's backend, and
    every VTT selector follows it through a scene, an encounter and a person."""
    gm, player = create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="Kept in Foundry", user_id=gm.id)
    pc = _create(server, gm, "person", name="Rhia", kind="pc", user_id=player.id, campaign_id=campaign["id"])
    scene = _create(server, gm, "scene", name="The quay", campaign_id=campaign["id"])
    encounter = asyncio.run(EXT_RPGCombat.RPGCombatExtension.start_encounter(str(gm.id), campaign["id"], person_ids=[pc["id"]]))
    assert _select(EXT_RPGScene.RPGSceneExtension, "scene_tokens", requester_id="u", scene_id=scene["id"]) is None
    current = server.get(f"/v1/campaign/{campaign['id']}", headers=_headers(gm))
    moved = server.put(
        f"/v1/campaign/{campaign['id']}",
        json={"campaign": {"backend": "foundry"}},
        headers={**_headers(gm), "If-Match": current.headers["ETag"]},
    )
    assert moved.status_code == 200, moved.text
    assert _select(EXT_RPGScene.RPGSceneExtension, "scene_tokens", requester_id="u", scene_id=scene["id"]) == "foundry"
    assert _select(EXT_RPGCombat.RPGCombatExtension, "next_turn", requester_id="u", encounter_id=encounter["id"]) == "foundry"
    assert _select(EXT_RPGDice.RPGDiceExtension, "test_options", requester_id="u", person_id=pc["id"]) == "foundry"
    assert _select(EXT_RPGBuilder.RPGBuilderExtension, "npc_sheet_options", requester_id="u", campaign_id=campaign["id"]) == "foundry"
