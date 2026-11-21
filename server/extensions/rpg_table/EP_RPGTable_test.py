# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_table against a real server: a campaign's GM hosts a table (a framework conversation), players
added to it seat their own characters, the host seats NPCs, whispers are read only by their two
seats' players and the host, lines are spoken only for a seat the speaker plays, and the AI GM speaks
for an NPC through the ``say`` ability."""

import asyncio
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_table.EXT_RPGTable import RPGTableExtension
from zephyrex.lib.Environment import env
from zephyrex.testing.factories import add_user_to_team, create_team, create_user, if_match_of

from vtt_app import create


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    yield TestClient(create())


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _post(server: TestClient, user: Any, resource: str, **fields: Any) -> Any:
    return server.post(f"/v1/{resource}", json={resource: fields}, headers=_headers(user))


def _made(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = _post(server, user, resource, **fields)
    assert response.status_code == 201, response.text
    made: dict[str, Any] = response.json()[resource]
    return made


@pytest.fixture(scope="module")
def table(server: TestClient) -> dict[str, Any]:
    """A GM's campaign and table with two players added (a participant must be someone the host can
    see, so they share a team), each player's character, an NPC, and a stranger who shares nothing."""
    host, ada_player, bram_player, stranger = (create_user(server) for _ in range(4))
    team = create_team(server, host.id, name=f"Table {uuid.uuid4().hex[:8]}")
    for player in (ada_player, bram_player):
        add_user_to_team(server, player.id, team.id, env("USER_ROLE_ID"))
    campaign = _made(server, host, "campaign", name="The Salt Road", user_id=host.id)
    people = {
        name: _made(server, host, "person", name=name, campaign_id=campaign["id"], user_id=owner)
        for name, owner in (("Ada", ada_player.id), ("Bram", bram_player.id), ("Mira", None))
    }
    made = _made(server, host, "table", name="Session 1", campaign_id=campaign["id"])
    for player in (ada_player, bram_player):
        added = server.post(
            f"/v1/conversation/{made['conversation_id']}/participants",
            json={"user_id": player.id},
            headers=_headers(host),
        )
        assert added.status_code == 200, added.text
    return {
        "host": host,
        "ada": ada_player,
        "bram": bram_player,
        "stranger": stranger,
        "campaign": campaign,
        "people": people,
        "table": made,
        "conversation": made["conversation_id"],
    }


def _seat(server: TestClient, user: Any, t: dict[str, Any], person: str, **extra: Any) -> Any:
    return _post(
        server, user, "table_seat", conversation_id=t["conversation"], person_id=t["people"][person]["id"], **extra
    )


def _seats(server: TestClient, user: Any, t: dict[str, Any]) -> Any:
    return server.get("/v1/table_seat", params={"conversation_id": t["conversation"]}, headers=_headers(user))


def test_only_the_campaigns_gm_hosts_a_table(server: TestClient, table: dict[str, Any]) -> None:
    refused = _post(server, table["ada"], "table", name="Mine now", campaign_id=table["campaign"]["id"])
    assert refused.status_code == 404, refused.text
    assert table["table"]["conversation_id"]


