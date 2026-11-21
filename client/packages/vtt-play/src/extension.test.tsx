// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, expect, it } from 'vitest';
import { vttExtension } from './extension';
import { campaignPath, scenePath, sheetPath, systemsPath, vttRoot } from './paths';

describe('the VTT as an extension', () => {
  it('mounts its pages under the base, most specific first, with nav entries', () => {
    const extension = vttExtension({ base: '/table/' });
    expect(extension.pages?.map((page) => page.path)).toEqual([
      'table/systems',
      'table/scene/:scene',
      'table/sheet/:person',
      'table/campaign/:campaign',
      'table',
    ]);
    expect(extension.navItems).toEqual([
      { title: 'Tables', url: '/table' },
      { title: 'Game systems', url: '/table/systems' },
    ]);
    expect(extension.serverExtension).toBe('rpg_scene');
  });

  it('mounts the pages without nav entries when the host asks', () => {
    const quiet = vttExtension({ nav: false });
    expect(quiet.navItems).toEqual([]);
    expect(quiet.pages).toHaveLength(5);
  });

  it('builds paths for apps that link in, segments encoded', () => {
    expect(vttRoot('vtt/')).toBe('/vtt');
    expect(campaignPath('vtt', 'c 1')).toBe('/vtt/campaign/c%201');
    expect(scenePath('/vtt', 's1')).toBe('/vtt/scene/s1');
    expect(sheetPath('vtt', 'p/1')).toBe('/vtt/sheet/p%2F1');
    expect(systemsPath('vtt')).toBe('/vtt/systems');
  });
});

describe('the extension module', () => {
  it('pulls in none of the play UI until a page renders', async () => {
    // vitest runs from the client directory; jsdom gives import.meta.url no file scheme.
    const fs = await import('node:fs');
    const path = await import('node:path');
    const source = fs.readFileSync(path.join(process.cwd(), 'packages/vtt-play/src/extension.tsx'), 'utf8');
    const staticImports = [...source.matchAll(/^import (?!type)[^;]*from '([^']+)'/gm)].map((match) => match[1]);
    expect(staticImports).toEqual(['react', './paths']);
  });
});
