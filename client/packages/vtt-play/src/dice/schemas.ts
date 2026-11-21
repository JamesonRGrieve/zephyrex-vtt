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
    difficulties: z.array(z.object({ slug: z.string(), modifier: z.number() })),
    default_difficulty: z.string(),
    has_sheet: z.boolean().default(true),
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
    degrees: z.number(),
    natural: z.enum(['success', 'failure']).nullable(),
    steps: z.array(step),
  }),
});
export type TestResult = z.infer<typeof testResultSchema>['test'];

export const rollResultSchema = z.object({
  roll: z.object({ formula: z.string(), total: z.number() }).passthrough(),
});
export type RollResult = z.infer<typeof rollResultSchema>['roll'];
