# Zephyrex VTT server

Consumer project built on the zephyrex server framework. Provides Zephyrex VTT’s domain extensions — the framework handles all infrastructure.

## Architecture

This is a **consumer project**, not a framework fork. It depends on `zephyrex[auth-session,genealogy]` from the server-framework checkout beside the repository, at the commit `deploy/frameworks.env` pins (`deploy/fetch-frameworks.sh` lays it out; `uv.lock` is committed), and provides only domain-specific extensions:

- **genealogy** — person/family tree models for RPG characters (bundled in the framework)
- **rpg_state** — character state, inventory, progression tracking

## Commands

```bash
uv sync                      # Install from uv.lock, with the dev group
uv run python vtt_app.py     # Boot the server on port 2000
uv run pytest                # Run extension tests (on a build runner, never the desktop)
```

## How it works

`vtt_app.py` calls `zephyrex.run(extensions="auth_session,genealogy,rpg_state", extensions_path="./extensions")`. The framework:

1. Discovers `BLL_*.py` models in `./extensions/<name>/`
2. Auto-generates SQLAlchemy tables (via `create_all` fallback — no Alembic migrations needed for dev)
3. Auto-generates REST CRUD endpoints at `/v1/<resource>`
4. Auto-generates GraphQL schema
5. Provides core auth (User, Team, Role, Session) out of the box
