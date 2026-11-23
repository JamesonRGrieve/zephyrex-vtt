// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The dice rack's pool: how many of each die, a flat modifier, and Advantage or Disadvantage on a
 * lone d20, written as the formula the server rolls (rpg_dice's notation: 2d6+1d8+3, 2d20kh1).
 * Pure, so the rack and its tests share it.
 */

export const SIDES = [4, 6, 8, 10, 12, 20, 100] as const;
export type Sides = (typeof SIDES)[number];
export type Edge = 'none' | 'advantage' | 'disadvantage';

export interface Pool {
  counts: Partial<Record<Sides, number>>;
  modifier: number;
  edge: Edge;
}

/** The most of one die a rack holds: past that, type the formula. */
export const MAX_DICE = 20;

export const EMPTY: Pool = { counts: {}, modifier: 0, edge: 'none' };

export function count(pool: Pool, sides: Sides): number {
  return pool.counts[sides] ?? 0;
}

export function add(pool: Pool, sides: Sides): Pool {
  return { ...pool, counts: { ...pool.counts, [sides]: Math.min(MAX_DICE, count(pool, sides) + 1) } };
}

export function remove(pool: Pool, sides: Sides): Pool {
  const left = Math.max(0, count(pool, sides) - 1);
  const counts = { ...pool.counts, [sides]: left };
  if (left === 0) delete counts[sides];
  return { ...pool, counts, edge: sides === 20 && left !== 1 ? 'none' : pool.edge };
}

/** Advantage and Disadvantage apply to a single d20 (5e: roll two, keep the higher or the lower). */
export function canEdge(pool: Pool): boolean {
  return count(pool, 20) === 1;
}

export function isEmpty(pool: Pool): boolean {
  return SIDES.every((sides) => count(pool, sides) === 0);
}

/** The formula the server rolls: the dice largest first, then the modifier. */
export function formulaOf(pool: Pool): string {
  const parts: string[] = [];
  for (const sides of [...SIDES].reverse()) {
    const many = count(pool, sides);
    if (many === 0) continue;
    if (sides === 20 && many === 1 && pool.edge !== 'none') parts.push(pool.edge === 'advantage' ? '2d20kh1' : '2d20kl1');
    else parts.push(`${many}d${sides}`);
  }
  let formula = parts.join('+');
  if (pool.modifier > 0) formula += `+${pool.modifier}`;
  if (pool.modifier < 0) formula += `${pool.modifier}`;
  return formula;
}

/** A starting pool from a plain formula (1d20, 1d100); anything else starts empty. */
export function poolOf(formula: string): Pool {
  const match = /^(\d+)d(\d+)$/.exec(formula.trim());
  const sides = match ? (Number(match[2]) as Sides) : null;
  if (!match || sides === null || !SIDES.includes(sides)) return EMPTY;
  return { ...EMPTY, counts: { [sides]: Number(match[1]) } };
}
