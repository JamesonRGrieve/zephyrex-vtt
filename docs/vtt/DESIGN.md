# zephyrex-vtt: design

A virtual tabletop that competes with Foundry VTT and Roll20, with map authoring that
competes with Inkarnate (and Dungeondraft for interiors). It is where a session is played:
maps, scenes, tokens, sheets, dice, combat, live play. It reads the world from the wiki,
and the AI product drives it. Suite context and ownership: [../SUITE.md](../SUITE.md).
Entity fields: [OBJECT_PLAN](../../server/OBJECT_PLAN.md) §4 (`world_spatial` map
authoring, `rpg_core`, `rpg_traits`, `rpg_scene`, `rpg_dice`, `rpg_combat`, `rpg_cards`),
§7 (UVTT and Foundry adapters) and §9 (MapEditor and SceneEditor components). Geometry
lessons: [DESIGN-LESSONS](../../server/DESIGN-LESSONS.md).

## Who it is for

- **The GM**: authors maps and scenes, runs combat, reveals the map, plays every NPC (or
  hands them to the AI GM).
- **The player**: moves their token, rolls, tracks their sheet, sees only what their
  character sees.
- **The cartographer**: makes world, region, city and battle maps with no game attached,
  and exports them.

## Principles

1. **Runs in a browser tab, nothing to install, no licence key.** Foundry needs a
   self-hosted server and a licence, and Roll20 a subscription for the good tools. Lite is
   free and self-hosted. SaaS is hosted.
2. **The server is the referee.** Rolls, damage, movement limits and cover are computed on
   the server (cover is a server endpoint, OBJECT_PLAN decision 12), so a player cannot
   fake a roll, and the AI GM gets the same truth a human GM does.
3. **System-agnostic core, system packs on top.** Traits, derivative math (six operations),
   dice formulas and sheet templates are data. A game system is a pack, not a fork.
4. **One renderer for authoring and play** (Pixi.js, decision 14). The map you paint is the
   battlemap you play on.
5. **Players see only what they should.** Vision, fog and hidden tokens are filtered on the
   server per player, never by hiding with CSS.

## Feature parity matrix: full parity

**The target is full feature parity with Foundry VTT, Roll20 and Inkarnate** (operator,
2026-11-20). Dungeondraft is included for interiors. Every feature those products offer is
planned here. Nothing is left out of scope.

Sources:

- OBJECT_PLAN §4 `rpg_scene`, which is modelled on Foundry's documents, and §4
  `world_spatial` authoring.
- Foundry's site and its v13 notes.
- Roll20's pricing and wiki pages (Plus, Pro, Mods/API, Transmogrifier).
- Inkarnate's FAQ, plan pages and changelog (filters, object shadows, tilt-shift, custom
  brushes, save as stamp, editing resolution vs 8K export).

Rows marked *(verify)* are known from the product but not yet confirmed against a current
page. Every row is re-checked in `docs/research/competitors.md` before launch.

