// @vitest-environment node
// SPDX-License-Identifier: AGPL-3.0-or-later
/** roll.ts against contract/roll-cases.json, the cases server/extensions/rpg_dice/Dice.py answers too. */
import { describe, expect, it } from 'vitest';
import contract from '../../../../contract/roll-cases.json';
import { cryptoDraw, DiceError, drawingFrom, MAX_DICE_PER_TERM, roll } from './roll';

interface RollCase {
  name: string;
  formula: string;
  stats?: Record<string, number>;
  draws: number[];
  expect?: unknown;
  error?: string;
}

const CASES = (contract as { cases: RollCase[] }).cases;

describe('contract/roll-cases.json against the lite twin', () => {
  it.each(CASES.map((one) => [one.name, one] as const))('%s', (_, testCase) => {
    const run = (): ReturnType<typeof roll> => roll(testCase.formula, drawingFrom(testCase.draws), testCase.stats);
    if (testCase.error !== undefined) {
      expect(run).toThrow(DiceError);
      expect(run).toThrow(expect.objectContaining({ code: testCase.error }));
      return;
    }
    const { total, terms, stats } = run();
    expect({ total, terms, stats }).toEqual(testCase.expect);
  });

  it('uses exactly the draws each case lists', () => {
    for (const testCase of CASES.filter((one) => one.error === undefined)) {
      const remaining = [...testCase.draws];
      roll(testCase.formula, () => remaining.shift() ?? 0, testCase.stats);
      expect(remaining, testCase.name).toEqual([]);
    }
  });
});

describe('cryptoDraw', () => {
  it('stays on the die, for a pool at the cap', () => {
    for (let i = 0; i < 50; i += 1) {
      const result = roll(`${MAX_DICE_PER_TERM}d6`, cryptoDraw);
      expect(result.terms[0].dice.every((die) => die.value >= 1 && die.value <= 6)).toBe(true);
    }
  });
});
