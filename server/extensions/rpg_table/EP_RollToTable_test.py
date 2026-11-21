# SPDX-License-Identifier: AGPL-3.0-or-later
"""roll_to_table: the VTT rolls for a seated character (a test or a formula, on the server, under
rpg_dice's access rule) and posts the result as that seat's out-of-character line, which is how a
decided roll from rpg-ai reaches the table."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_table.EXT_RPGTable import RPGTableExtension
from zephyrex.testing.factories import create_user

from vtt_app import create


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    with TestClient(create()) as client:
        yield client


def _made(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = server.post(f"/v1/{resource}", json={resource: fields}, headers={"Authorization": f"Bearer {user.jwt}"})
    assert response.status_code == 201, response.text
    made: dict[str, Any] = response.json()[resource]
    return made


def test_a_roll_for_a_seated_character_is_posted_as_their_line(server: TestClient) -> None:
    host = create_user(server)
    campaign = _made(server, host, "campaign", name="[redacted]", user_id=host.id)
    vell = _made(server, host, "person", name="Captain Vell", campaign_id=campaign["id"])
    stowaway = _made(server, host, "person", name="Stowaway", campaign_id=campaign["id"])
    table = _made(server, host, "table", name="Session 1", campaign_id=campaign["id"])
    seat = _made(server, host, "table_seat", conversation_id=table["conversation_id"], person_id=vell["id"], npc=True)

    posted = asyncio.run(
        RPGTableExtension.roll_to_table(str(host.id), table["conversation_id"], vell["id"], formula="2d6")
    )
    assert 2 <= posted["result"]["total"] <= 12
    line = posted["line"]
    assert line["seat_id"] == seat["id"] and line["channel"] == "ooc"
    assert line["text"] == f"Rolled 2d6: {posted['result']['total']}"

    with pytest.raises(HTTPException) as unseated:
        asyncio.run(RPGTableExtension.roll_to_table(str(host.id), table["conversation_id"], stowaway["id"], formula="1d6"))
    assert unseated.value.status_code == 422
    with pytest.raises(HTTPException) as both:
        asyncio.run(
            RPGTableExtension.roll_to_table(
                str(host.id), table["conversation_id"], vell["id"], name="[redacted]", formula="1d6"
            )
        )
    assert both.value.status_code == 422
