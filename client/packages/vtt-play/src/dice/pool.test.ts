// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { add, canEdge, EMPTY, formulaOf, isEmpty, MAX_DICE, poolOf, remove, type Pool } from './pool';

describe('the dice rack’s pool', () => {
  it('writes the dice largest first, then the modifier', () => {
    let pool: Pool = add(add(add(EMPTY, 6), 8), 6);
    expect(formulaOf(pool)).toBe('1d8+2d6');
    pool = { ...pool, modifier: 3 };
    expect(formulaOf(pool)).toBe('1d8+2d6+3');
    expect(formulaOf({ ...pool, modifier: -1 })).toBe('1d8+2d6-1');
  });

  it('rolls a lone d20 with Advantage or Disadvantage as two, keeping one', () => {
    const d20 = add(EMPTY, 20);
    expect(canEdge(d20)).toBe(true);
    expect(formulaOf({ ...d20, edge: 'advantage', modifier: 5 })).toBe('2d20kh1+5');
    expect(formulaOf({ ...d20, edge: 'disadvantage' })).toBe('2d20kl1');
    const two = add(d20, 20);
    expect(canEdge(two)).toBe(false);
    expect(formulaOf({ ...two, edge: 'advantage' })).toBe('2d20');
  });

  it('drops the edge when the lone d20 goes, and empties', () => {
    const edged: Pool = { ...add(EMPTY, 20), edge: 'advantage' };
    const gone = remove(edged, 20);
    expect(isEmpty(gone) && gone.edge === 'none').toBe(true);
    expect(gone.counts).toEqual({});
  });

  it('holds at most a rack of one die', () => {
    let pool = EMPTY;
    for (let index = 0; index < MAX_DICE + 5; index += 1) pool = add(pool, 4);
    expect(formulaOf(pool)).toBe(`${MAX_DICE}d4`);
  });

  it('starts from a plain formula, or empty', () => {
    expect(formulaOf(poolOf('1d100'))).toBe('1d100');
    expect(formulaOf(poolOf('1d20'))).toBe('1d20');
    expect(isEmpty(poolOf('4d6kh3'))).toBe(true);
  });
});
