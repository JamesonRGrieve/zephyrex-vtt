// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * A page holding SceneCanvas alone, drawing one step of the server's map play script (the operator,
 * 2026-11-25: "Maps are still completely fucked and need a whole testing framework on the part of
 * VTT"): window.vttView is the GM's view the server sent for that step (EP_MapPlay_test, exported
 * with MAP_PLAY_OUT), bundled by esbuild for map-play.spec.ts. Nothing talks to a server.
 */
import { createRoot } from 'react-dom/client';
import { SceneCanvas } from '../src/scene/SceneCanvas';
import type { SceneViewData } from '../src/scene/schemas';

const view = (window as unknown as { vttView: SceneViewData }).vttView;
const root = document.getElementById('root');
if (root && view) {
  createRoot(root).render(<SceneCanvas view={view} tool='select' onMove={() => undefined} onDoor={() => undefined} />);
}
