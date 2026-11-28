# SPDX-License-Identifier: AGPL-3.0-or-later
"""The VTT's rows go with the wiki records they belong to (Zephyrex RPG Wiki, 2026-11-28: deleted
playthroughs left person_traits, scene_tokens and scenes live): the remove hook takes a removed
campaign's rows and what references them (a scene's tokens and walls, an encounter's combatants),
counting them on a dry run and leaving another campaign's alone; sweep_orphans finds the rows a
person deleted earlier left behind, and only the server's own accounts sweep."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_systems.EXT_RPGSystems import RPGSystemsExtension
from zephyrex.extensions.rpg_systems.Removal import _metadata, remove_for, vtt_tables
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


def _delete(server: TestClient, user: Any, resource: str, record_id: str) -> None:
    current = server.get(f"/v1/{resource}/{record_id}", headers=_headers(user))
    assert current.status_code == 200, current.text
    deleted = server.delete(f"/v1/{resource}/{record_id}", headers={**_headers(user), "If-Match": current.headers["ETag"]})
    assert deleted.status_code in (200, 204), deleted.text


def _table(server: TestClient, gm: Any, name: str) -> dict[str, Any]:
    """A campaign with a character (a trait value, a token on a walled scene, a fight, a state)."""
    campaign = _create(server, gm, "campaign", name=name, user_id=gm.id)
    person = _create(server, gm, "person", name=f"{name} hero", kind="pc", campaign_id=campaign["id"])
    trait = _create(server, gm, "trait", name=f"{name} grit", kind="characteristic", campaign_id=campaign["id"])
    value = _create(server, gm, "person_trait", person_id=person["id"], trait_id=trait["id"], value=3)
    scene = _create(server, gm, "scene", name=f"{name} ford", campaign_id=campaign["id"], width=1000, height=800)
    token = _create(server, gm, "scene_token", name="hero", scene_id=scene["id"], person_id=person["id"], x=100, y=100)
    wall = _create(server, gm, "scene_wall", scene_id=scene["id"], points=[[0, 0], [100, 0]])
    encounter = _create(server, gm, "encounter", campaign_id=campaign["id"], scene_id=scene["id"], name="Ambush")
    combatant = _create(server, gm, "combatant", encounter_id=encounter["id"], person_id=person["id"])
    state = _create(server, gm, "character_state", person_id=person["id"], hp=4)
    rows = {
        "person_traits": value["id"], "traits": trait["id"], "scenes": scene["id"], "scene_tokens": token["id"],
        "scene_walls": wall["id"], "encounters": encounter["id"], "combatants": combatant["id"], "character_states": state["id"],
    }
    return {"campaign": campaign, "person": person, "rows": rows}


def _live(server: TestClient, rows: dict[str, str]) -> dict[str, bool]:
    registry = server.app.state.model_registry  # type: ignore[attr-defined]
    metadata = _metadata(registry)
    session = registry.DB.session()
    try:
        found = {}
        for name, row_id in rows.items():
            table = metadata.tables[name]
            deleted = session.execute(sa.select(table.c.deleted_at).where(table.c.id == row_id)).scalar_one()
            found[name] = deleted is None
        return found
    finally:
        session.close()


def test_the_vtts_tables_are_read_from_the_metadata(server: TestClient) -> None:
    names = {table.name for table in vtt_tables(_metadata(server.app.state.model_registry))}  # type: ignore[attr-defined]
    assert {"person_traits", "scenes", "scene_tokens", "encounters", "combatants", "character_states", "table_seats"} <= names
    assert "persons" not in names and "campaigns" not in names, "the wiki's own are the wiki's to remove"


def test_a_removed_campaigns_rows_go_and_anothers_stay(server: TestClient) -> None:
    gm = create_user(server)
    going, staying = _table(server, gm, "Tavern Start"), _table(server, gm, "Split Antler")
    registry = server.app.state.model_registry  # type: ignore[attr-defined]
    records = [going["person"]["id"]]
    counted = remove_for(registry, str(env("ROOT_ID")), [going["campaign"]["id"]], records, dry_run=True)
    assert counted == {f"vtt.{name}": 1 for name in going["rows"]}, "one of each, counted"
    assert all(_live(server, going["rows"]).values()), "a dry run removes nothing"

    assert remove_for(registry, str(env("ROOT_ID")), [going["campaign"]["id"]], records) == counted
    assert not any(_live(server, going["rows"]).values()), "the campaign's rows, and the scene's and fight's parts"
    assert all(_live(server, staying["rows"]).values()), "another campaign's stay"
    assert remove_for(registry, str(env("ROOT_ID")), [going["campaign"]["id"]], records) == {}, "nothing twice"


def test_a_sweep_finds_what_a_deleted_person_left(server: TestClient) -> None:
    gm = create_user(server)
    left = _table(server, gm, "Old Copy")
    _delete(server, gm, "person", left["person"]["id"])
    system = str(env("SYSTEM_ID"))
    dry = asyncio.run(RPGSystemsExtension.sweep_orphans(system))
    owned = {"vtt.person_traits", "vtt.scene_tokens", "vtt.combatants", "vtt.character_states"}
    assert dry["dry_run"] is True and owned <= set(dry["removed"])
    assert all(_live(server, {name: left["rows"][name] for name in ("person_traits", "scene_tokens")}).values())
    done = asyncio.run(RPGSystemsExtension.sweep_orphans(system, dry_run=False))
    assert done["dry_run"] is False and owned <= set(done["removed"])
    gone = _live(server, left["rows"])
    assert not any(gone[name] for name in ("person_traits", "scene_tokens", "combatants", "character_states"))
    assert gone["scenes"] and gone["encounters"] and gone["traits"], "the campaign is live: its scene, fight and traits stay"
    with pytest.raises(HTTPException) as refused:
        asyncio.run(RPGSystemsExtension.sweep_orphans(str(gm.id)))
    assert refused.value.status_code == 403


def test_deleting_a_campaign_takes_its_vtt_rows(server: TestClient) -> None:
    """End to end, through the wiki's register_remove_hook (wiki ec400e1+): the campaign's DELETE."""
    gm = create_user(server)
    going, staying = _table(server, gm, "Tavern Start copy"), _table(server, gm, "Kept")
    _delete(server, gm, "campaign", going["campaign"]["id"])
    assert not any(_live(server, going["rows"]).values()), "the hook took them with the campaign"
    assert all(_live(server, staying["rows"]).values())
