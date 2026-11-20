// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The lite edition's rpg_state records: game systems and campaigns, with the same fields and rules
 * as the SaaS server's GameSystemModel and CampaignModel (server/extensions/rpg_state). Both
 * editions answer contract/api-cases.json.
 */
import type { Prisma } from '@prisma/client';
import type { ResourceSpec } from '@zephyrex/lite';
import { z } from 'zod';
import { type Columns, columnsOf, fieldsOf, plain } from '~/lib/columns';
import { prisma } from '~/lib/prisma';

function written(columns: Columns, input: object, stamp: Date, userId?: string): Record<string, unknown> {
  return { ...columnsOf(columns, input), updatedAt: stamp, ...(userId === undefined ? {} : { updatedById: userId }) };
}

// ---- game_system --------------------------------------------------------------------------

const GAME_SYSTEM_COLUMNS: Columns = {
  name: plain('name'),
  description: plain('description'),
};

const gameSystemCreate = z.object({
  name: z.string(),
  description: z.string().nullable().default(null),
});
const gameSystemUpdate = z.object({ name: z.string(), description: z.string().nullable() }).partial();

type GameSystemRow = Prisma.GameSystemGetPayload<object>;

export const gameSystems: ResourceSpec<GameSystemRow, z.infer<typeof gameSystemCreate>, z.infer<typeof gameSystemUpdate>> = {
  resource: 'game_system',
  plural: 'game_systems',
  modelName: 'GameSystemModel',
  createSchema: gameSystemCreate,
  updateSchema: gameSystemUpdate,
  list: (ownerId) => prisma.gameSystem.findMany({ where: { createdById: ownerId }, orderBy: { name: 'asc' } }),
  find: (id, ownerId) => prisma.gameSystem.findFirst({ where: { id, createdById: ownerId } }),
  insert: (ownerId, input, stamp) =>
    prisma.gameSystem.create({
      data: { createdById: ownerId, ...written(GAME_SYSTEM_COLUMNS, input, stamp) } as Prisma.GameSystemUncheckedCreateInput,
    }),
  async updateIfCurrent(id, version, input, stamp, userId) {
    const { count } = await prisma.gameSystem.updateMany({
      where: { id, updatedAt: version },
      data: written(GAME_SYSTEM_COLUMNS, input, stamp, userId) as Prisma.GameSystemUncheckedUpdateManyInput,
    });
    return count === 0 ? null : prisma.gameSystem.findUnique({ where: { id } });
  },
  async remove(id) {
    await prisma.gameSystem.delete({ where: { id } });
  },
  fields: (row) => fieldsOf(GAME_SYSTEM_COLUMNS, row),
};

// ---- campaign -----------------------------------------------------------------------------

const CAMPAIGN_COLUMNS: Columns = {
  name: plain('name'),
  description: plain('description'),
  game_system_id: plain('gameSystemId'),
  user_id: plain('userId'),
};

// As the server's CampaignModel.Create: the game system and the game master are set at creation;
// an update changes only the name and the description.
const campaignCreate = z.object({
  name: z.string(),
  description: z.string().nullable().default(null),
  game_system_id: z.string().nullable().default(null),
  user_id: z.string().nullable().default(null),
});
const campaignUpdate = z.object({ name: z.string(), description: z.string().nullable() }).partial();

type CampaignRow = Prisma.CampaignGetPayload<object>;

export const campaigns: ResourceSpec<CampaignRow, z.infer<typeof campaignCreate>, z.infer<typeof campaignUpdate>> = {
  resource: 'campaign',
  plural: 'campaigns',
  modelName: 'CampaignModel',
  createSchema: campaignCreate,
  updateSchema: campaignUpdate,
  list: (ownerId) => prisma.campaign.findMany({ where: { createdById: ownerId }, orderBy: { name: 'asc' } }),
  find: (id, ownerId) => prisma.campaign.findFirst({ where: { id, createdById: ownerId } }),
  insert: (ownerId, input, stamp) =>
    prisma.campaign.create({
      data: { createdById: ownerId, ...written(CAMPAIGN_COLUMNS, input, stamp) } as Prisma.CampaignUncheckedCreateInput,
    }),
  async updateIfCurrent(id, version, input, stamp, userId) {
    const { count } = await prisma.campaign.updateMany({
      where: { id, updatedAt: version },
      data: written(CAMPAIGN_COLUMNS, input, stamp, userId) as Prisma.CampaignUncheckedUpdateManyInput,
    });
    return count === 0 ? null : prisma.campaign.findUnique({ where: { id } });
  },
  async remove(id) {
    await prisma.campaign.delete({ where: { id } });
  },
  fields: (row) => fieldsOf(CAMPAIGN_COLUMNS, row),
};
