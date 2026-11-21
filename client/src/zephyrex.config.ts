// SPDX-License-Identifier: AGPL-3.0-or-later
import type { ZephyrexConfig } from 'zephyrex';
import { VttLogo } from './brand/VttLogo';
import { genealogyExtension, rpgSystemsExtension } from './extensions/campaign';
import { rpgExtension } from './extensions/rpg';

/** Where a person works. `/` is the landing page for visitors. */
export const HOME_PATH = '/rpg';

/** The app's pages (matched as path prefixes); in the hosted build they need a signed-in person. */
const APP_ROUTES = [HOME_PATH];

export const APP_NAME = 'Zephyrex VTT';
export const APP_DESCRIPTION =
  'A virtual tabletop for any game system: campaigns and game systems today, with maps, scenes, dice and combat on the way.';

/**
 * The build edition decides only what the back end can do, never what a page shows: pages show
 * features by capability (`GET /v1/extension`). The hosted (saas) build turns on accounts. The
 * lite build has no sign-in for now: every record belongs to one local owner (lib/owner.ts), and
 * local accounts replace that owner as their own item (docs/DESIGN.md, Progress).
 */
const HOSTED = process.env.NEXT_PUBLIC_VTT_VARIANT === 'saas';

const DEFAULT_PORT = 1109;

const config: ZephyrexConfig = {
  server: {
    // Same-origin: the browser calls `/api/v1/...` on this app, answered by its own lite handlers
    // or, in the hosted build, proxied to server/ (next.config.js).
    baseUrl: '/api',
    ...(HOSTED
      ? { upstreamUrl: process.env.VTT_SERVER_URI || 'http://127.0.0.1:2000' }
      : { upstreamUrl: process.env.API_UPSTREAM_URL || `http://127.0.0.1:${process.env.PORT || DEFAULT_PORT}/api` }),
  },
  app: {
    name: APP_NAME,
    description: APP_DESCRIPTION,
    logo: VttLogo,
    defaultTheme: (process.env.NEXT_PUBLIC_THEME_DEFAULT_MODE as 'dark' | 'light') ?? 'dark',
    // Never send a signed-in person's email hash to Gravatar: no request leaves for a third party.
    gravatar: false,
  },
  // auth.enabled=false only in the lite build, which has no sign-in at all; the hosted build keeps it on.
  auth: HOSTED
    ? {
        enabled: true,
        authPath: '/user',
        home: HOME_PATH,
        privateRoutes: [...APP_ROUTES, ...(process.env.PRIVATE_ROUTES ?? '').split(',').filter(Boolean)],
      }
    : { enabled: false },
  extensions: [rpgExtension, genealogyExtension, rpgSystemsExtension],
};

export default config;
