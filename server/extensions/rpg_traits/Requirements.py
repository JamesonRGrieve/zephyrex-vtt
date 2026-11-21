# SPDX-License-Identifier: AGPL-3.0-or-later
"""A hook's requirement, evaluated: the wiki's rule (contract/requirement-cases.json, from the
operator's dh-campaign tracker), with the game-system checks it leaves to vtt decided against the
party: a character's traits (rpg_traits) are the options it holds.

A requirement is a hook id, ``{"all": [...]}``, ``{"any": [...]}`` or a check
``{"char": {dimension: slug | [slugs]}, "who": "any" | "all"}``. A node is met, unmet or (a check
nobody has decided) check:

- a hook id is met when that hook is resolved;
- a check, given the party, is met when any (``who: any``, the default) or every (``who: all``)
  party member holds, for every dimension it names, at least one of its slugs. With no party
  given it stays a check. An empty party passes no check, ``all`` included;
- ``all`` is unmet if any child is, else check if any child is, else met (an empty ``all`` is met);
- ``any`` is met if any child is, else check if any child is, else unmet (an empty ``any`` is
  unmet).

A hook's state: resolved if it is; else from its requirement (none is met): met → available,
check → needs_check, unmet → blocked. A check gates whether the party may attempt a hook, never a
roll's outcome.

The wiki holds the same rule without the party (wiki_shared/Requirements.py, and the lite edition's
requirements.ts); both editions answer the contract's cases.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Optional

Value = Literal["met", "unmet", "check"]
State = Literal["resolved", "available", "needs_check", "blocked"]
# A party member's held options: dimension → the slugs held (a homeworld, skills…).
Member = Mapping[str, Sequence[str]]

WHO = ("any", "all")
STATE_OF: dict[Value, State] = {"met": "available", "check": "needs_check", "unmet": "blocked"}


class RequirementError(ValueError):
    """A requirement that isn't one of the contract's shapes."""


@dataclass
class Evaluation:
    state: State
    # The checks that failed, as written in the requirement (for the GM to say why).
    unmet_checks: list[dict[str, Any]] = field(default_factory=list)


def _slugs(value: Any) -> list[str]:
    items = value if isinstance(value, list) else [value]
    if not items or not all(isinstance(item, str) and item for item in items):
        raise RequirementError(f"a check's value is a slug or a list of slugs, not {value!r}")
    return items


def _check(node: Mapping[str, Any]) -> tuple[dict[str, list[str]], str]:
    if set(node) - {"char", "who"}:
        raise RequirementError(f"a check holds char and who only, not {sorted(node)}")
    char = node["char"]
    if not isinstance(char, Mapping) or not char:
        raise RequirementError("a check's char names at least one dimension")
    who = node.get("who", "any")
    if who not in WHO:
        raise RequirementError(f"who is any or all, not {who!r}")
    return {str(dimension): _slugs(value) for dimension, value in char.items()}, who


def _holds(member: Member, wanted: Mapping[str, list[str]]) -> bool:
    return all(set(member.get(dimension, ())) & set(slugs) for dimension, slugs in wanted.items())


def _value(node: Any, resolved: set[str], party: Optional[Sequence[Member]], failed: list[dict[str, Any]]) -> Value:
    if isinstance(node, str):
        if not node:
            raise RequirementError("a hook id is never empty")
        return "met" if node in resolved else "unmet"
    if not isinstance(node, Mapping):
        raise RequirementError(f"a requirement is a hook id or an object, not {node!r}")
    if "char" in node:
        wanted, who = _check(node)
        if party is None:
            return "check"
        holders = [_holds(member, wanted) for member in party]
        met = bool(holders) and (all(holders) if who == "all" else any(holders))
        if not met:
            failed.append(dict(node))
        return "met" if met else "unmet"
    if len(node) != 1 or next(iter(node)) not in ("all", "any"):
        raise RequirementError(f"a requirement object is exactly one of all, any or char, not {sorted(node)}")
    key, children = next(iter(node.items()))
    if not isinstance(children, list):
        raise RequirementError(f"{key} takes a list")
    values = [_value(child, resolved, party, failed) for child in children]
    if key == "all":
        return "unmet" if "unmet" in values else "check" if "check" in values else "met"
    return "met" if "met" in values else "check" if "check" in values else "unmet"


def evaluate(
    requires: Any,
    resolved: Iterable[str],
    *,
    party: Optional[Sequence[Member]] = None,
    self_resolved: bool = False,
) -> Evaluation:
    """A hook's state from its requirement, the hooks already resolved and, to decide its checks,
    the party's held options (``None`` leaves them as needs_check)."""
    failed: list[dict[str, Any]] = []
    value: Value = "met" if requires is None else _value(requires, set(resolved), party, failed)
    if self_resolved:
        return Evaluation(state="resolved")
    return Evaluation(state=STATE_OF[value], unmet_checks=failed)


def hook_ids(requires: Any) -> list[str]:
    """The hooks a requirement names, in order, once each: the hook's dependency edges."""
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, str):
            if node not in found:
                found.append(node)
        elif isinstance(node, Mapping):
            for key in ("all", "any"):
                for child in node.get(key, ()):
                    walk(child)

    if requires is not None:
        walk(requires)
    return found
