// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * A scene to play on: the map the server lets this person see (the GM's whole scene; a player's
 * token's sight), with pan (drag the ground), zoom (wheel or pinch) and moving tokens (drag one you
 * may move: the GM any, a player their own; it snaps to the grid, and the server refuses a move
 * through a wall). Drawn on a 2D canvas only when something changes. Under it, the tokens as a
 * list with step buttons, for keyboards, screen readers and small screens.
 */
import { useCallback, useEffect, useRef, useState, type PointerEvent, type ReactNode } from 'react';
import { Button } from 'zephyrex/ui/button';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import { fit, panBy, snap, toScene, tokenAt, zoomAt, type Camera } from './geometry';
import { drawScene, paletteOf, type Drag } from './render';
import type { SceneViewData, ViewToken } from './schemas';
import { useSceneView } from './useSceneView';

export interface SceneViewProps {
  sceneId: string;
  /** The token a player sees from; by default the GM's whole view or the player's first token. */
  tokenId?: string;
  /** A character's wiki page, for the token list's names. */
  personHref?: (personId: string) => string | null;
}

const STEPS = [
  { label: 'north', dx: 0, dy: -1, glyph: '↑' },
  { label: 'west', dx: -1, dy: 0, glyph: '←' },
  { label: 'east', dx: 1, dy: 0, glyph: '→' },
  { label: 'south', dx: 0, dy: 1, glyph: '↓' },
] as const;

function movable(view: SceneViewData, one: ViewToken): boolean {
  return view.gm || one.mine;
}

function Canvas({
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
  }, []);

  useEffect(() => {
    viewRef.current = view;
    const element = canvas.current;
    if (element && !camera.current) {
      const grid = view.grid_size;
      camera.current = fit(view.width ?? 40 * grid, view.height ?? 30 * grid, [
        element.clientWidth || 1,
        element.clientHeight || 1,
      ]);
    }
    draw();
  }, [view, draw]);

  useEffect(() => {
    const element = box.current;
    if (!element || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(() => draw());
    observer.observe(element);
    return () => observer.disconnect();
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
    const hit = tokenAt(viewRef.current.tokens, x, y, viewRef.current.grid_size);
    if (hit && movable(viewRef.current, hit)) {
      drag.current = { id: hit.id, x: hit.x, y: hit.y, offsetX: x - hit.x, offsetY: y - hit.y, token: hit };
    }
  };

  const moveTo = (event: PointerEvent<HTMLCanvasElement>): void => {
    const last = pointers.current.get(event.pointerId);
    if (!last || !camera.current) return;
    const [sx, sy] = local(event);
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
        onWheel={(event) => {
          if (!camera.current) return;
          const rect = event.currentTarget.getBoundingClientRect();
          camera.current = zoomAt(
            camera.current,
            event.deltaY < 0 ? 1.15 : 1 / 1.15,
            event.clientX - rect.left,
            event.clientY - rect.top,
          );
          draw();
        }}
      />
    </div>
  );
}

export function SceneView({ sceneId, tokenId, personHref }: SceneViewProps): ReactNode {
  const scene = useSceneView(sceneId, tokenId);
  const [announcement, setAnnouncement] = useState('');
  const { data } = scene;
  if (data.state === 'loading') return <SkeletonRows rows={4} label='Loading the scene' />;
  if (data.state === 'failed') return <LoadProblem what='the scene' error={data.error} onRetry={scene.retry} />;
  const { view } = data;
  const move = (one: ViewToken, x: number, y: number): void => {
    void scene.move(one, x, y);
    setAnnouncement(`${one.name ?? 'Token'} moved`);
  };

  return (
    <section aria-label={view.name ?? 'Scene'} className='space-y-3'>
      <Canvas view={view} onMove={move} />
      {!view.lit && <p className='text-muted-foreground text-sm'>It’s dark here: you see only what’s lit or close.</p>}
      {scene.problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {scene.problem}
        </p>
      )}
      <p aria-live='polite' className='sr-only'>
        {announcement}
      </p>
      <ul aria-label='Tokens' className='divide-border divide-y'>
        {view.tokens.map((one) => {
          const href = one.person_id ? (personHref?.(one.person_id) ?? null) : null;
          return (
            <li key={one.id} className='flex min-h-11 flex-wrap items-center gap-2 py-1'>
              {href ? (
                <a href={href} className='font-medium underline-offset-4 hover:underline'>
                  {one.name ?? 'Token'}
                </a>
              ) : (
                <span className='font-medium'>{one.name ?? 'Token'}</span>
              )}
              <span className='text-muted-foreground text-xs'>
                {one.mine ? 'Yours' : (one.disposition ?? '')}
                {one.is_hidden ? ' · hidden' : ''}
              </span>
              {movable(view, one) && (
                <span className='ms-auto flex gap-1'>
                  {STEPS.map((step) => (
                    <Button
                      key={step.label}
                      type='button'
                      variant='outline'
                      size='sm'
                      className='min-h-11 min-w-11'
                      aria-label={`Move ${one.name ?? 'token'} ${step.label}`}
                      onClick={() => move(one, one.x + step.dx * view.grid_size, one.y + step.dy * view.grid_size)}
                    >
                      {step.glyph}
                    </Button>
                  ))}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
