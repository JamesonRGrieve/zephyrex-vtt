#!/usr/bin/env bash
# SPDX-License-Identifier: AGPL-3.0-or-later
# Builds the wiki's client package (@zephyrex-rpg/wiki: its pages, components and data hooks) from
# the pinned wiki checkout fetch-frameworks.sh laid out, and puts its dist/ into this app's injected
# copy. The VTT includes the wiki out of the box (operator, 2026-11-21).
#
# It compiles against this app's own installed dependencies (the wiki checkout's client/node_modules
# is a link to ours): the package's peers (react, next, zephyrex at our pins, swr, lucide-react,
# zod) are exactly what it runs against once injected, one tree, not the wiki app's own pins.
# Run after `pnpm install` in the client (and after the framework packages are compiled).
# Usage: deploy/compile-wiki.sh <root laid out by fetch-frameworks.sh>
set -euo pipefail
root=$(realpath -m "$1")
client="$root/zephyrex-vtt/client"
wiki="$root/zephyrex-rpg-wiki/client"
package="$wiki/packages/wiki"
[ -d "$client/node_modules" ] || { echo "install the client first (pnpm install in $client)" >&2; exit 1; }
[ -f "$package/package.json" ] || { echo "no wiki checkout at $wiki (deploy/fetch-frameworks.sh)" >&2; exit 1; }
if [ -e "$wiki/node_modules" ] && [ ! -L "$wiki/node_modules" ]; then
  echo "$wiki/node_modules is a real install; compile-wiki.sh links it to the VTT client's" >&2
  exit 1
fi
ln -sfn "$client/node_modules" "$wiki/node_modules"
# --no-lite: vtt doesn't mount the wiki's lite API (rpg-ai lite does), and src/lite types against a
# Prisma client generated with the wiki's models, which this app doesn't have. Older compile scripts
# ignore the flag (they have no src/lite).
(cd "$package" && node scripts/compile.mjs --no-lite)
installed=$(realpath "$client/node_modules/@zephyrex-rpg/wiki")
rm -rf "$installed/dist"
cp -a "$package/dist" "$installed/dist"
test -f "$installed/dist/extension.js"
echo "@zephyrex-rpg/wiki dist in $installed"
