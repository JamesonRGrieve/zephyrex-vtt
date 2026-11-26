// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * The scene's canvas, the whole of the map in play: drawn on a 2D canvas only when something changes.
 *
 * - Tap a token you may move (the GM any, a player their own) to select it: a ring and its name. Tap
 *   a cell to move it there (snapped to the grid; the server refuses a move through a wall); tap the
 *   selected token again, or press Escape, to let it go. Dragging a token moves it too.
 * - One finger on the ground pans, two pinch, a wheel zooms (the page doesn't scroll under it).
 * - Right-click, long-press, or Shift+F10 / the menu key on the focused map, opens a menu of what can
 *   be done with what's there (the operator, 2026-11-26: "Right click interact in the vtt should
 *   trigger action lines in the chat as if typed"): a token, a lying item, a door or a square. The
 *   host fills it (onContextAction); the canvas adds "Move here" for your token (through onMove,
 *   so the server's wall check stands) and "Details" (onTokenDetails). Arrow keys move through it,
 *   Enter chooses, Escape closes.
 * - Keyboard: the canvas takes focus; Enter or Space selects the next token you may move, the arrow
 *   keys move the selected one a cell, Escape lets go. A polite live region says what happened.
 * - It opens on the whole map, fitted to the width of a box shaped like it, and follows its box's size until
 *   the player pans or zooms (a panel that opens later measures 0 at first).
 * - The measure tool (tool 'measure'): drag from one point to another for the distance in the
 *   scene's units, whole cells; the line stays until the next measure.
 * - The GM taps a door to open or close it (onDoor).
 */
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type MouseEvent,
  type PointerEvent,
  type ReactNode,
} from 'react';
import {
  discAt,
  doorAt,
  fitCover,
  fitWidth,
  measure,
  MIN_TARGET,
  panBy,
  snap,
  toScene,
  tokenAt,
  zoomAt,
  type Camera,
  type Disc,
} from './geometry';
import { drawScene, paletteOf, type Drag, type Ruler } from './render';
import type { SceneViewData, ViewItem, ViewToken, ViewWall } from './schemas';

/** What a context menu was opened on: a token, a lying item, a map feature (a door) or a square. */
export interface SceneTarget {
  kind: 'token' | 'item' | 'feature' | 'square';
  id?: string;
  name?: string;
  personId?: string;
  /** The square's top-left, in scene pixels. */
  x: number;
  y: number;
  /** From your token, in the scene's units (whole squares × its grid distance); none without one. */
  distance?: number;
}

/** One choice in the menu: the host's (Talk to, Pick up, Attack…) or the canvas's own. */
export interface ContextAction {
  label: string;
  icon?: ReactNode;
  run: () => void;
}

/** A lying item under a scene point, with a reach of at least ``minSize`` scene units. */
function itemAt(items: readonly ViewItem[], x: number, y: number, grid: number, minSize = 0): ViewItem | null {
  for (let index = items.length - 1; index >= 0; index -= 1) {
    const item = items[index]!;
    const size = Math.max(grid, minSize);
    const left = item.x + (grid - size) / 2;
    const top = item.y + (grid - size) / 2;
    if (x >= left && x < left + size && y >= top && y < top + size) return item;
  }
  return null;
}

export function movable(view: SceneViewData, one: ViewToken): boolean {
  return view.gm || one.mine;
}

/** How far (screen px) a press may wander and still be a tap; how long a press is a long-press. */
const TAP_SLOP = 8;
const LONG_PRESS_MS = 550;

export interface SceneCanvasProps {
  view: SceneViewData;
  onMove: (token: ViewToken, x: number, y: number) => void;
  /** "Details" in a token's menu (right-click or long-press): show its details. */
  onTokenDetails?: (token: ViewToken) => void;
  /** The host's choices for what a menu was opened on (Talk to, Examine, Pick up, Attack…); each
   * one's run becomes, in rpg-ai, an action line in the chat as if typed. */
  onContextAction?: (target: SceneTarget) => ContextAction[] | Promise<ContextAction[]>;
  /** What a drag does: select and move tokens (the default), or measure. */
  tool?: 'select' | 'measure';
  /** The GM tapped a door: open or close it. */
  onDoor?: (wall: ViewWall) => void;
  /** Fill the container's height (a host that gives the map the screen, e.g. rpg-ai's MapView),
   * opening filled by the map's width or height, whichever fills more; else a box shaped like the
   * map, opening on its whole width. */
  fill?: boolean;
}

interface Press {
  sx: number;
  sy: number;
  hit: ViewToken | null;
  moved: boolean;
  long: boolean;
}

export function SceneCanvas({
  view,
  onMove,
  onTokenDetails,
  onContextAction,
  tool = 'select',
  onDoor,
  fill = false,
}: SceneCanvasProps): ReactNode {
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
  const ruler = useRef<Ruler | null>(null);
  // The discs as last drawn (spread apart where they'd overlap): a tap finds the one it lands on.
  const drawn = useRef<Disc[]>([]);
  const measuring = useRef(false);
  const toolRef = useRef(tool);
  const fillRef = useRef(fill);
  const [menu, setMenu] = useState<{ left: number; top: number; title: string; actions: ContextAction[] } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  // A long-press opened the menu: the finger's lifting must not hand focus back to the map.
  const longOpened = useRef(false);
  const hasMenu = Boolean(onContextAction || onTokenDetails);

  const refit = useCallback(() => {
    const element = canvas.current;
    if (!element || touched.current) return;
    const width = element.clientWidth;
    const height = element.clientHeight;
    if (width < 2 || height < 2) return;
    const current = viewRef.current;
    const grid = current.grid_size;
    // The whole map, fitted to the width of a box shaped like it (the operator, 2026-11-24: a town
    // opened on a few houses around one token).
    const fitted = fillRef.current ? fitCover : fitWidth;
    camera.current = fitted(current.width ?? 40 * grid, current.height ?? 30 * grid, [width, height]);
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
    drawn.current = drawScene(
      context,
      viewRef.current,
      camera.current,
      [width, height],
      paletteOf(element),
      drag.current,
      selectedRef.current,
      () => window.requestAnimationFrame(() => drawRef.current()),
      ruler.current,
    );
    element.dataset.measure = ruler.current?.label ?? '';
    // The camera and selection, for tests and tools.
    element.dataset.camera = `${camera.current.zoom.toFixed(4)},${camera.current.x.toFixed(1)},${camera.current.y.toFixed(1)}`;
    element.dataset.selected = selectedRef.current ?? '';
    element.dataset.discs = drawn.current
      .map((one) => `${one.id}:${one.cx.toFixed(1)},${one.cy.toFixed(1)},${one.r.toFixed(1)}`)
      .join(' ');
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
    fillRef.current = fill;
  }, [fill]);

  useEffect(() => {
    toolRef.current = tool;
    if (tool !== 'measure') ruler.current = null;
    draw();
  }, [tool, draw]);

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

  /** Your token: the selected one if it's yours, else your first (for "Move here" and distances). */
  const yours = (): ViewToken | null => {
    const current = viewRef.current;
    const chosen = current.tokens.find((one) => one.id === selectedRef.current && movable(current, one));
    return chosen ?? current.tokens.find((one) => one.mine) ?? null;
  };

  /** What lies under a screen point: a token's drawn disc, a lying item, a door, else the square. */
  const targetAt = (sx: number, sy: number): { target: SceneTarget; token: ViewToken | null } | null => {
    if (!camera.current) return null;
    const current = viewRef.current;
    const grid = current.grid_size;
    const [x, y] = toScene(camera.current, sx, sy);
    const reach = MIN_TARGET / camera.current.zoom;
    const onDisc = discAt(drawn.current, sx, sy);
    const token =
      (onDisc && current.tokens.find((one) => one.id === onDisc.id)) || tokenAt(current.tokens, x, y, grid, reach);
    const mine = yours();
    const away = (tx: number, ty: number): number | undefined =>
      mine
        ? Math.max(
            Math.abs(Math.floor(tx / grid) - Math.floor(mine.x / grid)),
            Math.abs(Math.floor(ty / grid) - Math.floor(mine.y / grid)),
          ) * current.grid_distance
        : undefined;
    if (token) {
      return {
        token,
        target: {
          kind: 'token',
          id: token.id,
          name: token.name ?? undefined,
          personId: token.person_id ?? undefined,
          x: token.x,
          y: token.y,
          distance: away(token.x, token.y),
        },
      };
    }
    const item = itemAt(current.items ?? [], x, y, grid, reach);
    if (item) {
      return {
        token: null,
        target: { kind: 'item', id: item.id, name: item.name, x: item.x, y: item.y, distance: away(item.x, item.y) },
      };
    }
    const door = doorAt(current.walls, x, y, reach);
    if (door) return { token: null, target: { kind: 'feature', id: door.id, name: 'Door', x, y, distance: away(x, y) } };
    const cellX = Math.floor(x / grid) * grid;
    const cellY = Math.floor(y / grid) * grid;
    return { token: null, target: { kind: 'square', x: cellX, y: cellY, distance: away(cellX, cellY) } };
  };

  const openMenu = async (sx: number, sy: number, at?: { left: number; top: number }): Promise<void> => {
    const found = targetAt(sx, sy);
    if (!found) return;
    const { target, token } = found;
    const own: ContextAction[] = [];
    const mine = yours();
    if (target.kind === 'square' && mine) {
      own.push({
        label: 'Move here',
        run: () => {
          onMove(mine, target.x, target.y);
          setSaid(`${mine.name ?? 'Token'} moved`);
        },
      });
    }
    if (token && onTokenDetails) own.push({ label: 'Details', run: () => onTokenDetails(token) });
    let theirs: ContextAction[] = [];
    try {
      theirs = onContextAction ? await onContextAction(target) : [];
    } catch {
      theirs = [];
    }
    const actions = [...theirs, ...own];
    if (actions.length === 0) return;
    const element = canvas.current;
    const width = element?.clientWidth ?? 0;
    const height = element?.clientHeight ?? 0;
    const title = target.name ?? (target.kind === 'square' ? 'This square' : 'Here');
    // Kept inside the map: a menu at the right or bottom edge opens back toward the middle.
    setMenu({
      left: Math.max(4, Math.min(at?.left ?? sx, width - 200)),
      top: Math.max(4, Math.min(at?.top ?? sy, height - 48 * (actions.length + 1))),
      title,
      actions,
    });
  };

  const closeMenu = (): void => {
    setMenu(null);
    canvas.current?.focus();
  };

  const contextMenu = (event: MouseEvent<HTMLCanvasElement>): void => {
    if (!hasMenu) return;
    event.preventDefault();
    const rect = event.currentTarget.getBoundingClientRect();
    void openMenu(event.clientX - rect.left, event.clientY - rect.top);
  };

  useEffect(() => {
    if (menu) menuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
  }, [menu]);

  const menuKey = (event: KeyboardEvent<HTMLDivElement>): void => {
    const items = [...(menuRef.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]') ?? [])];
    const at = items.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === 'Escape') {
      event.preventDefault();
      closeMenu();
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const next = (at + (event.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length;
      items[next]?.focus();
    } else if (event.key === 'Tab') {
      closeMenu();
    }
  };

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
    if (toolRef.current === 'measure') {
      measuring.current = true;
      ruler.current = { from: [x, y], to: [x, y], label: '' };
      press.current = null;
      draw();
      return;
    }
    // The disc drawn under the finger first (spread from its square at a far-out zoom), else the
    // token whose square it is.
    const onDisc = discAt(drawn.current, sx, sy);
    const hit =
      (onDisc && viewRef.current.tokens.find((one) => one.id === onDisc.id)) ||
      tokenAt(viewRef.current.tokens, x, y, viewRef.current.grid_size, MIN_TARGET / camera.current.zoom);
    press.current = { sx, sy, hit, moved: false, long: false };
    if (menu) setMenu(null);
    if (event.button === 2) {
      // A right-click: the menu (onContextMenu) handles it, never a tap or drag.
      press.current = null;
      return;
    }
    if (hasMenu) {
      // A long-press opens the same menu a right-click does (details are in it).
      longTimer.current = setTimeout(() => {
        if (press.current && !press.current.moved) {
          press.current.long = true;
          drag.current = null;
          longOpened.current = true;
          void openMenu(sx, sy);
        }
      }, LONG_PRESS_MS);
    }
  };

  const moveTo = (event: PointerEvent<HTMLCanvasElement>): void => {
    const last = pointers.current.get(event.pointerId);
    if (!last || !camera.current) return;
    const [sx, sy] = local(event);
    if (measuring.current && ruler.current && pointers.current.size === 1) {
      const current = viewRef.current;
      const to = toScene(camera.current, sx, sy);
      const measured = measure(ruler.current.from, to, current.grid_size, current.grid_distance, current.grid_units);
      ruler.current = { from: ruler.current.from, to, label: measured.label };
      pointers.current.set(event.pointerId, { x: sx, y: sy });
      draw();
      return;
    }
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
    if (longOpened.current) {
      // The menu a long-press opened keeps the focus once the finger lifts.
      window.setTimeout(() => menuRef.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus(), 0);
    }
    if (measuring.current) {
      measuring.current = false;
      if (ruler.current?.label) setSaid(`Measured ${ruler.current.label}`);
      draw();
      return;
    }
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
      if (!tap.hit && !chosen && current.gm && onDoor) {
        const [x, y] = toScene(camera.current, tap.sx, tap.sy);
        const door = doorAt(current.walls, x, y, MIN_TARGET / camera.current.zoom);
        if (door) {
          onDoor(door);
          setSaid(`Door ${door.door_state === 'open' ? 'closed' : 'opened'}`);
          return;
        }
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
    if (hasMenu && (event.key === 'ContextMenu' || (event.key === 'F10' && event.shiftKey))) {
      event.preventDefault();
      // At the selected token, else your own, else the middle of the view.
      const at = chosen ?? current.tokens.find((one) => one.mine) ?? null;
      const element = canvas.current;
      if (at && camera.current) {
        // Beside the token's square, not over it, so you still see whose menu it is.
        const cell = current.grid_size * camera.current.zoom;
        const sx = (at.x - camera.current.x) * camera.current.zoom;
        const sy = (at.y - camera.current.y) * camera.current.zoom;
        void openMenu(sx + cell / 2, sy + cell / 2, { left: sx + cell + 4, top: sy });
      } else if (element) {
        void openMenu(element.clientWidth / 2, element.clientHeight / 2);
      }
      return;
    }
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
    <div
      ref={box}
      className={`bg-muted relative min-h-64 w-full overflow-hidden rounded-md ${fill ? 'h-full' : 'max-h-[70svh]'}`}
      // Shaped like the map, so its width shows it whole with no empty band; or the host's height.
      style={
        fill ? undefined : { aspectRatio: `${view.width ?? 40 * view.grid_size} / ${view.height ?? 30 * view.grid_size}` }
      }
    >
      <canvas
        ref={canvas}
        tabIndex={0}
        role='application'
        aria-roledescription='map'
        aria-label={`Map of ${view.name ?? 'the scene'}. Enter selects your token, arrow keys move it, Escape lets go.${hasMenu ? ' Shift+F10 opens actions.' : ''}`}
        className='focus-visible:ring-ring h-full w-full touch-none outline-none focus-visible:ring-2'
        onPointerDown={down}
        onPointerMove={moveTo}
        onPointerUp={up}
        onPointerCancel={up}
        onKeyDown={key}
        onContextMenu={contextMenu}
        onTouchEnd={(event) => {
          // No mouse events emulated from a long-press's lifting: they would focus the map over the menu.
          if (longOpened.current) {
            event.preventDefault();
            longOpened.current = false;
          }
        }}
      />
      {menu && (
        <div
          ref={menuRef}
          role='menu'
          aria-label={`Actions: ${menu.title}`}
          className='bg-popover text-popover-foreground absolute z-10 min-w-44 rounded-md border p-1 shadow-md'
          style={{ left: menu.left, top: menu.top }}
          onKeyDown={menuKey}
        >
          <p className='text-muted-foreground px-2 py-1 text-xs font-medium'>{menu.title}</p>
          {menu.actions.map((action, index) => (
            <button
              key={`${action.label}-${index}`}
              type='button'
              role='menuitem'
              className='hover:bg-accent focus-visible:bg-accent flex min-h-11 w-full items-center gap-2 rounded-sm px-2 text-left text-sm outline-none'
              onClick={() => {
                setMenu(null);
                action.run();
                canvas.current?.focus();
              }}
            >
              {action.icon}
              {action.label}
            </button>
          ))}
        </div>
      )}
      <p aria-live='polite' className='sr-only'>
        {said}
      </p>
    </div>
  );
}
