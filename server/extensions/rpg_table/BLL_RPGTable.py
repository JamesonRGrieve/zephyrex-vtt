# SPDX-License-Identifier: AGPL-3.0-or-later
"""rpg_table: multiplayer tables, built on server-framework conversations (the operator's call,
2026-11-20: tables are the VTT's, and "the characters are the conversation members, not the users").

- ``/v1/table``: a campaign's table. Its GM makes it, which makes the table's conversation, owned by
  them as host. The host adds each player as a conversation participant (``/v1/conversation/{id}/
  participants``), which lets them read and post there.
- ``/v1/table_seat``: a character's seat. A player seats their own character (one of the campaign's
  people whose ``user_id`` is theirs), and the host seats NPCs (the campaign's people with no
  player), which no one controls. A seat keeps the character's name as seated. One seat per
  character per table; the seat's player or the host unseats it.
- ``/v1/table_whisper``: a whisper is a conversation of its own between two seats, owned by the host
  (who sees every whisper at their table) with the two seats' players as participants. One per
  pair of seats.
- ``/v1/table_line``: what a seat says, in the table's conversation or in one of its whispers, in
  character or out of character. A player speaks for their own seat; the host for an NPC's.

Reading follows the conversation (``permission_references``), so a whisper is read only by its two
players and the host. Every write is announced on its own conversation's live feed, so the table's
feed never carries a whisper's id; the client merges the feeds it can read into one.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal, Optional, Type

from fastapi import HTTPException
from pydantic import Field
from zephyrex.extensions.conversations.BLL_Conversations import (  # type: ignore[attr-defined]
    ConversationManager,
    ConversationModel,
    announce,
)
from zephyrex.extensions.genealogy.BLL_Genealogy import PersonManager, PersonModel
from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignManager, CampaignModel  # type: ignore[import-not-found]
from zephyrex.lib.Environment import env
from zephyrex.logic.AbstractLogicManager import (
    AbstractBLLManager,
    ApplicationModel,
    ModelMeta,
    NameMixinModel,
    StringSearchModel,
    UpdateMixinModel,
)
from zephyrex.logic.AbstractLogicManager.ownership import server_side
from zephyrex.pydantic2.fastapi import RouterMixin
from zephyrex.pydantic2.registry import BaseModel  # type: ignore[attr-defined]

MAX_LINE = 4000
MAX_TABLE_NAME = 200
Channel = Literal["in_character", "ooc"]

SEAT_CREATED, SEAT_DELETED = "table_seat.created", "table_seat.deleted"
WHISPER_CREATED = "table_whisper.created"
LINE_CREATED = "table_line.created"


def _refuse(status: int, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"message": message})


def _missing(model: str) -> HTTPException:
    return _refuse(404, f"Request searched {model} and could not find the required record.")


class TableModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    CampaignModel.Reference.Optional,
    ConversationModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["TableManager"]] = None
    table_comment: ClassVar[str] = "A campaign's multiplayer table: its conversation, hosted by the GM"
    # Reading follows the conversation; making one needs edit access to its campaign (the GM's).
    permission_references: ClassVar[list[str]] = ["conversation"]
    create_permission_reference: ClassVar[str] = "campaign"

    class Create(BaseModel, CampaignModel.Reference.ID):
        name: str = Field(..., min_length=1, max_length=MAX_TABLE_NAME)
        # Set by the server (TableManager.create makes the conversation); a client's value is ignored.
        conversation_id: Optional[str] = Field(None, description="Set by the server")

    class Update(BaseModel):
        name: Optional[str] = Field(None, min_length=1, max_length=MAX_TABLE_NAME)

    class Search(ApplicationModel.Search, CampaignModel.Reference.ID.Search, ConversationModel.Reference.ID.Search):
        name: Optional[StringSearchModel] = None


class TableSeatModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    ConversationModel.Reference.Optional,
    PersonModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["TableSeatManager"]] = None
    name: Optional[str] = Field(None, description="The character's name, as seated")
    avatar: Optional[str] = Field(None, description="The character's picture, as seated (none yet)")
    controller_id: Optional[str] = Field(None, description="The player who plays it; none for an NPC")
    table_comment: ClassVar[str] = "A character's seat at a table (the table's conversation)"
    permission_references: ClassVar[list[str]] = ["conversation"]

    class Create(BaseModel, ConversationModel.Reference.ID, PersonModel.Reference.ID):
        npc: bool = Field(False, description="Seat an NPC, which no one controls (the host only)")
        # Set by the server from the character and the requester; a client's values are ignored.
        name: Optional[str] = Field(None, description="Set by the server")
        avatar: Optional[str] = Field(None, description="Set by the server")
        controller_id: Optional[str] = Field(None, description="Set by the server")

    class Update(BaseModel):
        pass

    class Search(ApplicationModel.Search, ConversationModel.Reference.ID.Search, PersonModel.Reference.ID.Search):
        controller_id: Optional[StringSearchModel] = None


class TableWhisperModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    ConversationModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["TableWhisperManager"]] = None
    table_conversation_id: Optional[str] = Field(None, description="The table's conversation")
    seat_a_id: Optional[str] = Field(None, description="One seat")
    seat_b_id: Optional[str] = Field(None, description="The other seat")
    table_comment: ClassVar[str] = "A whisper between two seats: a conversation of its own, the host's"
    permission_references: ClassVar[list[str]] = ["conversation"]

    class Create(BaseModel):
        table_conversation_id: str = Field(..., description="The table")
        from_seat_id: Optional[str] = Field(None, description="The requester's own seat (the host: any NPC's)")
        to_seat_id: Optional[str] = Field(None, description="The other seat at the same table")
        # Set by the server (the whisper's own conversation and its two seats); a client's are ignored.
        conversation_id: Optional[str] = Field(None, description="Set by the server")
        seat_a_id: Optional[str] = Field(None, description="Set by the server")
        seat_b_id: Optional[str] = Field(None, description="Set by the server")

    class Update(BaseModel):
        pass

    class Search(ApplicationModel.Search, ConversationModel.Reference.ID.Search):
        table_conversation_id: Optional[StringSearchModel] = None
        seat_a_id: Optional[StringSearchModel] = None
        seat_b_id: Optional[StringSearchModel] = None


class TableLineModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    ConversationModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["TableLineManager"]] = None
    seat_id: Optional[str] = Field(None, description="The seat that says it")
    text: Optional[str] = Field(None)
    channel: Optional[Channel] = Field("in_character")
    table_comment: ClassVar[str] = "What a seat says, at the table or in a whisper"
    permission_references: ClassVar[list[str]] = ["conversation"]

    class Create(BaseModel, ConversationModel.Reference.ID):
        seat_id: str = Field(...)
        text: str = Field(..., min_length=1, max_length=MAX_LINE)
        channel: Channel = "in_character"

    class Update(BaseModel):
        pass

    class Search(ApplicationModel.Search, ConversationModel.Reference.ID.Search):
        seat_id: Optional[StringSearchModel] = None
        channel: Optional[StringSearchModel] = None


class _Tables:
    """The reads every table rule needs, as the requester and (once a rule has passed) as the system."""

    requester: Any
    model_registry: Any

    def _as(self, manager: type[Any], requester_id: str) -> Any:
        return manager(requester_id=requester_id, model_registry=self.model_registry)

    def _mine(self, manager: type[Any]) -> Any:
        return self._as(manager, str(self.requester.id))

    def _root(self, manager: type[Any]) -> Any:
        return self._as(manager, env("ROOT_ID"))

    def _root_get(self, manager: type[Any], record_id: str) -> Any | None:
        try:
            return self._root(manager).get(id=record_id)
        except HTTPException:
            return None

    def _readable_conversation(self, conversation_id: str) -> Any:
        """The conversation, if the requester can read it; the same 404 as a missing one otherwise."""
        try:
            return self._mine(ConversationManager).get(id=conversation_id)
        except HTTPException as error:
            raise _missing("ConversationModel") from error

    def _table_of(self, conversation_id: str) -> Any:
        tables = self._root(TableManager).list(conversation_id=conversation_id)
        if not tables:
            raise _missing("TableModel")
        return tables[0]

    def _host_of(self, table: Any) -> str:
        campaign = self._root_get(CampaignManager, table.campaign_id)
        return "" if campaign is None else str(campaign.user_id)

    def _speaks_for(self, seat: Any, host: str) -> bool:
        """Whether the requester may act for this seat: their own, or (the host) an NPC's."""
        requester = str(self.requester.id)
        return seat.controller_id == requester or (seat.controller_id is None and requester == host)


