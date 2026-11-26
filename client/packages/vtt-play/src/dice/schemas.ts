// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The dice routes' answers, as the server sends them (server/extensions/rpg_dice/BLL_RPGDice.py:
 * TestOptionsOut, TestOut, RollOut). Parsed at the boundary so the tray never trusts a shape.
 */
import { z } from 'zod';

const option = z.object({
  slug: z.string(),
  name: z.string(),
  short: z.string().nullish(),
  characteristic: z.string().nullish(),
  untrainable: z.boolean().default(false),
  specialisations: z.array(z.string()).default([]),
});

export const testOptionsSchema = z.object({
  options: z.object({
    person_id: z.string(),
    system: z.string(),
    characteristics: z.array(option),
    skills: z.array(option),
    // A d100 pack's difficulty is a modifier; a d20 pack's is a DC (modifier 0).
    difficulties: z.array(z.object({ slug: z.string(), modifier: z.number(), dc: z.number().nullish() })),
    default_difficulty: z.string(),
    has_sheet: z.boolean().default(true),
    // The pack's test: d100-under (percentile packs) or d20-over (5e).
    test_kind: z.enum(['d100-under', 'd20-over']).default('d100-under'),
  }),
});
export type TestOptions = z.infer<typeof testOptionsSchema>['options'];

const step = z.object({ step: z.string(), value: z.number() }).passthrough();

export const testResultSchema = z.object({
  test: z.object({
    person_id: z.string(),
    system: z.string(),
    name: z.string(),
    specialisation: z.string().nullish(),
    kind: z.enum(['characteristic', 'skill']),
    skill_rank: z.number().nullable(),
    trained: z.boolean(),
    target: z.number(),
    roll: z.number(),
    success: z.boolean(),
    // None for a d20 test: 5e has no degrees of success (mechanic d20).
    degrees: z.number().nullable(),
    natural: z.enum(['success', 'failure']).nullable(),
    steps: z.array(step),
    // d20-over (5e): roll + modifiers = total, against target (the DC); d100-under (percentile): roll against target.
    test_kind: z.enum(['d100-under', 'd20-over']).default('d100-under'),
    total: z.number().nullish(),
    no_sheet: z.boolean().default(false),
    // 5e: rolled with Advantage or Disadvantage; every die rolled (``roll`` is the one kept).
    advantage: z.enum(['advantage', 'disadvantage']).nullish(),
    rolls: z.array(z.number()).default([]),
    mechanic: z.enum(['d100-degrees', 'd20']).optional(),
    // A d20 test's natural 20 or 1, as the die fell.
    natural_roll: z.number().nullish(),
  }),
});
export type TestResult = z.infer<typeof testResultSchema>['test'];

const term = z.object({
  notation: z.string(),
  dice: z.array(z.object({ value: z.number(), kept: z.boolean().default(true) }).passthrough()).default([]),
  value: z.number().optional(),
});

export const rollResultSchema = z.object({
  roll: z.object({ formula: z.string(), total: z.number(), terms: z.array(term).default([]) }).passthrough(),
});
export type RollResult = z.infer<typeof rollResultSchema>['roll'];
