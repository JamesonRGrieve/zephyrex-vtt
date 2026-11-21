# zephyrex-vtt: design

A virtual tabletop that competes with Foundry VTT and Roll20, with map authoring that
competes with Inkarnate (and Dungeondraft for interiors). It is where a session is played:
maps, scenes, tokens, sheets, dice, combat, live play. It reads the world from the wiki,
and the AI product drives it. Suite context and ownership: [zephyrex-rpg-ai: docs/SUITE.md](https://github.com/JamesonRGrieve/zephyrex-rpg-ai/blob/main/docs/SUITE.md).
Entity fields: [OBJECT_PLAN](https://github.com/JamesonRGrieve/zephyrex-rpg-wiki/blob/main/server/OBJECT_PLAN.md) §4 (`world_spatial` map
authoring, `rpg_core`, `rpg_traits`, `rpg_scene`, `rpg_dice`, `rpg_combat`, `rpg_cards`),
§7 (UVTT and Foundry adapters) and §9 (MapEditor and SceneEditor components). Geometry
lessons: [DESIGN-LESSONS](../server/DESIGN-LESSONS.md).

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
| V38 | Editing resolution separate from export resolution; export up to 16K (Inkarnate's top tier, per the 2026-11-21 audit) and print sizes | Inkarnate | ✓ | ✓ |
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
| V56 | Resolution modes: mechanical (rules as written, the VTT as referee), narrative (rolls on request, light dice styles), hybrid by scene kind; declared per system pack | ours | ✓ | ✓ |
| **Parity additions from the 2026-11-21 audit** |
| V57 | Dice: the full modifier set (`rr`, `xo`/`xN`, `min`/`max`, `cf`, `df`/`sf`/`ms`, even/odd), pools `{}`, nested counts, math functions, labels, roll queries, manual and hardware dice entry | Foundry, Roll20 | ✓ | ✓ |
| V58 | Effects tool: one-shot visual effects on the canvas (bursts, beams), custom effects | Roll20 | ✓ | ✓ |
| V59 | Grid: dimetric and isometric | Roll20 | ✓ | ✓ |
| V60 | Safety tools at the table: a safety deck (X-card and the like) any player can play anonymously | Roll20 | ✓ | ✓ |
| V61 | Reactions: one-click preset chat lines, rolls and macros; game rollback to an earlier point | Roll20 | ✓ | ✓ |
| V62 | Settings, keybindings (rebindable) and guided tours | Foundry, Roll20 | ✓ | ✓ |
| **Parity additions: zephyr-cartography, native (operator, 2026-11-21)** |
| V63 | Light switches linking lamps, rooms and lights; daylight through windows, on by the scene's light | zephyr-cartography | ✓ | ✓ |
| V64 | Structure-aware stamps: walls from bounds or a traced silhouette, lights, doors that cut walls and follow their state, surfaces, movement cost, particles, sound; behaviour kept with the placed stamp | zephyr-cartography | ✓ | ✓ |
| V65 | Containers players open and loot, holding the Wiki's items | zephyr-cartography (Item Piles) | ✓ | ✓ |
| V66 | Hazards with a reach and a warning on entry, hazard presets; hidden traps that pause the game on first entry | zephyr-cartography | ✓ | ✓ |
| V67 | Interiors: a building leads to its own interior map (entrance, exit, arrival), or to upper floors in the same map | zephyr-cartography | ✓ | ✓ |
| V68 | Spawn areas (counts, centre or anywhere, snapped, no overlap) and pre-placed tokens in a built map | zephyr-cartography | ✓ | ✓ |
| V69 | Map builder: a map from a short description (with AI help), a floor plan from a seed, any map from a scene spec; editable features, one undo step | zephyr-cartography | ✓ | ✓ |

The package system (V40), scripts (V41) and the marketplace (V42) run third-party code. It
runs only in a sandbox with declared permissions, never with the server's own rights. The
sandbox design is a security-review item before V40/V41 ship.

## Feature audit: Foundry VTT, Roll20, Inkarnate (2026-11-21)

The parity matrix above says what is planned. This audit says what is there **today**: each
product's user-facing features, listed from its own current documentation (not memory), with
vtt's status. Asked by the operator (2026-11-21); the Wiki, rpg-ai and Parity audit their own
targets (World Anvil, Kanka, SillyTavern).

Sources:
- **Foundry VTT:** the Knowledge Base article index (foundryvtt.com/kb), one article per row
  (`/article/<name>/`).
- **Roll20:** the Help Center, read through its public article API, since the site refuses
  scripted page loads (`help.roll20.net/hc/en-us/articles/<id>`).
- **Inkarnate:** the Help Center (`help.inkarnate.com/articles/<id>`) and the home page.

Status, as of the commit that changed this section:
- **Covered:** built and tested in vtt (named where).
- **Partial:** some built; the missing part is named.
- **Planned (Vn):** in the parity matrix, nothing built yet.
- **Gap:** offered by the product but in no matrix row yet; it needs a row.
- **Elsewhere:** owned by another part of the suite (named); vtt uses it.
- **Out of scope:** not a product feature (hosting, billing, policy), with the reason.

What vtt has today:
- **Server:**
  - `rpg_scene`: scenes with grid size, distance and units, token vision, global light and darkness; tokens with position, size, elevation and rotation; walls with door type and state, sight and movement restrictions and one-way direction; and `scene_snapshot`, what a token sees, from `Vision.py`.
  - `rpg_dice`: the dice grammar, checks, saved formulas and roll tables (stored, no draw).
  - `rpg_traits`: traits, derived traits and character traits.
  - `rpg_systems`: game systems.
  - `rpg_table`: tables, seats, whispers and lines on framework conversations.
- **Client:** the landing page, the lite shell and the campaign and game-system APIs. No play
  screens yet.
- **Maps:** Inkarnate-style authoring exists today in zephyr-cartography, inside Foundry. Under
  the agreed maps plan (Foundry scene JSON and Universal VTT import, UVTT export) that pipeline
  feeds vtt, while vtt's own editor is V1–V8.

### Foundry VTT

| # | Feature (source article) | Status |
|---|---|---|
| F1 | Scene directory: folders, search, duplicate, delete (`scenes`) | Partial: `rpg_scene` Scene CRUD API; no folders, no screen (V9) |
| F2 | One active scene for everyone, a viewed scene per user, the navigation bar (`scenes`) | Planned (V17) |
| F3 | Scene JSON import and export; scenes from compendia (`scenes`) | Planned (V28, V27); Foundry scene JSON import is in the agreed maps plan |
| F4 | Background image, foreground image, background colour (`scenes`) | Planned (V9); art as `attachments` (`background`) |
| F5 | Grid: gridless, square, four hex layouts; size, offset, scale label, colour, opacity; alignment tool (`scenes`) | Partial: grid size, distance and units stored; no grid type, offset, alignment or drawing (V5) |
| F6 | Padding, initial view, thumbnails, preload (`scenes`) | Planned (V9) |
| F7 | Token-vision requirement, global illumination, darkness level and its threshold (`scenes`) | Partial: `token_vision`, `global_illumination`, `darkness_level` stored and used by `scene_snapshot`; no threshold, no rendering (V11) |
| F8 | Fog of war per user, fog image and tints, reset fog (`scenes`, `lighting`) | Planned (V12); the maps plan stores explored areas per character |
| F9 | A scene's linked journal, playlist and weather (`scenes`) | Planned (V9, V13); journals are the Wiki's |
| F10 | Walls restricting movement, light, sight and sound separately (`walls`) | Partial: walls restrict sight and movement, and `Vision.py` honours them; light and sound to come (V10) |
| F11 | Limited, proximity and reverse-proximity restriction; threshold attenuation (`walls`) | Planned (V10) |
| F12 | Doors and secret doors, open, closed or locked (`walls`) | Partial: `door_type`, `door_state`; an open door doesn't block; a secret door is never reported to players; no door controls (V10) |
| F13 | One-way walls (`walls`) | Partial: `direction`, honoured by `Vision.py` |
| F14 | Door art, double doors, open animations and sounds (`walls`) | Planned (V10) |
| F15 | Wall presets (solid, terrain, invisible, ethereal, window) and tools: draw, snap, palette, clear, placeables list (`walls`) | Planned (V10, V5) |
| F16 | Light sources: bright and dim radius, angle, rotation, colour, intensity (`lighting`) | Planned (V11); in the maps plan |
| F17 | Darkness sources, activation by darkness range, priority (`lighting`) | Planned (V11) |
| F18 | 19 light animations (`lighting`) | Planned (V11), within the phone frame budget |
| F19 | Wall constraint, light that grants vision, luminosity, gradual edges, saturation, contrast, shadows, coloration techniques (`lighting`) | Planned (V11); the costly techniques only on capable device tiers |
| F20 | Day and night transition synced for everyone (`lighting`) | Planned (V11, V17) |
| F21 | Tokens: place an actor, select, target, prototype vs placed token (`tokens`) | Partial: `SceneToken` (position, size, elevation, rotation) linked to a person; no art, targeting or screen |
| F22 | Token art: scale, mirror, tint, opacity, wildcard images, dynamic rings (`tokens`) | Planned (V21) |
| F23 | Nameplates, disposition, two resource bars (`tokens`) | Planned (V21) |
| F24 | Token vision: range, angle, vision modes (darkvision, tremorsense…), detection modes, shared vision (`tokens`) | Partial: `scene_snapshot` gives one token's line of sight; modes and ranges to come (V12) |
| F25 | Token light emission (`tokens`) | Planned (V11) |
| F26 | Elevation (`tokens`) | Partial: stored, not yet used for sight (V51) |
| F27 | Status effects on tokens, token HUD (`tokens`) | Planned (V22) |
| F28 | Ruler with waypoints and elevation, movement cost, hidden moves (`measurement`) | Planned (V17, V50) |
| F29 | Measured templates: circle, cone, rectangle, ray; textures (`measurement`) | Planned (V14) |
| F30 | Regions: eight shapes, holes, locked, attached to a token (`scene-regions`) | Planned (V15) |
| F31 | Region behaviours: darkness, apply effect, change level, surface, scrolling text, macro, script, movement cost, pause, suppress weather, teleport, toggle (`scene-regions`) | Planned (V15); macro and script sandboxed (V29) |
| F32 | Tiles: image or video, elevation, sort, occlusion modes, tile browser (`tiles`) | Planned (V14); tile art as `attachments` |
| F33 | Drawings: rectangle, circle, polygon, freehand, text, fill and texture, drawing permission (`drawings`) | Planned (V14) |
| F34 | Map notes linked to a journal entry or page; globally visible (`map-notes`) | Planned (V14); notes link to Wiki entities |
| F35 | Ambient sounds: radius, easing, walls, darkness activation, preview (`ambient-sound`) | Planned (V13) |
| F36 | Pings: basic, alert, pan everyone; off-screen arrows; photosensitivity mode (`pings`) | Planned (V17) |
| F37 | Canvas layers; levels (`canvas-layers`, `scene-regions`) | Planned (V5, V51); a single level first, `level_id` from day one |
| F38 | Combat tracker: encounters, initiative, rounds and turns, hidden, defeated, tracked resource, several encounters (`combat`) | Planned (V20) |
| F39 | Chat: in character, out of character, emote, whispers to several, roll commands, roll modes (GM, blind, self), bubbles, export (`chat`) | Partial: `rpg_table` lines spoken as a seat, whispers as two-seat conversations, the `say` ability; no commands, roll modes, export or screen (V18) |
| F40 | Dice: kh/kl/dh/dl, explode, reroll once, count successes, Fate, d%, actor data (`dice`, `dice-modifiers`) | Covered: `rpg_dice/Dice.py` and its twin `client/src/features/dice/roll.ts` on 27 shared cases; `/v1/dice/roll`; the `roll` ability |
| F41 | Dice: `rr`, `xo`/`xN`, `min`/`max`, `cf`, `df`/`sf`/`ms`, even/odd, pools `{}`, nested counts, math functions, labels, inline rolls (`dice-modifiers`, `dice-advanced`) | Gap: not in the grammar yet (V19 names inline rolls only) |
| F42 | Dice fulfilment: manual entry, hardware dice (`dice-advanced`) | Gap |
| F43 | Roll tables: weighted draw, with or without replacement, nested, blind, embedded (`roll-tables`) | Partial: tables and entries stored (`rpg_dice`); no draw (V19) |
| F44 | Active effects: change modes, durations, transfer from items, status (`active-effects`) | Partial: derived traits compute stats with a breakdown (`rpg_traits`, `/v1/dice/check`); effects with durations not built (V22) |
| F45 | Cards: decks, hands, piles; deal, draw, pass, play, shuffle, reset; faces; presets (`cards`) | Planned (V23) |
| F46 | Actors: sheets per system, ownership levels, prototype token, JSON import and export (`actors`) | Partial: characters are the Wiki's persons with vtt traits and checks; no sheet (V21, V26) |
| F47 | Items: owned items on an actor (`items`) | Elsewhere: the Wiki's `world_inventory`; vtt counts worn items in checks |
| F48 | Journal entries: text, image, video and PDF pages; secrets; show to players; links (`journal`) | Elsewhere: the Wiki's `world_narrative` and `entity_posts`; showing to players is V24 and V54 |
| F49 | Compendium packs (`compendium`) | Planned (V27) |
| F50 | Adventures (`adventure`) | Planned (V43) |
| F51 | Playlists: modes, fades, volumes, bulk import (`playlists`) | Planned (V48, V13) |
| F52 | Macros: chat and script; a hotbar of 50; permissions (`macros`) | Planned (V49, V29), with scripts sandboxed |
| F53 | Roles (none, player, trusted, assistant, GM), document ownership levels, player colours and avatars (`users`) | Partial: the campaign's GM vs player rule (dice, table); framework ACL; no assistant or trusted roles (V30) |
| F54 | Audio and video chat: modes, push to talk, dock, relay (`audio-video`) | Planned (V25), hosted edition |
| F55 | Systems, modules and package management (`modules`, `package-management`) | Planned (V40) |
| F56 | Game settings, keybinds, tours (`settings`, `keybinds`, `tours`) | Gap: no settings page (waits for the framework's, card 253); keybinds and tours not in the matrix |
| F57 | Localisation (`localization`) | Planned (V55) |
| F58 | Hosting, backups, S3 storage, TLS (`hosting`, `backups`, `aws-s3`, `ssl`) | Out of scope: deployment, not a product feature (the hosted service and the framework own it) |

### Roll20

| # | Feature (source article id) | Status |
|---|---|---|
| R1 | Pages: menu, folders, settings (size, background, scale, grid, play on load, archive) (360039675413, 360039675373) | Partial: Scene size and grid stored; no folders or screen (V9) |
| R2 | Grid types: none, square, hex both ways, dimetric, isometric (4416143791767) | Partial: square only; hex is V5; dimetric and isometric are a Gap |
| R3 | Layers: map, tokens, GM, lighting, foreground (360039675053, 30738192036887) | Planned (V5) |
| R4 | Importing, sizing and aligning maps; geomorphic tiles (360039178654, 360039243994, 360039715533) | Planned (V9, V14) |
| R5 | Tokens: three bars, bubbles, auras, markers, nameplate, tooltip, lock, GM notes, link to a journal (360039674573, 360039715593) | Partial: `SceneToken` linked to a person; the rest V21, V22 |
| R6 | Token marker sets (360041536313) | Planned (V22) |
| R7 | Dynamic lighting: vision, night vision, light, explorer mode, daylight mode, update on drop, GM darkness opacity (4403801475479, 360052521913, 360051754954) | Partial: server line of sight; the rest V11, V12 |
| R8 | Doors, windows and barriers (360051768974, 11462645998999) | Partial: walls and doors in `rpg_scene`; windows and placement tools V10 |
| R9 | Fog of war, classic and advanced; hide and reveal mask (360037774513, 360037774493, 360051768534) | Planned (V12) |
| R10 | Player view, preview token vision (41973886368151) | Partial: `scene_snapshot` answers what a token sees; no view yet |
| R11 | Map pins: tooltip, visibility, shape, symbol, image, bulk edit (36271267343639) | Planned (V14) |
| R12 | Measure tool: broadcast, shapes, grid measuring styles (360039674913) | Planned (V14, V17) |
| R13 | Drawing and text tools (360039674893) | Planned (V14) |
| R14 | Effects (FX) tool and custom effects (360037258714) | Gap |
| R15 | Turn tracker: custom items, values, sorting, several pages, visibility (360039178634) | Planned (V20) |
| R16 | Jukebox: uploads, playlists, pop-out (360039178714) | Planned (V48) |
| R17 | Jukebox's partner libraries (Tabletop Audio, BattleBards, Incompetech) (360039178714) | Gap: free-licence libraries could be listed; paid catalogues need agreements |
| R18 | Card decks: deal, recall, shuffle, steal, trade, cards for initiative (360039178754) | Planned (V23) |
| R19 | Safety deck (360039178754) | Gap |
| R20 | Journal: characters (bio, sheet, attributes and abilities), handouts, show to players (360039675133) | Partial: characters with traits (Wiki persons and `rpg_traits`); handouts are V24 |
| R21 | In-game compendium (360039178694, 360048312214, 360037258674) | Planned (V27) |
| R22 | Dice roller: quick rolls, secret and super-secret rolls, 3D dice (360039674933, 41407961155479, 360039715613) | Partial: the server rolls; secret rolls (V18) and 3D dice (V47) to come |
| R23 | Quantum Roll: dice rolled by the server, so no one can fake them (360037256594) | Covered: `rpg_dice` rolls on the server with `secrets.SystemRandom`; clients never roll for the record |
| R24 | Dice syntax: roll queries, inline rolls, grouped rolls, matching dice, tables in rolls (360037773133) | Partial: the grammar covers keep/drop, explode, reroll and successes; the rest is a Gap (as F41) |
| R25 | Chat commands: `/w`, `/em`, `/ooc`, `/desc`, `/as`, `/emas`, `/fx`, `/talktomyself`, multiline, GM hide, pause movement (360039675093) | Partial: lines and whispers (`rpg_table`); commands not parsed (V18) |
| R26 | Reactions: preset chat commands and macros (32901366352919) | Gap |
| R27 | Macros and token actions, quick bar, ability buttons, nesting (360037256794, 360039178674) | Planned (V49) |
| R28 | Mod scripts: sandbox, events, objects, one-click install (360037256714 and the "Mod Scripts" section) | Planned (V41) |
| R29 | Integrated voice and video (360041544734) | Planned (V25) |
| R30 | Game management: my games, game details, settings, invite and promote players (29619836768791, 29620064514071, 29620515876375) | Partial: tables and seats (`rpg_table`); invitations V30 |
| R31 | Rollback: restore a game to an earlier point (32139162477719) | Gap |
| R32 | Transmogrifier: move content between games (360037774433) | Planned (V45) |
| R33 | Character vault (360037258594) | Planned (V46) |
| R34 | Charactermancer: guided creation and levelling (glossary; sheet sections) | Planned (V44) |
| R35 | Character sheets per system; custom sheet development (360037773373 and the "Sheet Development" section) | Partial: game systems and traits (`rpg_systems`, `rpg_traits`); sheet layouts V26 |
| R36 | Demiplane sheet integration (30050730960151) | Out of scope: a proprietary third-party service |
| R37 | Marketplace content, search, redemption codes (360039725993, 360037773233, 360037773173) | Planned (V42) |
| R38 | Art library, WebP conversion (360039675113, 11616928242967) | Planned (V8, V36); files through `attachments` |
| R39 | PDFs in the journal (7711746351639) | Planned (V54) |
| R40 | Universal VTT upload; adjust its doors, windows, walls and lights afterwards (41643201127831) | Planned: the agreed maps plan (UVTT in and out; V7, V28) |
| R41 | Mobile: Roll20 on phones, table on tablet, mobile sheets (4411213438231, 360037774593) | Partial: the shell passes the phone and tablet audit; no play screens yet (V32) |
| R42 | Hotkeys and advanced hotkeys (360039675393, 360039178974) | Gap (with F56) |
| R43 | Dungeon Scrawl: layers; stamp, object, rectangle, polygon, path, wall, door, stairs and text tools; presets, textures, lighting; random dungeon; export, sharing, send to tabletop (the "Dungeon Scrawl" sections) | Planned (V1–V7); zephyr-cartography already has the floor plan from a seed; "send to tabletop" is the maps import |
| R44 | Support, payments, policies (the "Support" and "Policy" categories) | Out of scope: operations, not the product |

### Inkarnate

| # | Feature (source article id) | Status |
|---|---|---|
| I1 | Map styles and types: world, regional, city, battle, dungeon, interior, sci-fi, parchment, watercolour (2068557, 1317639) | Planned (V37) |
| I2 | Editor shell: tools, layers, object panel, status bar (resolution, snap, zoom), shortcut bar, undo and redo, autosave (6452044) | Planned (V1, V5) |
| I3 | Land tool: land mask, add and subtract, rough edges, circle, grid blocks, preset shapes, bucket fill, move area (3883631) | Planned (V3) |
| I4 | Brush tool: textures and colours, erase, shape brush, custom brushes, rough edges, grid blocks, softness, texture placement, colour adjustment, favourites (4018103) | Planned (V35) |
| I5 | Stamp tool: catalogue, stamp sets with a random child, recent and favourites, scale, rotate, flip, stretch, opacity, shadow, blend, blur, clip mask, HSBC, many-at-once with area and density (2431733) | Planned (V1, V2, V34) |
| I6 | Line and shape tools: free draw, pen with curves, brush mode, presets, add, subtract, merge, edit nodes, cut path, portals, stamp/colour/clip strokes, fills (3822773) | Planned (V4, V6) |
| I7 | Text tool: fonts, bold, curve, spacing, alignment, colour, outline, shadow, blend, blur (5385303) | Planned (V33) |
| I8 | Layers: object, brush, land, filter, grid, mask, colour; reorder, rename, hide, duplicate, mask, flatten (4641701, 9696284) | Planned (V5) |
| I9 | Filter layers (night, tilt-shift, black and white) and blend modes (4641701, 3131865) | Planned (V34) |
| I10 | Editing resolution apart from export resolution (3876000) | Planned (V38) |
| I11 | Export JPEG, PNG or WebP at 1K–16K or custom; VTT grid mode by pixels per cell (8519002) | Planned (V7, V38); V38 says 8K, and Inkarnate now goes to 16K |
| I12 | Catalogue and art manager (tags, styles); uploading assets; archive and delete (5242141, 1531863, 6836412, 7802070) | Planned (V8, V36) |
| I13 | Dashboard and managing maps (8362508, 3621891) | Planned (V1) |
| I14 | Explore, publish, profile, clone community maps (3850836, 0086595, 4517972, 2415049) | Planned (V39), hosted edition |
| I15 | Marketplace purchases (0233838, 6084268) | Planned (V42) |
| I16 | Day-to-night lighting on a map (home page) | Planned (V11, V34) |
| I17 | Account, subscription, billing (9596349, 7115423) | Out of scope: the framework's accounts and the hosted plans (V31) |

### zephyr-cartography: what the module adds to Foundry, native here

The operator (2026-11-21): "Make sure we natively support the features we had to add in our
foundry zephyrex cartography module." Each feature below exists because Foundry lacks it.
vtt has it as a first-class part of its own map model, not as a Foundry emulation.
Sources:
- the module's guide (`dh-campaign/.foundry-cartography/docs/guide/`);
- its published schemas (`schema/scene-spec.v1`, `stamp-pack.v1`, `map-intent.v1`);
- its source (`src/foundry/`, `src/tools/`).

**Import consequence.** The module keeps these features in its own store, not in Foundry's
documents:
- a features file per scene in the world's data folder, named by a scene flag (`tools/features-file.ts`);
- terrain paint as PNG masks (`foundry/splat-store.ts`);
- stamp behaviour copied from its pack.
A Foundry scene export alone carries only the walls, lights and tiles they produced.
vtt therefore imports the features file, the masks and the packs alongside the scene JSON,
and rebuilds each feature natively. The Foundry documents are the fallback for scenes the
module never touched.

**One model, shared** (operator, 2026-11-21). vtt's map features *are* the module's: the
scene-spec v1 feature kinds (region, stroke, path, room, stamp, pin, label, zone, shape,
token), with stamp-pack v1 for art and behaviour. The module's Foundry-free code (geometry,
compose, generate, the UVTT writer) moves into a package that both the Foundry module and vtt
depend on. Import is lossless, the map builder and the floor-plan generator run in vtt
unchanged, and a fix lands in both. vtt's own code is the renderer, the server model, play and
storage.

| # | Feature the module adds | vtt row |
|---|---|---|
| Z1 | Terrain painting: 13 biomes as ground that knows what it is (water, lava, ice…), blended edges, baked blends; terrain as regions with movement cost, effects and spawns | V3 (extended: biome meaning, region effects) |
| Z2 | Roads and rivers: width per control point, tapered ends, optional walls along the centreline, liquid, bed and shade | V4 (extended) |
| Z3 | Rooms: grid-snapped polygons with floor and wall materials and a wall kind; shared walls between neighbours; a centre light; a ceiling when a level is above; openings (no door, no wall); doors with sound and animation; movement cost, effects and spawns per room; windows | V6 (extended) |
| Z4 | Light switches: a switch, worked like a door, turning linked lamps, rooms and lights on and off; lamp art follows | V63 |
| Z5 | Daylight through windows: a warm light outside each window, on only while the scene is light enough | V63 |
| Z6 | Drop shadows: standing stamps cast soft shadows away from a sun whose direction a system or script can move; per-stamp shadow height | V34 (extended) |
| Z7 | Structure-aware stamps: walls from the art's bounds or traced silhouette, with per-sense restriction; lights; doors that cut room walls, with art that follows the door's state; surfaces (roofs and balconies, hidden until reached); movement cost; particles and sound | V64 |
| Z8 | Stamp variants (open, lit, broken…) switched in place | V2 |
| Z9 | Stamp browser: map scale (system → interior), perspective (orthographic, isometric, front, central), setting or genre, categories and tags; place at the view centre; stamps stand on the table or desk under them | V8 (extended) |
| Z10 | A placed stamp keeps a copy of its behaviour, so a scene still works when its pack is gone | V64 |
| Z11 | Containers: chests and lockers players open and loot, with art that follows open and closed (Item Piles in Foundry) | V65, holding the Wiki's `world_inventory` items |
| Z12 | Hazards (fire, acid, toxic, radiation, electric, fall) with a reach past the footprint; a warning on entry; hazard presets for zones | V66 |
| Z13 | Traps: hidden from players, over an area that pauses the game the first time a token enters | V66 |
| Z14 | Interiors: a building leads to its own interior scene, with linked entrance and exit and a choice of where tokens arrive; or upper floors in the same scene | V67, as the Wiki's nested locations |
| Z15 | Levels: add above and below, height bands, per-level background, foreground, fog image and look, preload; stairs, ladders, lifts and hatches joining levels; ceilings | V51 (one level first, `level_id` from day one) |
| Z16 | Map pins: a journal entry and page, icon, size, global, hidden; signs players read on hover | V14 (extended: readable signs) |
| Z17 | Map labels: text, size 8–256, colour, font, rotation, hidden | V33 |
| Z18 | Zones: circle, ellipse, ring, cone, line, rectangle, grid spaces, emanation; follows the grid; attached to a token; saved as presets | V15 (extended) |
| Z19 | Area effects: movement cost ×0–5; region settings and behaviours; spawning tokens into an area (counts, at the centre or anywhere, snapped, without overlap) | V15, V50; spawning is V68 |
| Z20 | Pre-placed tokens of world or compendium actors in a built map | V68 |
| Z21 | Map builder: compose a map from a short description (a map intent), with AI help; a floor plan from a seed; any map from a scene spec (a published JSON Schema). The result is ordinary editable features, undone in one step | V69 |
| Z22 | Cover graded on walls | V16 |
| Z23 | Wall thresholds (proximity) | V10 |
| Z24 | Asset packs (stamp-pack v1): stamps, texture sets, ambience, tiles, tokens, character art, music, sound effects, animations, scenes | V8 (extended to the whole pack) |
| Z25 | A script API: build from a spec, move the sun, export UVTT | V29, V41 (extended) |
| Z26 | Universal VTT export of the viewed level | V7, in the agreed maps plan |
| Z27 | Scene flags kept for game systems to find a place by | Data passthrough in the importer |

### Counts and the gaps that matter for the first release

| Product | Rows | Covered | Partial | Planned | Gap | Elsewhere | Out of scope |
|---|---|---|---|---|---|---|---|
| Foundry VTT | 58 | 1 | 14 | 37 | 3 | 2 | 1 |
| Roll20 | 44 | 1 | 13 | 22 | 6 | 0 | 2 |
| Inkarnate | 17 | 0 | 0 | 16 | 0 | 0 | 1 |

The **Gap** rows now have parity rows: V57–V62 below the matrix. Inkarnate's 16K export updates V38.

The first release is phases 1–3: data, dice and combat; scenes; the live table. What stands
between today and that:
1. **No play screens at all.** Everything Partial is server-side: there are no sheets, dice
   tray, chat, combat tracker or scene canvas (F21, F39, F46; R5, R20, R25).
2. **Maps:** Foundry scene and UVTT import, UVTT export and the mobile renderer (F3, F4, F32;
   R40). The plan is agreed, and the build waits on the operator's renderer and tiling
   choices.
3. **Lights and fog** (F8, F16, F24; R7, R9): the renderer's first job after walls. The
   Cartography fixture carries lights.
4. **Combat tracker** (F38, R15), phase 1.
5. **Sheets per system** (F46, R35): the data is there (`rpg_traits`, `rpg_systems`); the layout
   isn't (V26).
6. **Dice:** drawing from roll tables (F43), and the missing syntax that system packs will need:
   `rr`, `min`/`max`, pools, inline rolls, roll queries (F41, R24, V57).
7. **Roll modes and chat commands:** secret, blind and GM rolls, `/w`, `/em`, `/ooc` (F39, R22,
   R25).
8. **Invitations and roles,** including assistant GM (F53, R30, V30), for any table with more
   than one person.
9. **Settings and keybindings** (F56, R42, V62): the theme choice waits for the framework's
   settings page (card 253).

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

## Narrative and mechanical play

The AI product runs a campaign in a resolution mode its frame sets (zephyrex-rpg-ai
`docs/DESIGN.md`, *Narrative and mechanical modes*). A human GM at this table picks one the
same way. The VTT serves both modes:

- **Mechanical:** the VTT is the referee. Every check the system pack defines is rolled here,
  `legal_actions` lists what a combatant may do, and `apply_action` is the only way a sheet,
  condition or position changes. Results stand: the table can only override them by an
  explicit, logged GM action.
- **Narrative:** the VTT holds the map, the positions and the sheets as reference. Rolls are
  made on request, including light dice styles a system pack can declare (e.g. 2d6 with
  full success, partial and miss). Initiative and movement limits are off unless the GM
  calls for them.
- **Hybrid:** the mode follows the scene's kind (combat, social, exploration). The scene's
  mode is shown on the table's top bar and in the combat HUD.

A system pack (V26) declares which of its rules apply in each mode, so "mechanical" means the
pack's rules as written. Scenario encounters from the AI product open as VTT encounters, with
their combatants placed.

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
  `rpg_combat`, `rpg_cards` (ownership in [zephyrex-rpg-ai: docs/SUITE.md](https://github.com/JamesonRGrieve/zephyrex-rpg-ai/blob/main/docs/SUITE.md)). Mechanical events
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
2. Scenes: walls, doors, tokens, server-side vision and cover; map import (Foundry scene
   JSON and Universal VTT, with UVTT export) so zephyr-cartography's maps play here; the table
   canvas in play mode, rendered for phones first (operator, 2026-11-21).
3. Real-time table (after the framework room-sync capability lands), chat, rolls, fog,
   lighting.
4. Map editor: stamps, variants, terrain, paths, rooms; export and publish to the wiki.
5. System packs, compendia, Foundry world import, cards, playlists, AV chat.
6. The Inkarnate parity set: labels, filters, brushes, save as stamp, art styles, 8K
   export, gallery (V33–V39).
7. The content platform: packages, sandboxed scripts, adventures, character builder and
   vault, transfer between games, marketplace (V40–V46). Then the remaining play parity
   (V47–V55).

Ported back from the AI product's build: the shared UI shell, dice result cards, the
combat HUD, and the mechanics endpoints the AI GM proved out (phase 1 comes first for that
reason) ([zephyrex-rpg-ai: docs/DESIGN.md](https://github.com/JamesonRGrieve/zephyrex-rpg-ai/blob/main/docs/DESIGN.md)).

## Progress

| Item | State |
|---|---|
| Framework pins and lockfiles | `deploy/frameworks.env` pins all five frameworks; `client/pnpm-lock.yaml` and `server/uv.lock` are committed. |
| Lite edition, first slice | `VTT_VARIANT` switch (`route.lite.ts` in lite, `/api` proxied in SaaS), a Prisma SQLite store, `/api/v1/extension` and `/healthz`, and lite twins of rpg_state's game systems and campaigns on `@zephyrex/lite`, held to `contract/api-cases.json` on both back ends. |
| Lite owner | lite: one local owner for now; local accounts (V30) next as its own item. The owner is resolved in one place (`client/src/lib/owner.ts`) and every record keeps `createdById`, so local accounts swap the resolver, with no migration. |
| Landing | `/` on `@zephyrex/marketing`: what works today, with every planned feature marked "Planned". |
| rpg_state retired (operator, 2026-11-20) | The VTT server pins the wiki as a path source beside server-framework and reads extensions from both. The wiki owns `rpg_core` (campaigns and the person injection), `world_spatial` (locations), `world_social` (factions, the relationship injection), `world_inventory` (items) and `world_narrative` (hooks). The VTT keeps `rpg_systems` (game systems and the `game_system_id` injection) and `rpg_traits` (traits, derivative traits, person traits), each with its own initial migration. In progress: waits for the framework's multiple extension roots and a wiki pin with its migrations. Until the wiki's `world_narrative` (S3) and relationships (S4) land, `rpg_state` keeps only the hooks and the faction endpoints on relationships. A check counts an item's contributions while it is worn or wielded: its instance sits in an `equipment_slot` or `body_part` location (the wiki's world_spatial) bound to the character by `associated_person_id`; carried anywhere else, it is packed and doesn't count. Which slots a game system has comes from its system pack (V26). |
| Dice and checks (A21 for the AI product) | `rpg_dice`: dice notation (`server/extensions/rpg_dice/Dice.py`, its lite twin `client/src/features/dice/roll.ts`, both held to `contract/roll-cases.json`), rolled on the server with the system's random source; stats resolved through rpg_state's derivative pipeline (`Check.py`, `contract/check-cases.json`); `POST /v1/dice/roll` and `/check`, and the abilities `roll` and `check`. A check is for the campaign's GM or the character's own player. Its stats are read as the system, and a player sees contributions from records they can't read only as one `hidden` step with its net effect. A player may name the game system's stat templates (`campaign_id` NULL), which are the rules and public to every member, and the campaign traits they can read; any other name (a GM's undiscovered Curse) answers exactly as one that doesn't exist. Per-record hiding comes with `acl_rbac`. **Authoring note:** until then, a campaign's own public stats (a house-rule Sanity, say) are authored as game-system templates, not as campaign-scoped traits, so players can name them. Results are not yet written to the wiki's `rpg_log` (its own item). Lite lists `rpg_dice` once it has traits. |

| Scene awareness (A23 for the AI product) | `rpg_scene`: the scene, token and wall fields sight needs first (OBJECT_PLAN §4); `Vision.py`, pure line of sight held to `contract/vision-cases.json` (range, cone, normal, limited and one-way walls, open or broken doors, hidden tokens never perceived); `POST /v1/scene/{scene_id}/snapshot` and the ability `scene_snapshot`: the tokens a token sees, nearest first with their distance, and the doors. For the campaign's GM, or the player whose character the token is; anyone else gets the same 404 as a missing token. Not yet: lights (V11, so a dark scene shows nothing), elevation, fog memory, the map (the wiki's world_spatial). |

**Clamp, as the VTT reads it.** rpg_state says only that a clamp's sign "selects min vs max". The VTT
reads a value of 0 or more as a floor (the stat is at least it) and a negative value as a ceiling at
its size, so "never below 0" is `0` and "at most 20" is `-20`. A ceiling at 0 or below can't be
written this way. If a system needs one, the fix is two operations, `clamp_min` and `clamp_max`, in
rpg_traits' operation list.

## Proposed, not confirmed

Ideas this product proposes beyond the operator's confirmed scope above. **None is built until the
operator confirms it.** Size: S (days), M (one to two weeks), L (more). Requested 2026-11-20 for the
operator's review.

| # | Idea | Why it helps | Size | Depends on |
|---|---|---|---|---|
| VP1 | Map from a description | Draft a battlemap from a scene's text through the cartography composer, then edit it in the map editor | L | V1, the AI product |
| VP2 | Phone as a player controller | A minimal phone view (my token, my sheet, my dice) while a shared screen shows the map | M | V17, V32 |
| VP3 | Physical-table mode | A TV or projector shows the map top-down with fog, players use their phones, and a grid calibrates to real minis | M | VP2, V12 |
| VP4 | Encounter difficulty estimate | How hard a planned encounter is for this party, from the system pack, with the reasons shown | M | V26, the AI product's decision models |
| VP5 | Session replay | Scrub back through a session's token moves, rolls and chat | M | V17 (event log) |
| VP6 | Walls from an imported image | Detect walls and doors on an uploaded map image as a first draft to correct | M | V10 |
| VP7 | Accessible play | Colour-blind-safe token rings, a screen-reader summary of each combat turn, and a dyslexia-friendly font option | S | V20 |
| VP8 | Low-bandwidth table | Vector-only maps and no video for weak connections, chosen automatically from the device tier and connection | S | Device tier probe, V25 |
