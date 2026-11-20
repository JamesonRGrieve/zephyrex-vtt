// @vitest-environment node
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { config } from '../../proxy';
import { GET } from './route';

describe('GET /healthz', () => {
  it('answers 204 with no body and nothing cached', async () => {
    const response = GET();
    expect(response.status).toBe(204);
    expect(response.headers.get('cache-control')).toBe('no-store');
    expect(await response.text()).toBe('');
  });

  it('is outside the auth proxy, which still covers the app pages', () => {
    const [matcher] = config.matcher;
    const pattern = new RegExp(`^${matcher}$`);
    expect(pattern.test('/healthz')).toBe(false);
    expect(pattern.test('/rpg')).toBe(true);
  });
});
