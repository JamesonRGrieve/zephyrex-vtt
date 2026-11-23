# SPDX-License-Identifier: AGPL-3.0-or-later
"""Installing a bridge bundle as a private module, against a real server, with a synthetic bundle
(the real content is private): the module and its traits are the installing account's alone, every
document gets a record with its data, and a re-install is incremental (unchanged left alone, changed
updated in place, dropped removed). 130 documents, so a default page size couldn't hide any."""

import copy
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_modules.BLL_RPGModules import ModuleRecordManager
from zephyrex.extensions.rpg_modules.Install import install, trait_kind
from zephyrex.testing.factories import create_user

from vtt_app import create

TALENTS = 120
# The kinds a bundle carries (a bridge writes them for its source system): talents and skills are
# traits, an origin document takes its kind from its step.
KINDS = {
    "types": {"talent": "talent", "skill": "skill"},
    "fields": {"origin": {"path": ["step"], "map": {"homeland": "homeland"}, "default": "origin", "slug_unknown": True}},
}


def _document(index: int, **changes: Any) -> dict[str, Any]:
    document = {
        "line": "testline",
        "id": f"TALENT{index:010d}",
        "name": f"Talent {index}",
        "foundry_class": "Item",
        "type": "talent",
        "pack": "test-talents",
        "category": "talents",
        "homebrew": False,
        "conversion": False,
        "img": None,
        "source": {"provenance": "raw", "book": "Test Book", "page": "120"},
        "system": {"description": {"value": f"<p>Talent {index}</p>"}, "tier": 1},
        "items": [],
        "hash": f"h{index}",
    }
    document.update(changes)
    return document


def _bundle() -> dict[str, Any]:
    documents = [_document(index) for index in range(TALENTS)]
    documents.append(
        _document(
            900,
            name="Feral World",
            type="origin",
            system={"step": "homeland", "description": {"value": "<p>Wild</p>"}},
            hash="hw",
        )
    )
    documents.append(_document(901, name="Crossbow", type="weapon", system={"damage": "1d10+3"}, hash="w"))
    for index in range(8):
        documents.append(
            _document(950 + index, name=f"Port {index}", homebrew=True, conversion=True, hash=f"p{index}")
        )
    return {
        "line": "testline", "system": "percentile-test", "name": "Test line", "slug": "testline", "kinds": KINDS,
        "packs": ["test-talents"], "documents": documents, "problems": [],
    }


@pytest.fixture(scope="module")
def app() -> Iterator[Any]:
    application = create()
    with TestClient(application):
        yield application


def _headers(user: Any) -> dict[str, str]:
    return {"Authorization": f"Bearer {user.jwt}"}


def test_the_kinds_follow_the_bundles_scheme() -> None:
    assert trait_kind(_document(1), KINDS) == "talent"
    assert trait_kind(_document(1, type="origin", system={"step": "homeland"}), KINDS) == "homeland"
    assert trait_kind(_document(1, type="origin", system={"step": "Far Shore"}), KINDS) == "far-shore", "an unknown step, slugged"
    assert trait_kind(_document(1, type="weapon"), KINDS) is None
    assert trait_kind(_document(1, type="skill"), KINDS) == "skill"
    assert trait_kind(_document(1, type="skill", conversion=True), KINDS) is None
    assert trait_kind(_document(1, foundry_class="Actor", type="npc"), KINDS) is None
    assert trait_kind(_document(1)) is None, "no scheme, no traits"


