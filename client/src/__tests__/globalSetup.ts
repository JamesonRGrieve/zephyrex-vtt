// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Migrates one template SQLite database for the code under test.
 * Workers spawn after this runs and inherit the env; each copies
 * the template into a database of its own (workerDatabase.ts), so test files run
 * in parallel without interleaving writes.
 *
 * The migrated template is kept in a cache keyed by the migrations' own bytes, so a run migrates
 * only when the schema changed: `prisma migrate deploy` costs over a minute on a loaded runner
 * and nothing on a cache hit. A changed or new migration changes the key, so a stale schema is
 * never reused.
 */
import { execFileSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, mkdtempSync, renameSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { migrationsKey } from './migrationsKey';
import { TEMPLATE_DATABASE_FILE } from './workerDatabase';

const MIGRATE_TIMEOUT_MS = 60_000;
const MIGRATIONS = path.resolve('prisma/migrations');
const CACHE = process.env.TEST_DATABASE_CACHE ?? path.resolve('node_modules/.cache/vtt-test-db');

export default function setup(): () => void {
  const dir = mkdtempSync(path.join(tmpdir(), 'vtt-test-'));
  process.env.TEST_DATABASE_DIR = dir;
  process.env.APP_URI = 'http://localhost';
  const template = path.join(dir, TEMPLATE_DATABASE_FILE);
  const cached = path.join(CACHE, `template-${migrationsKey(MIGRATIONS)}.db`);

  if (existsSync(cached)) {
    copyFileSync(cached, template);
  } else {
    execFileSync(path.resolve('node_modules/.bin/prisma'), ['migrate', 'deploy'], {
      env: { ...process.env, DATABASE_URL: `file:${template}` },
      stdio: 'pipe',
      timeout: MIGRATE_TIMEOUT_MS,
    });
    // Written aside, then renamed, so a run that stops halfway never leaves a half-copied template.
    mkdirSync(CACHE, { recursive: true });
    const partial = `${cached}.${process.pid}.partial`;
    copyFileSync(template, partial);
    renameSync(partial, cached);
  }
  return () => rmSync(dir, { recursive: true, force: true });
}
