# Zephyrex VTT

Virtual tabletop (Foundry/Roll20/Inkarnate parity) on the Zephyrex framework. Part of the Zephyrex RPG suite (wiki ← vtt ← ai);
suite ownership and composition: zephyrex-rpg-ai `docs/SUITE.md`. Design: `docs/DESIGN.md`.

## Structure

```
server/     Python backend: zephyrex server consumer (`zephyrex[auth-session,genealogy]` at the pinned server-framework); extension `rpg_state`
client/     Next.js frontend: zephyrex npm consumer
docs/       DESIGN.md
deploy/     frameworks.env (the five framework pins), fetch-frameworks.sh, compile-frameworks.sh
```

## Rules for this repo

- This product's extensions only. Anything generic belongs in the frameworks; anything another
  suite product owns is reached through that product's API, never its internals.
- Pages never branch on edition or on which suite products are loaded: a feature shows when
  `GET /v1/extension` lists the extension that serves it.
- UI follows the shared standard (zephyrex design tokens, shadcn, lucide, a Storybook story with
  a `play` test per component), as in 16 Worldviews, Zephyreader and Chronos.
- Heavy work (installs, builds, test suites) runs on the build runner, never the desktop, in a
  workspace laid out by `deploy/fetch-frameworks.sh`, never against sibling checkouts.
- `client/pnpm-lock.yaml` and `server/uv.lock` are committed; regenerate them only in a pinned
  workspace, and in the same commit that bumps `deploy/frameworks.env`.
- Read the SOP Stack Standards (Python; TypeScript and JavaScript; React and Next.js) before a
  first edit. Work state: Card 256 on Zephyrex Software.

## Commands

```bash
deploy/fetch-frameworks.sh <root>     # lay out a build workspace: this repo + the frameworks at their pins
deploy/compile-frameworks.sh <root>   # compile the framework packages the client installs
deploy/compile-wiki.sh <root>         # after the client's install: build the wiki's client package into it
cd <root>/zephyrex-vtt/server && uv sync && uv run pytest
cd <root>/zephyrex-vtt/client && pnpm install --frozen-lockfile && pnpm typecheck
```
