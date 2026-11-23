# zephyrex-vtt

A virtual tabletop for running tabletop RPG campaigns in the browser: scenes and maps, tokens,
character sheets, dice rolled on the server, encounters and initiative, and live multi-player play.

[![License: AGPL-3.0-or-later](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](./server/LICENSE)

zephyrex-vtt is the table in the Zephyrex RPG suite. The world lives in
[zephyrex-rpg-wiki](https://github.com/JamesonRGrieve/zephyrex-rpg-wiki): its campaigns, characters,
places and items are what the VTT puts on the map. [zephyrex-rpg-ai](https://github.com/JamesonRGrieve/zephyrex-rpg-ai)
composes both and plays NPCs and the game master through the VTT's abilities. The VTT can also
run on its own, with the wiki's extensions loaded beside its own.

Rules come from rules packs, never from code. The public repository carries one game system, the
fifth-edition SRD 5.2 (CC-BY-4.0), as `srd-5e`. Other systems are installed by their owners on a
private instance.

## Contents

- [Status](#status)
- [Requirements](#requirements)
- [Setup](#setup)
- [Configuration](#configuration)
- [Game systems and packs](#game-systems-and-packs)
- [Server extensions](#server-extensions)
- [Abilities other products call](#abilities-other-products-call)
- [The play UI](#the-play-ui)
- [Tools](#tools)
- [Development](#development)
- [Repository layout](#repository-layout)
- [Content and licensing](#content-and-licensing)
- [License](#license)

## Status

Alpha. The design and its decisions are in [docs/DESIGN.md](docs/DESIGN.md). What works today:

- Scenes with walls, doors, lights and tokens; what each token can see, decided on the server; a
  phone-first map with tap-to-move, pinch zoom, a measure tool, and door toggles for the GM.
- Dice and tests rolled on the server under the campaign's rules pack (5e D20 Tests with Advantage
  and Disadvantage, or a percentile pack), with a dice rack, a result card, a roll history and 3D
  dice that land on the server's values.
- Character sheets, the creation steps of a pack (class, background and species; ability scores by
  standard array, point buy or roll), NPC sheets from the SRD's stat blocks, and starting sheets
  for a setting's pregenerated characters (`build_pregen`).
- Encounters: initiative, rounds and turns, and weapon attacks resolved on the server.
- Multiplayer tables: characters seated in a conversation, whispers and lines.

Spells and spell slots, reach from the map, pings and fog of war are next.

## Requirements

- Python 3.11 or later and [uv](https://docs.astral.sh/uv/)
- Node.js 24 and pnpm
- The Zephyrex frameworks at the commits pinned in [deploy/frameworks.env](deploy/frameworks.env)
  (server-framework, client-framework, auth, dynamic-form, zod2gql, and the wiki). The deploy
  scripts fetch them; nothing is installed from a registry.

## Setup

Lay out a workspace with this repository and the frameworks at their pins, compile the framework
packages, then run the server and the client:

```bash
deploy/fetch-frameworks.sh ~/vtt-root
deploy/compile-frameworks.sh ~/vtt-root
cd ~/vtt-root/zephyrex-vtt/server && uv sync && uv run python vtt_app.py
```

```bash
cd ~/vtt-root/zephyrex-vtt/client && pnpm install --frozen-lockfile && pnpm dev
```

The API listens on port 2000 and the UI on port 1109. The client takes the framework packages from
the checkouts beside the repository (`client/pnpm-workspace.yaml` overrides); the server takes
server-framework from the same layout (`server/pyproject.toml`, `[tool.uv.sources]`). After the
client's install, `deploy/compile-wiki.sh ~/vtt-root` builds the wiki's client package into it.

## Configuration

| Variable | Where | What it does |
|---|---|---|
| `VTT_VARIANT` | client | `lite` (the default) runs the client on its own handlers; `saas` builds it against the server |
| `VTT_PACKS_DIRS` | server | More directories to load rules packs from, separated by `:`; a private instance points it at its own packs |
| `DATABASE_NAME`, `DATABASE_PATH` | server | The database the framework opens (see server-framework) |
| `JWT_SECRET` | server | Signs the session tokens |

## Game systems and packs

A game system is a row (`rpg_systems`) with a slug, and its rules are a pack: a JSON file named
after the slug in `server/extensions/rpg_systems/packs/`, or in a directory on `VTT_PACKS_DIRS`. A
campaign takes the rules of its system's pack; a setting with exactly one packed system lends it to
campaigns made without one.

`srd-5e.json` is generated from the SRD's own text by `tools/foundry-bridge/srd5e.py`, never written
by hand. Every rule it carries is parsed from a stated sentence of the SRD (the D20 Test, the
Typical Difficulty Classes, the Proficiency Bonus table, Advantage, the attack and damage rules,
the base Armor Class, the Standard Array by Class), and the bridge stops if the text no longer says
it. It also carries the SRD's 37 simple and martial weapons and its humanoid stat blocks.

A system without a pack runs dice formulas only. A private line's rules arrive as a content module
(`rpg_modules`) installed by its owner, which a campaign then enables.

## Server extensions

Each extension lives in `server/extensions/<name>/` with its own manifest and Alembic history.

| Extension | Depends on | Provides |
|---|---|---|
| `rpg_systems` | `rpg_core`, `world_inventory` | Game systems, their packs, and the system of a campaign |
| `rpg_traits` | `rpg_systems`, `rpg_core`, `genealogy`, `world_narrative` | Traits (abilities, skills, weapons, resources), what each character holds, and plot hooks' character checks |
| `rpg_modules` | `rpg_systems`, `rpg_traits`, `rpg_core` | Private rules and content modules, owned by the account that installs them |
| `rpg_dice` | `rpg_traits`, `rpg_core`, `rpg_modules`, `world_inventory`, `world_spatial` | Dice notation, roll tables, tests and checks rolled on the server |
| `rpg_builder` | `rpg_dice`, `rpg_traits`, `genealogy` | Character creation by the pack's rules, NPC sheets, pregens' starting sheets |
| `rpg_scene` | `rpg_core`, `world_spatial`, `genealogy` | Scenes, tokens, walls, lights and what each token sees |
| `rpg_combat` | `rpg_core`, `rpg_dice`, `rpg_scene`, `genealogy` | Encounters, initiative, turns, and attacks resolved on the server |
| `rpg_table` | `conversations`, `rpg_core`, `rpg_dice`, `genealogy` | Multiplayer tables: seats, whispers and lines |

The `rpg_core`, `world_*` and `conversations` extensions are the wiki's and server-framework's,
loaded from a second extensions root.

## Abilities other products call

zephyrex-rpg-ai drives the table through abilities, each a REST route too. The ones it relies on
most:

| Ability | Route | What it does |
|---|---|---|
| `scene_tokens` | `GET /v1/scene/{id}/tokens` | The tokens on a scene, as the GM or a member sees them |
| `place_person` | `POST /v1/scene/{id}/place` | A character onto a scene, beside another or at its entry |
| `move_token_to_scene` | `POST /v1/scene_token/{id}/move_scene` | A token to another scene of the campaign |
| `remove_person_from_scene` | `POST /v1/scene/{id}/remove` | A character's token off a scene, their wiki location left as it is |
| `test` | `POST /v1/dice/test` | A test under the campaign's pack, with Advantage where the pack has it |
| `npc_sheet_options` | `POST /v1/builder/npc-options` | What the pack can build an NPC from |
| `npc_sheet` | `POST /v1/builder/npc-sheet` | An NPC's sheet from a named option or the closest stat block |
| `build_pregen` | `POST /v1/builder/pregen` | A setting pregen's starting sheet; open choices are reported, not guessed |
| `combat_options` | `POST /v1/encounter/{id}/options` | A combatant's legal actions and targets now |
| `take_combat_action` | `POST /v1/encounter/{id}/action` | One of those actions, resolved on the server |

The GM-only abilities answer anyone else as if the record weren't there.

## The play UI

`client/packages/vtt-play` (`@zephyrex/vtt-play`) is the play UI as a package any Zephyrex app can
embed; rpg-ai composes it. It exports the scene view and map controls, the dice tray and its replay,
the character sheet, the creation steps, the seat list, the combat order, inventory and loot. Each
component has a Storybook story with a `play` test in `client/src/components/`.

## Tools

| Tool | What it does |
|---|---|
| `tools/foundry-bridge/srd5e.py` | Writes the `srd-5e` pack and the SRD content bundle from the open fifth-edition Foundry system's packs |
| `tools/foundry-bridge/install.py` | Installs a bridge's bundle as one account's private content module |
| `tools/pregen-backfill/backfill.py` | Builds every setting pregen's starting sheet; a dry run unless `--write` |
| `tools/vault-import/import.py` | Imports character sheets from vault notes onto a campaign's characters |

Each runs in-process with the app's environment (`--app module:factory` boots a composing app such
as rpg-ai) and says what it does in its own `--help`.

## Development

Builds and test suites run on a build runner, in a workspace laid out by `fetch-frameworks.sh`,
never on a desktop or against sibling checkouts.

```bash
cd ~/vtt-root/zephyrex-vtt/server && uv run pytest
cd ~/vtt-root/zephyrex-vtt/client && pnpm typecheck && pnpm lint && pnpm test
```

The client's phone tests run the map and the 3D dice in a Pixel 7 Playwright profile
(`client/packages/vtt-play/e2e`). Storybook builds with `pnpm storybook-build`, and
`pnpm storybook-test` runs every story's `play` test and its accessibility check against a running
Storybook.

`contract/api-cases.json` holds the HTTP cases both back ends answer the same way: the client's
`src/contract.test.ts` runs them against the lite handlers and
`server/extensions/rpg_systems/EP_Contract_test.py` against the server.

`client/pnpm-lock.yaml` and `server/uv.lock` are committed and regenerated only in a pinned
workspace, in the same commit that changes `deploy/frameworks.env`.

## Repository layout

```text
server/        FastAPI backend: the VTT's extensions on server-framework
client/        Next.js frontend, and the vtt-play package (client/packages/vtt-play)
contract/      HTTP and rules cases both back ends answer the same way
deploy/        Framework pins and the scripts that lay out and compile a workspace
tools/         The SRD bridge, the pregen backfill and the vault import
docs/          DESIGN.md
```

## Content and licensing

This repository contains the VTT's code, the fifth-edition SRD 5.2 rules pack, and a synthetic
percentile pack used only by the tests (`server/test_packs`).

It contains no setting-specific game system, rules, bridge or content. Those are personal use only
and are installed on a separate private instance, never published here.

The `srd-5e` pack includes material from the System Reference Document 5.2 by Wizards of the
Coast LLC, available under the Creative Commons Attribution 4.0 International License
(https://creativecommons.org/licenses/by/4.0/legalcode). The pack's `$comment` carries the SRD's
own attribution statement.

## License

[AGPL-3.0-or-later](./server/LICENSE).
