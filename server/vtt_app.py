"""Zephyrex VTT: a consumer app built on the zephyrex server framework.

Virtual tabletop on the Zephyrex framework: maps, scenes, tokens, sheets, dice, combat, live play.
All infrastructure (auth, DB, REST, GraphQL, migrations) comes from the
framework; this project only provides its own domain extensions.

    python vtt_app.py          # boot with uvicorn
    python -c "from vtt_app import create; create()"  # programmatic
"""
import os
from pathlib import Path

os.environ.setdefault("APP_NAME", "Zephyrex VTT")
os.environ.setdefault("DATABASE_TYPE", "sqlite")
os.environ.setdefault("DATABASE_NAME", "zephyrex_vtt")
os.environ.setdefault("SEED_DATA", "true")
os.environ.setdefault("JWT_SECRET", "dev-only-change-in-production-32chars!")

from zephyrex import run

_SERVER = Path(__file__).resolve().parent

# Where extensions are found, in order: this product's own, then the wiki's, pinned beside the
# repository like the frameworks (deploy/frameworks.env WIKI_REF; deploy/fetch-frameworks.sh). The
# same name in two roots fails boot (server-framework's DuplicateExtensionError).
EXTENSIONS_ROOTS = [
    str(_SERVER / "extensions"),
    str(_SERVER.parent.parent / "zephyrex-rpg-wiki" / "server" / "extensions"),
]

# From the framework: auth_session (signed-in sessions; the hosted edition has accounts), genealogy
# (persons, the character table), acl_rbac (conversations requires it: it grants participants their
# access) and conversations (tables and whispers). From the wiki: places,
# factions, items and rpg_core (campaigns, the character fields). The VTT's own: rpg_systems (game
# systems), rpg_traits, rpg_state (hooks, until the wiki takes them), rpg_dice (A21), rpg_scene
# (A23) and rpg_table (multiplayer tables).
EXTENSIONS = ",".join(
    [
        "auth_session",
        "genealogy",
        "acl_rbac",
        "conversations",
        "world_spatial",
        "world_social",
        "world_inventory",
        "rpg_core",
        "rpg_systems",
        "rpg_traits",
        "rpg_state",
        "rpg_dice",
        "rpg_scene",
        "rpg_table",
    ]
)

if __name__ == "__main__":
    run(
        extensions=EXTENSIONS,
        extensions_path=EXTENSIONS_ROOTS,
        port=2000,
    )


def create():
    """Return a FastAPI app instance for testing or ASGI mounting."""
    from zephyrex import instance, set_extensions_root

    set_extensions_root(EXTENSIONS_ROOTS)
    return instance(extensions=EXTENSIONS)
