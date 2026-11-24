# SPDX-License-Identifier: AGPL-3.0-or-later
"""The map is never empty for a table (the operator: "The map is also completely nonfunctional"):
a player reads the campaign's current scene (scenes are the GM's rows, so membership is checked,
not the player's own read); with none active the first becomes current; a campaign with no scene
gets a default grid scene at the party's wiki location with their tokens; and a scenario's scenes
copy into a playthrough with its characters remapped."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_scene.EXT_RPGScene import RPGSceneExtension
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


def _current(server: TestClient, user: Any, campaign_id: str) -> Any:
    response = server.post("/v1/scene/current", json={"current": {"campaign_id": campaign_id}}, headers=_headers(user))
    assert response.status_code == 200, response.text
    return response.json()["scene"]


def test_a_player_sees_the_gms_scene_and_the_first_becomes_current(server: TestClient) -> None:
    gm, player, stranger = create_user(server), create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="Harbour", user_id=gm.id)
    _create(server, gm, "person", name="Rhia", kind="pc", user_id=player.id, campaign_id=campaign["id"])
    bridge = _create(server, gm, "scene", name="Bridge", campaign_id=campaign["id"], width=800, height=600)
    shown = _current(server, player, campaign["id"])
    assert shown is not None and shown["id"] == bridge["id"], "not active yet: the first becomes current"
    assert _current(server, gm, campaign["id"])["id"] == bridge["id"]
    assert _current(server, stranger, campaign["id"]) is None


def test_a_campaign_with_no_scene_gets_one_where_the_party_is(server: TestClient) -> None:
    gm, player = create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="Split Antler", user_id=gm.id)
    inn = _create(server, gm, "location", name="The Split Antler")
    road = _create(server, gm, "location", name="North Road")
    brann = _create(server, gm, "person", name="Brann", kind="pc", user_id=player.id, campaign_id=campaign["id"], location_id=inn["id"])
    _create(server, gm, "person", name="Innkeeper", kind="npc", campaign_id=campaign["id"], location_id=inn["id"])
    _create(server, gm, "person", name="Bandit", kind="npc", campaign_id=campaign["id"], location_id=road["id"])

    made = _current(server, player, campaign["id"])
    assert made is not None and (made["name"], made["location_id"]) == ("The Split Antler", inn["id"])
    assert _current(server, player, campaign["id"])["id"] == made["id"], "made once"
    tokens = asyncio.run(RPGSceneExtension.scene_tokens(str(gm.id), made["id"]))
    assert sorted(one["name"] for one in tokens) == ["Brann", "Innkeeper"]
    assert brann["id"] in {one["entity_id"] for one in tokens}
    cells = {(one["token_id"]) for one in tokens}
    assert len(cells) == 2


def test_a_scenarios_scenes_copy_into_its_playthrough(server: TestClient) -> None:
    author, player, other = create_user(server), create_user(server), create_user(server)
    scenario = _create(server, author, "campaign", name="Scenario", user_id=author.id)
    vell = _create(server, author, "person", name="Vell", kind="npc", campaign_id=scenario["id"])
    town = _create(server, author, "location", name="Saltmere", kind="city", campaign_id=scenario["id"])
    house = _create(server, author, "location", name="Halloway house", kind="building", parent_id=town["id"], campaign_id=scenario["id"])
    deck = _create(
        server, author, "scene", name="Deck", campaign_id=scenario["id"], location_id=town["id"], width=1000, height=600,
        background_url="/v1/asset/a1/content",
    )
    _create(server, author, "scene_wall", scene_id=deck["id"], points=[[500, 0], [500, 400]])
    _create(server, author, "scene_light", scene_id=deck["id"], x=300, y=200, dim=30, bright=15)
    _create(
        server, author, "scene_region", scene_id=deck["id"], location_id=house["id"], name="Halloway house",
        shapes=[{"type": "rectangle", "x": 100, "y": 100, "width": 200, "height": 100}],
    )
    _create(server, author, "scope_place", campaign_id=scenario["id"], location_id=house["id"], x=0.4, y=0.3)
    _create(server, author, "scene_token", name="Vell", scene_id=deck["id"], person_id=vell["id"], x=100, y=100)
    asyncio.run(RPGSceneExtension.activate_scene(str(author.id), deck["id"]))

    playthrough = _create(server, author, "campaign", name="Playthrough", user_id=author.id)
    copy_of_vell = _create(server, author, "person", name="Vell", kind="npc", campaign_id=playthrough["id"])
    copy_of_town = _create(server, author, "location", name="Saltmere", kind="city", campaign_id=playthrough["id"])
    copy_of_house = _create(server, author, "location", name="Halloway house", kind="building", parent_id=copy_of_town["id"], campaign_id=playthrough["id"])
    id_map = {vell["id"]: copy_of_vell["id"], town["id"]: copy_of_town["id"], house["id"]: copy_of_house["id"]}
    copied = asyncio.run(RPGSceneExtension.copy_scenes(str(author.id), scenario["id"], playthrough["id"], id_map))
    assert [one["name"] for one in copied] == ["Deck"] and copied[0]["campaign_id"] == playthrough["id"]
    assert _current(server, author, playthrough["id"])["id"] == copied[0]["id"]
    tokens = asyncio.run(RPGSceneExtension.scene_tokens(str(author.id), copied[0]["id"]))
    assert [one["entity_id"] for one in tokens] == [copy_of_vell["id"]]
    walls = server.get("/v1/scene_wall", params={"scene_id": copied[0]["id"]}, headers=_headers(author)).json()["scene_walls"]
    assert [wall["points"] for wall in walls] == [[[500, 0], [500, 400]]]
    # What an imported map carries: its art link, lights, regions on the copied places, the GM's pins.
    assert copied[0]["background_url"] == "/v1/asset/a1/content" and copied[0]["location_id"] == copy_of_town["id"]
    lights = server.get("/v1/scene_light", params={"scene_id": copied[0]["id"]}, headers=_headers(author)).json()["scene_lights"]
    assert [(one["x"], one["dim"]) for one in lights if one["scene_id"] == copied[0]["id"]] == [(300.0, 30.0)]
    regions = server.get("/v1/scene_region", params={"scene_id": copied[0]["id"]}, headers=_headers(author)).json()["scene_regions"]
    assert [one["location_id"] for one in regions if one["scene_id"] == copied[0]["id"]] == [copy_of_house["id"]]
    pins = server.get("/v1/scope_place", params={"campaign_id": playthrough["id"]}, headers=_headers(author)).json()["scope_places"]
    assert [(one["location_id"], one["x"], one["y"]) for one in pins if one["campaign_id"] == playthrough["id"]] == [(copy_of_house["id"], 0.4, 0.3)]

    with pytest.raises(HTTPException) as refused:
        asyncio.run(RPGSceneExtension.copy_scenes(str(other.id), scenario["id"], playthrough["id"], {}))
    assert refused.value.status_code == 404


def test_a_playthrough_opens_on_the_scene_where_the_party_starts(server: TestClient) -> None:
    """The operator: The Missing Merchant opens in the Halloway parlour, so play must open on the
    house map, not the town the scenario last had current."""
    author, player = create_user(server), create_user(server)
    scenario = _create(server, author, "campaign", name="The Missing Merchant", user_id=author.id)
    town = _create(server, author, "location", name="Saltmere", kind="city", campaign_id=scenario["id"])
    house = _create(server, author, "location", name="Halloway house", kind="building", parent_id=town["id"], campaign_id=scenario["id"])
    _create(server, author, "scene", name="Halloway house, ground floor", campaign_id=scenario["id"], location_id=house["id"])
    saltmere = _create(server, author, "scene", name="Saltmere", campaign_id=scenario["id"], location_id=town["id"])
    asyncio.run(RPGSceneExtension.activate_scene(str(author.id), saltmere["id"]))

    playthrough = _create(server, author, "campaign", name="Playthrough", user_id=author.id)
    copy_town = _create(server, author, "location", name="Saltmere", kind="city", campaign_id=playthrough["id"])
    copy_house = _create(server, author, "location", name="Halloway house", kind="building", parent_id=copy_town["id"], campaign_id=playthrough["id"])
    parlour = _create(server, author, "location", name="The parlour", kind="room", parent_id=copy_house["id"], campaign_id=playthrough["id"])
    _create(server, author, "person", name="Brann", kind="pc", user_id=player.id, campaign_id=playthrough["id"], location_id=parlour["id"])
    copied = asyncio.run(
        RPGSceneExtension.copy_scenes(str(author.id), scenario["id"], playthrough["id"], {town["id"]: copy_town["id"], house["id"]: copy_house["id"]})
    )
    opened = _current(server, author, playthrough["id"])
    assert opened["name"] == "Halloway house, ground floor" and opened["id"] in {one["id"] for one in copied}


def test_starting_a_playthrough_copies_the_scenarios_scenes(server: TestClient) -> None:
    """The wiki's start (POST /v1/campaign/{id}/instantiate, its AFTER_INSTANTIATE callbacks) brings the
    scenario's scenes into the playthrough, tokens on the copied characters, the current one current."""
    import time

    author = create_user(server)
    scenario = _create(server, author, "campaign", name="The Lantern", user_id=author.id, is_scenario=True)
    vell = _create(server, author, "person", name="Vell", kind="npc", campaign_id=scenario["id"])
    deck = _create(server, author, "scene", name="Deck", campaign_id=scenario["id"], width=800, height=600)
    _create(server, author, "scene_token", name="Vell", scene_id=deck["id"], person_id=vell["id"], x=200, y=200)
    asyncio.run(RPGSceneExtension.activate_scene(str(author.id), deck["id"]))

    accepted = server.post(f"/v1/campaign/{scenario['id']}/instantiate", json={"instantiate": {}}, headers=_headers(author))
    assert accepted.status_code == 202, accepted.text
    start = accepted.json()["start"]
    deadline = time.monotonic() + 60
    while start["state"] == "running":
        assert time.monotonic() < deadline, start
        time.sleep(0.5)
        start = server.get(f"/v1/campaign_start/{start['id']}", headers=_headers(author)).json()["campaign_start"]
    assert start["state"] == "done", start.get("error") or start

    playthrough = start["campaign_id"]
    shown = _current(server, author, playthrough)
    assert shown is not None and shown["name"] == "Deck" and shown["campaign_id"] == playthrough
    tokens = asyncio.run(RPGSceneExtension.scene_tokens(str(author.id), shown["id"]))
    assert len(tokens) == 1 and tokens[0]["entity_id"] != vell["id"], "on the playthrough's copy of Vell"
    copied = server.get(f"/v1/person/{tokens[0]['entity_id']}", headers=_headers(author)).json()["person"]
    assert (copied["name"], copied["campaign_id"]) == ("Vell", playthrough)


