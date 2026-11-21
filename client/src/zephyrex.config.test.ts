// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import config, { WIKI_BASE } from './zephyrex.config';

describe('the VTT includes the wiki', () => {
  it('mounts the wiki’s pages, a record page for every kind among them, and lists Worlds', () => {
    const wiki = config.extensions?.find((extension) => extension.serverExtension === 'rpg_core');
    expect(wiki).toBeDefined();
    const paths = (wiki?.pages ?? []).map((page) => page.path);
    expect(paths).toEqual(expect.arrayContaining([WIKI_BASE, `${WIKI_BASE}/:world/:kind`, `${WIKI_BASE}/:world/:kind/:id`]));
    expect(wiki?.navItems).toEqual(expect.arrayContaining([expect.objectContaining({ url: `/${WIKI_BASE}` })]));
  });
});
