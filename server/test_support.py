# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers for vtt's server tests: the synthetic percentile-test system (test_packs/), made once per
database as the framework's SYSTEM user with its characteristic and skill templates, as a seed makes a
catalog system (readable by everyone signed in)."""

from typing import Any

from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_systems.BLL_RPGSystems import GameSystemManager  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_systems.Packs import load_pack  # type: ignore[import-not-found]
from zephyrex.extensions.rpg_traits.BLL_RPGTraits import TraitManager  # type: ignore[import-not-found]
from zephyrex.lib.Environment import env

SLUG = "percentile-test"


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def percentile_system(server: TestClient, user: Any = None) -> dict[str, Any]:
    """The percentile-test game system (made on first use) with its trait templates."""
    registry = server.app.state.model_registry  # type: ignore[attr-defined]
    systems = GameSystemManager(requester_id=env("ROOT_ID"), model_registry=registry)
    found = systems.list(slug=SLUG)
    if found:
        return found[0].model_dump()
    as_system = GameSystemManager(requester_id=env("SYSTEM_ID"), model_registry=registry)
    system = as_system.create(name="Percentile Test", slug=SLUG)
    traits = TraitManager(requester_id=env("SYSTEM_ID"), model_registry=registry)
    pack = load_pack(SLUG) or {}
    for kind, entries in (("characteristic", pack["characteristics"]), ("skill", pack["skills"])):
        for one in entries:
            traits.create(name=one["name"], slug=one["slug"], kind=kind, game_system_id=system.id)
    made: dict[str, Any] = system.model_dump()
    return made


def template(server: TestClient, user: Any, system_id: str, slug: str) -> str:
    """A trait template's id by its slug in a system."""
    found = server.get("/v1/trait", params={"slug": slug, "game_system_id": system_id}, headers=_headers(user)).json()["traits"]
    assert len(found) == 1, found
    return str(found[0]["id"])
