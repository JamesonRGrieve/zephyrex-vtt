# SPDX-License-Identifier: AGPL-3.0-or-later
"""A playthrough's characters keep their sheets (the operator: pregens' sheets "should all be done
already at start"): the wiki's start runs rpg_traits' AFTER_INSTANTIATE callback, which copies the
scenario's own traits and each copied person's person_traits."""

import asyncio
import time
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_systems.EXT_RPGSystems import RPGSystemsExtension
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


def test_a_started_playthroughs_characters_keep_their_sheets(server: TestClient) -> None:
    author = create_user(server)
    systems = {one["slug"]: one for one in asyncio.run(RPGSystemsExtension.game_systems(str(author.id)))}
    dnd = systems["dnd-5e"]["id"]
    scenario = _create(server, author, "campaign", name="Tavern", user_id=author.id, is_scenario=True, game_system_id=dnd)
    brann = _create(server, author, "person", name="Brann", kind="pc", campaign_id=scenario["id"])
    strength = server.get("/v1/trait", params={"slug": "strength", "game_system_id": dnd}, headers=_headers(author)).json()["traits"][0]
    _create(server, author, "person_trait", person_id=brann["id"], trait_id=strength["id"], value=16)
    oath = _create(server, author, "trait", name="Tavern Oath", kind="feat", campaign_id=scenario["id"])
    _create(server, author, "person_trait", person_id=brann["id"], trait_id=oath["id"])

    start = server.post(f"/v1/campaign/{scenario['id']}/instantiate", json={"instantiate": {}}, headers=_headers(author)).json()["start"]
    deadline = time.monotonic() + 60
    while start["state"] == "running":
        assert time.monotonic() < deadline, start
        time.sleep(0.5)
        start = server.get(f"/v1/campaign_start/{start['id']}", headers=_headers(author)).json()["campaign_start"]
    assert start["state"] == "done", start.get("error") or start

    playthrough = start["campaign_id"]
    copies = server.get("/v1/person", params={"campaign_id": playthrough}, headers=_headers(author)).json()["persons"]
    copy = next(one for one in copies if one["name"] == "Brann")
    sheet = server.get("/v1/person_trait", params={"person_id": copy["id"]}, headers=_headers(author)).json()["person_traits"]
    by_trait = {row["trait_id"]: row for row in sheet}
    assert by_trait[strength["id"]]["value"] == 16, "the system trait, shared"
    copied_oath = [row for row in sheet if row["trait_id"] not in (strength["id"], oath["id"])]
    assert len(copied_oath) == 1, sheet
    trait = server.get(f"/v1/trait/{copied_oath[0]['trait_id']}", headers=_headers(author)).json()["trait"]
    assert (trait["name"], trait["campaign_id"]) == ("Tavern Oath", playthrough), "the scenario's trait, copied"