def test_the_gm_owns_the_table_they_made(server: TestClient, table: dict[str, Any]) -> None:
    """The table is the GM's own record: its owner is them, and they rename and delete it."""
    host = table["host"]
    made = _made(server, host, "table", name="Spare table", campaign_id=table["campaign"]["id"])
    assert made["created_by_user_id"] == host.id
    renamed = server.put(
        f"/v1/table/{made['id']}",
        json={"table": {"name": "Session 2"}},
        headers={**_headers(host), **if_match_of(made)},
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["table"]["name"] == "Session 2"
    gone = server.delete(
        f"/v1/table/{made['id']}", headers={**_headers(host), **if_match_of(renamed.json()["table"])}
    )
    assert gone.status_code == 204, gone.text


def test_seats(server: TestClient, table: dict[str, Any]) -> None:
    host, ada, bram, stranger = table["host"], table["ada"], table["bram"], table["stranger"]
    # Only the host seats an NPC, and a player can't seat someone else's character.
    assert _seat(server, ada, table, "Mira", npc=True).status_code == 403
    assert _seat(server, ada, table, "Bram").status_code == 404
    assert _seat(server, stranger, table, "Ada").status_code == 404

    # The server sets who plays it and how it shows, whatever the request says.
    seated = _seat(server, ada, table, "Ada", controller_id=host.id, name="Someone else")
    assert seated.status_code == 201, seated.text
    seat = seated.json()["table_seat"]
    assert (seat["controller_id"], seat["name"]) == (ada.id, "Ada")
    npc = _seat(server, host, table, "Mira", npc=True)
    assert npc.status_code == 201, npc.text
    assert npc.json()["table_seat"]["controller_id"] is None
    assert _seat(server, bram, table, "Bram").status_code == 201
    # One seat per character per table.
    assert _seat(server, ada, table, "Ada").status_code == 422

    # Every member reads every seat; a stranger reads none.
    for member in (host, ada, bram):
        listed = _seats(server, member, table)
        assert listed.status_code == 200, listed.text
        assert {row["name"] for row in listed.json()["table_seats"]} == {"Ada", "Bram", "Mira"}
    assert _seats(server, stranger, table).json()["table_seats"] == []


def _seat_of(server: TestClient, t: dict[str, Any], name: str) -> dict[str, Any]:
    rows = _seats(server, t["host"], t).json()["table_seats"]
    return next(row for row in rows if row["name"] == name)


def test_whispers_are_read_by_their_two_players_and_the_host(server: TestClient, table: dict[str, Any]) -> None:
    host, ada, bram = table["host"], table["ada"], table["bram"]
    ada_seat, bram_seat, mira = (_seat_of(server, table, name) for name in ("Ada", "Bram", "Mira"))
    started = _post(
        server, ada, "table_whisper", table_conversation_id=table["conversation"],
        from_seat_id=ada_seat["id"], to_seat_id=mira["id"],
    )
    assert started.status_code == 201, started.text
    whisper = started.json()["table_whisper"]
    # Ada can't whisper from Bram's seat.
    assert _post(
        server, ada, "table_whisper", table_conversation_id=table["conversation"],
        from_seat_id=bram_seat["id"], to_seat_id=mira["id"],
    ).status_code == 403

    said = _made(
        server, ada, "table_line", conversation_id=whisper["conversation_id"], seat_id=ada_seat["id"], text="Psst"
    )
    answered = _made(
        server, host, "table_line", conversation_id=whisper["conversation_id"], seat_id=mira["id"], text="Not here"
    )
    # Bram neither reads the whisper nor speaks in it.
    assert _post(
        server, bram, "table_line", conversation_id=whisper["conversation_id"], seat_id=bram_seat["id"], text="Hi"
    ).status_code == 404
    for reader, sees in ((ada, True), (host, True), (bram, False)):
        lines = server.get(
            "/v1/table_line", params={"conversation_id": whisper["conversation_id"]}, headers=_headers(reader)
        ).json()["table_lines"]
        assert {line["id"] for line in lines} == ({said["id"], answered["id"]} if sees else set())


def test_lines_are_spoken_for_a_seat_the_speaker_plays(server: TestClient, table: dict[str, Any]) -> None:
    host, ada = table["host"], table["ada"]
    ada_seat, bram_seat, mira = (_seat_of(server, table, name) for name in ("Ada", "Bram", "Mira"))
    line = _made(server, ada, "table_line", conversation_id=table["conversation"], seat_id=ada_seat["id"], text="Hello")
    assert line["channel"] == "in_character"
    assert _post(
        server, ada, "table_line", conversation_id=table["conversation"], seat_id=bram_seat["id"], text="I'm Bram"
    ).status_code == 403
    assert _post(
        server, ada, "table_line", conversation_id=table["conversation"], seat_id=mira["id"], text="I'm Mira"
    ).status_code == 403
    ooc = _made(
        server, host, "table_line", conversation_id=table["conversation"], seat_id=mira["id"], text="Back in 5",
        channel="ooc",
    )
    assert ooc["channel"] == "ooc"


def test_the_ai_gm_speaks_for_an_npc_and_reads_the_seats(table: dict[str, Any], server: TestClient) -> None:
    mira = _seat_of(server, table, "Mira")
    host = str(table["host"].id)
    line = asyncio.run(RPGTableExtension.say(host, mira["id"], "Welcome, travellers."))
    assert (line["seat_id"], line["text"]) == (mira["id"], "Welcome, travellers.")
    seats = asyncio.run(RPGTableExtension.table_seats(host, table["conversation"]))
    assert {seat["name"] for seat in seats} == {"Ada", "Bram", "Mira"}
    whispers = asyncio.run(RPGTableExtension.seat_whispers(host, mira["id"]))
    assert len(whispers) == 1 and [line["text"] for line in whispers[0]["lines"]] == ["Psst", "Not here"]


def test_the_seats_player_or_the_host_unseats_it(server: TestClient, table: dict[str, Any]) -> None:
    host, ada, bram = table["host"], table["ada"], table["bram"]
    mira, bram_seat = _seat_of(server, table, "Mira"), _seat_of(server, table, "Bram")
    assert server.delete(
        f"/v1/table_seat/{mira['id']}", headers={**_headers(ada), **if_match_of(mira)}
    ).status_code == 403
    left = server.delete(f"/v1/table_seat/{bram_seat['id']}", headers={**_headers(bram), **if_match_of(bram_seat)})
    assert left.status_code == 204, left.text
    removed = server.delete(f"/v1/table_seat/{mira['id']}", headers={**_headers(host), **if_match_of(mira)})
    assert removed.status_code == 204, removed.text
    assert {row["name"] for row in _seats(server, host, table).json()["table_seats"]} == {"Ada"}
