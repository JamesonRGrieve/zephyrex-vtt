// SPDX-License-Identifier: AGPL-3.0-or-later
/** The scene view route's answer (server/extensions/rpg_scene: ViewOut), parsed at the boundary. */
import { z } from 'zod';

export const viewSchema = z.object({
  view: z.object({
    scene_id: z.string(),
    name: z.string().nullish(),
    width: z.number().nullish(),
    height: z.number().nullish(),
    grid_size: z.number(),
    grid_distance: z.number(),
    grid_units: z.string(),
    background_color: z.string().nullish(),
    gm: z.boolean(),
    viewer: z.string().nullish(),
    lit: z.boolean(),
    tokens: z.array(
      z.object({
        id: z.string(),
        name: z.string().nullish(),
        person_id: z.string().nullish(),
        disposition: z.string().nullish(),
        x: z.number(),
        y: z.number(),
        width: z.number(),
        height: z.number(),
        rotation: z.number(),
        is_hidden: z.boolean(),
        mine: z.boolean(),
      }),
    ),
    walls: z.array(
      z.object({
        id: z.string(),
        points: z.array(z.array(z.number())),
        door_type: z.string().nullish(),
        door_state: z.string().nullish(),
      }),
    ),
  }),
});
export type SceneViewData = z.infer<typeof viewSchema>['view'];
export type ViewToken = SceneViewData['tokens'][number];
