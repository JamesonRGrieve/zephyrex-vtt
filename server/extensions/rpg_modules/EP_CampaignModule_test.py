# SPDX-License-Identifier: AGPL-3.0-or-later
"""A test names the traits of the content modules enabled on its campaign: an enabled module's
Might wins over the system's public template, and another account's private module (which
a trusted read lists) never makes a name ambiguous or answers for it."""

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_dice.EXT_RPGDice import RPGDiceExtension
from zephyrex.extensions.rpg_modules.Install import install
from zephyrex.testing.factories import create_user

from test_support import percentile_system
from vtt_app import create

RULES = {"characteristics": [{"slug": "might", "key": "might", "name": "Might", "short": "MT"}]}
BUNDLE = {
    "line": "testline", "system": "percentile-test", "name": "Test line", "slug": "testline",
    "packs": [], "documents": [], "problems": [],
}


@pytest.fixture(scope="module")
def app() -> Iterator[Any]:
    application = create()
    with TestClient(application):
        yield application


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def _create(server: TestClient, user: Any, resource: str, **fields: Any) -> dict[str, Any]:
    response = server.post(f"/v1/{resource}", json={resource: fields}, headers=_headers(user))
    assert response.status_code == 201, response.text
    created: dict[str, Any] = response.json()[resource]
    return created


def _might(server: TestClient, user: Any, system_id: str, *, mine: bool) -> str:
    traits = server.get(
        "/v1/trait", params={"slug": "might", "game_system_id": system_id}, headers=_headers(user)
    ).json()["traits"]
    found = [one for one in traits if (one["created_by_user_id"] == str(user.id)) == mine]
    assert len(found) == 1, found
    return str(found[0]["id"])


def test_an_enabled_module_answers_and_anothers_never_does(app: Any) -> None:
    server = TestClient(app)
    registry = app.state.model_registry
    gm, stranger = create_user(server), create_user(server)
    system_id = percentile_system(server)["id"]
    # Someone else installs the line first: their Might is a system-level trait a trusted read sees.
    install(registry, str(stranger.id), BUNDLE, rules=RULES)
    campaign = _create(server, gm, "campaign", name="Harbour", user_id=gm.id, game_system_id=system_id)
    acolyte = _create(server, gm, "person", name="Osk", kind="pc", user_id=gm.id, campaign_id=campaign["id"])
    template = _might(server, gm, system_id, mine=False)
    _create(server, gm, "person_trait", person_id=acolyte["id"], trait_id=template, value=30)

    before = asyncio.run(RPGDiceExtension.test(str(gm.id), acolyte["id"], "might"))
    assert before["target"] == 30, "the template answers; the stranger's module neither answers nor makes it ambiguous"

    module = install(registry, str(gm.id), BUNDLE, rules=RULES)
    own = _might(server, gm, system_id, mine=True)
    _create(server, gm, "person_trait", person_id=acolyte["id"], trait_id=own, value=45)
    installed = asyncio.run(RPGDiceExtension.test(str(gm.id), acolyte["id"], "might"))
    assert installed["target"] == 30, "installed but not enabled on the campaign: still the template"

    _create(server, gm, "campaign_module", campaign_id=campaign["id"], content_module_id=module.module_id)
    enabled = asyncio.run(RPGDiceExtension.test(str(gm.id), acolyte["id"], "might"))
    assert enabled["target"] == 45, "the enabled module's trait wins over the template"


def test_a_line_without_a_committed_pack_runs_by_its_enabled_modules_rules(app: Any) -> None:
    """A system with no pack anywhere (a private line's) runs its campaign's tests by the rules of the
    module enabled on it (a bridge's rules step writes them in a pack's shape), and answers 422 before."""
    from zephyrex.extensions.rpg_systems.Packs import load_pack

    server = TestClient(app)
    registry = app.state.model_registry
    gm = create_user(server)
    made = server.post("/v1/game_system", json={"game_system": {"name": "Packless Test", "slug": "packless-test"}}, headers=_headers(gm))
    assert made.status_code == 201, made.text
    packless = made.json()["game_system"]["id"]
    shaped = {key: value for key, value in (load_pack("percentile-test") or {}).items() if key not in ("system", "$comment")}
    rules = {**shaped, "line": "packless", "characteristic_generation": {"roll": {"dice": "2d10", "base": 25}}, "starting_xp": 0}
    campaign = _create(server, gm, "campaign", name="Lantern", user_id=gm.id, game_system_id=packless)
    explorer = _create(server, gm, "person", name="Vell", kind="pc", user_id=gm.id, campaign_id=campaign["id"])
    with pytest.raises(Exception) as before:
        asyncio.run(RPGDiceExtension.test_options(str(gm.id), explorer["id"]))
    assert getattr(before.value, "status_code", None) == 422

    bundle = {"line": "packless", "system": "packless-test", "name": "Packless", "slug": "packless", "packs": [], "documents": [], "problems": []}
    module = install(registry, str(gm.id), bundle, rules=rules)
    _create(server, gm, "campaign_module", campaign_id=campaign["id"], content_module_id=module.module_id)
    options = asyncio.run(RPGDiceExtension.test_options(str(gm.id), explorer["id"]))
    assert options["system"] == "packless-test" and options["characteristics"]
