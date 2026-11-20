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
cd server && pip install -e ".[dev]" && python app.py     # API on :2000
cd client && pnpm install && pnpm dev                       # UI on :1109
```

The client depends on the framework packages checked out as siblings (`../client-framework`,
`../auth`, `../zod2gql`, `../dynamic-form`) through `file:` paths.

## Tests

```bash
cd server && python -m pytest extensions/
```

## License

[AGPL-3.0-or-later](./server/LICENSE)