def test_a_seated_player_sees_from_their_token_and_rolls_without_owning_the_person(server: TestClient) -> None:
    """A playthrough's copied pregen is played through a table seat (controller_id), not the
    person's user_id: its player sees the scene from its token, and rolls its tests. A player of the
    campaign with no token on the scene gets the map and nothing on it."""
    from zephyrex.extensions.rpg_dice.EXT_RPGDice import RPGDiceExtension
    from zephyrex.extensions.rpg_table.BLL_RPGTable import TableSeatManager
    from zephyrex.lib.Environment import env

    gm, player, other = create_user(server), create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="Playthrough", user_id=gm.id)
    pregen = _create(server, gm, "person", name="Osk", kind="pc", campaign_id=campaign["id"])
    _create(server, gm, "person", name="Wren", kind="pc", user_id=other.id, campaign_id=campaign["id"])
    table = _create(server, gm, "table", name="Session 1", campaign_id=campaign["id"])
    seats = TableSeatManager(requester_id=env("ROOT_ID"), model_registry=server.app.state.model_registry)
    seats.create_row(conversation_id=table["conversation_id"], person_id=pregen["id"], name="Osk", avatar=None, controller_id=str(player.id))
    scene = _create(server, gm, "scene", name="Chapel", campaign_id=campaign["id"], width=500, height=500)
    _create(server, gm, "scene_token", name="Osk", scene_id=scene["id"], person_id=pregen["id"], x=100, y=100)

    assert _current(server, player, campaign["id"])["id"] == scene["id"]
    seen = server.post(f"/v1/scene/{scene['id']}/view", json={"view": {}}, headers=_headers(player))
    assert seen.status_code == 200, seen.text
    view = seen.json()["view"]
    assert view["gm"] is False and [one["name"] for one in view["tokens"] if one["mine"]] == ["Osk"]

    tokenless = server.post(f"/v1/scene/{scene['id']}/view", json={"view": {}}, headers=_headers(other))
    assert tokenless.status_code == 200, tokenless.text
    assert tokenless.json()["view"]["tokens"] == [] and tokenless.json()["view"]["walls"] == []

    options = asyncio.run(RPGDiceExtension.roll(str(player.id), "1d6"))
    assert 1 <= options["total"] <= 6
    with pytest.raises(HTTPException) as no_pack:
        asyncio.run(RPGDiceExtension.test_options(str(player.id), pregen["id"]))
    assert no_pack.value.status_code == 422, "past the access rule: only the system is missing"


