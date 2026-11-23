# SPDX-License-Identifier: AGPL-3.0-or-later
"""The `test` ability against a real server under a d100 roll-under pack (the synthetic
percentile-test pack, test_packs/): a character's values and ranks, the target each test reaches,
refusals the rules require, and who may ask. The roll is the server's own, so the outcome is checked
for agreeing with the roll and the target, not for a particular result."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_dice.EXT_RPGDice import RPGDiceExtension
from zephyrex.testing.factories import create_user

from test_support import percentile_system, template
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
def table(server: TestClient) -> dict[str, Any]:
    """A character: Might 40, Wits 35, Nerve 30; Repair rank 2; Lore (Stars) rank 3 and (Old
    Kingdoms) rank 1; no Athletics or Stealth."""
    gm, player = create_user(server), create_user(server)
    system = percentile_system(server, gm)
    campaign = _create(server, gm, "campaign", name="Test table", user_id=gm.id, game_system_id=system["id"])
    hero = _create(server, gm, "person", name="Rhia", kind="pc", user_id=player.id, campaign_id=campaign["id"])
    for slug, value in (("might", 40), ("wits", 35), ("nerve", 30)):
        _create(server, gm, "person_trait", person_id=hero["id"], trait_id=template(server, gm, system["id"], slug), value=value)
    _create(server, gm, "person_trait", person_id=hero["id"], trait_id=template(server, gm, system["id"], "repair"), rank=2)
    lore = template(server, gm, system["id"], "lore")
    for specialisation, rank in (("Stars", 3), ("Old Kingdoms", 1)):
        _create(server, gm, "person_trait", person_id=hero["id"], trait_id=lore, rank=rank, specialisation=specialisation)
    plain = _create(server, gm, "campaign", name="No pack", user_id=gm.id)
    stranger_pc = _create(server, gm, "person", name="Otto", kind="pc", user_id=player.id, campaign_id=plain["id"])
    return {"gm": gm, "player": player, "hero": hero, "unpacked": stranger_pc, "system": system}


def _test(user: Any, person: dict[str, Any], name: str, **options: Any) -> dict[str, Any]:
    return asyncio.run(RPGDiceExtension.test(str(user.id), person["id"], name, **options))


def _agrees(result: dict[str, Any]) -> None:
    if result["natural"] is None:
        assert result["success"] == (result["roll"] <= result["target"])
    assert result["degrees"] >= 1


@pytest.mark.parametrize(
    ("name", "options", "target", "rank", "trained"),
    [
        ("might", {"difficulty": "hard"}, 20, None, True),
        ("repair", {"difficulty": "standard"}, 45, 2, True),
        ("athletics", {}, 20, None, False),
        ("repair", {"difficulty": "easy", "modifiers": [40]}, 105, 2, True),
    ],
)
def test_the_target_follows_the_pack(
    table: dict[str, Any], name: str, options: dict[str, Any], target: int, rank: int | None, trained: bool
) -> None:
    result = _test(table["player"], table["hero"], name, **options)
    assert (result["system"], result["target"], result["skill_rank"], result["trained"]) == (
        "percentile-test",
        target,
        rank,
        trained,
    )
    _agrees(result)


@pytest.mark.parametrize(
    ("name", "options"),
    [
        ("lore", {"specialisation": "Sea Lanes"}),
        ("lore", {}),
        ("repair", {"specialisation": "Stars"}),
        ("might", {"difficulty": "impossible"}),
        ("sword-drill", {}),
    ],
)
def test_what_the_rules_forbid_is_refused(table: dict[str, Any], name: str, options: dict[str, Any]) -> None:
    with pytest.raises(HTTPException) as refused:
        _test(table["gm"], table["hero"], name, **options)
    assert refused.value.status_code == 422


def test_a_specialist_skill_tests_the_named_specialisation(table: dict[str, Any]) -> None:
    stars = _test(table["player"], table["hero"], "lore", specialisation=" stars ")
    assert (stars["skill_rank"], stars["target"], stars["specialisation"]) == (3, 55, "stars")
    kingdoms = _test(table["player"], table["hero"], "lore", specialisation="Old Kingdoms")
    assert (kingdoms["skill_rank"], kingdoms["target"]) == (1, 35)


def test_a_campaign_without_a_pack_says_so(table: dict[str, Any]) -> None:
    with pytest.raises(HTTPException) as refused:
        _test(table["gm"], table["unpacked"], "might")
    assert refused.value.status_code == 422


def test_only_the_gm_and_the_characters_player_may_test(server: TestClient, table: dict[str, Any]) -> None:
    with pytest.raises(HTTPException) as refused:
        _test(create_user(server), table["hero"], "might")
    assert refused.value.status_code == 404


def test_the_route_answers_like_the_ability(server: TestClient, table: dict[str, Any]) -> None:
    body = {"test": {"person_id": table["hero"]["id"], "name": "repair", "difficulty": "easy"}}
    response = server.post("/v1/dice/test", json=body, headers=_headers(table["player"]))
    assert response.status_code == 200, response.text
    assert response.json()["test"]["target"] == 65


def test_a_dice_tray_reads_what_a_test_can_name(server: TestClient, table: dict[str, Any]) -> None:
    body = {"options": {"person_id": table["hero"]["id"]}}
    response = server.post("/v1/dice/test-options", json=body, headers=_headers(table["player"]))
    assert response.status_code == 200, response.text
    options = response.json()["options"]
    assert options["system"] == "percentile-test" and options["default_difficulty"] == "standard"
    assert {one["slug"] for one in options["characteristics"]} >= {"might", "nerve"}
    lore = next(one for one in options["skills"] if one["slug"] == "lore")
    assert lore["untrainable"] is True and lore["characteristic"] == "wits"
    assert {"slug": "very-hard", "modifier": -40, "dc": None} in options["difficulties"]
    stranger = server.post("/v1/dice/test-options", json=body, headers=_headers(create_user(server)))
    assert stranger.status_code == 404
    assert lore["specialisations"] == ["Old Kingdoms", "Stars"]
    assert next(one for one in options["skills"] if one["slug"] == "repair")["specialisations"] == []


def test_a_tray_knows_when_there_is_no_sheet_and_an_imported_campaigns_creator_is_its_gm(server: TestClient) -> None:
    gm = create_user(server)
    system = percentile_system(server, gm)
    # A campaign made without an owner (as a vault import makes one): its creator is its GM.
    campaign = _create(server, gm, "campaign", name="Imported", game_system_id=system["id"])
    pregen = _create(server, gm, "person", name="Wren", kind="pc", campaign_id=campaign["id"])
    body = {"options": {"person_id": pregen["id"]}}
    blank = server.post("/v1/dice/test-options", json=body, headers=_headers(gm))
    assert blank.status_code == 200, blank.text
    assert blank.json()["options"]["has_sheet"] is False
    _create(server, gm, "person_trait", person_id=pregen["id"], trait_id=template(server, gm, system["id"], "grace"), value=45)
    sheet = server.post("/v1/dice/test-options", json=body, headers=_headers(gm)).json()["options"]
    assert sheet["has_sheet"] is True


def test_a_characters_sheet_reads_back_in_sections(server: TestClient, table: dict[str, Any]) -> None:
    body = {"sheet": {"person_id": table["hero"]["id"]}}
    response = server.post("/v1/dice/sheet", json=body, headers=_headers(table["player"]))
    assert response.status_code == 200, response.text
    sheet = response.json()["sheet"]
    assert sheet["has_sheet"] is True and sheet["system"] == "percentile-test"
    assert {one["name"]: one["value"] for one in sheet["characteristics"]} == {"Might": 40.0, "Nerve": 30.0, "Wits": 35.0}
    lore = [(one["specialisation"], one["rank"]) for one in sheet["skills"] if one["slug"] == "lore"]
    assert lore == [("Old Kingdoms", 1), ("Stars", 3)]
    assert sheet["gear"] == []
    stranger = server.post("/v1/dice/sheet", json=body, headers=_headers(create_user(server)))
    assert stranger.status_code == 404
