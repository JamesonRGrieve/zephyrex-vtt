// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The end-to-end suite runs against production builds of both editions, each in its own build
 * directory and port (two `next dev` servers from one client/ directory reload each other). The
 * builds are made first, with no time limit, and Playwright only starts them (Gates: build first,
 * then serve):
 *
 *   VTT_VARIANT=lite NEXT_DIST_DIR=.next-e2e-lite next build
 *   VTT_VARIANT=saas NEXT_DIST_DIR=.next-e2e-saas next build
 *
 * - `lite`: the app's own API routes on a throwaway SQLite file (E2E_DATABASE_URL), one local owner.
 * - `saas`: the hosted build's visitor pages (signed out); its signed-in pages need the server.
 */
import { defineConfig, devices } from '@playwright/test';

// vtt's block on the shared runner is 48090–48099 (48000 + 10 × its 58137 lane, 9), so suites of
// different apps never take each other's ports.
export const PORTS = { lite: 48090, saas: 48091 } as const;
const host = (port: number): string => `http://127.0.0.1:${port}`;
const NEXT = './node_modules/.bin/next';
const STARTUP_MS = 120_000;

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [['list']],
  timeout: 90_000,
  expect: { timeout: 15_000 },
  use: { trace: 'retain-on-failure', navigationTimeout: 60_000 },
  projects: [
    { name: 'lite', use: { ...devices['Desktop Chrome'], baseURL: host(PORTS.lite) } },
    { name: 'saas', use: { ...devices['Desktop Chrome'], baseURL: host(PORTS.saas) } },
  ],
  webServer: [
    {
      command: `${NEXT} start -p ${PORTS.lite} -H 127.0.0.1`,
      url: `${host(PORTS.lite)}/healthz`,
      reuseExistingServer: !process.env.CI,
      timeout: STARTUP_MS,
      env: {
        NEXT_TELEMETRY_DISABLED: '1',
        VTT_VARIANT: 'lite',
        NEXT_DIST_DIR: '.next-e2e-lite',
        PORT: String(PORTS.lite),
        DATABASE_URL: process.env.E2E_DATABASE_URL ?? 'file:./e2e-lite.db',
      },
    },
    {
      command: `${NEXT} start -p ${PORTS.saas} -H 127.0.0.1`,
      url: `${host(PORTS.saas)}/healthz`,
      reuseExistingServer: !process.env.CI,
      timeout: STARTUP_MS,
      env: { NEXT_TELEMETRY_DISABLED: '1', VTT_VARIANT: 'saas', NEXT_DIST_DIR: '.next-e2e-saas', PORT: String(PORTS.saas) },
    },
  ],
});
