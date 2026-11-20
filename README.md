# zephyrex-vtt

A virtual tabletop built on the Zephyrex framework: map authoring, scenes, tokens,
character sheets, dice, combat and live multi-player play. It is planned for full
feature parity with Foundry VTT, Roll20 and Inkarnate.

It is one of three products in the Zephyrex RPG suite:

- [zephyrex-rpg-wiki](https://github.com/JamesonRGrieve/zephyrex-rpg-wiki): the world.
- **zephyrex-vtt**: the table.
- [zephyrex-rpg-ai](https://github.com/JamesonRGrieve/zephyrex-rpg-ai): AI characters and
  an AI game master.

The VTT reads the wiki (a scene sits on a location's map, and a token is a person).
The AI product drives the VTT.

Status: early alpha. The design is in [docs/DESIGN.md](docs/DESIGN.md). The server
currently carries the `rpg_state` extension, which OBJECT_PLAN §6 (in zephyrex-rpg-wiki)
splits into the VTT's `rpg_core`/`rpg_traits` and the wiki's `world_*` extensions.

## Layout

```
server/   FastAPI backend, a consumer of the zephyrex Python package
client/   Next.js frontend, a consumer of the zephyrex npm package
docs/     DESIGN.md
```

## Server extensions

| Extension   | Depends on                         | Provides |
|-------------|------------------------------------|----------|
| `rpg_state` | `genealogy`, `acl_rbac` (optional) | Campaign state: characters, factions, items, quests, locations, traits |

## Running

```bash
deploy/fetch-frameworks.sh <root>    # this repo + the five frameworks at deploy/frameworks.env's pins
deploy/compile-frameworks.sh <root>  # compile the framework packages the client installs
cd <root>/zephyrex-vtt/server && uv sync && uv run python vtt_app.py      # API on :2000
cd <root>/zephyrex-vtt/client && pnpm install --frozen-lockfile && pnpm dev   # UI on :1109 (lite)
```

The client takes the framework packages from the checkouts `fetch-frameworks.sh` lays out beside
the repository, injected from their compiled `dist` (`client/pnpm-workspace.yaml` overrides); the
server takes server-framework from the same layout (`server/pyproject.toml`, `[tool.uv.sources]`).
`VTT_VARIANT=saas` builds the client against the server instead of its own lite handlers.

## Tests

On a build runner, never the desktop:

```bash
cd <root>/zephyrex-vtt/server && uv run pytest
cd <root>/zephyrex-vtt/client && pnpm test
```

`contract/api-cases.json` holds the HTTP cases both back ends answer the same way; the client's
`src/contract.test.ts` runs them against the lite handlers and the server's
`extensions/rpg_state/EP_Contract_test.py` against the server.

## License

[AGPL-3.0-or-later](./server/LICENSE)
