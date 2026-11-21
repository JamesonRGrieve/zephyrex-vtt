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

Status: early alpha. The design is in [docs/DESIGN.md](docs/DESIGN.md). The server loads the
wiki's extensions (its `rpg_core` campaigns and characters, and its `world_*` places, factions,
items, journals and plot hooks) from a second extensions root, and adds the VTT's own below.

## Layout

```
server/   FastAPI backend, a consumer of the zephyrex Python package
client/   Next.js frontend, a consumer of the zephyrex npm package
docs/     DESIGN.md
```

## Server extensions

| Extension | Depends on | Provides |
|---|---|---|
| `rpg_systems` | `rpg_core`, `world_inventory` | Game systems (on the wiki's campaigns and items) |
| `rpg_traits` | `rpg_systems`, `rpg_core`, `genealogy`, `world_narrative` | Traits, derived traits, the traits a character holds, and plot hooks' character checks (`check_requirements`) |
| `rpg_dice` | `rpg_traits`, `rpg_core`, `world_inventory`, `world_spatial` | Dice and checks, rolled on the server |
| `rpg_scene` | `rpg_core`, `genealogy` | Scenes and maps (zephyr-cartography's model), tokens, walls, lights, what a token sees |
| `rpg_table` | `conversations`, `rpg_core`, `genealogy` | Multiplayer tables: seats, whispers, lines |

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
`extensions/rpg_systems/EP_Contract_test.py` against the server.

## License

[AGPL-3.0-or-later](./server/LICENSE)
