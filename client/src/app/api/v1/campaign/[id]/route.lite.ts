// SPDX-License-Identifier: AGPL-3.0-or-later
import { recordRoutes } from '@zephyrex/lite';
import { owner } from '~/lib/owner';
import { campaigns } from '~/lib/vttRecords';

// GET, PUT (If-Match) and DELETE (If-Match) /v1/campaign/{id}.
export const { GET, PUT, DELETE } = recordRoutes(campaigns, owner);
