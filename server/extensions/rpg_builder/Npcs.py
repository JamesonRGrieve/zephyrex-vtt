# SPDX-License-Identifier: AGPL-3.0-or-later
"""Picking a compendium stat block for an NPC from their role and a line about them (rpg_builder's
npc_sheet). Pure. The blocks and their numbers are the pack's (dnd-5e: the SRD's humanoids); this
only chooses one, by the words of the role and hint against each block's name, and a few common
roles the SRD names differently (a barkeeper is a Commoner, a watchman a Guard). With no match, the
pack's generic block (the Commoner), marked as the template.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Literal

# Common roles → the SRD block that plays them (vtt's matching, not rules data).
ROLE_WORDS: dict[str, str] = {
    "barkeep": "commoner", "barkeeper": "commoner", "bartender": "commoner", "innkeeper": "commoner",
    "tavern": "commoner", "keeper": "commoner", "merchant": "commoner", "shopkeeper": "commoner",
    "farmer": "commoner", "villager": "commoner", "peasant": "commoner", "servant": "commoner",
    "watchman": "guard", "watch": "guard", "soldier": "guard", "sentry": "guard", "guardsman": "guard",
    "brigand": "bandit", "thief": "bandit", "outlaw": "bandit", "highwayman": "bandit", "robber": "bandit",
    "thug": "tough", "bruiser": "tough", "enforcer": "tough", "bouncer": "tough", "heavy": "tough",
    "lord": "noble", "lady": "noble", "aristocrat": "noble", "courtier": "noble", "duke": "noble",
    "cleric": "priest", "acolyte": "priest-acolyte", "monk": "priest-acolyte", "templar": "knight",
    "mercenary": "warrior-veteran", "veteran": "warrior-veteran", "sellsword": "warrior-veteran",
    "infantry": "warrior-infantry", "militia": "warrior-infantry", "wizard": "mage", "sorcerer": "mage",
    "hunter": "scout", "ranger": "scout", "tracker": "scout", "agent": "spy", "informant": "spy",
    "cult": "cultist", "cultist": "cultist", "fanatic": "cultist-fanatic", "killer": "assassin", "sailor": "pirate",
}


def words(text: str) -> list[str]:
    return re.findall(r"[a-z]+", text.lower())


def pick(blocks: Sequence[Mapping[str, Any]], generic: str, role: str, hint: str = "") -> tuple[Mapping[str, Any], Literal["compendium", "template"]]:
    """The block whose name best matches the role (then the hint), or the generic block."""
    by_slug = {block["slug"]: block for block in blocks}
    role_words, hint_words = words(role), words(hint)
    scores: dict[str, int] = {}
    for weight, said in ((3, role_words), (1, hint_words)):
        for word in said:
            for block in blocks:
                if word in words(block["name"]) or word == block["slug"]:
                    scores[block["slug"]] = scores.get(block["slug"], 0) + weight * 2
            mapped = ROLE_WORDS.get(word)
            if mapped in by_slug:
                scores[mapped] = scores.get(mapped, 0) + weight
    if scores:
        best = max(scores.items(), key=lambda item: (item[1], -float(by_slug[item[0]].get("cr") or 0)))[0]
        return by_slug[best], "compendium"
    if generic not in by_slug:
        raise LookupError(f"the pack's generic NPC {generic!r} isn't among its blocks")
    return by_slug[generic], "template"
