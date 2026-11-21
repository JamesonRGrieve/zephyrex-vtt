// SPDX-License-Identifier: AGPL-3.0-or-later
const path = require('node:path');

// The repository root, not this directory: the app reads contract/, the cases it shares with the
// SaaS server, from beside client/. Turbopack resolves nothing outside its root, and the standalone
// output is traced from the same root. The framework packages come in injected from their compiled
// dist (pnpm-workspace.yaml overrides), so nothing here reaches into a framework checkout.
const REPOSITORY_ROOT = path.join(__dirname, '..');

// Public origin of the app.
const APP_URI = process.env.APP_URI || 'http://localhost:1109';

// Which back end answers /api/v1/*. The UI is the same either way: it only ever calls the
// same-origin /api, so switching editions is a build-time config change.
//   lite (default): the app's own `route.lite.ts` handlers (a home table, Next.js only).
//   saas:           server/ (the zephyrex server framework), reached through a proxy.
const VARIANTS = ['lite', 'saas'];
const VARIANT = process.env.VTT_VARIANT || 'lite';
if (!VARIANTS.includes(VARIANT)) {
  throw new Error(`VTT_VARIANT must be one of ${VARIANTS.join(', ')}, got "${VARIANT}"`);
}
const IS_LITE = VARIANT === 'lite';

// The framework server the SaaS build proxies to (server-side only, never sent to the browser).
// Its routes live at /v1/*, so /api/v1/x maps to ${SERVER_URI}/v1/x.
const SERVER_URI = process.env.VTT_SERVER_URI || 'http://127.0.0.1:2000';

const DEFAULT_PAGE_EXTENSIONS = ['tsx', 'ts', 'jsx', 'js'];

/** @type {import('next').NextConfig} */
module.exports = {
  outputFileTracingRoot: REPOSITORY_ROOT,
  turbopack: { root: REPOSITORY_ROOT },
  // Lets the e2e suite build beside a running dev server without sharing its output.
  distDir: process.env.NEXT_DIST_DIR || '.next',
  // Self-contained server bundle for the deploy.
  ...(process.env.NEXT_OUTPUT_STANDALONE ? { output: 'standalone' } : {}),
  // `route.lite.ts` is a route only in the lite build; the SaaS build never sees it.
  pageExtensions: IS_LITE ? ['lite.ts', ...DEFAULT_PAGE_EXTENSIONS] : DEFAULT_PAGE_EXTENSIONS,
  env: {
    NEXT_PUBLIC_VTT_VARIANT: VARIANT,
    APP_URI,
    // The framework middleware drops the CSP's upgrade-insecure-requests only when this is an
    // http:// origin, as on a local or e2e build; without it every request goes to https.
    NEXT_PUBLIC_APP_URI: APP_URI,
    NEXT_PUBLIC_THEME_DEFAULT_MODE: process.env.DEFAULT_THEME_MODE || 'dark',
  },
  async rewrites() {
    if (IS_LITE) {
      return [];
    }
    // beforeFiles, so the app-root [...slug] catch-all page never claims an API path.
    return { beforeFiles: [{ source: '/api/v1/:path*', destination: `${SERVER_URI}/v1/:path*` }] };
  },
};