def test_a_campaign_without_a_system_uses_its_settings_packed_system(server: TestClient) -> None:
    """A vault-imported scenario (or its playthrough) has a setting but no game system: rpg_dice uses
    the one system of that setting with a rules pack."""
    from zephyrex.extensions.rpg_dice.EXT_RPGDice import RPGDiceExtension
    from zephyrex.extensions.rpg_systems.BLL_RPGSystems import GameSystemManager
    from zephyrex.lib.Environment import env
    from test_support import percentile_system

    gm = create_user(server)
    setting = _create(server, gm, "setting", name="Far Shores", slug="far-shores")
    system = percentile_system(server)
    systems = GameSystemManager(requester_id=env("ROOT_ID"), model_registry=server.app.state.model_registry)
    systems.update(id=system["id"], setting_id=setting["id"])
    campaign = _create(server, gm, "campaign", name="Imported", user_id=gm.id, setting_id=setting["id"])
    villager = _create(server, gm, "person", name="Villager", kind="npc", campaign_id=campaign["id"])
    options = asyncio.run(RPGDiceExtension.test_options(str(gm.id), villager["id"]))
    assert options["system"] == "percentile-test" and len(options["skills"]) == 4

def test_the_gm_places_a_new_npc_beside_the_seats_character(server: TestClient) -> None:
    gm, player = create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="Split Antler", user_id=gm.id)
    brann = _create(server, gm, "person", name="Brann", kind="pc", user_id=player.id, campaign_id=campaign["id"])
    tam = _create(server, gm, "person", name="Old Tam", kind="npc", campaign_id=campaign["id"])
    taproom = _create(server, gm, "scene", name="Taproom", campaign_id=campaign["id"], width=1000, height=800)
    _create(server, gm, "scene_token", name="Brann", scene_id=taproom["id"], person_id=brann["id"], x=400, y=400)

    placed = asyncio.run(RPGSceneExtension.place_person(str(gm.id), taproom["id"], tam["id"], near_person_id=brann["id"]))
    assert placed["scene_id"] == taproom["id"] and placed["token_id"]
    assert max(abs(placed["x"] - 400), abs(placed["y"] - 400)) == 100, "the nearest free cell beside Brann"

    with pytest.raises(HTTPException) as refused:
        asyncio.run(RPGSceneExtension.place_person(str(player.id), taproom["id"], tam["id"], x=100, y=100))
    assert refused.value.status_code == 404
    rest = server.post(
        f"/v1/scene/{taproom['id']}/place", json={"place": {"person_id": tam["id"], "x": 850, "y": 650}}, headers=_headers(gm)
    )
    assert rest.status_code == 200, rest.text
    tokens = asyncio.run(RPGSceneExtension.scene_tokens(str(gm.id), taproom["id"]))
    assert sorted(one["name"] for one in tokens) == ["Brann", "Old Tam"], "one token per person"


