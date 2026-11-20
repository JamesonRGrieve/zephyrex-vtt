// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The key of the cached test database template (globalSetup.ts): a hash of every migration file,
 * by name and content, in a stable order. Kept free of local imports so a job script can run it
 * with Node alone, to seed the cache once without a time limit on a loaded runner.
 */
import { createHash } from 'node:crypto';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

export function migrationsKey(dir: string): string {
  const hash = createHash('sha256');
  const walk = (at: string): void => {
    for (const entry of readdirSync(at, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const full = path.join(at, entry.name);
      if (entry.isDirectory()) walk(full);
      else hash.update(path.relative(dir, full)).update('\0').update(readFileSync(full)).update('\0');
    }
  };
  walk(dir);
  return hash.digest('hex').slice(0, 16);
}
