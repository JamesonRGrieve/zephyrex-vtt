// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * The scene's canvas: the map drawn on a 2D canvas only when something changes, with one-finger pan
 * (drag the ground), pinch and wheel zoom (the page doesn't scroll under it), and dragging tokens
 * this person may move (the GM any, a player their own) with a 44 px target at any zoom; it snaps to
 * the grid, and the server refuses a move through a wall. It opens fitted to its width, and follows
 * its box's size until the player pans or zooms (a panel that opens later measures 0 at first).
 * No data fetching: SceneView wraps it with the server's view.
 */
import { useCallback, useEffect, useRef, type PointerEvent, type ReactNode } from 'react';
import { fitWidth, MIN_TARGET, panBy, snap, toScene, tokenAt, zoomAt, type Camera } from './geometry';
import { drawScene, paletteOf, type Drag } from './render';
import type { SceneViewData, ViewToken } from './schemas';

export function movable(view: SceneViewData, one: ViewToken): boolean {
  return view.gm || one.mine;
}

/** The scene's canvas alone (pan, pinch, wheel zoom, dragging tokens), for embedding and tests. */
export function SceneCanvas({
  view,
  onMove,
}: {
  view: SceneViewData;
  onMove: (token: ViewToken, x: number, y: number) => void;
}): ReactNode {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const camera = useRef<Camera | null>(null);
  const drag = useRef<(Drag & { offsetX: number; offsetY: number; token: ViewToken }) | null>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const viewRef = useRef(view);
  // Until the player pans or zooms, the camera follows the box's size: a panel that opens after the
  // map mounts (a phone's sheet, a tab) measures 0 at first, and a fit made then would be useless.
  const touched = useRef(false);

  const refit = useCallback(() => {
    const element = canvas.current;
    if (!element || touched.current) return;
    const width = element.clientWidth;
    const height = element.clientHeight;
    if (width < 2 || height < 2) return;
    const grid = viewRef.current.grid_size;
    camera.current = fitWidth(viewRef.current.width ?? 40 * grid, viewRef.current.height ?? 30 * grid, [width, height]);
  }, []);

  const draw = useCallback(() => {
    const element = canvas.current;
    const context = element?.getContext('2d');
    if (!element || !context || !camera.current) return;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    const width = element.clientWidth;
    const height = element.clientHeight;
    if (element.width !== Math.round(width * ratio)) element.width = Math.round(width * ratio);
    if (element.height !== Math.round(height * ratio)) element.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    drawScene(context, viewRef.current, camera.current, [width, height], paletteOf(element), drag.current);
    // The camera, for tests and tools (zoom, then the scene point at the top-left).
    element.dataset.camera = `${camera.current.zoom.toFixed(4)},${camera.current.x.toFixed(1)},${camera.current.y.toFixed(1)}`;
  }, []);

  useEffect(() => {
    viewRef.current = view;
    if (!camera.current) refit();
    draw();
  }, [view, draw, refit]);

  useEffect(() => {
    const element = box.current;
    if (!element || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(() => {
      refit();
      draw();
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [draw, refit]);

  // Wheel zoom over the map, without the page scrolling under it: React's wheel listener is
  // passive, so this one is added by hand.
  useEffect(() => {
    const element = canvas.current;
    if (!element) return undefined;
    const wheel = (event: WheelEvent): void => {
      if (!camera.current) return;
      event.preventDefault();
      touched.current = true;
      const rect = element.getBoundingClientRect();
      camera.current = zoomAt(
        camera.current,
        event.deltaY < 0 ? 1.15 : 1 / 1.15,
        event.clientX - rect.left,
        event.clientY - rect.top,
      );
      draw();
    };
    element.addEventListener('wheel', wheel, { passive: false });
    return () => element.removeEventListener('wheel', wheel);
  }, [draw]);

  const local = (event: PointerEvent<HTMLCanvasElement>): [number, number] => {
    const rect = event.currentTarget.getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
  };

  const down = (event: PointerEvent<HTMLCanvasElement>): void => {
    if (!camera.current) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const [sx, sy] = local(event);
    pointers.current.set(event.pointerId, { x: sx, y: sy });
    if (pointers.current.size > 1) {
      drag.current = null;
      return;
    }
    const [x, y] = toScene(camera.current, sx, sy);
    const hit = tokenAt(viewRef.current.tokens, x, y, viewRef.current.grid_size, MIN_TARGET / camera.current.zoom);
    if (hit && movable(viewRef.current, hit)) {
      drag.current = { id: hit.id, x: hit.x, y: hit.y, offsetX: x - hit.x, offsetY: y - hit.y, token: hit };
    }
  };

  const moveTo = (event: PointerEvent<HTMLCanvasElement>): void => {
    const last = pointers.current.get(event.pointerId);
    if (!last || !camera.current) return;
    const [sx, sy] = local(event);
    if (!drag.current) touched.current = true;
    if (pointers.current.size === 2) {
      const other = [...pointers.current.entries()].find(([id]) => id !== event.pointerId)?.[1];
      if (other) {
        const before = Math.hypot(last.x - other.x, last.y - other.y);
        const after = Math.hypot(sx - other.x, sy - other.y);
        if (before > 0) camera.current = zoomAt(camera.current, after / before, (sx + other.x) / 2, (sy + other.y) / 2);
      }
    } else if (drag.current) {
      const [x, y] = toScene(camera.current, sx, sy);
      drag.current = { ...drag.current, x: x - drag.current.offsetX, y: y - drag.current.offsetY };
    } else {
      camera.current = panBy(camera.current, sx - last.x, sy - last.y);
    }
    pointers.current.set(event.pointerId, { x: sx, y: sy });
    draw();
  };

  const up = (event: PointerEvent<HTMLCanvasElement>): void => {
    pointers.current.delete(event.pointerId);
    const held = drag.current;
    drag.current = null;
    if (held) {
      const [x, y] = snap(held.x, held.y, viewRef.current.grid_size);
      if (x !== held.token.x || y !== held.token.y) onMove(held.token, x, y);
    }
    draw();
  };

  return (
    <div ref={box} className='bg-muted relative h-[60svh] min-h-64 w-full overflow-hidden rounded-md'>
      <canvas
        ref={canvas}
        role='img'
        aria-label={`Map of ${view.name ?? 'the scene'}`}
        className='h-full w-full touch-none'
        onPointerDown={down}
        onPointerMove={moveTo}
        onPointerUp={up}
        onPointerCancel={up}
      />
    </div>
  );
}
