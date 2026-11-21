// SPDX-License-Identifier: AGPL-3.0-or-later
/** Runs a headless throw off the main thread, so a tumble never costs the page a frame. */
import type { DieKind } from './faces';
import { simulateThrow } from './simulate';

// The worker's own scope (the DOM lib types `self` as a window, whose postMessage wants an origin).
const scope = self as unknown as {
  onmessage: ((event: MessageEvent<{ kinds: DieKind[]; seed: number }>) => void) | null;
  postMessage(message: unknown): void;
};

scope.onmessage = (event) => {
  scope.postMessage(simulateThrow(event.data.kinds, event.data.seed));
};