class TableManager(_Tables, AbstractBLLManager, RouterMixin):
    _model = TableModel

    def create(self, **kwargs: Any) -> Any:
        """A table for a campaign, by its GM, with its conversation hosted by them."""
        if kwargs.get("entities") is not None:
            raise _refuse(422, "Make one table at a time")
        campaign = self._root_get(CampaignManager, kwargs["campaign_id"])
        if campaign is None or str(campaign.user_id) != str(self.requester.id):
            # The same answer as a campaign that isn't there, for anyone but its GM.
            raise _missing("CampaignModel")
        conversation = self._mine(ConversationManager).create(name=kwargs["name"], is_group_chat=True)
        # As the GM, so the table is theirs (its owner fields name them, and they edit or delete it).
        return super().create(name=kwargs["name"], campaign_id=campaign.id, conversation_id=conversation.id)


class TableSeatManager(_Tables, AbstractBLLManager, RouterMixin):
    _model = TableSeatModel

    def create(self, **kwargs: Any) -> Any:
        """A seat for the requester's own character, or (the host) an NPC, at a table they can read."""
        if kwargs.get("entities") is not None:
            raise _refuse(422, "Seat one character at a time")
        conversation = self._readable_conversation(kwargs["conversation_id"])
        table = self._table_of(conversation.id)
        host, requester = self._host_of(table), str(self.requester.id)
        person = self._root_get(PersonManager, kwargs["person_id"])
        npc = bool(kwargs.get("npc", False))
        if person is None or getattr(person, "campaign_id", None) != table.campaign_id:
            raise _missing("PersonModel")
        player = getattr(person, "user_id", None)
        if npc:
            if requester != host:
                raise _refuse(403, "Only the table's host seats NPCs")
            if player is not None:
                raise _refuse(422, "A player's character isn't an NPC")
        elif player != requester:
            # Someone else's character reads as missing, as one that doesn't exist.
            raise _missing("PersonModel")
        if self._root(TableSeatManager).list(conversation_id=conversation.id, person_id=person.id):
            raise _refuse(422, "That character already has a seat at this table")
        seat = self._root(TableSeatManager).create_row(
            conversation_id=conversation.id,
            person_id=person.id,
            name=person.name,
            avatar=None,
            controller_id=None if npc else requester,
        )
        announce(conversation.id, SEAT_CREATED, seat.id)
        return seat

    def create_row(self, **fields: Any) -> Any:
        """The seat row itself, once seating is authorized (as the system, so the table's members
        read it through the conversation, whoever seated it)."""
        return super().create(**fields)

    def delete(self, id: str) -> None:
        """The seat's player or the table's host unseats it."""
        seat = self.get(id=id)
        requester = str(self.requester.id)
        if not server_side(requester) and seat.controller_id != requester:
            if self._host_of(self._table_of(seat.conversation_id)) != requester:
                raise _refuse(403, "Only the seat's player or the table's host unseats it")
        self._root(TableSeatManager).delete_row(id)
        announce(seat.conversation_id, SEAT_DELETED, id)

    def delete_row(self, id: str) -> None:
        super().delete(id)


