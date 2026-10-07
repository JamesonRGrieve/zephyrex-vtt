"""rpg_state extension definition.

Hard-depends on ``genealogy`` (widens PersonModel and RelationshipModel
via @extension_model). ``rpg_log`` depends on rpg_state for trait /
item / location references.
"""

from typing import ClassVar

from zephyrex.extensions.AbstractExtensionProvider import (
    AbstractStaticExtension,
)
from zephyrex.lib.Dependencies import Dependencies, EXT_Dependency


class RPGStateExtension(AbstractStaticExtension):
    name: ClassVar[str] = "rpg_state"
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = (
        "Present-state schema for RPG campaigns (system-agnostic). "
        "Widens genealogy.PersonModel to serve as the character table."
    )
    dependencies: ClassVar[Dependencies] = Dependencies(
        [
            EXT_Dependency(
                name="genealogy",
                friendly_name="Genealogy",
                optional=False,
                reason="rpg_state widens genealogy's Person and Relationship models",
            ),
            EXT_Dependency(
                name="acl_rbac",
                friendly_name="ACL / RBAC",
                optional=True,
                reason="Per-row visibility for GM-secret NPCs, quests and lore",
            ),
        ]
    )
