// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Whom a lite request acts for, decided here and nowhere else: every `route.lite.ts` takes its
 * owner from this resolver. For now that is @zephyrex/lite's one local owner. Local accounts (so
 * players join the table from their own devices) replace it with a session check, and nothing else
 * changes: records already keep their owner in `createdById`.
 */
import { localOwner, type OwnerResolver } from '@zephyrex/lite';

export const owner: OwnerResolver = localOwner;
