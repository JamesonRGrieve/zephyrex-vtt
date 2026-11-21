# SPDX-License-Identifier: AGPL-3.0-or-later
"""The game system catalog against a real server: the systems the operator named are seeded once by
slug, the game_systems ability lists them (and filters by the wiki's setting), and a system made
without a slug gets one from its name. The seeded catalog is the SYSTEM user's, so anyone signed in
reads it over REST too."""

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_systems.EXT_RPGSystems import RPGSystemsExtension
from zephyrex.testing.factories import create_user

from vtt_app import create

SEEDED = [one["slug"] for one in json.loads((Path(__file__).parent / "game-systems.json").read_text())["systems"]]


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    yield TestClient(create())


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _systems(user: Any, setting_id: str | None = None) -> list[dict[str, Any]]:
    return asyncio.run(RPGSystemsExtension.game_systems(str(user.id), setting_id))


def test_the_named_systems_are_seeded_once_each(server: TestClient) -> None:
    listed = _systems(create_user(server))
    slugs = [one["slug"] for one in listed]
    for slug in SEEDED:
        assert slugs.count(slug) == 1, slug
    heresy = next(one for one in listed if one["slug"] == "redacted")
    assert heresy["name"] == "[redacted]" and heresy["setting_id"] is None


def test_a_system_made_without_a_slug_gets_one_from_its_name(server: TestClient) -> None:
    gm = create_user(server)
    response = server.post("/v1/game_system", json={"game_system": {"name": "Gloom & Grit 3e"}}, headers=_headers(gm))
    assert response.status_code == 201, response.text
    assert response.json()["game_system"]["slug"] == "gloom-grit-3e"


def test_systems_filter_by_the_wikis_setting(server: TestClient) -> None:
    gm = create_user(server)
    setting = "11111111-2222-4333-8444-555555555555"
    made = server.post(
        "/v1/game_system",
        json={"game_system": {"name": "Hollow Stars", "setting_id": setting}},
        headers=_headers(gm),
    )
    assert made.status_code == 201, made.text
    assert [one["slug"] for one in _systems(gm, setting)] == ["hollow-stars"]


def test_the_catalog_is_readable_over_rest(server: TestClient) -> None:
    reader = create_user(server)
    response = server.get("/v1/game_system", params={"slug": "redacted"}, headers=_headers(reader))
    assert response.status_code == 200, response.text
    assert [one["slug"] for one in response.json()["game_systems"]] == ["redacted"]
