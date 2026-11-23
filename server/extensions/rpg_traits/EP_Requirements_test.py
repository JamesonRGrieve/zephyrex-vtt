# SPDX-License-Identifier: AGPL-3.0-or-later
"""check_requirements against a real server: a plot hook's character checks decided by the traits the
campaign's player characters hold, beside the wiki's own hook requirements, for the GM and the
campaign's players only."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_traits.EXT_RPGTraits import RPGTraitsExtension
from zephyrex.testing.factories import create_user

from vtt_app import create


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    yield TestClient(create())


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _create(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = server.post(f"/v1/{resource}", json={resource: fields}, headers=_headers(user))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()[resource]
    return created


@pytest.fixture(scope="module")
def campaign(server: TestClient) -> dict[str, Any]:
    """Two player characters: Ada (a seafaring tinker with Repair) and Brin (hill-born). An
    NPC with Dowsing, who isn't in the party. Hooks needing each of those, one done."""
    gm, ada_player, brin_player = create_user(server), create_user(server), create_user(server)
    vaults = _create(server, gm, "campaign", name="The Vaults", user_id=gm.id)
    on = {"campaign_id": vaults["id"]}
    ada = _create(server, gm, "person", name="Ada", kind="pc", user_id=ada_player.id, **on)
    brin = _create(server, gm, "person", name="Brin", kind="pc", user_id=brin_player.id, **on)
    seer = _create(server, gm, "person", name="Seer", kind="npc", **on)
    tech_use = _create(server, gm, "trait", name="Repair", kind="skill")
    dowsing = _create(server, gm, "trait", name="Dowsing", kind="skill")
    seafarer = _create(server, gm, "trait", name="Seafarer", kind="homeland")
    hive = _create(server, gm, "trait", name="Hill Born", kind="homeland")
    for person, trait in ((ada, tech_use), (ada, seafarer), (brin, hive), (seer, dowsing)):
        _create(server, gm, "person_trait", person_id=person["id"], trait_id=trait["id"])
    approach = _create(server, gm, "hook", name="Approach", resolved_at="2026-11-20T20:00:00", **on)
    hooks = {
        "approach": approach,
        "machine": _create(server, gm, "hook", name="Wake the machine", requires={"char": {"skill": "repair"}}, **on),
        "spring": _create(server, gm, "hook", name="Find the spring", requires={"char": {"skill": "dowsing"}}, **on),
        "sea": _create(
            server, gm, "hook", name="All sea-born", requires={"char": {"homeland": "seafarer"}, "who": "all"}, **on
        ),
        "after": _create(
            server,
            gm,
            "hook",
            name="After the approach",
            requires={"all": [approach["id"], {"char": {"homeland": ["seafarer", "hill-born"]}}]},
            **on,
        ),
    }
    return {"gm": gm, "player": ada_player, "campaign": vaults, "hooks": hooks, "tech_use": tech_use}


def _check(user: Any, campaign: dict[str, Any], hook: str) -> dict[str, Any]:
    return asyncio.run(
        RPGTraitsExtension.check_requirements(str(user.id), campaign["campaign"]["id"], campaign["hooks"][hook]["id"])
    )


def test_a_trait_slug_comes_from_its_name(campaign: dict[str, Any]) -> None:
    assert campaign["tech_use"]["slug"] == "repair"


@pytest.mark.parametrize(
    ("hook", "state"),
    [
        ("approach", "resolved"),
        ("machine", "available"),
        ("spring", "blocked"),
        ("sea", "blocked"),
        ("after", "available"),
    ],
)
def test_the_partys_traits_decide_the_checks(campaign: dict[str, Any], hook: str, state: str) -> None:
    assert _check(campaign["gm"], campaign, hook)["state"] == state


def test_a_blocked_hook_says_which_check_failed(campaign: dict[str, Any]) -> None:
    got = _check(campaign["player"], campaign, "spring")
    assert got["unmet_checks"] == [{"char": {"skill": "dowsing"}}]


def test_only_the_gm_and_the_campaigns_players_may_ask(server: TestClient, campaign: dict[str, Any]) -> None:
    stranger = create_user(server)
    with pytest.raises(HTTPException) as refused:
        _check(stranger, campaign, "machine")
    assert refused.value.status_code == 404
