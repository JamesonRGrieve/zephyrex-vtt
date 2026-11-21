// SPDX-License-Identifier: AGPL-3.0-or-later
/** Which dice a server result shows: a test's d100, or each die of a formula's terms. */
import type { RollResult, TestResult } from '../dice/schemas';
import { diceFor, type ShownDie } from './faces';

/** A tray shows at most this many dice tumbling; the card always has the full result. */
export const MAX_SHOWN = 10;

interface Term {
  notation?: string;
  dice?: { value: number }[];
}

function sidesOf(notation: string | undefined): number | null {
  const match = /d(%|\d+)/i.exec(notation ?? '');
  if (!match) return null;
  return match[1] === '%' ? 100 : Number(match[1]);
}

export function shownDice(result: TestResult | RollResult): ShownDie[] {
  // A roll result passes extra keys through, so `in` can't tell them apart: a test has numeric degrees.
  const test = result as Partial<TestResult>;
  if (typeof test.degrees === 'number' && typeof test.roll === 'number') return diceFor(100, test.roll);
  const shown: ShownDie[] = [];
  for (const term of ((result as { terms?: Term[] }).terms ?? []) as Term[]) {
    const sides = sidesOf(term.notation);
    if (sides === null || ![6, 10, 20, 100].includes(sides)) continue;
    for (const die of term.dice ?? []) shown.push(...diceFor(sides, die.value));
  }
  return shown.slice(0, MAX_SHOWN);
}
