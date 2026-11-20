// SPDX-License-Identifier: AGPL-3.0-or-later
import { collectionRoutes } from '@zephyrex/lite';
import { owner } from '~/lib/owner';
import { campaigns } from '~/lib/vttRecords';

// GET /v1/campaign (list) and POST /v1/campaign (create).
export const { GET, POST } = collectionRoutes(campaigns, owner);
