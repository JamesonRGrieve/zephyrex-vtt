// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { pictureUrl } from './pictures';

describe('a picture to load', () => {
  const client = { url: (path: string) => `https://api.example${path}` };

  it('puts an upload at the API base and leaves a link elsewhere as it is', () => {
    expect(pictureUrl(client, '/v1/asset/a1/content')).toBe('https://api.example/v1/asset/a1/content');
    expect(pictureUrl(client, 'https://maps.example/saltmere.webp')).toBe('https://maps.example/saltmere.webp');
    expect(pictureUrl(client, null)).toBeNull();
    expect(pictureUrl({}, '/v1/asset/a1/content')).toBe('/v1/asset/a1/content');
  });
});
