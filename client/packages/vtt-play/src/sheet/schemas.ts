// SPDX-License-Identifier: AGPL-3.0-or-later
/** The sheet route's answer (server/extensions/rpg_dice: SheetOut), parsed at the boundary. */
import { z } from 'zod';

const entry = z.object({
  trait_id: z.string(),
  slug: z.string().nullish(),
  name: z.string(),
  kind: z.string().nullish(),
  value: z.number().nullish(),
  rank: z.number().nullish(),
  specialisation: z.string().nullish(),
});

export const sheetSchema = z.object({
  sheet: z.object({
    person_id: z.string(),
    name: z.string().nullish(),
    system: z.string().nullish(),
    has_sheet: z.boolean(),
    characteristics: z.array(entry),
    skills: z.array(entry),
    resources: z.array(entry),
    origins: z.array(entry),
    abilities: z.array(entry),
    gear: z.array(
      z.object({ id: z.string(), item_id: z.string().nullish(), name: z.string().nullish(), quantity: z.number() }),
    ),
  }),
});
export type Sheet = z.infer<typeof sheetSchema>['sheet'];
export type SheetEntry = Sheet['skills'][number];
