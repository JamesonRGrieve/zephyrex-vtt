// SPDX-License-Identifier: AGPL-3.0-or-later
import { collectionRoutes } from '@zephyrex/lite';
import { owner } from '~/lib/owner';
import { gameSystems } from '~/lib/vttRecords';

// GET /v1/game_system (list) and POST /v1/game_system (create).
export const { GET, POST } = collectionRoutes(gameSystems, owner);
