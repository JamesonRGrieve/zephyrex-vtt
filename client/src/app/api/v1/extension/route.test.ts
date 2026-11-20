// @vitest-environment node
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { GET } from './route.lite';

describe('GET /v1/extension (lite)', () => {
  it('lists rpg_state, which serves game systems and campaigns, and nothing for accounts', async () => {
    const body = (await GET().json()) as { extensions: { name: string }[] };
    expect(body.extensions.map((one) => one.name)).toEqual(['rpg_state']);
  });
});
