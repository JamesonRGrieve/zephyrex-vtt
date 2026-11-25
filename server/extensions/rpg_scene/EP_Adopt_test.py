# SPDX-License-Identifier: AGPL-3.0-or-later
"""VTT's adopt hooks for the wiki's system_adopt (wiki ed56c11; operator, 2026-11-25: "The out of
the box scenarios, pregens, everything with the SRD should also be system level down to campaigns
which are user level"), called here as system_adopt calls them: once for the primary copy of a
setting (no id map), then for a duplicate merged into it (its ids → the primary's). The primary's
scenes, tokens, pins, traits and pregen sheets become SYSTEM's; a duplicate's move in with their
references turned, or are removed where the primary already has their match."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_scene.Adopt import adopt_scenes
from zephyrex.extensions.rpg_scene.BLL_RPGScene import SceneManager, SceneTokenManager, ScopePlaceManager
from zephyrex.extensions.rpg_traits.Adopt import adopt_traits
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import PersonTraitManager, TraitManager
from zephyrex.lib.Environment import env
from zephyrex.testing.factories import create_user

from vtt_app import create


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


def _rows(registry: Any, manager: Any, **filters: Any) -> list[Any]:
    found = manager(requester_id=env("ROOT_ID"), model_registry=registry)
    return list(found.list(filters=[found.DB.deleted_at.is_(None)], **filters))


def _copy(server: TestClient, user: Any, setting: dict[str, Any], *, extra_scene: bool) -> dict[str, Any]:
    """One account's import of The Missing Merchant: its scenario, a place, a pregen with a sheet
    (or none), a scene with the pregen's token, a pin and a scenario trait."""
    scenario = _create(server, user, "campaign", name="The Missing Merchant", user_id=user.id, setting_id=setting["id"], is_scenario=True)
    house = _create(server, user, "location", name="Halloway house", kind="building", campaign_id=scenario["id"])
    brann = _create(server, user, "person", name="Brann", kind="pc", campaign_id=scenario["id"])
    scene = _create(server, user, "scene", name="Halloway house, ground floor", campaign_id=scenario["id"], location_id=house["id"])
    token = _create(server, user, "scene_token", name="Brann", scene_id=scene["id"], person_id=brann["id"], x=100, y=100)
    made = {"scenario": scenario, "house": house, "brann": brann, "scene": scene, "token": token}
    if extra_scene:
        quay = _create(server, user, "scene", name="The quay", campaign_id=scenario["id"])
        made["quay"] = quay
        made["quay_token"] = _create(server, user, "scene_token", name="Brann", scene_id=quay["id"], person_id=brann["id"], x=50, y=50)
        trait = _create(server, user, "trait", name="Salt Lore", slug="salt-lore", kind="skill", campaign_id=scenario["id"])
        made["trait"] = trait
        made["row"] = _create(server, user, "person_trait", person_id=brann["id"], trait_id=trait["id"], rank=1)
        made["pin"] = _create(server, user, "scope_place", campaign_id=scenario["id"], location_id=house["id"], x=0.5, y=0.5)
    else:
        made["trait"] = _create(server, user, "trait", name="Salt Lore", slug="salt-lore", kind="skill", campaign_id=scenario["id"])
    return made


def test_a_setting_made_system_level_takes_its_scenes_and_sheets_and_merges_a_duplicates(server: TestClient) -> None:
    registry = server.app.state.model_registry  # type: ignore[attr-defined]
    system = str(env("SYSTEM_ID"))
    first, second = create_user(server), create_user(server)
    setting = _create(server, first, "setting", name="The Salt Coast", slug="the-salt-coast-adopt")
    other = _create(server, second, "setting", name="The Salt Coast", slug="the-salt-coast-adopt-2")
    primary = _copy(server, first, setting, extra_scene=False)
    duplicate = _copy(server, second, other, extra_scene=True)

    # The primary: its ids kept, no map; a dry run first writes nothing.
    dry = adopt_scenes(registry, setting["id"], [primary["scenario"]["id"]], {}, True)
    assert "dry run" in dry[0] and "1 scenes" in dry[0]
    assert str(_rows(registry, SceneManager, id=primary["scene"]["id"])[0].created_by_user_id) == str(first.id)
    said = adopt_scenes(registry, setting["id"], [primary["scenario"]["id"]], {}, False)
    assert "1 scenes" in said[0] and "1 parts" in said[0], said
    adopt_traits(registry, setting["id"], [primary["scenario"]["id"]], {}, False)
    assert str(_rows(registry, SceneManager, id=primary["scene"]["id"])[0].created_by_user_id) == system
    assert str(_rows(registry, SceneTokenManager, id=primary["token"]["id"])[0].created_by_user_id) == system
    assert str(_rows(registry, TraitManager, id=primary["trait"]["id"])[0].created_by_user_id) == system
    # Every account reads the instance's scene.
    seen = server.get(f"/v1/scene/{primary['scene']['id']}", headers=_headers(second))
    assert seen.status_code == 200, seen.text

    # The duplicate merged in: the wiki's map turns its scenario, place and pregen to the primary's.
    id_map = {
        duplicate["scenario"]["id"]: primary["scenario"]["id"],
        duplicate["house"]["id"]: primary["house"]["id"],
        duplicate["brann"]["id"]: primary["brann"]["id"],
        other["id"]: setting["id"],
    }
    lines = adopt_scenes(registry, setting["id"], [primary["scenario"]["id"]], id_map, False)
    lines += adopt_traits(registry, setting["id"], [primary["scenario"]["id"]], id_map, False)
    assert any("removed scenes" in line for line in lines), lines
    # Its ground floor matched the primary's (by name): removed with its token.
    assert _rows(registry, SceneManager, id=duplicate["scene"]["id"]) == []
    assert _rows(registry, SceneTokenManager, id=duplicate["token"]["id"]) == []
    # Its quay had no match: moved in, its token's person turned to the primary's Brann.
    quay = _rows(registry, SceneManager, id=duplicate["quay"]["id"])[0]
    assert (str(quay.campaign_id), str(quay.created_by_user_id)) == (primary["scenario"]["id"], system)
    token = _rows(registry, SceneTokenManager, id=duplicate["quay_token"]["id"])[0]
    assert (str(token.person_id), str(token.created_by_user_id)) == (primary["brann"]["id"], system)
    pin = _rows(registry, ScopePlaceManager, id=duplicate["pin"]["id"])[0]
    assert (str(pin.campaign_id), str(pin.location_id)) == (primary["scenario"]["id"], primary["house"]["id"])
    # Its Salt Lore matched the primary's (kind and slug): removed, and its sheet row follows; the
    # primary's Brann had no sheet, so the duplicate's moves onto him as SYSTEM's.
    assert _rows(registry, TraitManager, id=duplicate["trait"]["id"]) == []
    row = _rows(registry, PersonTraitManager, id=duplicate["row"]["id"])[0]
    assert (str(row.person_id), str(row.trait_id), str(row.created_by_user_id)) == (primary["brann"]["id"], primary["trait"]["id"], system)

    # Run again (system_adopt is idempotent): nothing more moves or goes.
    again = adopt_traits(registry, setting["id"], [primary["scenario"]["id"]], {}, False)
    assert "removed" not in again[0]
