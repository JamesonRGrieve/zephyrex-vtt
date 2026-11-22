// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * vtt-play's own browser tests: components alone in a page, no app or server (scene-mobile: the map
 * on a phone). The harness is bundled first (esbuild, path in HARNESS_JS); see scene-mobile.spec.ts.
 */
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: '.',
  testMatch: /.*\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  projects: [{ name: 'phone', use: { ...devices['Pixel 7'], viewport: { width: 390, height: 844 } } }],
});
