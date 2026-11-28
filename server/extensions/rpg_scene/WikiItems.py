# SPDX-License-Identifier: AGPL-3.0-or-later
"""The wiki's item abilities (rpg_core's Items, wiki 13ceb82+: items_at, items_carried, take_item,
spend_item, drop_item), reached the way one product reaches another: through loaded_ability, never
its internals. The wiki owns where a thing is and who carries it (EntityInventory); the VTT draws it
on the map and applies what the rules do with it."""

from __future__ import annotations

import inspect
from typing import Any, Optional


def wiki_items(model_registry: Any, ability: str, requester_id: str, **arguments: Any) -> Optional[dict[str, Any]]:
    """The answer of the wiki's ``ability`` for ``requester_id``, or None when the wiki doesn't offer
    it (an older wiki). A backend-routed ability's answer is awaited here, from synchronous code.
    The server calls these as SYSTEM, never ROOT: a ROOT read includes soft-deleted rows, so a potion
    drunk to the last would still be carried."""
    from zephyrex.extensions.AbstractExtensionProvider import loaded_ability

    call = loaded_ability(model_registry, "rpg_core", ability)
    if call is None:
        return None
    answer = call(model_registry, str(requester_id), **arguments)
    if inspect.isawaitable(answer):
        from zephyrex.logic.AbstractLogicManager.manager import _cache_sync_run

        answer = _cache_sync_run(answer)
    return dict(answer or {})


def carried_by(model_registry: Any, requester_id: str, person_id: str) -> Optional[list[dict[str, Any]]]:
    """What a person carries (items_carried's shape), or None on a wiki without the ability."""
    answer = wiki_items(model_registry, "items_carried", requester_id, person_ids=[str(person_id)])
    if answer is None:
        return None
    return [dict(one) for one in (answer.get("items") or {}).get(str(person_id), [])]
