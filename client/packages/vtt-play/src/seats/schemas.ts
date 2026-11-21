// SPDX-License-Identifier: AGPL-3.0-or-later
/** The table routes' rows (server/extensions/rpg_table, rpg_core's person), parsed at the boundary. */
import { z } from 'zod';

const versioned = { created_at: z.string().nullish(), updated_at: z.string().nullish() };

export const tableSchema = z
  .object({
    id: z.string(),
    conversation_id: z.string().nullish(),
    campaign_id: z.string().nullish(),
    created_by_user_id: z.string().nullish(),
    ...versioned,
  })
  .passthrough();
export type Table = z.infer<typeof tableSchema>;

export const seatSchema = z
  .object({
    id: z.string(),
    conversation_id: z.string().nullish(),
    person_id: z.string().nullish(),
    name: z.string().nullish(),
    avatar: z.string().nullish(),
    controller_id: z.string().nullish(),
    ...versioned,
  })
  .passthrough();
export type Seat = z.infer<typeof seatSchema>;

export const personSchema = z
  .object({
    id: z.string(),
    name: z.string().nullish(),
    user_id: z.string().nullish(),
    kind: z.string().nullish(),
    ...versioned,
  })
  .passthrough();
export type Person = z.infer<typeof personSchema>;

export const whisperSchema = z.object({
  table_whisper: z.object({ id: z.string(), conversation_id: z.string().nullish() }).passthrough(),
});
