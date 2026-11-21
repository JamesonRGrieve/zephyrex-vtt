// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * A roll that was already made, replayed: its result card and the 3D dice tumbling onto its faces,
 * with no new roll. For decided rolls the server made (POST /v1/dice/test or /roll, roll_to_table),
 * shown in a panel as they happen. Takes the result as those routes answer it ({test}, {roll}) or
 * the inner object. Reduced motion and the device's setting are honoured as in the tray; three.js
 * and cannon-es load only when a replay first shows.
 */
import { lazy, Suspense, useMemo, type ReactNode } from 'react';
import { canDrawDice } from '../dice3d/canDraw';
import { useDiceAnimation } from '../dice3d/useDiceAnimation';
import { DiceResult } from './DiceTray';
import { rollResultSchema, testResultSchema, type RollResult, type TestResult } from './schemas';

const DiceStage = lazy(() => import('../dice3d/DiceStage'));

export interface DiceReplayProps {
  /** As /v1/dice/test or /roll answer it ({test} or {roll}), or the result itself. */
  result: unknown;
  /** The tumble's seed; by default one derived from the result, so a replay looks the same each time. */
  seed?: number;
}

/** The result a route answered, or null when it isn't one. */
export function readResult(answer: unknown): TestResult | RollResult | null {
  const value = answer as { test?: unknown; roll?: unknown } | null;
  if (value && typeof value === 'object') {
    if ('test' in value) return testResultSchema.safeParse(value).data?.test ?? null;
    if ('roll' in value && typeof value.roll === 'object') return rollResultSchema.safeParse(value).data?.roll ?? null;
  }
  return (
    testResultSchema.safeParse({ test: answer }).data?.test ??
    rollResultSchema.safeParse({ roll: answer }).data?.roll ??
    null
  );
}

function seedOf(result: TestResult | RollResult): number {
  const text = JSON.stringify(result);
  let hash = 2166136261;
  for (let index = 0; index < text.length; index += 1) hash = Math.imul(hash ^ text.charCodeAt(index), 16777619);
  return hash >>> 0;
}

export function DiceReplay({ result, seed }: DiceReplayProps): ReactNode {
  const read = useMemo(() => readResult(result), [result]);
  const motion = useDiceAnimation();
  if (read === null) return <p className='text-muted-foreground text-sm'>Not a roll this tray can show.</p>;
  return (
    <section aria-label='Roll' className='space-y-3'>
      <DiceResult result={read} />
      {canDrawDice() && (
        <Suspense fallback={null}>
          <DiceStage result={read} seed={seed ?? seedOf(read)} animate={motion.animate} />
        </Suspense>
      )}
    </section>
  );
}
