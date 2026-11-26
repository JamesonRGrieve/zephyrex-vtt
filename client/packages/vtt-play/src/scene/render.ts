// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Draws a scene view on a 2D canvas, once per call: the scene's ground, its grid, walls and doors
 * (the GM's whole set, or only the doors a player's token sees), and tokens. Called on change only
 * (the view arrived, the camera moved, a token is being dragged), never in a loop, so a settled
 * scene costs no frames. Colours come from the theme tokens, so it follows light and dark.
 */
import { spreadDiscs, toScreen, type Camera, type Disc } from './geometry';
import type { SceneViewData, ViewToken } from './schemas';

export interface Palette {
  ground: string;
  grid: string;
  wall: string;
  door: string;
  ink: string;
  friendly: string;
  hostile: string;
  neutral: string;
  mine: string;
}

/** A colour a canvas accepts, whatever form the theme gives a token in: a full colour (oklch(...),
 * #hex, rgb(...)), or a bare channel list as shadcn themes store them ("240 4.8% 95.9%" for
 * hsl(), "0.97 0 0" for oklch()). An invalid fill is ignored by a canvas (it keeps black), so each
 * candidate is checked, and the fallback used when none is a colour. */
export function resolveColour(value: string, fallback: string): string {
  const raw = value.trim();
  if (!raw) return fallback;
  const supports = (candidate: string): boolean =>
    typeof CSS !== 'undefined' && typeof CSS.supports === 'function' ? CSS.supports('color', candidate) : false;
  const candidates = /^[\d.]/.test(raw) ? [`hsl(${raw})`, `oklch(${raw})`, raw] : [raw];
  return candidates.find(supports) ?? fallback;
}

function token(style: CSSStyleDeclaration, name: string, fallback: string): string {
  return resolveColour(style.getPropertyValue(name), fallback);
}

export function paletteOf(element: Element): Palette {
  const style = getComputedStyle(element);
  return {
    ground: token(style, '--muted', '#f4f4f5'),
    grid: token(style, '--border', '#d4d4d8'),
    wall: token(style, '--foreground', '#18181b'),
    door: token(style, '--chart-4', '#d97706'),
    ink: token(style, '--primary-foreground', '#ffffff'),
    friendly: token(style, '--chart-2', '#16a34a'),
    hostile: token(style, '--destructive', '#dc2626'),
    neutral: token(style, '--muted-foreground', '#71717a'),
    mine: token(style, '--primary', '#7a34f2'),
  };
}

// Pictures (a location's painting, a character's portrait), loaded once each. A picture that isn't
// loaded yet draws nothing; its load asks for one more draw (the `redraw` a caller passes).
const pictures = new Map<string, HTMLImageElement>();
const waiting = new Map<string, Set<() => void>>();

function picture(url: string | null | undefined, redraw?: () => void): HTMLImageElement | null {
  if (!url || typeof Image === 'undefined') return null;
  const known = pictures.get(url);
  if (known) return known.complete && known.naturalWidth > 0 ? known : null;
  const image = new Image();
  image.decoding = 'async';
  image.referrerPolicy = 'no-referrer';
  pictures.set(url, image);
  if (redraw) waiting.set(url, new Set([redraw]));
  const done = (): void => {
    for (const again of waiting.get(url) ?? []) again();
    waiting.delete(url);
  };
  image.onload = done;
  image.onerror = done;
  image.src = url;
  return null;
}

/** An image drawn to cover a box (cropped, never stretched). */
function cover(
  context: CanvasRenderingContext2D,
  image: HTMLImageElement,
  x: number,
  y: number,
  w: number,
  h: number,
): void {
  const scale = Math.max(w / image.naturalWidth, h / image.naturalHeight);
  const sw = w / scale;
  const sh = h / scale;
  context.drawImage(image, (image.naturalWidth - sw) / 2, (image.naturalHeight - sh) / 2, sw, sh, x, y, w, h);
}

function initials(name: string | null | undefined): string {
  const words = (name ?? '?').trim().split(/\s+/);
  return (words.length > 1 ? `${words[0]![0]}${words[1]![0]}` : (words[0] ?? '?').slice(0, 2)).toUpperCase();
}

function fill(one: ViewToken, palette: Palette): string {
  if (one.mine) return palette.mine;
  if (one.disposition === 'hostile') return palette.hostile;
  if (one.disposition === 'friendly') return palette.friendly;
  return palette.neutral;
}

export interface Drag {
  id: string;
  x: number;
  y: number;
}

