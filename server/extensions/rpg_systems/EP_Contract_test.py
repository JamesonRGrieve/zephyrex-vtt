# SPDX-License-Identifier: AGPL-3.0-or-later
"""The SaaS server against contract/api-cases.json, the cases the lite route handlers answer too
(client/src/contract.test.ts): each case is one signed-in person's requests, in order."""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from zephyrex.testing.factories import create_user

from vtt_app import create

CASES = json.loads((Path(__file__).resolve().parents[3] / "contract" / "api-cases.json").read_text())["cases"]
SAVED_REFERENCE = re.compile(r"\{(\w+)\.(id|etag)\}")


@pytest.fixture(scope="module")
def server() -> Iterator[TestClient]:
    yield TestClient(create())


def _fill(value: Any, saved: dict[str, dict[str, str]]) -> Any:
    """Replaces '{name.id}' and '{name.etag}' in every string inside ``value``."""
    if isinstance(value, str):
        return SAVED_REFERENCE.sub(lambda match: saved[match.group(1)][match.group(2)], value)
    if isinstance(value, list):
        return [_fill(item, saved) for item in value]
    if isinstance(value, dict):
        return {key: _fill(item, saved) for key, item in value.items()}
    return value


def _subset(expected: Any, actual: Any) -> bool:
    """True when every key ``expected`` names is in ``actual`` with that value."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(key in actual and _subset(item, actual[key]) for key, item in expected.items())
    return bool(expected == actual)


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_contract_case(server: TestClient, case: dict[str, Any]) -> None:
    person = create_user(server)
    saved: dict[str, dict[str, str]] = {}
    for raw in case["requests"]:
        request = _fill(raw, saved)
        headers = {"Authorization": f"Bearer {person.jwt}", **request.get("headers", {})}
        response = server.request(request["method"], request["path"], json=request.get("body"), headers=headers)
        answer = None if response.status_code == 204 else response.json()
        expected = request["expect"]
        assert response.status_code == expected["status"], f"{request['method']} {request['path']}: {response.text}"
        if "body" in expected:
            assert _subset(expected["body"], answer), f"{request['method']} {request['path']}: {answer}"
        if "listed" in expected:
            assert expected["listed"]["id"] in [one["id"] for one in answer[expected["listed"]["key"]]]
        if "save" in raw and answer is not None:
            record = next(item for item in answer.values() if isinstance(item, dict) and "id" in item)
            saved[raw["save"]] = {"id": record["id"], "etag": response.headers.get("ETag", "")}