def test_only_a_scenes_own_picture_is_drawn_never_its_places(server: TestClient) -> None:
    gm = create_user(server)
    campaign = _create(server, gm, "campaign", name="Saltmere", user_id=gm.id)
    docks = _create(server, gm, "location", name="Saltmere Docks", picture_url="https://example.org/docks.jpg")
    _create(server, gm, "person", name="Nia", kind="pc", user_id=gm.id, campaign_id=campaign["id"])
    scene = _create(server, gm, "scene", name="Docks", campaign_id=campaign["id"], location_id=docks["id"])
    view = server.post(f"/v1/scene/{scene['id']}/view", json={"view": {}}, headers=_headers(gm)).json()["view"]
    assert view["background_url"] is None, "never the place's picture: an illustration isn't a map"
    current = server.get(f"/v1/scene/{scene['id']}", headers=_headers(gm))
    put = server.put(
        f"/v1/scene/{scene['id']}",
        json={"scene": {"background_url": "https://example.org/battlemap.png"}},
        headers={**_headers(gm), "If-Match": current.headers["ETag"]},
    )
    assert put.status_code == 200, put.text
    view = server.post(f"/v1/scene/{scene['id']}/view", json={"view": {}}, headers=_headers(gm)).json()["view"]
    assert view["background_url"] == "https://example.org/battlemap.png", "the scene's own map wins"


