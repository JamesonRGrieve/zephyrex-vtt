# SPDX-License-Identifier: AGPL-3.0-or-later
"""The character fields the VTT relies on, against a real server: genealogy's person carries the fields
the wiki's rpg_core adds (``@extension_model(PersonModel)``, its migration adding the columns), and
they round-trip through the API. They were once silently dropped (server-framework skipped
ModelMeta-only extensions), so a character's campaign and player were lost, and the dice check could
not tell who may roll. Kept in rpg_systems (moved from rpg_state when it retired) as the VTT's guard
on that contract."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.genealogy.BLL_Genealogy import PersonModel
from zephyrex.testing.factories import create_user

from vtt_app import create

CHARACTER_FIELDS = ("kind", "campaign_id", "user_id", "location_id")


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    yield TestClient(create())


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def test_the_person_model_carries_the_character_fields(server: TestClient) -> None:
    del server  # the app is up, so every extension's injections have been applied
    assert set(CHARACTER_FIELDS) <= set(PersonModel.model_fields)


def test_a_characters_fields_round_trip(server: TestClient) -> None:
    gm, player = create_user(server), create_user(server)
    body = {"campaign": {"name": "Round Trip", "user_id": gm.id}}
    campaign = server.post("/v1/campaign", json=body, headers=_headers(gm))
    assert campaign.status_code == 201, campaign.text
    campaign_id = campaign.json()["campaign"]["id"]
    fields = {"name": "Ada", "kind": "pc", "campaign_id": campaign_id, "user_id": player.id}
    created = server.post("/v1/person", json={"person": fields}, headers=_headers(gm))
    assert created.status_code == 201, created.text
    person = created.json()["person"]
    read = server.get(f"/v1/person/{person['id']}", headers=_headers(gm))
    assert read.status_code == 200, read.text
    for record in (person, read.json()["person"]):
        assert {key: record.get(key) for key in ("kind", "campaign_id", "user_id")} == {
            "kind": "pc",
            "campaign_id": campaign_id,
            "user_id": player.id,
        }
