// @vitest-environment node
// SPDX-License-Identifier: AGPL-3.0-or-later
import { LOCAL_OWNER_ID } from '@zephyrex/lite';
import { NextRequest } from 'next/server';
import { describe, expect, it } from 'vitest';
import { owner } from './owner';

describe('owner', () => {
  it('is the one local owner until local accounts replace it', async () => {
    const resolved = await owner(new NextRequest('http://localhost/api/v1/campaign'));
    expect(resolved.id).toBe(LOCAL_OWNER_ID);
  });
});