class TableWhisperManager(_Tables, AbstractBLLManager, RouterMixin):
    _model = TableWhisperModel

    def create(self, **kwargs: Any) -> Any:
        """A whisper from the requester's own seat (the host: any NPC's) to another seat at the table:
        a conversation the host owns, with the two seats' players as participants."""
        if kwargs.get("entities") is not None:
            raise _refuse(422, "Start one whisper at a time")
        table_conversation = self._readable_conversation(kwargs["table_conversation_id"])
        table = self._table_of(table_conversation.id)
        host = self._host_of(table)
        seats = self._root(TableSeatManager)
        ours = [seat for seat in seats.list(conversation_id=table_conversation.id)]
        by_id = {seat.id: seat for seat in ours}
        speaker, listener = by_id.get(kwargs.get("from_seat_id") or ""), by_id.get(kwargs.get("to_seat_id") or "")
        if speaker is None or listener is None:
            raise _missing("TableSeatModel")
        if speaker.id == listener.id:
            raise _refuse(422, "A whisper is between two seats")
        if not self._speaks_for(speaker, host):
            raise _refuse(403, "Whisper from your own seat")
        pair = {speaker.id, listener.id}
        for existing in self._root(TableWhisperManager).list(table_conversation_id=table_conversation.id):
            if {existing.seat_a_id, existing.seat_b_id} == pair:
                return existing
        conversation = self._as(ConversationManager, host).create(
            name=f"{speaker.name} and {listener.name}", is_group_chat=True
        )
        hosting = self._as(ConversationManager, host)
        for seat in (speaker, listener):
            if seat.controller_id is not None and seat.controller_id != host:
                hosting.add_participant(conversation_id=conversation.id, user_id=seat.controller_id)
        whisper = self._root(TableWhisperManager).create_row(
            conversation_id=conversation.id,
            table_conversation_id=table_conversation.id,
            seat_a_id=speaker.id,
            seat_b_id=listener.id,
        )
        announce(conversation.id, WHISPER_CREATED, whisper.id)
        return whisper

    def create_row(self, **fields: Any) -> Any:
        return super().create(**fields)


