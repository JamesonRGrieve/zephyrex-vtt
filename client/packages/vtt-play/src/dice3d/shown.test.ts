// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import type { RollResult, TestResult } from '../dice/schemas';
import { diceFor } from './faces';
import { MAX_SHOWN, shownDice } from './shown';

const test = { roll: 73, degrees: 1 } as unknown as TestResult;

function roll(terms: { notation: string; dice: { value: number }[] }[]): RollResult {
  return { formula: 'x', total: 0, terms } as unknown as RollResult;
}

describe('the dice a result shows', () => {
  it('shows a test as its d100, tens and units', () => {
    expect(shownDice(test)).toEqual([
      { kind: 'd10-tens', label: '70' },
      { kind: 'd10', label: '3' },
    ]);
  });

  it('shows a d20 pack’s test as its d20', () => {
    const check = { roll: 17, degrees: 0, test_kind: 'd20-over' } as unknown as TestResult;
    expect(shownDice(check)).toEqual(diceFor(20, 17));
  });

  it('shows each die of a formula it has a model for, and skips the rest', () => {
    const result = roll([
      { notation: '2d6', dice: [{ value: 4 }, { value: 1 }] },
      { notation: '1d8', dice: [{ value: 5 }] },
      { notation: '1d%', dice: [{ value: 100 }] },
      { notation: '3', dice: [] },
    ]);
    expect(shownDice(result)).toEqual([
      { kind: 'd6', label: '4' },
      { kind: 'd6', label: '1' },
      { kind: 'd10-tens', label: '00' },
      { kind: 'd10', label: '0' },
    ]);
  });

  it('shows at most a tray of dice', () => {
    const many = roll([{ notation: '30d6', dice: Array.from({ length: 30 }, () => ({ value: 3 })) }]);
    expect(shownDice(many)).toHaveLength(MAX_SHOWN);
  });
});
