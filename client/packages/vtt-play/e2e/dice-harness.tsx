// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * A page holding DiceStage alone, for the phone test (dice-mobile.spec.ts): bundled by esbuild into
 * one script. window.diceMode picks the case: "open" (the stage on the page), "drawer" (inside a
 * drawer that opens after the dice are thrown, as a phone's sheet does) or "no-webgl" (a browser
 * that names WebGL but gives no context). Nothing talks to a server.
 */
import { useEffect, useState, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import type { RollResult } from '../src/dice/schemas';
import DiceStage from '../src/dice3d/DiceStage';

const mode = (window as unknown as { diceMode?: string }).diceMode ?? 'open';

if (mode === 'no-webgl') {
  const plain = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, kind: string, ...rest: unknown[]) {
    return /webgl/i.test(kind) ? null : (plain as (...args: unknown[]) => unknown).call(this, kind, ...rest);
  } as typeof plain;
}

// A 5e damage-and-attack roll: a d8 and a d20 (dice the stage once had no model for).
const result = {
  formula: '1d8+1d20',
  total: 22,
  terms: [
    { notation: '1d8', dice: [{ value: 5 }] },
    { notation: '1d20', dice: [{ value: 17 }] },
  ],
} as unknown as RollResult;

function Page(): ReactNode {
  const [open, setOpen] = useState(mode !== 'drawer');
  useEffect(() => {
    if (mode !== 'drawer') return undefined;
    const timer = window.setTimeout(() => setOpen(true), 600);
    return () => window.clearTimeout(timer);
  }, []);
  return (
    <section>
      <p id='result'>Total 22</p>
      <div id='drawer' style={{ display: open ? 'block' : 'none' }}>
        <DiceStage result={result} seed={7} animate={false} />
      </div>
    </section>
  );
}

createRoot(document.getElementById('root')!).render(<Page />);
