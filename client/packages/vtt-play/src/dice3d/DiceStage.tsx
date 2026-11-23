// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * The dice tumbling for a server result. The result is already on the card (and announced) before
 * any die moves: this is decoration. A worker throws the dice headless, the faces are relabelled so
 * each die rests on the server's value, and the stage replays the throw once. With reduced motion
 * the dice appear at rest, already showing it. Loaded only when a tray shows a result
 * (DiceTray lazy-loads it), so three.js and cannon-es cost a page nothing until then.
 */
import { useEffect, useMemo, useRef, type ReactNode } from 'react';
import type { RollResult, TestResult } from '../dice/schemas';
import { facesOf, relabel, upFace, type DieKind } from './faces';
import { simulateThrow, type Throw } from './simulate';
import { createStage, type Stage } from './stage';
import { shownDice } from './shown';

export interface DiceStageProps {
  result: TestResult | RollResult;
  /** The throw's seed: the same seed is the same tumble on every seat. */
  seed: number;
  /** False skips the tumble (reduced motion, or the device's own setting). */
  animate: boolean;
}

export { canDrawDice } from './canDraw';

function thrownOffThread(kinds: DieKind[], seed: number): Promise<Throw> {
  if (typeof Worker === 'undefined') return Promise.resolve(simulateThrow(kinds, seed));
  return new Promise((resolve) => {
    let worker: Worker;
    try {
      worker = new Worker(new URL('./throw.worker.ts', import.meta.url), { type: 'module' });
    } catch {
      resolve(simulateThrow(kinds, seed));
      return;
    }
    worker.onmessage = (event: MessageEvent<Throw>) => {
      resolve(event.data);
      worker.terminate();
    };
    worker.onerror = () => {
      worker.terminate();
      resolve(simulateThrow(kinds, seed));
    };
    worker.postMessage({ kinds, seed });
  });
}

export default function DiceStage({ result, seed, animate }: DiceStageProps): ReactNode {
  const canvas = useRef<HTMLCanvasElement>(null);
  const stage = useRef<Stage | null>(null);
  const dice = useMemo(() => shownDice(result), [result]);

  useEffect(() => {
    const element = canvas.current;
    if (!element) return undefined;
    try {
      stage.current = createStage(element);
    } catch {
      // A browser that names WebGL2 but won't give a context (a phone's GPU blocklist, a lost
      // context): the stage hides and the result card above it is what shows.
      element.style.display = 'none';
      return undefined;
    }
    // The canvas can be laid out after the first throw (a drawer still opening on a phone) or change
    // size later: refit and draw again whenever it does.
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => stage.current?.resize());
    observer?.observe(element);
    return () => {
      observer?.disconnect();
      stage.current?.dispose();
      stage.current = null;
    };
  }, []);

  useEffect(() => {
    if (dice.length === 0) return;
    let current = true;
    const kinds = dice.map((die) => die.kind);
    void thrownOffThread(kinds, seed).then((thrown) => {
      if (!current || !stage.current) return;
      const faces = dice.map((die, index) => {
        const plain = facesOf(die.kind);
        return relabel(plain, upFace(plain, thrown.rests[index]!), die.label);
      });
      void stage.current.play(thrown, faces, animate);
    });
    return () => {
      current = false;
    };
  }, [dice, seed, animate]);

  // The canvas stays mounted while there's nothing to show, so a result with no dice to draw (a d3)
  // doesn't leave every later roll without a stage.
  return (
    <canvas
      ref={canvas}
      aria-hidden='true'
      data-dice-stage=''
      className={dice.length === 0 ? 'hidden' : 'h-40 w-full rounded-md sm:h-48'}
    />
  );
}
