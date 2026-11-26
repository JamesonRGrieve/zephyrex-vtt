# SPDX-License-Identifier: AGPL-3.0-or-later
"""A non-owner's start of an adopted (TEMPLATE) scenario with several maps (Zephyrex RPG's find on
dev, 2026-11-26: The Haunted Manor's three scenes, all with art, adopted; each start by a test user
made one bare scene, a different one each time, and never the hall the party opens in). Here the
scenario is imported the way vault_import does it (an importer maps three of its places), adopted
as system_adopt does (the wiki's rows TEMPLATE's, then VTT's hooks), and started twice by a plain
user: each start copies all three scenes with their art and opens on the hall, the same both times."""

import asyncio
import base64
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.cloud.EXT_Cloud import EXT_Cloud
from zephyrex.extensions.rpg_scene.Adopt import adopt_scenes
from zephyrex.extensions.rpg_scene.EXT_RPGScene import RPGSceneExtension
from zephyrex.extensions.rpg_traits.Adopt import adopt_traits
from zephyrex.lib.Environment import env
from zephyrex.testing.factories import create_user

from vtt_app import create

from .EP_LocationMap_test import LANTERN, png


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    with TestClient(create()) as client:
        yield client


@pytest.fixture(autouse=True)
def store(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    files: dict[str, bytes] = {}

    async def upload_file(cls: Any, path: str, content: bytes, provider: Any = None) -> dict[str, Any]:
        files[path] = content
        return {"provider": "memory", "path": path}

    async def download_file(cls: Any, provider: str, path: str) -> bytes:
        return files[path]

    monkeypatch.setattr(EXT_Cloud, "upload_file", classmethod(upload_file))
    monkeypatch.setattr(EXT_Cloud, "download_file", classmethod(download_file))
    return files


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _create(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = server.post(f"/v1/{resource}", json={resource: fields}, headers=_headers(user))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()[resource]
    return created


def _start(server: TestClient, user: Any, scenario_id: str) -> str:
    accepted = server.post(f"/v1/campaign/{scenario_id}/instantiate", json={"instantiate": {}}, headers=_headers(user))
    assert accepted.status_code == 202, accepted.text
    start = accepted.json()["start"]
    deadline = time.monotonic() + 90
    while start["state"] == "running":
        assert time.monotonic() < deadline, start
        time.sleep(0.5)
        start = server.get(f"/v1/campaign_start/{start['id']}", headers=_headers(user)).json()["campaign_start"]
    assert start["state"] == "done", start.get("error") or start
    return str(start["campaign_id"])


def _as_template(registry: Any, manager: Any, ids: list[str]) -> None:
    """The wiki's system_adopt on its own rows: TEMPLATE's (a campaign's user_id too)."""
    rows = manager(requester_id=env("ROOT_ID"), model_registry=registry)
    session = rows.db
    try:
        table = rows.DB.__table__
        values = {"created_by_user_id": env("TEMPLATE_ID")}
        if manager.__name__ == "CampaignManager":
            values["user_id"] = env("TEMPLATE_ID")
        session.execute(table.update().where(table.c.id.in_(ids)).values(**values))
        session.commit()
    finally:
        session.close()


def test_a_non_owner_starts_an_adopted_three_map_scenario_on_its_opening_map_every_time(server: TestClient) -> None:
    from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager
    from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignManager, SettingManager  # type: ignore[import-not-found]
    from zephyrex.extensions.rpg_scene.BLL_RPGScene import SceneManager
    from zephyrex.extensions.world_spatial.BLL_WorldSpatial import LocationManager  # type: ignore[import-not-found]

    registry = server.app.state.model_registry  # type: ignore[attr-defined]
    importer, player = create_user(server), create_user(server)
    setting = _create(server, importer, "setting", name="The Ashgrove Vale", slug="the-ashgrove-vale-shared")
    scenario = _create(server, importer, "campaign", name="The Haunted Manor", user_id=importer.id, setting_id=setting["id"], is_scenario=True)
    village = _create(server, importer, "location", name="Hollin's End", kind="city", campaign_id=scenario["id"])
    manor = _create(server, importer, "location", name="Ashgrove Manor", kind="building", parent_id=village["id"], campaign_id=scenario["id"])
    hall = _create(server, importer, "location", name="The manor's hall", kind="room", parent_id=manor["id"], campaign_id=scenario["id"])
    crypt = _create(server, importer, "location", name="Ashgrove Crypt", kind="building", parent_id=village["id"], campaign_id=scenario["id"])
    people = [
        _create(server, importer, "person", name=name, kind="pc", campaign_id=scenario["id"], location_id=hall["id"])
        for name in ("Wren", "Tobias", "Ilse", "Garrick")
    ]
    bastian = _create(server, importer, "person", name="Lord Bastian Ashgrove", kind="npc", campaign_id=scenario["id"], location_id=hall["id"])

    # The importer maps three places (vault_import's map step), crypt and village before the hall.
    made = {}
    for place, art in ((crypt, png(120, 90)), (village, png(200, 150)), (manor, None)):
        given = {"uvtt": LANTERN} if art is None else {"image_base64": base64.b64encode(art).decode(), "grid_size": 10}
        made[place["name"]] = asyncio.run(RPGSceneExtension.map_location(str(importer.id), place["id"], **given))

    # Adopted: the wiki's rows TEMPLATE's, then VTT's hooks (scenes, parts, art, sheets).
    _as_template(registry, SettingManager, [setting["id"]])
    _as_template(registry, CampaignManager, [scenario["id"]])
    _as_template(registry, LocationManager, [village["id"], manor["id"], hall["id"], crypt["id"]])
    _as_template(registry, PersonManager, [one["id"] for one in [*people, bastian]])
    said = adopt_scenes(registry, setting["id"], [scenario["id"]], {}, False)
    adopt_traits(registry, setting["id"], [scenario["id"]], {}, False)
    assert "3 scenes" in said[0] and "3 art" in said[0], said

    opened = []
    for _ in range(2):
        playthrough = _start(server, player, scenario["id"])
        scenes = SceneManager(requester_id=env("ROOT_ID"), model_registry=registry)
        copied = [one for one in scenes.list(filters=[scenes.DB.deleted_at.is_(None)], campaign_id=playthrough)]
        assert sorted(one.name for one in copied) == sorted(made), "every scenario map, no stand-in"
        assert all(one.background_url for one in copied), [(one.name, one.background_url) for one in copied]
        shown = asyncio.run(RPGSceneExtension.current_scene(str(player.id), playthrough))
        assert shown is not None and shown["name"] == "Ashgrove Manor", shown
        art = server.get(f"/v1/scene/{shown['id']}/background", headers=_headers(player))
        assert art.status_code == 200, art.text
        opened.append(shown["name"])
    assert opened[0] == opened[1]


def test_a_scenario_with_no_maps_opens_on_a_stand_in_where_most_of_the_party_is_every_time(server: TestClient) -> None:
    """With no map to copy, the start's stand-in scene is made where most of the party stands (the
    opening place), the same scene each time, not wherever the first character in an unfixed order
    happens to be (two starts on dev opened in the village and the crypt)."""
    author = create_user(server)
    scenario = _create(server, author, "campaign", name="Goblin Ambush", user_id=author.id, is_scenario=True)
    road = _create(server, author, "location", name="The Triboar Trail", kind="region", campaign_id=scenario["id"])
    cave = _create(server, author, "location", name="Cragmaw Hideout", kind="building", campaign_id=scenario["id"])
    for name, where in (("Zed", cave), ("Ana", road), ("Bo", road), ("Cy", road)):
        _create(server, author, "person", name=name, kind="pc", campaign_id=scenario["id"], location_id=where["id"])
    shown = []
    for _ in range(2):
        playthrough = _start(server, author, scenario["id"])
        found = asyncio.run(RPGSceneExtension.current_scene(str(author.id), playthrough))
        assert found is not None
        shown.append(found["name"])
    assert shown == ["The Triboar Trail", "The Triboar Trail"], shown
