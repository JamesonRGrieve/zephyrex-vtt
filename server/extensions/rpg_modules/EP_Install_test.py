# SPDX-License-Identifier: AGPL-3.0-or-later
"""Installing a bridge bundle as a private module (and open content as the instance's), against a real server, with a synthetic bundle
(the real content is private): the module and its traits are the installing account's alone, every
document gets a record with its data, and a re-install is incremental (unchanged left alone, changed
updated in place, dropped removed). 130 documents, so a default page size couldn't hide any."""

import copy
from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.extensions.rpg_modules.BLL_RPGModules import ModuleRecordManager
from zephyrex.extensions.rpg_modules.Install import install, instance_wide_bundle, trait_kind
from zephyrex.lib.Environment import env
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


def _open_bundle(**extra: Any) -> dict[str, Any]:
    """Open content (as srd5e.py writes it): a few documents of their own names, so no other test's
    traits answer for them."""
    documents = [_document(index, id=f"OPEN{index:06d}", name=f"Open Feat {index}", hash=f"o{index}") for index in range(3)]
    return {
        "line": "openline", "system": "percentile-test", "name": "Open line", "slug": "openline", "kinds": KINDS,
        "packs": [], "documents": documents, "problems": [], **extra,
    }


def test_open_content_is_the_instances_and_takes_over_its_installers_own_copy(app: Any) -> None:
    """Operator, 2026-11-25: "The public domain stuff is instance wide" / "Private stuff is personal".
    A bundle saying "visibility": "instance" installs for every account; installed by an account that
    already had it as its own (installed before the ruling), it takes that module over in place."""
    client = TestClient(app)
    owner, other = create_user(client), create_user(client)
    registry = app.state.model_registry
    assert instance_wide_bundle(_open_bundle(visibility="instance")) and not instance_wide_bundle(_open_bundle())

    before = install(registry, str(owner.id), _open_bundle())
    assert not before.instance_wide
    feat = client.get("/v1/trait", params={"slug": "open-feat-0"}, headers=_headers(owner)).json()["traits"]
    assert len(feat) == 1 and feat[0]["created_by_user_id"] == str(owner.id)
    assert client.get("/v1/trait", params={"slug": "open-feat-0"}, headers=_headers(other)).json()["traits"] == []

    shared = install(registry, str(owner.id), _open_bundle(visibility="instance"), rules={"characteristics": []})
    assert shared.instance_wide and shared.adopted_from == str(owner.id)
    assert shared.module_id == before.module_id, "the same module, so campaigns that enabled it keep it"
    assert (shared.created, shared.removed) == (0, 0)
    seen = client.get("/v1/trait", params={"slug": "open-feat-0"}, headers=_headers(other)).json()["traits"]
    assert [one["id"] for one in seen] == [feat[0]["id"]], "the same trait, now every account's"
    assert seen[0]["created_by_user_id"] == str(env("SYSTEM_ID"))
    listed = client.get("/v1/content_module", params={"slug": "openline"}, headers=_headers(other)).json()["content_modules"]
    assert [one["id"] for one in listed] == [shared.module_id]
    records = ModuleRecordManager(requester_id=str(other.id), model_registry=registry).list(content_module_id=shared.module_id)
    assert len(records) == 3

    # Every account reads it; none changes it.
    current = client.get(f"/v1/trait/{feat[0]['id']}", headers=_headers(other))
    changed = client.put(
        f"/v1/trait/{feat[0]['id']}",
        json={"trait": {"name": "Mine now"}},
        headers={**_headers(other), "If-Match": current.headers.get("ETag", "*")},
    )
    assert changed.status_code in (403, 404), changed.text

    # Another account installing it again finds the instance's: one module, nothing taken over.
    again = install(registry, str(other.id), _open_bundle(visibility="instance"))
    assert again.module_id == shared.module_id and again.adopted_from is None and again.unchanged == 3
    # And any GM plays with it on their own campaign.
    campaign = client.post("/v1/campaign", json={"campaign": {"name": "Open table", "user_id": str(other.id)}}, headers=_headers(other))
    assert campaign.status_code == 201, campaign.text
    enabled = client.post(
        "/v1/campaign_module",
        json={"campaign_module": {"campaign_id": campaign.json()["campaign"]["id"], "content_module_id": shared.module_id}},
        headers=_headers(other),
    )
    assert enabled.status_code == 201, enabled.text


def test_an_explicit_flag_overrides_the_bundle(app: Any) -> None:
    client = TestClient(app)
    owner = create_user(client)
    registry = app.state.model_registry
    bundle = {**_open_bundle(), "slug": "flagline", "line": "flagline"}
    bundle["documents"] = [dict(one, name=one["name"].replace("Open", "Flag")) for one in bundle["documents"]]
    summary = install(registry, str(owner.id), bundle, instance_wide=True)
    assert summary.instance_wide and summary.adopted_from is None
    trait = client.get("/v1/trait", params={"slug": "flag-feat-1"}, headers=_headers(create_user(client))).json()["traits"]
    assert len(trait) == 1