class TableLineManager(_Tables, AbstractBLLManager, RouterMixin):
    _model = TableLineModel

    def create(self, **kwargs: Any) -> Any:
        """A line said by a seat the requester speaks for, at its table or in a whisper it's part of."""
        if kwargs.get("entities") is not None:
            raise _refuse(422, "Say one line at a time")
        conversation = self._readable_conversation(kwargs["conversation_id"])
        seat = self._root_get(TableSeatManager, kwargs["seat_id"])
        if seat is None:
            raise _missing("TableSeatModel")
        whispers = self._root(TableWhisperManager).list(conversation_id=conversation.id)
        if whispers:
            whisper = whispers[0]
            if seat.id not in (whisper.seat_a_id, whisper.seat_b_id):
                raise _refuse(403, "Only the whisper's two seats speak in it")
            table_conversation_id = whisper.table_conversation_id
        else:
            table_conversation_id = conversation.id
            if seat.conversation_id != conversation.id:
                raise _missing("TableSeatModel")
        if not self._speaks_for(seat, self._host_of(self._table_of(table_conversation_id))):
            raise _refuse(403, "Speak for your own seat")
        line = self._root(TableLineManager).create_row(
            conversation_id=conversation.id,
            seat_id=seat.id,
            text=kwargs["text"],
            channel=kwargs.get("channel", "in_character"),
        )
        announce(conversation.id, LINE_CREATED, line.id)
        return line

    def create_row(self, **fields: Any) -> Any:
        return super().create(**fields)


TableModel.Manager = TableManager
TableSeatModel.Manager = TableSeatManager
TableWhisperModel.Manager = TableWhisperManager
TableLineModel.Manager = TableLineManager

ALL_MODELS: list[type] = [TableModel, TableSeatModel, TableWhisperModel, TableLineModel]
