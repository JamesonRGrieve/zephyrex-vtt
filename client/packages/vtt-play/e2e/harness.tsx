// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * A page holding SceneCanvas alone, for the phone test (scene-mobile.spec.ts): bundled by esbuild into
 * one script and loaded into a 390 px page taller than the screen. Moves are recorded on
 * window.moves; nothing talks to a server.
 */
import { createRoot } from 'react-dom/client';
import { SceneCanvas } from '../src/scene/SceneCanvas';
import type { SceneViewData } from '../src/scene/schemas';

declare global {
  interface Window {
    moves: { id: string; x: number; y: number }[];
    doors: string[];
    chosen: string[];
  }
}

/** A plain red picture, made here, as the place's painting (the test reads the ground's colour). */
function redPicture(): string {
  const canvas = document.createElement('canvas');
  canvas.width = 8;
  canvas.height = 8;
  const context = canvas.getContext('2d')!;
  context.fillStyle = '#e00000';
  context.fillRect(0, 0, 8, 8);
  return canvas.toDataURL('image/png');
}

const withPicture = Boolean((window as unknown as { vttPicture?: boolean }).vttPicture);
// The measure tool, and the GM's view (a door to tap), for those tests.
const tool = (window as unknown as { vttTool?: 'select' | 'measure' }).vttTool ?? 'select';
const gm = Boolean((window as unknown as { vttGm?: boolean }).vttGm);

const view = {
  id: 's1',
  name: 'The Split Antler',
  width: 2000,
  height: 1500,
  grid_size: 100,
  grid_distance: 5,
  grid_units: 'ft',
  lit: true,
  tokens: [
    {
      id: 'brann',
      name: 'Brann',
      x: 1000,
      y: 700,
      width: 1,
      height: 1,
      mine: true,
      disposition: 'friendly',
      is_hidden: false,
      person_id: 'p1',
    },
    {
      id: 'keeper',
      name: 'Innkeeper',
      x: 300,
      y: 300,
      width: 1,
      height: 1,
      mine: false,
      disposition: 'neutral',
      is_hidden: false,
      person_id: 'p2',
    },
  ],
  walls: gm
    ? [
        {
          id: 'door',
          points: [
            [600, 200],
            [700, 200],
          ],
          door_type: 'door',
          door_state: 'closed',
        },
      ]
    : [],
  background_url: withPicture ? redPicture() : null,
  gm,
  // A silver key lying three squares below Brann, to pick up from the map.
  items: [{ id: 'key', item_id: 'silver-key', name: 'Silver key', quantity: 1, x: 1000, y: 1000 }],
} as unknown as SceneViewData;

window.moves = [];
window.doors = [];
window.chosen = [];
const root = document.getElementById('root');
if (root) {
  createRoot(root).render(
    <SceneCanvas
      view={view}
      tool={tool}
      onMove={(token, x, y) => window.moves.push({ id: token.id, x, y })}
      onDoor={(wall) => window.doors.push(wall.id)}
      onContextAction={(target) =>
        target.kind === 'square'
          ? []
          : [
              {
                label: target.kind === 'item' ? `Pick up ${target.name}` : `Talk to ${target.name}`,
                run: () => window.chosen.push(`${target.kind}:${target.id}:${target.distance ?? ''}`),
              },
            ]
      }
    />,
  );
}
