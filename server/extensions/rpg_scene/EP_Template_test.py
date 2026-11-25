# SPDX-License-Identifier: AGPL-3.0-or-later
"""One shared copy of the SRD content (the operator, 2026-11-25): a scenario, its maps and its
pregens' sheets are TEMPLATE's (the framework's template account: every account reads and copies
them, only ROOT or SYSTEM changes them); only a campaign is a user's. SYSTEM builds the shared
copy's map (map_location) and it stays TEMPLATE's; a plain user starts a playthrough from it and gets
the scenes and the pregen's sheet as their own copies, and can change neither the template's scene
nor its sheet."""

import asyncio
import base64
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.cloud.EXT_Cloud import EXT_Cloud
from zephyrex.extensions.rpg_scene.EXT_RPGScene import RPGSceneExtension
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


def _as_template(registry: Any, manager: Any, *row_ids: str) -> None:
    """Rows kept as TEMPLATE's, as the wiki's system_adopt and VTT's own builds leave them."""
    rows = manager(requester_id=env("ROOT_ID"), model_registry=registry)
    session = rows.db
    try:
        table = rows.DB.__table__
        values = {"created_by_user_id": env("TEMPLATE_ID")}
        if "user_id" in table.c and manager.__name__ == "CampaignManager":
            values["user_id"] = env("TEMPLATE_ID")
        session.execute(table.update().where(table.c.id.in_(list(row_ids))).values(**values))
        session.commit()
    finally:
        session.close()


def test_a_user_starts_a_campaign_from_the_shared_copy_and_cannot_change_it(server: TestClient, store: dict[str, bytes]) -> None:
    from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager
    from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignManager  # type: ignore[import-not-found]
    from zephyrex.extensions.rpg_scene.BLL_RPGScene import SceneManager
    from zephyrex.extensions.rpg_traits.BLL_RPGTraits import PersonTraitManager, TraitManager
    from zephyrex.extensions.world_spatial.BLL_WorldSpatial import LocationManager  # type: ignore[import-not-found]

    registry = server.app.state.model_registry  # type: ignore[attr-defined]
    system, template = str(env("SYSTEM_ID")), str(env("TEMPLATE_ID"))

    def as_system(manager: Any) -> Any:
        return manager(requester_id=system, model_registry=registry)

    # The shared copy, as system_adopt leaves it: TEMPLATE's scenario, place, pregen and sheet.
    scenario = as_system(CampaignManager).create(name="The Tavern Start (shared)", user_id=system, is_scenario=True)
    lantern = as_system(LocationManager).create(name="The Leaning Lantern", kind="building", campaign_id=scenario.id)
    rowan = as_system(PersonManager).create(name="Rowan Hale", kind="pc", campaign_id=scenario.id, location_id=lantern.id)
    lore = as_system(TraitManager).create(name="Tavern Lore", slug="tavern-lore", kind="skill", campaign_id=scenario.id)
    sheet = as_system(PersonTraitManager).create(person_id=rowan.id, trait_id=lore.id, rank=2)
    _as_template(registry, CampaignManager, scenario.id)
    _as_template(registry, LocationManager, lantern.id)
    _as_template(registry, PersonManager, rowan.id)
    _as_template(registry, TraitManager, lore.id)
    _as_template(registry, PersonTraitManager, sheet.id)

    # SYSTEM builds its map; it stays TEMPLATE's.
    made = asyncio.run(RPGSceneExtension.map_location(system, lantern.id, uvtt=LANTERN))
    assert made["created"]
    scene = SceneManager(requester_id=env("ROOT_ID"), model_registry=registry).get(id=made["scene_id"])
    assert str(scene.created_by_user_id) == template

    # A plain user reads it and can't change it.
    user = create_user(server)
    seen = server.get(f"/v1/scene/{made['scene_id']}", headers=_headers(user))
    assert seen.status_code == 200, seen.text
    renamed = server.put(
        f"/v1/scene/{made['scene_id']}",
        json={"scene": {"name": "Mine now"}},
        headers={**_headers(user), "If-Match": seen.headers.get("ETag", "*")},
    )
    assert renamed.status_code in (403, 404), renamed.text
    with pytest.raises(Exception):
        asyncio.run(RPGSceneExtension.map_location(str(user.id), lantern.id, image_base64=base64.b64encode(png(10, 10)).decode()))

    # The user starts a playthrough: the scenes and the pregen's sheet are copied as theirs.
    accepted = server.post(f"/v1/campaign/{scenario.id}/instantiate", json={"instantiate": {}}, headers=_headers(user))
    assert accepted.status_code == 202, accepted.text
    start = accepted.json()["start"]
    deadline = time.monotonic() + 90
    while start["state"] == "running":
        assert time.monotonic() < deadline, start
        time.sleep(0.5)
        start = server.get(f"/v1/campaign_start/{start['id']}", headers=_headers(user)).json()["campaign_start"]
    assert start["state"] == "done", start.get("error") or start
    playthrough = str(start["campaign_id"])
    shown = asyncio.run(RPGSceneExtension.current_scene(str(user.id), playthrough))
    assert shown is not None and shown["name"] == "The Leaning Lantern" and shown["campaign_id"] == playthrough
    copied_scene = SceneManager(requester_id=env("ROOT_ID"), model_registry=registry).get(id=shown["id"])
    assert str(copied_scene.created_by_user_id) == str(user.id), "the playthrough's scene is the user's own"
    art = server.get(f"/v1/scene/{shown['id']}/background", headers=_headers(user))
    assert art.status_code == 200

    people = PersonManager(requester_id=env("ROOT_ID"), model_registry=registry)
    copy = next(one for one in people.list(campaign_id=playthrough) if one.name == "Rowan Hale")
    rows = PersonTraitManager(requester_id=env("ROOT_ID"), model_registry=registry)
    copied_rows = rows.list(filters=[rows.DB.deleted_at.is_(None)], person_id=copy.id)
    assert [(row.rank, str(row.created_by_user_id)) for row in copied_rows] == [(2, str(user.id))], "the sheet copied as theirs"

    # The template's own sheet row is untouched and still the template's.
    held = rows.get(id=sheet.id)
    assert (held.rank, str(held.created_by_user_id)) == (2, template)
