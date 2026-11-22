// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * The scene's canvas, the whole of the map in play: drawn on a 2D canvas only when something changes.
 *
 * - Tap a token you may move (the GM any, a player their own) to select it: a ring and its name. Tap
 *   a cell to move it there (snapped to the grid; the server refuses a move through a wall); tap the
 *   selected token again, or press Escape, to let it go. Dragging a token moves it too.
 * - One finger on the ground pans, two pinch, a wheel zooms (the page doesn't scroll under it).
 * - Long-press a token for its details (onTokenDetails).
 * - Keyboard: the canvas takes focus; Enter or Space selects the next token you may move, the arrow
 *   keys move the selected one a cell, Escape lets go. A polite live region says what happened.
 * - It opens fitted to its tokens (else the whole scene's width), and follows its box's size until
 *   the player pans or zooms (a panel that opens later measures 0 at first).
 */
import { useCallback, useEffect, useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';
import { fitBox, fitWidth, MIN_TARGET, panBy, snap, toScene, tokenAt, tokensBox, zoomAt, type Camera } from './geometry';
import { drawScene, paletteOf, type Drag } from './render';
import type { SceneViewData, ViewToken } from './schemas';

export function movable(view: SceneViewData, one: ViewToken): boolean {
  return view.gm || one.mine;
}

/** How far (screen px) a press may wander and still be a tap; how long a press is a long-press. */
const TAP_SLOP = 8;
const LONG_PRESS_MS = 550;

export interface SceneCanvasProps {
  view: SceneViewData;
  onMove: (token: ViewToken, x: number, y: number) => void;
  /** A long-press on a token (any token this person sees): show its details. */
  onTokenDetails?: (token: ViewToken) => void;
}

interface Press {
  sx: number;
  sy: number;
  hit: ViewToken | null;
  moved: boolean;
  long: boolean;
}

export function SceneCanvas({ view, onMove, onTokenDetails }: SceneCanvasProps): ReactNode {
  const box = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const camera = useRef<Camera | null>(null);
  const drag = useRef<(Drag & { offsetX: number; offsetY: number; token: ViewToken }) | null>(null);
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const press = useRef<Press | null>(null);
  const longTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const viewRef = useRef(view);
  const selectedRef = useRef<string | null>(null);
  const [said, setSaid] = useState('');
  const touched = useRef(false);

  const refit = useCallback(() => {
    const element = canvas.current;
    if (!element || touched.current) return;
    const width = element.clientWidth;
    const height = element.clientHeight;
    if (width < 2 || height < 2) return;
    const current = viewRef.current;
    const grid = current.grid_size;
    const around = tokensBox(current.tokens, grid);
    camera.current = around
      ? fitBox(around, [width, height])
      : fitWidth(current.width ?? 40 * grid, current.height ?? 30 * grid, [width, height]);
  }, []);

  // A picture's arrival draws again through this, so the callback below needn't depend on itself.
  const drawRef = useRef<() => void>(() => undefined);
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
    drawScene(
      context,
      viewRef.current,
      camera.current,
      [width, height],
      paletteOf(element),
      drag.current,
      selectedRef.current,
      () => window.requestAnimationFrame(() => drawRef.current()),
    );
    // The camera and selection, for tests and tools.
    element.dataset.camera = `${camera.current.zoom.toFixed(4)},${camera.current.x.toFixed(1)},${camera.current.y.toFixed(1)}`;
    element.dataset.selected = selectedRef.current ?? '';
  }, []);

  useEffect(() => {
    drawRef.current = draw;
  }, [draw]);

  const select = useCallback(
    (one: ViewToken | null) => {
      selectedRef.current = one?.id ?? null;
      setSaid(one ? `${one.name ?? 'Token'} selected` : 'Nothing selected');
      draw();
    },
    [draw],
  );

  useEffect(() => {
    viewRef.current = view;
    if (selectedRef.current && !view.tokens.some((one) => one.id === selectedRef.current)) selectedRef.current = null;
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

  useEffect(
    () => () => {
      if (longTimer.current) clearTimeout(longTimer.current);
    },
    [],
  );

  const local = (event: PointerEvent<HTMLCanvasElement>): [number, number] => {
    const rect = event.currentTarget.getBoundingClientRect();
    return [event.clientX - rect.left, event.clientY - rect.top];
  };

  const cancelLong = (): void => {
    if (longTimer.current) clearTimeout(longTimer.current);
    longTimer.current = null;
  };

  const down = (event: PointerEvent<HTMLCanvasElement>): void => {
    if (!camera.current) return;
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const [sx, sy] = local(event);
    pointers.current.set(event.pointerId, { x: sx, y: sy });
    if (pointers.current.size > 1) {
      drag.current = null;
      press.current = null;
      cancelLong();
      return;
    }
    const [x, y] = toScene(camera.current, sx, sy);
    const hit = tokenAt(viewRef.current.tokens, x, y, viewRef.current.grid_size, MIN_TARGET / camera.current.zoom);
    press.current = { sx, sy, hit, moved: false, long: false };
    if (hit && onTokenDetails) {
      longTimer.current = setTimeout(() => {
        if (press.current && !press.current.moved) {
          press.current.long = true;
          drag.current = null;
          onTokenDetails(hit);
        }
      }, LONG_PRESS_MS);
    }
  };

  const moveTo = (event: PointerEvent<HTMLCanvasElement>): void => {
    const last = pointers.current.get(event.pointerId);
    if (!last || !camera.current) return;
    const [sx, sy] = local(event);
    const started = press.current;
    if (started && !started.moved && Math.hypot(sx - started.sx, sy - started.sy) > TAP_SLOP) {
      started.moved = true;
      cancelLong();
      const hit = started.hit;
      if (hit && movable(viewRef.current, hit) && !started.long) {
        const [x, y] = toScene(camera.current, started.sx, started.sy);
        drag.current = { id: hit.id, x: hit.x, y: hit.y, offsetX: x - hit.x, offsetY: y - hit.y, token: hit };
      }
    }
    if (pointers.current.size === 2) {
      touched.current = true;
      const other = [...pointers.current.entries()].find(([id]) => id !== event.pointerId)?.[1];
      if (other) {
        const before = Math.hypot(last.x - other.x, last.y - other.y);
        const after = Math.hypot(sx - other.x, sy - other.y);
        if (before > 0) camera.current = zoomAt(camera.current, after / before, (sx + other.x) / 2, (sy + other.y) / 2);
      }
    } else if (drag.current) {
      const [x, y] = toScene(camera.current, sx, sy);
      drag.current = { ...drag.current, x: x - drag.current.offsetX, y: y - drag.current.offsetY };
    } else if (started?.moved) {
      touched.current = true;
      camera.current = panBy(camera.current, sx - last.x, sy - last.y);
    }
    pointers.current.set(event.pointerId, { x: sx, y: sy });
    draw();
  };

  const up = (event: PointerEvent<HTMLCanvasElement>): void => {
    pointers.current.delete(event.pointerId);
    cancelLong();
    const held = drag.current;
    const tap = press.current;
    drag.current = null;
    press.current = null;
    if (held) {
      const [x, y] = snap(held.x, held.y, viewRef.current.grid_size);
      if (x !== held.token.x || y !== held.token.y) onMove(held.token, x, y);
      select(null);
      return;
    }
    if (tap && !tap.moved && !tap.long && camera.current) {
      const current = viewRef.current;
      const chosen = current.tokens.find((one) => one.id === selectedRef.current) ?? null;
      if (tap.hit && movable(current, tap.hit)) {
        select(tap.hit.id === chosen?.id ? null : tap.hit);
        return;
      }
      if (chosen && !tap.hit) {
        const [x, y] = toScene(camera.current, tap.sx, tap.sy);
        const grid = current.grid_size;
        const cellX = Math.floor(x / grid) * grid;
        const cellY = Math.floor(y / grid) * grid;
        if (cellX !== chosen.x || cellY !== chosen.y) {
          onMove(chosen, cellX, cellY);
          setSaid(`${chosen.name ?? 'Token'} moved`);
        }
        selectedRef.current = null;
      }
    }
    draw();
  };

  const key = (event: KeyboardEvent<HTMLCanvasElement>): void => {
    const current = viewRef.current;
    const mine = current.tokens.filter((one) => movable(current, one));
    const chosen = current.tokens.find((one) => one.id === selectedRef.current) ?? null;
    const steps: Record<string, [number, number]> = {
      ArrowUp: [0, -1],
      ArrowDown: [0, 1],
      ArrowLeft: [-1, 0],
      ArrowRight: [1, 0],
    };
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      if (mine.length === 0) return setSaid('No token here you can move');
      const at = chosen ? mine.findIndex((one) => one.id === chosen.id) : -1;
      select(mine[(at + 1) % mine.length] ?? null);
    } else if (event.key === 'Escape') {
      select(null);
    } else if (steps[event.key] && chosen) {
      event.preventDefault();
      const [dx, dy] = steps[event.key]!;
      onMove(chosen, chosen.x + dx * current.grid_size, chosen.y + dy * current.grid_size);
      setSaid(`${chosen.name ?? 'Token'} moved`);
    }
  };

  return (
    <div ref={box} className='bg-muted relative h-[60svh] min-h-64 w-full overflow-hidden rounded-md'>
      <canvas
        ref={canvas}
        tabIndex={0}
        role='application'
        aria-roledescription='map'
        aria-label={`Map of ${view.name ?? 'the scene'}. Enter selects your token, arrow keys move it, Escape lets go.`}
        className='focus-visible:ring-ring h-full w-full touch-none outline-none focus-visible:ring-2'
        onPointerDown={down}
        onPointerMove={moveTo}
        onPointerUp={up}
        onPointerCancel={up}
        onKeyDown={key}
      />
      <p aria-live='polite' className='sr-only'>
        {said}
      </p>
    </div>
  );
}
