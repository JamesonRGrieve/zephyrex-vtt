// SPDX-License-Identifier: AGPL-3.0-or-later
/** The scene view's pure geometry: the camera (pan and zoom), snapping and hit-testing tokens. */

export interface Camera {
  /** Screen pixels per scene pixel. */
  zoom: number;
  /** The scene point at the canvas's top-left corner. */
  x: number;
  y: number;
}

export interface Box {
  x: number;
  y: number;
  /** Grid cells. */
  width: number;
  height: number;
}

export const MIN_ZOOM = 0.1;
export const MAX_ZOOM = 4;

export function toScene(camera: Camera, sx: number, sy: number): [number, number] {
  return [camera.x + sx / camera.zoom, camera.y + sy / camera.zoom];
}

export function toScreen(camera: Camera, x: number, y: number): [number, number] {
  return [(x - camera.x) * camera.zoom, (y - camera.y) * camera.zoom];
}

/** The camera zoomed by `factor` about a screen point, which stays under the pointer. */
export function zoomAt(camera: Camera, factor: number, sx: number, sy: number): Camera {
  const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, camera.zoom * factor));
  const [px, py] = toScene(camera, sx, sy);
  return { zoom, x: px - sx / zoom, y: py - sy / zoom };
}

/** The camera moved by a screen-pixel drag. */
export function panBy(camera: Camera, dx: number, dy: number): Camera {
  return { ...camera, x: camera.x - dx / camera.zoom, y: camera.y - dy / camera.zoom };
}

/** A camera showing the whole scene (width × height) in a viewport, centred. */
export function fit(width: number, height: number, viewport: [number, number]): Camera {
  const [vw, vh] = viewport;
  const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.min(vw / Math.max(width, 1), vh / Math.max(height, 1))));
  return { zoom, x: -(vw / zoom - width) / 2, y: -(vh / zoom - height) / 2 };
}

/** A camera fitting the scene's width to the viewport (a phone held upright), centred vertically
 * when the scene is shorter than the viewport, else showing its top. */
export function fitWidth(width: number, height: number, viewport: [number, number]): Camera {
  const [vw, vh] = viewport;
  const zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, vw / Math.max(width, 1)));
  const shown = height * zoom;
  return { zoom, x: -(vw / zoom - width) / 2, y: shown < vh ? -(vh / zoom - height) / 2 : 0 };
}

/** A camera showing a box of the scene (its left, top, width, height) in a viewport, centred, no
 * closer than `maxZoom` (a lone token shouldn't fill the screen). */
export function fitBox(box: [number, number, number, number], viewport: [number, number], maxZoom = 1.5): Camera {
  const [left, top, width, height] = box;
  const [vw, vh] = viewport;
  const zoom = Math.min(maxZoom, MAX_ZOOM, Math.max(MIN_ZOOM, Math.min(vw / Math.max(width, 1), vh / Math.max(height, 1))));
  return { zoom, x: left - (vw / zoom - width) / 2, y: top - (vh / zoom - height) / 2 };
}

/** The box around tokens, padded by `pad` cells on every side; null with no tokens. */
export function tokensBox<T extends Box>(
  tokens: readonly T[],
  grid: number,
  pad = 3,
): [number, number, number, number] | null {
  if (tokens.length === 0) return null;
  const left = Math.min(...tokens.map((one) => one.x)) - pad * grid;
  const top = Math.min(...tokens.map((one) => one.y)) - pad * grid;
  const right = Math.max(...tokens.map((one) => one.x + one.width * grid)) + pad * grid;
  const bottom = Math.max(...tokens.map((one) => one.y + one.height * grid)) + pad * grid;
  return [left, top, right - left, bottom - top];
}

/** The smallest tap target, in screen pixels (WCAG 2.5.5's 44 px). */
export const MIN_TARGET = 44;

/** A token's top-left snapped so it sits on the grid. */
export function snap(x: number, y: number, grid: number): [number, number] {
  return [Math.round(x / grid) * grid, Math.round(y / grid) * grid];
}

/** The topmost token under a scene point (the last drawn wins), or null. `minSize` (scene units)
 * grows a small token's hit box about its centre, so a far-out zoom still leaves a 44 px target. */
export function tokenAt<T extends Box>(tokens: readonly T[], x: number, y: number, grid: number, minSize = 0): T | null {
  for (let index = tokens.length - 1; index >= 0; index -= 1) {
    const token = tokens[index]!;
    const width = Math.max(token.width * grid, minSize);
    const height = Math.max(token.height * grid, minSize);
    const left = token.x + (token.width * grid - width) / 2;
    const top = token.y + (token.height * grid - height) / 2;
    if (x >= left && x < left + width && y >= top && y < top + height) return token;
  }
  return null;
}

export interface Measured {
  /** Grid cells between the two points, counting a diagonal step as one (the grid's own reckoning). */
  cells: number;
  distance: number;
  label: string;
}

/** The distance from one scene point to another in the scene's units: whole cells, each `distance`. */
export function measure(
  from: readonly [number, number],
  to: readonly [number, number],
  grid: number,
  distance: number,
  units: string,
): Measured {
  const cells = Math.round(Math.max(Math.abs(to[0] - from[0]), Math.abs(to[1] - from[1])) / grid);
  const total = cells * distance;
  return { cells, distance: total, label: `${total} ${units}`.trim() };
}

export interface DoorLike {
  points: number[][];
  door_type?: string | null;
}

/** The door whose middle is nearest a scene point, within `radius`; walls that aren't doors don't count. */
export function doorAt<T extends DoorLike>(walls: readonly T[], x: number, y: number, radius: number): T | null {
  let best: T | null = null;
  let nearest = radius;
  for (const wall of walls) {
    if (!wall.door_type || wall.door_type === 'none' || wall.points.length === 0) continue;
    const cx = wall.points.reduce((sum, point) => sum + (point[0] ?? 0), 0) / wall.points.length;
    const cy = wall.points.reduce((sum, point) => sum + (point[1] ?? 0), 0) / wall.points.length;
    const away = Math.hypot(cx - x, cy - y);
    if (away <= nearest) {
      nearest = away;
      best = wall;
    }
  }
  return best;
}
