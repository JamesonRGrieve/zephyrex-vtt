// SPDX-License-Identifier: AGPL-3.0-or-later
import { mkdirSync, mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { migrationsKey } from './migrationsKey';

function migrations(files: Record<string, string>): string {
  const dir = mkdtempSync(path.join(tmpdir(), 'migrations-'));
  for (const [name, content] of Object.entries(files)) {
    mkdirSync(path.dirname(path.join(dir, name)), { recursive: true });
    writeFileSync(path.join(dir, name), content);
  }
  return dir;
}

describe('migrationsKey', () => {
  it('is the same for the same migrations, and changes with any of them', () => {
    const one = migrationsKey(migrations({ '1_init/migration.sql': 'CREATE TABLE a;' }));
    expect(migrationsKey(migrations({ '1_init/migration.sql': 'CREATE TABLE a;' }))).toBe(one);
    expect(migrationsKey(migrations({ '1_init/migration.sql': 'CREATE TABLE b;' }))).not.toBe(one);
    expect(
      migrationsKey(migrations({ '1_init/migration.sql': 'CREATE TABLE a;', '2_more/migration.sql': 'ALTER;' })),
    ).not.toBe(one);
  });
});
