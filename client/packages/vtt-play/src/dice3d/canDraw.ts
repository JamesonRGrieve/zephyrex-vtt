// SPDX-License-Identifier: AGPL-3.0-or-later
/** Whether this browser can draw the 3D dice (WebGL2). Its own module, so asking costs no three.js. */
export function canDrawDice(): boolean {
  return typeof window !== 'undefined' && typeof window.WebGL2RenderingContext !== 'undefined';
}
