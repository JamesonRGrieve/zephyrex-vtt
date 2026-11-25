# SPDX-License-Identifier: AGPL-3.0-or-later
"""The map, played through (the operator, 2026-11-25: "Maps are still completely fucked and need a
whole testing framework on the part of VTT"). The map world (map_fixture: an outside, an inside, a
fight) is started as a real playthrough (the wiki's instantiate), then walked as rpg-ai's map_step
walks it: people moved by pilot_token (a move to a place), arrivals by place_person on the current
scene, departures by remove_person_from_scene. After every step the current scene and who stands
where on it are asserted, as a player's map pane would show them."""

import asyncio
import json
import os
import time
from pathlib import Path
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_combat.EXT_RPGCombat import RPGCombatExtension
from zephyrex.extensions.rpg_scene.EXT_RPGScene import RPGSceneExtension
from zephyrex.testing.factories import create_user

import map_fixture
from vtt_app import create


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    with TestClient(create()) as client:
        yield client


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _start(server: TestClient, author: Any, scenario_id: str) -> str:
    accepted = server.post(f"/v1/campaign/{scenario_id}/instantiate", json={"instantiate": {}}, headers=_headers(author))
    assert accepted.status_code == 202, accepted.text
    start = accepted.json()["start"]
    deadline = time.monotonic() + 90
    while start["state"] == "running":
        assert time.monotonic() < deadline, start
        time.sleep(0.5)
        start = server.get(f"/v1/campaign_start/{start['id']}", headers=_headers(author)).json()["campaign_start"]
    assert start["state"] == "done", start.get("error") or start
    return str(start["campaign_id"])