def test_a_feat_takes_its_kind_from_what_it_belongs_to() -> None:
    """A 5e SRD bundle's scheme (as tools/foundry-bridge/srd5e.py writes it): origins and class, spells,
    and each feat by what it belongs to (system.type.value)."""
    srd = {
        "types": {"race": "species", "background": "background", "class": "class", "subclass": "subclass", "spell": "spell"},
        "fields": {"feat": {"path": ["type", "value"], "map": {"class": "class-feature", "race": "species-trait", "feat": "feat"}, "default": "feat"}},
    }

    def five(type_: str, **system: Any) -> str | None:
        return trait_kind({"line": "srd5e", "foundry_class": "Item", "type": type_, "system": system}, srd)

    assert five("race") == "species"
    assert five("background") == "background"
    assert (five("class"), five("subclass")) == ("class", "subclass")
    assert five("feat", type={"value": "class"}) == "class-feature"
    assert five("feat", type={"value": "race"}) == "species-trait"
    assert five("feat", type={"value": "feat"}) == "feat"
    assert five("spell") == "spell", "a known spell is a trait, so the sheet lists it under abilities"
    assert five("weapon") is None


def test_a_module_is_its_owners_alone_and_reinstalls_incrementally(app: Any) -> None:
    client = TestClient(app)
    owner, other = create_user(client), create_user(client)
    registry = app.state.model_registry
    bundle = _bundle()
    rules = {
        "characteristics": [
            {"slug": "might", "key": "might", "name": "Might", "short": "MT"},
            {"slug": "grace", "key": "grace", "name": "Grace", "short": "GR"},
        ],
        "resources": [{"slug": "wounds", "key": "wounds", "name": "Wounds"}, {"slug": "fate", "key": "fate", "name": "Fate"}],
    }
    first = install(registry, str(owner.id), bundle, system_ref="sys1", content_ref="c1", rules=rules)
    assert (first.created, first.updated, first.unchanged, first.removed) == (len(bundle["documents"]) + 4, 0, 0, 0)
    assert first.traits == TALENTS + 1 + 8 + 4 and first.kinds["homeland"] == 1
    assert first.kinds["characteristic"] == 2 and first.kinds["resource"] == 2

    records = ModuleRecordManager(requester_id=str(owner.id), model_registry=registry).list(
        content_module_id=first.module_id
    )
    assert len(records) == len(bundle["documents"]) + 4
    crossbow = next(row for row in records if row.source_id == "TALENT0000000901")
    assert crossbow.entity_id is None and crossbow.data == {"damage": "1d10+3"}
    port = next(row for row in records if row.source_id == "TALENT0000000950")
    assert port.homebrew and port.conversion

    mine = client.get("/v1/trait", params={"slug": "feral-world"}, headers=_headers(owner)).json()["traits"]
    assert [one["kind"] for one in mine] == ["homeland"]
    theirs = client.get("/v1/trait", params={"slug": "feral-world"}, headers=_headers(other)).json()["traits"]
    assert theirs == [], "another account never sees a private module's traits"
    assert client.get("/v1/content_module", headers=_headers(other)).json()["content_modules"] == []

    changed = copy.deepcopy(bundle)
    changed["documents"][0] = _document(0, name="Talent Zero", hash="h0-new")
    del changed["documents"][1]
    second = install(registry, str(owner.id), changed, system_ref="sys2", content_ref="c2", rules=rules)
    assert second.module_id == first.module_id
    assert (second.created, second.updated, second.removed) == (0, 1, 1)
    assert second.unchanged == len(changed["documents"]) - 1 + 4
    # The owner's own trait (a system's public templates of the same slug would also match).
    skill = client.get("/v1/trait", params={"slug": "might"}, headers=_headers(owner)).json()["traits"]
    assert [one["kind"] for one in skill if one["created_by_user_id"] == str(owner.id)] == ["characteristic"]
    renamed = client.get("/v1/trait", params={"slug": "talent-zero"}, headers=_headers(owner)).json()["traits"]
    assert len(renamed) == 1
    gone = client.get("/v1/trait", params={"slug": "talent-1"}, headers=_headers(owner)).json()["traits"]
    assert gone == []


def test_an_origin_steps_record_keeps_the_systems_normalized_reading() -> None:
    from zephyrex.extensions.rpg_modules.Install import _data

    origin = {"step": "homeland", "grants": {"skills": ["Swimming"]}}
    assert _data({"system": {"step": "homeland"}, "origin": origin}) == {"step": "homeland", "_origin": origin}
    assert _data({"system": {"tier": 1}}) == {"tier": 1}
