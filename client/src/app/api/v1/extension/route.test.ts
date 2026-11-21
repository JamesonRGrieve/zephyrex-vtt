// @vitest-environment node
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { GET } from './route.lite';

describe('GET /v1/extension (lite)', () => {
  it('lists rpg_core (campaigns) and rpg_systems (game systems), and nothing for accounts', async () => {
    const body = (await GET().json()) as { extensions: { name: string }[] };
    expect(body.extensions.map((one) => one.name)).toEqual(['rpg_core', 'rpg_systems']);
  });
});
