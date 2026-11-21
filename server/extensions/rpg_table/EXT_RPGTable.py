# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_table extension: multiplayer tables (BLL_RPGTable), and the abilities the AI GM uses at one
(rpg-ai's A34): read the seats, read an NPC's whispers, and speak as an NPC. The AI GM runs as the
table's host, so the same rules hold for it as for a human host."""

from typing import Any, ClassVar, Optional

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension, ability
from zephyrex.extensions.rpg_table.BLL_RPGTable import (
    TableLineManager,
    TableSeatManager,
    TableWhisperManager,
)
from zephyrex.lib.Dependencies import Dependencies, EXT_Dependency


def _row(record: Any) -> dict[str, Any]:
    dumped: dict[str, Any] = record.model_dump() if hasattr(record, "model_dump") else dict(record)
    return dumped


class RPGTableExtension(AbstractStaticExtension):
    name: ClassVar[str] = "rpg_table"
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = "Multiplayer tables: characters seated in a conversation, whispers and lines"
    dependencies: ClassVar[Dependencies] = Dependencies(
        [
            EXT_Dependency(
                name="conversations",
                friendly_name="Conversations",
                optional=False,
                reason="A table and each whisper are framework conversations, with their live feeds",
            ),
            EXT_Dependency(
                name="rpg_core",
                friendly_name="Rpg Core",
                optional=False,
                reason="A table belongs to a campaign, and its seats are the campaign's characters",
            ),
            EXT_Dependency(
                name="genealogy",
                friendly_name="Genealogy",
                optional=False,
                reason="A seat holds one of genealogy's persons",
            ),
        ]
    )

    @classmethod
    @ability("table_seats")
    async def table_seats(cls, requester_id: str, table_conversation_id: str) -> list[dict[str, Any]]:
        """The characters seated at a table: each seat's name, character, and player (none for an
        NPC the GM voices)."""
        seats = cls.as_requester(TableSeatManager, requester_id)
        return [_row(seat) for seat in seats.list(conversation_id=table_conversation_id)]

    @classmethod
    @ability("seat_whispers")
    async def seat_whispers(cls, requester_id: str, seat_id: str) -> list[dict[str, Any]]:
        """A seat's whispers that the requester can read, each with its lines in order."""
        whispers = cls.as_requester(TableWhisperManager, requester_id)
        lines = cls.as_requester(TableLineManager, requester_id)
        found = [*whispers.list(seat_a_id=seat_id), *whispers.list(seat_b_id=seat_id)]
        return [
            {**_row(whisper), "lines": [_row(line) for line in lines.list(conversation_id=whisper.conversation_id)]}
            for whisper in found
        ]

    @classmethod
    @ability("say")
    async def say(
        cls,
        requester_id: str,
        seat_id: str,
        text: str,
        conversation_id: Optional[str] = None,
        channel: str = "in_character",
    ) -> dict[str, Any]:
        """Say a line as a seat: the table's host speaks for its NPCs, a player for their own seat.
        In the table's conversation unless ``conversation_id`` names one of the seat's whispers."""
        seat = cls.as_requester(TableSeatManager, requester_id).get(id=seat_id)
        lines = cls.as_requester(TableLineManager, requester_id)
        line = lines.create(
            conversation_id=conversation_id or seat.conversation_id, seat_id=seat_id, text=text, channel=channel
        )
        return _row(line)
