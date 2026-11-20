# Design Lessons (cross-pollinated)

Entity-model lessons learned while building **separate** sibling projects, kept
here because they could improve this repo's object model (see `OBJECT_PLAN.md`,
esp. `world_spatial` and `rpg_scene`). These are **design insights only** — the
source projects are independent, not integration targets.

---

## From `dh-cartography-draw` (a standalone AGPL Foundry cartography plugin)

An in-Foundry map painter (roads/rivers, biome terrain regions, brush painting,
textured rendering, room/wall structure mapping). Building its feature model
surfaced these entity-relationship observations relevant to `world_spatial` /
`rpg_scene`:

### 1. Terrain "area" and terrain "stroke" are two distinct geometries
`TerrainRegionModel` models a **closed polygon** (an area fill — a lake, a
forest). But brush-*painting* terrain produces an **open centerline + width**
swath (a mossy trail, a scorch streak) that degrades badly if forced into a
polygon. In the plugin these are separate feature types (`RegionFeature` =
closed polygon; `StrokeFeature` = centerline + radius). **Suggestion:** give the
terrain entity a `geometry_kind` discriminator (`polygon` | `stroke`), where
`stroke` carries a centerline + width, or add a sibling stroke entity. The
authoring intents are genuinely different.

### 2. Paths and terrain-strokes are the same geometric primitive
`MapPathModel` (road/river = points + `stroke_width`) and a terrain brush stroke
are structurally identical: a **centerline + width ribbon**. They differ only in
*fill semantics* (a stroked line vs. a texture-filled swath). **Suggestion:**
model one shared ribbon/centerline primitive with a `fill_mode`
(`stroke` | `fill_textured`), rather than two parallel "width-along-a-centerline"
implementations. (The plugin reuses one ribbon builder for both roads and
terrain strokes — one code path, two fills.)

### 3. Texture selection wants a Pack/Theme entity, not just a per-object asset FK
The plugin bundles **multiple swappable texture packs** (verified CC0: Poly
Haven, ambientCG), where a biome's texture resolves as **(pack × role) → asset**
and the whole scene can switch packs at once (one setting). Modeling each
region/wall/tile with a single `texture_asset_id` FK makes a theme swap an
O(n)-edit. **Suggestion:** a `TexturePack`/`Theme` entity + a stable `role` key
on terrain/wall/tile (biome name, "road", "floor", etc.); a scene/room points at
a pack, and per-object `texture_asset_id` becomes an *override*, not the primary
selector. Lets a GM re-skin a whole map by changing one FK.

### 4. (Validated) Doors as a wall attribute, not a stamp
The plugin is deliberately no-stamp, which forced doors to be modeled as a
**property of the wall segment**. This matches — and validates —
`SceneWallModel.door_type`/`door_state`. Keeping doors on the wall (rather than a
separate door stamp/entity) is the right call: it keeps the wall graph and the
door state in one place and avoids a stamp↔wall join.
