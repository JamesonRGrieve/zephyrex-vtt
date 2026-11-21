# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `test` ability against a real server, under the [redacted] pack: the
seeded characteristic and skill templates, a character's values and ranks, the target each test
reaches, refusals the rules require, and who may ask. The roll is the server's own, so the outcome
is checked for agreeing with the roll and the target, not for a particular result."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_dice.EXT_RPGDice import RPGDiceExtension
from zephyrex.extensions.rpg_systems.EXT_RPGSystems import RPGSystemsExtension
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


def _template(server: TestClient, user: Any, system_id: str, slug: str) -> str:
    response = server.get("/v1/trait", params={"slug": slug, "game_system_id": system_id}, headers=_headers(user))
    assert response.status_code == 200, response.text
    found = response.json()["traits"]
    assert len(found) == 1, found
    return str(found[0]["id"])


@pytest.fixture(scope="module")
def table(server: TestClient) -> dict[str, Any]:
    """An acolyte: WS 40, Int 35, Fel 30; [redacted] Trained (rank 2); [redacted] ([redacted]) Experienced
    (rank 3) and ([redacted]) Known (rank 1); no Deceive or [redacted]."""
    gm, player = create_user(server), create_user(server)
    systems = asyncio.run(RPGSystemsExtension.game_systems(str(gm.id)))
    heresy = next(one for one in systems if one["slug"] == "redacted")
    campaign = _create(server, gm, "campaign", name="[redacted]", user_id=gm.id, game_system_id=heresy["id"])
    acolyte = _create(server, gm, "person", name="Rhia", kind="pc", user_id=player.id, campaign_id=campaign["id"])
    for slug, value in (("[redacted]", 40), ("intelligence", 35), ("fellowship", 30)):
        trait_id = _template(server, gm, heresy["id"], slug)
        _create(server, gm, "person_trait", person_id=acolyte["id"], trait_id=trait_id, value=value)
    tech_use = _template(server, gm, heresy["id"], "[redacted]")
    _create(server, gm, "person_trait", person_id=acolyte["id"], trait_id=tech_use, rank=2)
    lore = _template(server, gm, heresy["id"], "[redacted]")
    for specialisation, rank in (("[redacted]", 3), ("[redacted]", 1)):
        fields = {"person_id": acolyte["id"], "trait_id": lore, "rank": rank, "specialisation": specialisation}
        _create(server, gm, "person_trait", **fields)
    plain = _create(server, gm, "campaign", name="No pack", user_id=gm.id)
    stranger_pc = _create(server, gm, "person", name="Otto", kind="pc", user_id=player.id, campaign_id=plain["id"])
    return {"gm": gm, "player": player, "acolyte": acolyte, "unpacked": stranger_pc}


def _test(user: Any, person: dict[str, Any], name: str, **options: Any) -> dict[str, Any]:
    return asyncio.run(RPGDiceExtension.test(str(user.id), person["id"], name, **options))


def _agrees(result: dict[str, Any]) -> None:
    if result["natural"] is None:
        assert result["success"] == (result["roll"] <= result["target"])
    assert result["degrees"] >= 1


@pytest.mark.parametrize(
    ("name", "options", "target", "rank", "trained"),
    [
        ("[redacted]", {"difficulty": "hard"}, 20, None, True),
        ("[redacted]", {"difficulty": "ordinary"}, 55, 2, True),
        ("deceive", {}, 10, None, False),
        ("[redacted]", {"difficulty": "elementary", "modifiers": [20]}, 105, 2, True),
    ],
)
def test_the_target_follows_the_pack(
    table: dict[str, Any], name: str, options: dict[str, Any], target: int, rank: int | None, trained: bool
) -> None:
    result = _test(table["player"], table["acolyte"], name, **options)
    assert (result["system"], result["target"], result["skill_rank"], result["trained"]) == (
        "redacted",
        target,
        rank,
        trained,
    )
    _agrees(result)


@pytest.mark.parametrize(
    ("name", "options"),
    [
        ("[redacted]", {"specialisation": "[redacted]"}),
        ("[redacted]", {"specialisation": "[redacted]"}),
        ("[redacted]", {}),
        ("[redacted]", {"specialisation": "[redacted]"}),
        ("[redacted]", {"difficulty": "impossible"}),
        ("[redacted]-drill", {}),
    ],
)
def test_what_the_rules_forbid_is_refused(table: dict[str, Any], name: str, options: dict[str, Any]) -> None:
    with pytest.raises(HTTPException) as refused:
        _test(table["gm"], table["acolyte"], name, **options)
    assert refused.value.status_code == 422


def test_a_specialist_skill_tests_the_named_specialisation(table: dict[str, Any]) -> None:
    imperium = _test(table["player"], table["acolyte"], "[redacted]", specialisation=" imperium ")
    assert (imperium["skill_rank"], imperium["target"], imperium["specialisation"]) == (3, 55, "imperium")
    arbites = _test(table["player"], table["acolyte"], "[redacted]", specialisation="[redacted]")
    assert (arbites["skill_rank"], arbites["target"]) == (1, 35)


def test_a_campaign_without_a_pack_says_so(table: dict[str, Any]) -> None:
    with pytest.raises(HTTPException) as refused:
        _test(table["gm"], table["unpacked"], "[redacted]")
    assert refused.value.status_code == 422


def test_only_the_gm_and_the_characters_player_may_test(server: TestClient, table: dict[str, Any]) -> None:
    with pytest.raises(HTTPException) as refused:
        _test(create_user(server), table["acolyte"], "[redacted]")
    assert refused.value.status_code == 404


def test_the_route_answers_like_the_ability(server: TestClient, table: dict[str, Any]) -> None:
    body = {"test": {"person_id": table["acolyte"]["id"], "name": "[redacted]", "difficulty": "routine"}}
    response = server.post("/v1/dice/test", json=body, headers=_headers(table["player"]))
    assert response.status_code == 200, response.text
    assert response.json()["test"]["target"] == 65


def test_a_dice_tray_reads_what_a_test_can_name(server: TestClient, table: dict[str, Any]) -> None:
    body = {"options": {"person_id": table["acolyte"]["id"]}}
    response = server.post("/v1/dice/test-options", json=body, headers=_headers(table["player"]))
    assert response.status_code == 200, response.text
    options = response.json()["options"]
    assert options["system"] == "redacted" and options["default_difficulty"] == "challenging"
    assert {one["slug"] for one in options["characteristics"]} >= {"[redacted]", "fellowship"}
    lore = next(one for one in options["skills"] if one["slug"] == "[redacted]")
    assert lore["untrainable"] is True and lore["characteristic"] == "intelligence"
    assert {"slug": "hellish", "modifier": -60} in options["difficulties"]
    stranger = server.post("/v1/dice/test-options", json=body, headers=_headers(create_user(server)))
    assert stranger.status_code == 404
    common = next(one for one in options["skills"] if one["slug"] == "[redacted]")
    assert common["specialisations"] == ["[redacted]", "[redacted]"]
    assert next(one for one in options["skills"] if one["slug"] == "[redacted]")["specialisations"] == []
