// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Draws a scene view on a 2D canvas, once per call: the scene's ground, its grid, walls and doors
 * (the GM's whole set, or only the doors a player's token sees), and tokens. Called on change only
 * (the view arrived, the camera moved, a token is being dragged), never in a loop, so a settled
 * scene costs no frames. Colours come from the theme tokens, so it follows light and dark.
 */
import { toScreen, type Camera } from './geometry';
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
): void {
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
  // The place's name, faint in the scene's corner: a map with no art still says where it is.
  if (view.name) {
    context.fillStyle = palette.neutral;
    context.globalAlpha = 0.6;
    context.font = '600 14px system-ui, sans-serif';
    context.textAlign = 'left';
    context.textBaseline = 'top';
    context.fillText(view.name, Math.max(left, 0) + 8, Math.max(top, 0) + 8);
    context.globalAlpha = 1;
  }

  // The grid, only where it's visible and only when cells are big enough to read.
  if (grid * camera.zoom >= 8) {
    context.strokeStyle = palette.grid;
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
  }

  for (const wall of view.walls) {
    const door = wall.door_type && wall.door_type !== 'none';
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

  for (const one of view.tokens) {
    const at = drag && drag.id === one.id ? drag : one;
    const [sx, sy] = toScreen(camera, at.x, at.y);
    const w = one.width * grid * camera.zoom;
    const h = one.height * grid * camera.zoom;
    const radius = Math.min(w, h) / 2 - 2;
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
      const chipY = sy - 28;
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
}
