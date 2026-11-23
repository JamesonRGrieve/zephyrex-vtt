"""Test configuration for zephyrex-vtt.

Sets up the extensions roots (this product's, then the wiki's pinned checkout; vtt_app.py) so test
imports like ``from zephyrex.extensions.rpg_dice.Dice import ...`` or the wiki's
``zephyrex.extensions.rpg_core...`` resolve.
"""

import os
import tempfile
from pathlib import Path

import pytest

_project_root = Path(__file__).resolve().parent
# This product's extensions, then the wiki's pinned checkout beside the repository (vtt_app.py).
_roots = [
    _project_root / "extensions",
    _project_root.parent.parent / "zephyrex-rpg-wiki" / "server" / "extensions",
]

# The roots the framework searches, in order (os.pathsep-joined, as EXTENSIONS_PATH takes them).
os.environ.setdefault("EXTENSIONS_PATH", os.pathsep.join(str(root) for root in _roots))
os.environ.setdefault("DATABASE_TYPE", "sqlite")
# One database per xdist worker, assigned (never setdefault): the controller loads this file
# first, and a setdefault would leave every worker on its name, sharing and seeding one database
# (SOP Stack Standards → Python §11).
os.environ["DATABASE_NAME"] = f"test_zephyrex_vtt_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}"
os.environ.setdefault("DATABASE_PATH", tempfile.mkdtemp(prefix="zephyrex-vtt-db-"))
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-32-bytes-or-more-aaaaaa")
os.environ.setdefault("SEED_DATA", "true")
# The tests' synthetic rules pack (test_packs/percentile-test.json): the d100 engine runs on it, as a
# private instance's own packs would load from its VTT_PACKS_DIRS.
os.environ.setdefault("VTT_PACKS_DIRS", str(_project_root / "test_packs"))

import zephyrex.extensions  # noqa: E402

# Every root on the zephyrex.extensions namespace path, in order, ahead of the bundled extensions.
for _root in reversed(_roots):
    if str(_root) not in zephyrex.extensions.__path__:
        zephyrex.extensions.__path__ = [str(_root), *zephyrex.extensions.__path__]


@pytest.fixture(autouse=True)
def _reset_rate_limit_counts_between_tests() -> None:
    """Each test starts with no sign-ins counted against the rate limits, as in the framework's own
    conftest: every test signs in from the same test-client address, so earlier tests' sign-ins
    (10 a minute) would refuse later ones."""
    from zephyrex.lib.InboundSecurity import reset_rate_limit_counts

    reset_rate_limit_counts()
