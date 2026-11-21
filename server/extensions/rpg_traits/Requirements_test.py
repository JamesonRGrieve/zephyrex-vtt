# SPDX-License-Identifier: AGPL-3.0-or-later
"""The hook-requirement rule against the wiki's own cases (contract/requirement-cases.json in the
pinned wiki checkout): its three-valued cases with no party, its checks decided against a party, the
hooks a requirement names, and every malformed shape refused."""

import json
from pathlib import Path
from typing import Any

import pytest

from zephyrex.extensions.rpg_traits.Requirements import RequirementError, evaluate, hook_ids

# The wiki is checked out beside vtt (deploy/fetch-frameworks.sh; vtt_app.EXTENSIONS_ROOTS).
CASES_FILE = Path(__file__).resolve().parents[4] / "zephyrex-rpg-wiki" / "contract" / "requirement-cases.json"
CASES: dict[str, Any] = json.loads(CASES_FILE.read_text())


def _named(cases: list[dict[str, Any]]) -> Any:
    return pytest.mark.parametrize("case", cases, ids=[case.get("name", str(i)) for i, case in enumerate(cases)])


@_named(CASES["cases"])
def test_without_a_party_a_check_needs_the_table(case: dict[str, Any]) -> None:
    got = evaluate(case["requires"], case["resolved"], self_resolved=case["self_resolved"])
    assert got.state == case["state"]


@_named(CASES["party_cases"])
def test_the_partys_options_decide_its_checks(case: dict[str, Any]) -> None:
    got = evaluate(case["requires"], case["resolved"], party=case["party"])
    assert got.state == case["state"]
    if case["state"] == "blocked" and not case["resolved"]:
        assert got.unmet_checks, "a blocked hook says which checks failed"


@_named(CASES["leaves"])
def test_the_hooks_a_requirement_names(case: dict[str, Any]) -> None:
    assert hook_ids(case["requires"]) == case["hooks"]


@_named(CASES["invalid"])
def test_malformed_requirements_are_refused(case: dict[str, Any]) -> None:
    with pytest.raises(RequirementError):
        evaluate(case["requires"], [], party=[])