/** A measuring line, in scene coordinates, with its distance. */
export interface Ruler {
  from: [number, number];
  to: [number, number];
  label: string;
}

/** The smallest a token is drawn on screen, in CSS pixels (its portrait and name still read). */
export const MIN_DRAWN_RADIUS = 11;

/** A lying item's diamond: gold, unlike any disposition's colour. */
export const ITEM_FILL = '#d4a017';

export function drawScene(
  context: CanvasRenderingContext2D,
  view: SceneViewData,
  camera: Camera,
  size: [number, number],
  palette: Palette,
  drag: Drag | null = null,
  selected: string | null = null,
  redraw?: () => void,
  ruler: Ruler | null = null,
): Disc[] {
  const [width, height] = size;
  const grid = view.grid_size;
  context.clearRect(0, 0, width, height);
  const sceneWidth = view.width ?? 40 * grid;
  const sceneHeight = view.height ?? 30 * grid;
  const [left, top] = toScreen(camera, 0, 0);
  context.fillStyle = view.background_color ?? palette.ground;
  context.fillRect(left, top, sceneWidth * camera.zoom, sceneHeight * camera.zoom);
  // The scene's battlemap art (never a place's illustration): cover-fitted, a little dimmed so the grid
  // and tokens read over it.
  const backdrop = picture(view.background_url, redraw);
  if (backdrop) {
    context.globalAlpha = 0.85;
    cover(context, backdrop, left, top, sceneWidth * camera.zoom, sceneHeight * camera.zoom);
    context.globalAlpha = 1;
  }
  // The grid, only where it's visible and only when cells are big enough to read.
  if (grid * camera.zoom >= 8) {
    // Over map art the grid is a faint guide, not a second picture on top of it.
    context.strokeStyle = backdrop ? palette.wall : palette.grid;
    context.globalAlpha = backdrop ? 0.14 : 1;
    context.lineWidth = 1;
    context.beginPath();
    for (let x = 0; x <= sceneWidth; x += grid) {
      const [sx] = toScreen(camera, x, 0);
      if (sx < 0 || sx > width) continue;
      context.moveTo(sx + 0.5, Math.max(top, 0));
      context.lineTo(sx + 0.5, Math.min(top + sceneHeight * camera.zoom, height));
    }
    for (let y = 0; y <= sceneHeight; y += grid) {
      const [, sy] = toScreen(camera, 0, y);
      if (sy < 0 || sy > height) continue;
      context.moveTo(Math.max(left, 0), sy + 0.5);
      context.lineTo(Math.min(left + sceneWidth * camera.zoom, width), sy + 0.5);
    }
    context.stroke();
    context.globalAlpha = 1;
  }

  if (view.name && !backdrop) {
    // No map art: the place, named large across what's on screen (operator, 2026-11-24: never a
    // bare grid), sized to fit the visible part of the scene, with a line saying there's no map yet.
    const visibleLeft = Math.max(left, 0);
    const visibleRight = Math.min(left + sceneWidth * camera.zoom, width);
    const visibleTop = Math.max(top, 0);
    const visibleBottom = Math.min(top + sceneHeight * camera.zoom, height);
    if (visibleRight > visibleLeft && visibleBottom > visibleTop) {
      const span = visibleRight - visibleLeft;
      const middleX = (visibleLeft + visibleRight) / 2;
      const middleY = visibleTop + (visibleBottom - visibleTop) * 0.3;
      let big = Math.max(16, Math.min(40, span / 10));
      context.font = `700 ${Math.round(big)}px system-ui, sans-serif`;
      const wide = context.measureText(view.name).width;
      if (wide > span * 0.9) big = Math.max(12, (big * span * 0.9) / wide);
      context.fillStyle = palette.neutral;
      context.globalAlpha = 0.55;
      context.font = `700 ${Math.round(big)}px system-ui, sans-serif`;
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      context.fillText(view.name, middleX, middleY);
      context.font = '500 13px system-ui, sans-serif';
      context.fillText('No map of this place yet', middleX, middleY + big * 0.9);
      context.globalAlpha = 1;
    }
  }

  for (const wall of view.walls) {
    const door = wall.door_type && wall.door_type !== 'none';
    // Map art draws its own walls: over it only the doors show (they open and shut); a map with no
    // art is its walls (operator, 2026-11-24: traced walls in black over the art buried it).
    if (backdrop && !door) continue;
    context.strokeStyle = door ? palette.door : palette.wall;
    context.lineWidth = door ? 5 : 3;
    context.setLineDash(door && wall.door_state === 'open' ? [6, 6] : []);
    context.beginPath();
    wall.points.forEach(([x, y], index) => {
      const [sx, sy] = toScreen(camera, x ?? 0, y ?? 0);
      if (index === 0) context.moveTo(sx, sy);
      else context.lineTo(sx, sy);
    });
    context.stroke();
  }
  context.setLineDash([]);

  // Things lying here, under the tokens: a gold diamond on their square, readable at any zoom.
  for (const item of view.items ?? []) {
    const [ix, iy] = toScreen(camera, item.x + grid / 2, item.y + grid / 2);
    const half = Math.max((grid * camera.zoom) / 4, 7);
    context.save();
    context.fillStyle = ITEM_FILL;
    context.strokeStyle = palette.ink;
    context.lineWidth = 1.5;
    context.beginPath();
    context.moveTo(ix, iy - half);
    context.lineTo(ix + half, iy);
    context.lineTo(ix, iy + half);
    context.lineTo(ix - half, iy);
    context.closePath();
    context.fill();
    context.stroke();
    context.restore();
  }

  // Each name chip drawn so far, so the next steps aside rather than covering one (left, top, right, bottom).
  const chips: [number, number, number, number][] = [];
  const hits = (box: [number, number, number, number]): boolean =>
    chips.some(([l, t, r, b]) => box[0] < r && box[2] > l && box[1] < b && box[3] > t);
  // Every token's disc on screen, so a name chip covers no one else's face; spread apart where
  // they'd overlap (a far-out zoom: a whole town on a phone), each drawn where it ends up.
  const exact = view.tokens.map((one) => {
    const at = drag && drag.id === one.id ? drag : one;
    const [x, y] = toScreen(camera, at.x, at.y);
    const w = one.width * grid * camera.zoom;
    const h = one.height * grid * camera.zoom;
    return { id: one.id, cx: x + w / 2, cy: y + h / 2, r: Math.max(Math.min(w, h) / 2 - 2, MIN_DRAWN_RADIUS) };
  });
  const discs = spreadDiscs(exact);
  const drawnAt = new Map(discs.map((disc) => [disc.id, disc]));
  const exactAt = new Map(exact.map((disc) => [disc.id, disc]));
  const coversDisc = (box: [number, number, number, number], id: string): boolean =>
    discs.some(
      (d) => d.id !== id && box[0] < d.cx + d.r && box[2] > d.cx - d.r && box[1] < d.cy + d.r && box[3] > d.cy - d.r,
    );
  for (const one of view.tokens) {
    const at = drag && drag.id === one.id ? drag : one;
    let [sx, sy] = toScreen(camera, at.x, at.y);
    const w = one.width * grid * camera.zoom;
    const h = one.height * grid * camera.zoom;
    // Never smaller on screen than a readable disc (operator, 2026-11-24: on a whole town the cast
    // were 7 px dots with no faces or names); taps already reach 44 px around (MIN_TARGET).
    const radius = Math.max(Math.min(w, h) / 2 - 2, MIN_DRAWN_RADIUS);
    // Where the disc is drawn: spread from its square when it would cover a neighbour, with a fine
    // line back to the square it stands on so the board stays exact.
    const disc = drawnAt.get(one.id);
    const truth = exactAt.get(one.id);
    const dx = disc && truth ? disc.cx - truth.cx : 0;
    const dy = disc && truth ? disc.cy - truth.cy : 0;
    sx += dx;
    sy += dy;
    if (truth && Math.hypot(dx, dy) > 2) {
      context.save();
      context.globalAlpha = 0.8;
      context.strokeStyle = fill(one, palette);
      context.lineWidth = 1.5;
      context.beginPath();
      context.moveTo(truth.cx, truth.cy);
      context.lineTo(sx + w / 2, sy + h / 2);
      context.stroke();
      context.beginPath();
      context.arc(truth.cx, truth.cy, 2.5, 0, Math.PI * 2);
      context.fillStyle = fill(one, palette);
      context.fill();
      context.restore();
    }
    context.globalAlpha = one.is_hidden ? 0.45 : 1;
    context.fillStyle = fill(one, palette);
    context.beginPath();
    context.arc(sx + w / 2, sy + h / 2, Math.max(radius, 2), 0, Math.PI * 2);
    context.fill();
    const portrait = radius >= 8 ? picture(one.picture_url, redraw) : null;
    if (portrait) {
      // The portrait inside a ring of the token's colour (whose it is: yours, friend, foe).
      context.save();
      context.beginPath();
      context.arc(sx + w / 2, sy + h / 2, Math.max(radius - 3, 2), 0, Math.PI * 2);
      context.clip();
      cover(context, portrait, sx + w / 2 - radius, sy + h / 2 - radius, radius * 2, radius * 2);
      context.restore();
    }
    if (one.is_hidden) {
      context.setLineDash([4, 4]);
      context.strokeStyle = palette.wall;
      context.stroke();
      context.setLineDash([]);
    }
    if (radius >= 10 && !portrait) {
      context.fillStyle = palette.ink;
      context.font = `600 ${Math.round(radius * 0.8)}px system-ui, sans-serif`;
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      context.fillText(initials(one.name), sx + w / 2, sy + h / 2);
    }
    if (one.id !== selected && radius >= 8 && one.name) {
      // Every token's name under it (operator, 2026-11-24), on a faint chip so it reads over art.
      context.font = '600 11px system-ui, sans-serif';
      const label = one.name.length > 18 ? `${one.name.slice(0, 17)}…` : one.name;
      const textWidth = context.measureText(label).width;
      // Below the token, else above, right or left: the first place that covers no other name or
      // face (operator, 2026-11-24: names lay across neighbours in a cluster). With none clear,
      // the name waits for the token to be selected; its face or initials still say who it is.
      const cx = sx + w / 2;
      const cy = sy + h / 2;
      const chipW = textWidth + 8;
      // Kept inside the canvas: a name at the edge of the view slides in rather than being cut off.
      const inside = ([x, y]: [number, number]): [number, number] => [
        Math.min(Math.max(x, 2), Math.max(2, width - chipW - 2)),
        Math.min(Math.max(y, 2), Math.max(2, height - 17)),
      ];
      const places: [number, number][] = (
        [
          [cx - chipW / 2, cy + radius + 2],
          [cx - chipW / 2, cy - radius - 17],
          [cx + radius + 3, cy - 7.5],
          [cx - radius - 3 - chipW, cy - 7.5],
        ] as [number, number][]
      ).map(inside);
      // A token off the view has no name on it: a clamped name would sit beside someone else.
      const onScreen = cx >= 0 && cx <= width && cy >= 0 && cy <= height;
      const spot = !onScreen
        ? undefined
        : places.find(([x, y]) => !hits([x, y, x + chipW, y + 15]) && !coversDisc([x, y, x + chipW, y + 15], one.id));
      if (spot) {
        const [chipX, chipY] = spot;
        chips.push([chipX, chipY, chipX + chipW, chipY + 15]);
        context.globalAlpha = one.is_hidden ? 0.45 : 0.85;
        context.fillStyle = palette.ground;
        context.beginPath();
        context.roundRect?.(chipX, chipY, chipW, 15, 4);
        context.fill();
        context.fillStyle = palette.wall;
        context.textAlign = 'center';
        context.textBaseline = 'middle';
        context.fillText(label, chipX + chipW / 2, chipY + 8);
      }
    }
    context.globalAlpha = 1;
    if (one.id === selected) {
      // Selected: a ring and the name in a chip above, readable at any zoom.
      context.strokeStyle = palette.mine;
      context.lineWidth = 3;
      context.beginPath();
      context.arc(sx + w / 2, sy + h / 2, Math.max(radius, 2) + 4, 0, Math.PI * 2);
      context.stroke();
      const label = one.name ?? 'Token';
      context.font = '600 13px system-ui, sans-serif';
      const textWidth = context.measureText(label).width;
      const chipX = sx + w / 2 - textWidth / 2 - 8;
      const chipY = sy + h / 2 - radius - 30;
      context.fillStyle = palette.wall;
      context.beginPath();
      context.roundRect?.(chipX, chipY, textWidth + 16, 22, 11);
      context.fill();
      context.fillStyle = palette.ground;
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      context.fillText(label, sx + w / 2, chipY + 11);
    }
  }
  if (ruler) {
    const [ax, ay] = toScreen(camera, ruler.from[0], ruler.from[1]);
    const [bx, by] = toScreen(camera, ruler.to[0], ruler.to[1]);
    context.setLineDash([]);
    context.strokeStyle = palette.door;
    context.lineWidth = 3;
    context.beginPath();
    context.moveTo(ax, ay);
    context.lineTo(bx, by);
    context.stroke();
    context.font = '600 14px sans-serif';
    const text = ruler.label;
    const width = context.measureText(text).width + 12;
    context.fillStyle = palette.wall;
    context.fillRect(bx + 8, by - 26, width, 22);
    context.fillStyle = palette.ground;
    context.fillText(text, bx + 14, by - 10);
  }
  return discs;
}
