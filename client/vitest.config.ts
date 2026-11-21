// SPDX-License-Identifier: AGPL-3.0-or-later
import path from 'path';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    // workerDatabase first, then the framework's jsdom stand-ins: each worker gets its own copy of the migrated database, so files run in parallel.
    setupFiles: ['src/__tests__/workerDatabase.ts', 'zephyrex/testing/setup', 'src/__tests__/setup.ts'],
    globalSetup: ['src/__tests__/globalSetup.ts'],
    // Threads over forks: lighter per-worker memory and startup; one worker per core.
    pool: 'threads',
    maxWorkers: '100%',
    globals: true,
    exclude: ['**/node_modules/**', '.next/**', 'e2e/**', 'tests/**', '**/*.stories.{ts,tsx}'],
    // Inline the compiled framework, so this app's module mocks (next/navigation, cookies-next) reach
    // the framework's own imports too (Zephyrex Framework App Standards, Testing). Vitest tests a
    // RegExp against the module's full path, so the scoped packages match on their node_modules path.
    server: { deps: { inline: ['zephyrex', /\/node_modules\/@zephyrex\//] } },
  },
  resolve: {
    alias: {
      // Mirrors the tsconfig `~/*` path to this app's source.
      '~': path.resolve(__dirname, './src'),
    },
  },
});
