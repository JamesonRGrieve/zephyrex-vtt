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
  }
}

const view = {
  id: 's1',
  name: 'The Split Antler',
  width: 2000,
  height: 1500,
  grid_size: 100,
  gm: false,
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
  walls: [],
} as unknown as SceneViewData;

window.moves = [];
const root = document.getElementById('root');
if (root) {
  createRoot(root).render(<SceneCanvas view={view} onMove={(token, x, y) => window.moves.push({ id: token.id, x, y })} />);
}
