# SPDX-License-Identifier: AGPL-3.0-or-later
"""spells_for_campaign (Zephyrex RPG, 2026-11-26, for the operator's "x casts y (spell effects) on
z"): the spells of the campaign's own game system, never a same-named trait of another system; a
campaign's own spell over its system's; for its GM, its players and anyone for a shared scenario,
never a stranger."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_traits.EXT_RPGTraits import RPGTraitsExtension
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


def _spells(requester_id: str, campaign_id: str) -> list[dict[str, Any]]:
    got = asyncio.run(RPGTraitsExtension.spells_for_campaign(str(requester_id), campaign_id))
    return list(got["spells"])


def test_a_campaigns_spells_are_its_systems_for_its_table_only(server: TestClient) -> None:
    gm, player, stranger = create_user(server), create_user(server), create_user(server)
    fifth = _create(server, gm, "game_system", name="Spell Test Fifth")
    grim = _create(server, gm, "game_system", name="Spell Test Grim")
    campaign = _create(server, gm, "campaign", name="The Ford", game_system_id=fifth["id"], user_id=gm.id)
    _create(server, gm, "person", name="Ada", kind="pc", campaign_id=campaign["id"], user_id=player.id)
    flame = "<p>A flame-like radiance descends: Dexterity save or 1d8 radiant damage.</p>"
    _create(server, gm, "trait", name="Sacred Flame", kind="spell", game_system_id=fifth["id"], description=flame)
    _create(server, gm, "trait", name="Vicious Mockery", kind="spell", game_system_id=fifth["id"], description="1d4 psychic; disadvantage")
    _create(server, gm, "trait", name="Stealth", kind="skill", game_system_id=fifth["id"])
    _create(server, gm, "trait", name="Sacred Flame", kind="spell", game_system_id=grim["id"], description="A 40k talent's text")
    other = _create(server, gm, "campaign", name="Elsewhere", game_system_id=fifth["id"], user_id=gm.id)
    _create(server, gm, "trait", name="Mockery", kind="spell", game_system_id=fifth["id"], campaign_id=other["id"])

    got = _spells(gm.id, campaign["id"])
    assert [(one["name"], one["description"]) for one in got] == [
        ("Sacred Flame", flame),
        ("Vicious Mockery", "1d4 psychic; disadvantage"),
    ], "its own system's spells only, not another campaign's own"
    assert got[0]["slug"] == "sacred-flame"
    assert _spells(player.id, campaign["id"]) == got, "a player reads them too"
    with pytest.raises(HTTPException) as refused:
        _spells(stranger.id, campaign["id"])
    assert refused.value.status_code == 404

    # A campaign's own spell stands in for its system's of the same slug.
    _create(server, gm, "trait", name="Sacred Flame", kind="spell", game_system_id=fifth["id"], campaign_id=campaign["id"], description="House rule: 1d10")
    assert [one["description"] for one in _spells(gm.id, campaign["id"]) if one["name"] == "Sacred Flame"] == ["House rule: 1d10"]

    # A shared scenario (the instance's copy) is anyone's to read, as its start screen is.
    from zephyrex.extensions.rpg_core.BLL_RPGCore import CampaignManager  # type: ignore[import-not-found]

    registry = server.app.state.model_registry  # type: ignore[attr-defined]
    rows = CampaignManager(requester_id=env("ROOT_ID"), model_registry=registry)
    session = registry.DB.session()
    try:
        table = rows.DB.__table__
        session.execute(table.update().where(table.c.id == campaign["id"]).values(created_by_user_id=str(env("TEMPLATE_ID"))))
        session.commit()
    finally:
        session.close()
    from zephyrex.logic.AbstractLogicManager.manager import _cache_sync_run, get_entity_cache

    cache = get_entity_cache()
    if cache is not None:
        _cache_sync_run(cache.invalidate_table("campaigns"))
    assert [one["name"] for one in _spells(stranger.id, campaign["id"])] == ["Sacred Flame", "Vicious Mockery"]
