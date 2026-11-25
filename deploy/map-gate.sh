#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# The map gate (the operator, 2026-11-25: "Maps are still completely fucked and need a whole testing
# framework on the part of VTT"): every change to rpg_scene, vtt-play's scene, the map fixtures or
# the e2e harnesses runs this, and a map regression fails the build.
#   1. the server's map tests: the play script through a real start (EP_MapPlay, exporting each
#      step's view), a place's map made its scene (EP_LocationMap), the shared copy (EP_Template),
#      moves (EP_Pilot) and the current scene (EP_CurrentScene);
#   2. the browser: every play step drawn at a phone's and a desktop's width (map-play.spec: the
#      scene, its art, everyone on their own square, no disc over another), and the map on a phone
#      (scene-mobile.spec: open, pan, pinch, taps, drags, doors). Screenshots land in <out>/map-shots
#      for the review the SOP asks.
# Usage: deploy/map-gate.sh <root> <out>
#   <root> laid out by deploy/fetch-frameworks.sh, the server synced (uv) and the client installed
#   (pnpm); <out> a local (never NFS) directory. GATE_CORES (a taskset list) pins it when set.
set -uo pipefail
root=${1:?usage: map-gate.sh <root> <out>}
out=${2:?usage: map-gate.sh <root> <out>}
app="$root/zephyrex-vtt"
mkdir -p "$out/map-play" "$out/map-shots" "$out/e2e"
pin=()
[ -n "${GATE_CORES:-}" ] && pin=(taskset -c "$GATE_CORES")
status=0

echo "== map gate: server"
(
  cd "$app/server" &&
    MAP_PLAY_OUT="$out/map-play" "${pin[@]}" uv run --locked python -m pytest -q -p no:cacheprovider -o addopts= \
      extensions/rpg_scene/EP_MapPlay_test.py extensions/rpg_scene/EP_LocationMap_test.py \
      extensions/rpg_scene/EP_Template_test.py extensions/rpg_scene/EP_Pilot_test.py \
      extensions/rpg_scene/EP_CurrentScene_test.py
) || { echo "FAIL map gate: server"; status=1; }
steps=$(ls "$out/map-play"/*.json 2>/dev/null | wc -l)
[ "$steps" -ge 6 ] || { echo "FAIL map gate: the play script exported $steps steps, not 6"; status=1; }

echo "== map gate: browser"
cd "$app/client" || exit 2
esbuild=$(ls node_modules/.pnpm/esbuild@*/node_modules/esbuild/bin/esbuild 2>/dev/null | head -1)
[ -x "$esbuild" ] || { echo "FAIL map gate: no esbuild (install the client first)"; exit 1; }
for harness in harness map-play-harness; do
  "$esbuild" "packages/vtt-play/e2e/$harness.tsx" --bundle --format=iife --jsx=automatic \
    --define:process.env.NODE_ENV='"production"' --outfile="$out/e2e/$harness.js" --log-level=warning ||
    { echo "FAIL map gate: bundle $harness"; status=1; }
done
HARNESS_JS="$out/e2e/harness.js" MAP_PLAY_JS="$out/e2e/map-play-harness.js" MAP_PLAY_DIR="$out/map-play" \
  MAP_PLAY_SHOTS="$out/map-shots" "${pin[@]}" ./node_modules/.bin/playwright test \
  -c packages/vtt-play/e2e/playwright.config.ts map-play.spec.ts scene-mobile.spec.ts --output "$out/e2e/results" ||
  { echo "FAIL map gate: browser"; status=1; }

[ "$status" -eq 0 ] && echo "PASS map gate ($steps steps, $(ls "$out/map-shots" | wc -l) screenshots in $out/map-shots)"
exit "$status"
