# Zephyrex VTT

Virtual tabletop (Foundry/Roll20/Inkarnate parity) on the Zephyrex framework. Part of the Zephyrex RPG suite (wiki ← vtt ← ai);
suite ownership and composition: zephyrex-rpg-ai `docs/SUITE.md`. Design: `docs/DESIGN.md`.

## Structure

```
server/     Python backend: zephyrex server consumer (PyPI `zephyrex[genealogy]~=0.0.1`); extension `rpg_state`
client/     Next.js frontend: zephyrex npm consumer
docs/       DESIGN.md
```

## Rules for this repo

- This product's extensions only. Anything generic belongs in the frameworks; anything another
  suite product owns is reached through that product's API, never its internals.
- Pages never branch on edition or on which suite products are loaded: a feature shows when
  `GET /v1/extension` lists the extension that serves it.
- UI follows the shared standard (zephyrex design tokens, shadcn, lucide, a Storybook story with
  a `play` test per component), as in 16 Worldviews, Zephyreader and Chronos.
- Heavy work (installs, builds, test suites) runs on the build runner, never the desktop.
- Read the SOP Stack Standards (Python; TypeScript and JavaScript; React and Next.js) before a
  first edit. Work state: Card 256 on Zephyrex Software.

## Commands

```bash
cd server && pip install -e ".[dev]" && python app.py
cd server && python -m pytest extensions/
cd client && pnpm install && pnpm dev
```
