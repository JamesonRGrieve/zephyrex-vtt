# SPDX-License-Identifier: AGPL-3.0-or-later
"""The VTT's migrations, run the way production runs them: the app boots on a fresh database
(conftest's temp DATABASE_PATH), the framework runs every extension's migrations in dependency order
(the wiki's, then rpg_systems and rpg_traits), and each table and injected column is there with its
real foreign key. Every vtt extension ships its own migrations, and what they build is exactly what
the models declare: the framework's create_all fallback never makes a vtt table."""

import glob
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from vtt_app import create

OWNED = {"game_systems", "traits", "derivative_traits", "person_traits"}
INJECTED = {"campaigns": {"game_system_id"}, "items": {"game_system_id"}}
FOREIGN_KEYS = {
    ("campaigns", "game_system_id"): "game_systems",
    ("items", "game_system_id"): "game_systems",
    ("traits", "game_system_id"): "game_systems",
    ("traits", "campaign_id"): "campaigns",
    ("person_traits", "person_id"): "persons",
    ("person_traits", "trait_id"): "traits",
}


# The extensions this repo owns (the wiki's are its own repo's concern).
VTT_EXTENSIONS = ("rpg_systems", "rpg_traits", "rpg_dice", "rpg_scene", "rpg_table", "rpg_modules")
EXTENSIONS_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def models() -> Iterator[Any]:
    """The app's model metadata, the tables the models declare."""
    app = create()
    with TestClient(app):
        pass
    yield app.state.model_registry.DB.manager.Base.metadata


@pytest.fixture(scope="module")
def database(models: Any) -> Iterator[sqlite3.Connection]:
    name = os.environ["DATABASE_NAME"]
    files = glob.glob(os.path.join(os.environ["DATABASE_PATH"], f"{name}*.db"))
    assert files, f"no database file for {name} in {os.environ['DATABASE_PATH']}"
    connection = sqlite3.connect(files[0])
    yield connection
    connection.close()


def test_the_vtts_tables_exist(database: sqlite3.Connection) -> None:
    tables = {row[0] for row in database.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert OWNED <= tables, OWNED - tables


def test_the_game_system_is_on_the_wikis_campaigns_and_items(database: sqlite3.Connection) -> None:
    for table, columns in INJECTED.items():
        present = {row[1] for row in database.execute(f"PRAGMA table_info({table})")}
        assert columns <= present, (table, columns - present)


def test_the_references_are_real_foreign_keys(database: sqlite3.Connection) -> None:
    for (table, column), target in FOREIGN_KEYS.items():
        keys = {(row[3], row[2]) for row in database.execute(f"PRAGMA foreign_key_list({table})")}
        assert (column, target) in keys, (table, column, target, keys)


def test_the_wikis_character_fields_are_on_persons(database: sqlite3.Connection) -> None:
    present = {row[1] for row in database.execute("PRAGMA table_info(persons)")}
    assert {"kind", "campaign_id", "user_id", "location_id"} <= present


@pytest.mark.parametrize("extension", VTT_EXTENSIONS)
def test_every_vtt_extension_ships_its_migrations(extension: str) -> None:
    versions = sorted((EXTENSIONS_DIR / extension / "migrations" / "versions").glob("*.py"))
    assert versions, f"{extension} has no migrations: its tables would come from the create_all fallback"


def test_the_migrated_schema_is_what_the_models_declare(models: Any, database: sqlite3.Connection) -> None:
    tables = [table for table in models.sorted_tables if table.info.get("extension") in VTT_EXTENSIONS]
    assert tables
    for table in tables:
        migrated = {row[1]: bool(row[3]) for row in database.execute(f"PRAGMA table_info({table.name})")}
        declared = {column.name: not column.nullable for column in table.columns}
        assert migrated == declared, (table.name, set(declared) ^ set(migrated))
        keys = {(row[3], row[2]) for row in database.execute(f"PRAGMA foreign_key_list({table.name})")}
        wanted = {(fk.parent.name, fk.column.table.name) for fk in table.foreign_keys}
        assert keys == wanted, (table.name, keys ^ wanted)