def test_the_gm_sets_a_scenes_background_through_the_ability(server: TestClient) -> None:
    gm, player = create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="Saltmere", user_id=gm.id)
    _create(server, gm, "person", name="Nia", kind="pc", user_id=player.id, campaign_id=campaign["id"])
    scene = _create(server, gm, "scene", name="Docks", campaign_id=campaign["id"])
    before = asyncio.run(RPGSceneExtension.current_scene(str(gm.id), campaign["id"]))
    assert before is not None and before["background_url"] is None, "nothing to draw: rpg-ai generates"
    made = asyncio.run(RPGSceneExtension.set_scene_background(str(gm.id), scene["id"], "/v1/asset/a1/content"))
    assert made["background_url"] == "/v1/asset/a1/content"
    after = asyncio.run(RPGSceneExtension.current_scene(str(player.id), campaign["id"]))
    assert after is not None and after["background_url"] == "/v1/asset/a1/content"
    with pytest.raises(HTTPException) as refused:
        asyncio.run(RPGSceneExtension.set_scene_background(str(player.id), scene["id"], "/v1/asset/x/content"))
    assert refused.value.status_code == 404


def test_the_gm_moves_a_token_to_another_scene(server: TestClient) -> None:
    gm, player = create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="Saltmere", user_id=gm.id)
    nia = _create(server, gm, "person", name="Nia", kind="pc", user_id=player.id, campaign_id=campaign["id"])
    docks = _create(server, gm, "scene", name="Docks", campaign_id=campaign["id"], width=1000, height=800)
    tavern = _create(server, gm, "scene", name="Tavern", campaign_id=campaign["id"], width=600, height=400)
    token = _create(server, gm, "scene_token", name="Nia", scene_id=docks["id"], person_id=nia["id"], x=100, y=100)

    with pytest.raises(HTTPException) as refused:
        asyncio.run(RPGSceneExtension.move_token_to_scene(str(player.id), token["id"], tavern["id"]))
    assert refused.value.status_code == 404
    moved = server.post(
        f"/v1/scene_token/{token['id']}/move_scene", json={"move_scene": {"scene_id": tavern["id"]}}, headers=_headers(gm)
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["scene_id"] == tavern["id"]
    on_docks = asyncio.run(RPGSceneExtension.scene_tokens(str(gm.id), docks["id"]))
    on_tavern = asyncio.run(RPGSceneExtension.scene_tokens(str(gm.id), tavern["id"]))
    assert on_docks == [] and [one["name"] for one in on_tavern] == ["Nia"], "one token, now in the tavern"
    # The GM's own list sees (and so can edit) the token that arrived: it's theirs, not the system's.
    listed = server.get("/v1/scene_token", params={"scene_id": tavern["id"]}, headers=_headers(gm))
    assert listed.status_code == 200, listed.text
    assert [one["id"] for one in listed.json()["scene_tokens"]] == [moved.json()["token_id"]]


def test_the_gm_takes_a_person_off_a_scene_leaving_their_location(server: TestClient) -> None:
    gm, player = create_user(server), create_user(server)
    campaign = _create(server, gm, "campaign", name="Saltmere", user_id=gm.id)
    hesk = _create(server, gm, "person", name="Old Hesk", kind="npc", campaign_id=campaign["id"])
    ferry = _create(server, gm, "scene", name="Ferry", campaign_id=campaign["id"], width=600, height=400)
    placed = asyncio.run(RPGSceneExtension.place_person(str(gm.id), ferry["id"], hesk["id"]))
    where = server.get(f"/v1/person/{hesk['id']}", headers=_headers(gm)).json()["person"].get("location_id")

    with pytest.raises(HTTPException) as refused:
        asyncio.run(RPGSceneExtension.remove_person_from_scene(str(player.id), ferry["id"], hesk["id"]))
    assert refused.value.status_code == 404
    gone = server.post(f"/v1/scene/{ferry['id']}/remove", json={"remove": {"person_id": hesk["id"]}}, headers=_headers(gm))
    assert gone.status_code == 200, gone.text
    assert gone.json() == {"scene_id": ferry["id"], "person_id": hesk["id"], "removed": True}
    assert asyncio.run(RPGSceneExtension.scene_tokens(str(gm.id), ferry["id"])) == []
    assert placed["token_id"] and server.get(f"/v1/person/{hesk['id']}", headers=_headers(gm)).json()["person"].get("location_id") == where
    again = asyncio.run(RPGSceneExtension.remove_person_from_scene(str(gm.id), ferry["id"], hesk["id"]))
    assert again["removed"] is False