class Table:
    """The playthrough as the map pane and map_step see it, by name."""

    def __init__(self, server: TestClient, gm: Any, campaign_id: str) -> None:
        self.server, self.gm, self.campaign_id = server, gm, campaign_id

    def _list(self, resource: str, plural: str) -> list[dict[str, Any]]:
        rows = self.server.get(f"/v1/{resource}", params={"campaign_id": self.campaign_id, "limit": 200}, headers=_headers(self.gm)).json()[plural]
        return [one for one in rows if one.get("campaign_id") == self.campaign_id]

    def person(self, name: str) -> dict[str, Any]:
        return next(one for one in self._list("person", "persons") if one["name"] == name)

    def place(self, name: str) -> dict[str, Any]:
        return next(one for one in self._list("location", "locations") if one["name"] == name)

    def current(self) -> dict[str, Any]:
        found = asyncio.run(RPGSceneExtension.current_scene(str(self.gm.id), self.campaign_id))
        assert found is not None, "no current scene"
        return dict(found)

    def squares_apart(self, scene_id: str | None = None) -> None:
        """No two people on one square of the scene (the map review: three stood on one)."""
        scene = scene_id or self.current()
        grid = float((scene if isinstance(scene, dict) else self.current())["grid_size"])
        here = self.tokens(scene["id"] if isinstance(scene, dict) else scene)
        cells = [(int(x // grid), int(y // grid)) for x, y in here.values()]
        assert len(set(cells)) == len(cells), here

    def tokens(self, scene_id: str | None = None) -> dict[str, tuple[float, float]]:
        """Who stands where on a scene (the current one by default): name → the token's top-left."""
        from zephyrex.extensions.rpg_scene.BLL_RPGScene import SceneTokenManager
        from zephyrex.lib.Environment import env

        scene = scene_id or self.current()["id"]
        names = {one["id"]: one["name"] for one in self._list("person", "persons")}
        rows = SceneTokenManager(requester_id=env("ROOT_ID"), model_registry=self.server.app.state.model_registry)  # type: ignore[attr-defined]
        on = rows.list(filters=[rows.DB.deleted_at.is_(None)], scene_id=scene)
        return {names.get(one.person_id, one.name): (float(one.x or 0), float(one.y or 0)) for one in on}

    def scene_named(self, name: str) -> str:
        return next(one["id"] for one in self._list("scene", "scenes") if one["name"] == name)

    def pilot(self, name: str, place: str) -> dict[str, Any]:
        return dict(asyncio.run(RPGSceneExtension.pilot_token(str(self.gm.id), self.person(name)["id"], location_id=self.place(place)["id"])))

    def arrive(self, name: str, beside: str) -> dict[str, Any]:
        scene = self.current()["id"]
        return dict(asyncio.run(RPGSceneExtension.place_person(str(self.gm.id), scene, self.person(name)["id"], near_person_id=self.person(beside)["id"])))

    def leave(self, name: str) -> None:
        asyncio.run(RPGSceneExtension.remove_person_from_scene(str(self.gm.id), self.current()["id"], self.person(name)["id"]))


def _export(table: "Table", step: str) -> None:
    """The step's map as the GM's pane is sent it (POST /v1/scene/{id}/view), for the browser render
    test (vtt-play e2e map-play.spec.ts): written when MAP_PLAY_OUT names a directory."""
    out = os.environ.get("MAP_PLAY_OUT")
    if not out:
        return
    shown = table.current()
    view = table.server.post(f"/v1/scene/{shown['id']}/view", json={"view": {}}, headers=_headers(table.gm))
    assert view.status_code == 200, view.text
    names = {one["id"]: one["name"] for one in table._list("person", "persons")}
    found = view.json()["view"]
    shape = map_fixture.SCENES[shown["name"]]
    Path(out).mkdir(parents=True, exist_ok=True)
    Path(out, f"{step}.json").write_text(
        json.dumps({"step": step, "scene": shown["name"], "art": list(shape["art"]), "people": {str(one.get("person_id")): names.get(one.get("person_id")) for one in found["tokens"]}, "view": found}, indent=1)
    )


def _inside(point: tuple[float, float], box: tuple[int, int, int, int], grid: int) -> bool:
    """A token (its top-left cell) stands in a region: its centre is inside the box."""
    x, y = point[0] + grid / 2, point[1] + grid / 2
    left, top, width, height = box
    return left <= x <= left + width and top <= y <= top + height


@pytest.fixture(scope="module")
def table(server: TestClient) -> Table:
    author = create_user(server)
    world = map_fixture.seed(server, author)
    return Table(server, author, _start(server, author, world["scenario"]["id"]))


def test_1_play_opens_where_the_party_is_with_everyone_present_on_the_map(table: Table) -> None:
    """The scenario had the town current; the party starts in the parlour, so the house map opens
    (CT 7103 showed the whole town until the house was activated by hand), and everyone in the
    parlour stands in the parlour, the party included."""
    shown = table.current()
    assert shown["name"] == "Halloway house, ground floor", shown["name"]
    here = table.tokens()
    assert set(here) == {"Brann", "Sefa", "Mara Halloway", "Old Hesk"}, here
    parlour = map_fixture.region_of("Halloway house, ground floor", "The parlour")
    for name in ("Brann", "Sefa"):
        assert _inside(here[name], parlour, 100), (name, here[name])
    assert len(set(here.values())) == len(here), "no two on one square"
    table.squares_apart()
    _export(table, "1-arrive")


def test_2_the_party_walks_to_the_market_and_the_map_follows_them(table: Table) -> None:
    table.pilot("Brann", "The market")
    assert table.current()["name"] == "Halloway house, ground floor", "one of two gone: the map stays with the party"
    table.pilot("Sefa", "The market")
    shown = table.current()
    assert shown["name"] == "Saltmere", "the whole party is in town: the town map"
    here = table.tokens()
    market = map_fixture.region_of("Saltmere", "The market")
    assert _inside(here["Brann"], market, 68) and _inside(here["Sefa"], market, 68), here
    assert table.person("Brann")["location_id"] == table.place("The market")["id"]
    assert set(table.tokens(table.scene_named("Halloway house, ground floor"))) == {"Mara Halloway", "Old Hesk"}, "one token per person"
    table.squares_apart()
    _export(table, "2-market")


def test_2b_a_turn_where_no_one_moves_never_changes_the_map(table: Table) -> None:
    """rpg-ai writes a location banner whenever current_scene changes (MapStep.banner_due): the
    current scene must hold still between moves, however often it's read."""
    shown = [table.current()["id"] for _ in range(3)]
    assert len(set(shown)) == 1


def test_2c_a_refused_move_changes_neither_the_token_nor_the_place(table: Table) -> None:
    """A stranger's pilot is refused (404); Brann's token and wiki location stay as they were."""
    from fastapi import HTTPException
    from zephyrex.testing.factories import create_user

    before, place = table.tokens()["Brann"], table.person("Brann")["location_id"]
    with pytest.raises(HTTPException):
        asyncio.run(RPGSceneExtension.pilot_token(str(create_user(table.server).id), table.person("Brann")["id"], location_id=table.place("The cellar")["id"]))
    assert table.tokens()["Brann"] == before and table.person("Brann")["location_id"] == place


def test_3_into_a_building_with_no_map_of_its_own_stays_on_the_town(table: Table) -> None:
    table.pilot("Brann", "Watch house")
    table.pilot("Sefa", "Watch house")
    shown = table.current()
    assert shown["name"] == "Saltmere"
    here = table.tokens()
    watch = map_fixture.region_of("Saltmere", "Watch house")
    assert _inside(here["Brann"], watch, 68) and _inside(here["Sefa"], watch, 68), here
    assert table.person("Sefa")["location_id"] == table.place("Watch house")["id"]
    table.squares_apart()
    _export(table, "3-watch-house")


def test_4_an_arrival_stands_beside_the_one_it_joins(table: Table) -> None:
    placed = table.arrive("Captain Ord", beside="Brann")
    here = table.tokens()
    assert "Captain Ord" in here
    (bx, by), (ox, oy) = here["Brann"], here["Captain Ord"]
    assert max(abs(bx - ox), abs(by - oy)) <= 68 * 2, (here["Brann"], here["Captain Ord"])
    assert placed["scene_id"] == table.current()["id"]
    table.squares_apart()
    _export(table, "4-arrival")


def test_5_down_to_the_cellar_the_map_is_the_cellar_and_the_fight_is_there(table: Table) -> None:
    table.pilot("Brann", "The cellar")
    table.pilot("Sefa", "The cellar")
    shown = table.current()
    assert shown["name"] == "Halloway cellar"
    here = table.tokens()
    assert {"Brann", "Sefa", "Cellar thug"} <= set(here), here
    fight = asyncio.run(RPGCombatExtension.start_encounter(str(table.gm.id), table.campaign_id, scene_id=shown["id"]))
    names = sorted(one.get("name") or "" for one in fight["combatants"])
    assert names == ["Brann", "Cellar thug", "Sefa"], names
    table.squares_apart()
    _export(table, "5-cellar-fight")


def test_6_a_departure_takes_the_token_off_and_a_road_off_every_map(table: Table) -> None:
    table.leave("Cellar thug")
    assert "Cellar thug" not in table.tokens()
    table.squares_apart()
    _export(table, "6-departure")
    table.pilot("Mara Halloway", "The coast road")
    for scene in ("Saltmere", "Halloway house, ground floor", "Halloway cellar"):
        assert "Mara Halloway" not in table.tokens(table.scene_named(scene)), scene
    assert table.person("Mara Halloway")["location_id"] == table.place("The coast road")["id"]
