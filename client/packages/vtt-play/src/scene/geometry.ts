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

/** A token's top-left snapped so it sits on the grid. */
export function snap(x: number, y: number, grid: number): [number, number] {
  return [Math.round(x / grid) * grid, Math.round(y / grid) * grid];
}

/** The topmost token under a scene point (the last drawn wins), or null. */
export function tokenAt<T extends Box>(tokens: readonly T[], x: number, y: number, grid: number): T | null {
  for (let index = tokens.length - 1; index >= 0; index -= 1) {
    const token = tokens[index]!;
    if (x >= token.x && x < token.x + token.width * grid && y >= token.y && y < token.y + token.height * grid) return token;
  }
  return null;
}