| # | Feature | Seen in | Lite | SaaS |
|---|---|---|---|---|
| **Cartography (Inkarnate / Dungeondraft)** |
| V1 | Map editor at every scale (stellar → interior): stamp palette by scale, transform, flip, tint | Inkarnate | ✓ | ✓ |
| V2 | Stamp variants on free-form axes (state, damage, season, orientation) | — (ours) | ✓ | ✓ |
| V3 | Terrain regions (polygon) and terrain strokes (centerline + width); texture packs swappable per map (DESIGN-LESSONS 1–3) | Inkarnate, Dungeondraft | ✓ | ✓ |
| V4 | Paths: roads, rivers, borders, orbits, with Bézier handles | Inkarnate | ✓ | ✓ |
| V5 | Layers, groups, grid overlay (square, hex), snapping | all | ✓ | ✓ |
| V6 | Room-first interiors: rooms generate walls, nested rooms, per-side wall textures, doors on walls | Dungeondraft | ✓ | ✓ |
| V7 | Export: PNG/WEBP, UVTT v1/v2, Foundry scene; publish to a wiki map | Dungeondraft, Inkarnate | ✓ | ✓ |
| V8 | Asset packs: import and browse stamp and texture packs (the zephyrex-cartography-assets layout) | Inkarnate (paid art) | ✓ | ✓ |
| **Scenes** |
| V9 | Scenes on a map: background, grid, padding, darkness, weather, initial view | Foundry, Roll20 | ✓ | ✓ |
| V10 | Walls with per-sense blocking, one-way walls, thresholds, doors (open, locked, secret, broken) | Foundry | ✓ | ✓ |
| V11 | Dynamic lighting: dim and bright radii, cones, colour, animation, darkness sources | Foundry, Roll20 (Pro) | ✓ | ✓ |
| V12 | Token vision and fog of war, with per-player explored memory | Foundry, Roll20 | ✓ | ✓ |
| V13 | Ambient sounds, playlists | Foundry, Roll20 | ✓ | ✓ |
| V14 | Tiles, drawings, notes, measured templates (circle, cone, ray, rect) | Foundry, Roll20 | ✓ | ✓ |
| V15 | Regions with behaviours (teleport, darkness, script, pause) | Foundry | ✓ | ✓ |
| V16 | Cover from geometry (height and density), mapped per system; GM cover heat map | — (ours) | ✓ | ✓ |
| **Play** |
| V17 | Real-time multi-player table: token drag, pings, cursors, measure, scene switch for everyone | Foundry, Roll20 | ✓ (home network) | ✓ |
| V18 | Chat with rolls, whispers, emotes, in-character and out-of-character | Foundry, Roll20 | ✓ | ✓ |
| V19 | Dice: formula roller, 3D dice option, roll tables, inline rolls in text | Foundry, Roll20 | ✓ | ✓ |
| V20 | Combat tracker: initiative, rounds, turns, groups, defeated, hidden | Foundry, Roll20 | ✓ | ✓ |
| V21 | Character sheets from system templates; computed stats with "why" breakdown | Foundry, Roll20 | ✓ | ✓ |
| V22 | Conditions and effects with durations that tick with rounds | Foundry | ✓ | ✓ |
| V23 | Cards: decks, hands, piles, deal, draw, flip | Foundry, Roll20 | ✓ | ✓ |
| V24 | Handouts and journals (the wiki's entities, shown to chosen players) | Roll20, Foundry | ✓ | ✓ |
| V25 | Audio and video chat at the table | Roll20, Foundry (WebRTC) | – | ✓ |
| **Systems and content** |
| V26 | Game-system packs: traits, derivative rules, sheet layout, dice conventions, cover mapping | Foundry systems, Roll20 sheets | ✓ | ✓ |
| V27 | Compendia: reusable actors, items, scenes, tables | Foundry | ✓ | ✓ |
| V28 | Import: Foundry world export, UVTT, Roll20 character JSON | — | ✓ | ✓ |
| V29 | Macros and scripted hooks (stamp interaction hooks, region scripts) | Foundry, Roll20 (API, Pro) | ✓ (sandboxed) | ✓ (sandboxed) |
| **Accounts** |
| V30 | Invite players by link; GM, assistant GM, player, observer roles | Roll20, Foundry | ✓ (local accounts) | ✓ |
| V31 | Plans: storage, concurrent tables, asset packs | Roll20 | – | ✓ |
| V32 | Installable; touch-friendly play on a tablet | Roll20 (app) | ✓ | ✓ |
| **Parity additions: cartography (Inkarnate)** |
| V33 | Text labels: fonts, curved text along a path, outline, shadow, letter spacing | Inkarnate | ✓ | ✓ |
| V34 | Map filters: HSBC (hue, saturation, brightness, contrast), tilt-shift, vignette, overlays; object shadows | Inkarnate | ✓ | ✓ |
| V35 | Brushes: texture painting, custom brushes, blend and erase | Inkarnate | ✓ | ✓ |
| V36 | Save a selection as a stamp; upload your own stamps, textures and brushes | Inkarnate (Creator) | ✓ | ✓ (with storage quotas) |
| V37 | Art styles and map types: world, regional, city, battlemap, interior, sci-fi and star maps | Inkarnate | ✓ | ✓ |
| V38 | Editing resolution separate from export resolution; export up to 8K and print sizes | Inkarnate | ✓ | ✓ |
| V39 | Map gallery: share maps publicly, browse and remix the community's | Inkarnate | – | ✓ |
| **Parity additions: play and content (Foundry, Roll20)** |
| V40 | Package system: systems, modules and worlds installed by manifest URL, with versions, dependencies and updates; a sandboxed module API | Foundry | ✓ | ✓ |
| V41 | Script API ("Mods"): sandboxed server-side scripts reacting to table events | Roll20 (Pro) | ✓ | ✓ |
| V42 | Marketplace: free and paid systems, modules, adventures, maps and art; creator payouts | Foundry, Roll20 | ✓ (install bought packages) | ✓ |
| V43 | Adventures: packaged scenes, actors, journals, tables and playlists, imported in one step | Foundry, Roll20 (modules) | ✓ | ✓ |
| V44 | Guided character creation (a system-driven builder) | Roll20 (Charactermancer) | ✓ | ✓ |
| V45 | Move characters, handouts, macros, tables and playlists between games | Roll20 (Transmogrifier) | ✓ | ✓ |
| V46 | A character vault: keep a character across games | Roll20 | ✓ | ✓ |
| V47 | 3D dice with themes; dice-tray sharing | Roll20, Foundry (module) | ✓ | ✓ |
| V48 | Jukebox: a music library with playlists and per-track volume | Roll20 | ✓ | ✓ |
| V49 | Token actions and macro bar per character; macro sharing | Roll20, Foundry | ✓ | ✓ |
| V50 | Turn-based movement limits, measured paths, difficult terrain | Foundry (v12+) *(verify)* | ✓ | ✓ |
| V51 | Elevation and multi-level scenes | Foundry | ✓ | ✓ |
| V52 | Looking for group: list a game, apply, schedule | Roll20 | – | ✓ |
| V53 | Discord integration: rolls and summaries to a channel, play from Discord | Roll20 *(verify)* | – | ✓ |
| V54 | PDF and handout viewer shared to chosen players | Foundry, Roll20 | ✓ | ✓ |
| V55 | Localisation of the UI and of system packs | Foundry | ✓ | ✓ |

The package system (V40), scripts (V41) and the marketplace (V42) run third-party code. It
runs only in a sandbox with declared permissions, never with the server's own rights. The
sandbox design is a security-review item before V40/V41 ship.

## Screens

| Path | What it is |
|---|---|
| `/` | Landing: hero with a live animated battlemap (fog lifting as a token walks), Foundry/Roll20/Inkarnate comparison, pricing, FAQ. |
| `/tables` | Your games: each campaign's tables, next session, players. |
| `/t/[table]` | **The table.** The full-bleed Pixi canvas. Left: a floating tool palette (select, measure, ping, draw, template, plus GM tools). Right: a collapsible dock with tabs: chat and rolls, combat, actors, scenes, journal, audio. Bottom: the hotbar and your token's bars. Top: the scene name, players present, and the GM's "pause the table" switch. |
| `/t/[table]/sheet/[actor]` | The character sheet: also a pop-out window from the table. |
| `/maps` | Map library across scales, with thumbnails. |
| `/maps/[id]/edit` | **The map editor.** The same canvas, with authoring tools: stamp palette, terrain brush, path tool, room, wall, light, sound, region and layers panels; variant picker; export dialog. |
| `/compendia` | Actors, items, scenes, tables: browse, import, drag to a table. |
| `/systems` | Installed game-system packs, sheet template preview. |
| `/settings` | Dice style, sounds, reduced motion, contrast, grid colours, keybindings. |

### Key interactions

- **Token drag:** a ghost path with distance by the system's measuring rule. Walls stop the
  ghost at the wall. The server confirms the move. A rejected move snaps back with a reason.
- **Rolls everywhere:** click any stat on a sheet and the server rolls it. The result card
  shows the formula, each die and the modifiers' "why" from the derivative pipeline.
- **GM reveal:** the GM's lens shows the scene as a chosen player sees it (vision and fog).
- **Variant change in play:** right-click a door or a burning building and pick a variant
  axis value. Linked hooks fire (OBJECT_PLAN `StampInteractionHookModel`).
- **Command palette (⌘K)** and full keybindings, remappable.

## Visual design

Canvas first. Dark, low-saturation chrome that recedes behind the map, panels on blurred
translucent surfaces, and tool palettes that float and remember their place. Strong focus
rings on every tool, and a list equivalent for everything on the canvas (tokens, walls,
lights) for keyboard and screen-reader use. Motion: dice tumble and fog dissolves are
respectful of reduced motion (instant reveal). Light chrome is available, though the
canvas itself is the map's own colours.

## Real-time architecture

- **The table is server-authoritative.** Clients send intents (move token, open door, roll)
  and the server validates, applies, writes and broadcasts. A late joiner gets a snapshot
  and then the stream.
- **Transport:** a multi-user table channel with presence (who is here, GM or player) and
  per-recipient filtering (vision, fog, whispers, hidden tokens).
  **Framework gap:** `live_sync` is "between a user's own devices", so a multi-user,
  per-recipient-filtered room is a new generic framework capability (table/room sync), not
  VTT code. It is raised on card 253 before VTT play is built. The AI product needs it too.
- **Rendering:** Pixi.js stage layers (background, tiles, drawings, walls (GM),
  tokens, lighting/vision mask, fog, effects, UI overlay). Vision polygons are computed
  per client from server-sent geometry for the viewer's own tokens. The server keeps the
  authoritative explored fog.

## Data and contract

- **Extensions:** `vtt_cartography` (the authoring half of OBJECT_PLAN `world_spatial`),
  `rpg_core` (game systems, character injection), `rpg_traits`, `rpg_scene`, `rpg_dice`,
  `rpg_combat`, `rpg_cards` (ownership in [../SUITE.md](../SUITE.md)). Mechanical events
  are written to the wiki's `rpg_log`.
- **It depends on the wiki** for locations, maps, persons, items and campaigns.
- **The AI product calls these as tools,** under the caller's ACL:
  - `roll(formula|stat)`;
  - `legal_actions(combatant)`: the enumerated actions the rules allow now, which feed the
    decision models;
  - `apply_action`, `move_token`, `cover(attacker, target, scene)`, `encounter_state`,
    `advance_turn`;
  - `scene_snapshot(viewer)`: what a given character can perceive.
  Each is an ordinary endpoint plus an `@ability` so a framework agent can use it.
- REST shape as the framework (ETag, `If-Match`, `412`/`428`), plus the table stream.

## Editions

- **Lite:** a home table. The GM's machine serves the table to players on the same network,
  with local accounts and every authoring and play feature. No AV chat.
- **SaaS:** hosted tables, invites by link, AV chat, cloud asset storage with quotas, plans.

## Phases

1. `rpg_core`/`rpg_traits` and character sheets, dice, combat tracker (the data the AI GM
   needs first).
2. Scenes: walls, doors, tokens, server-side vision and cover; the table canvas in play
   mode.
3. Real-time table (after the framework room-sync capability lands), chat, rolls, fog,
   lighting.
4. Map editor: stamps, variants, terrain, paths, rooms; export and publish to the wiki.
5. System packs, compendia, Foundry/UVTT import, cards, playlists, AV chat.
6. The Inkarnate parity set: labels, filters, brushes, save as stamp, art styles, 8K
   export, gallery (V33–V39).
7. The content platform: packages, sandboxed scripts, adventures, character builder and
   vault, transfer between games, marketplace (V40–V46). Then the remaining play parity
   (V47–V55).

Ported back from the AI product's build: the shared UI shell, dice result cards, the
combat HUD, and the mechanics endpoints the AI GM proved out (phase 1 comes first for that
reason) ([../ai/DESIGN.md](../ai/DESIGN.md)).
