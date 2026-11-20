// SPDX-License-Identifier: AGPL-3.0-or-later
import type { ZephyrexConfig } from 'zephyrex';
import { genealogyExtension, rpgStateExtension } from './extensions/campaign';
import { rpgExtension } from './extensions/rpg';

const config: ZephyrexConfig = {
  server: {
    baseUrl: process.env.NEXT_PUBLIC_API_URI ?? 'http://localhost:2000',
  },
  app: {
    name: 'Zephyrex VTT',
    description: 'Virtual tabletop on the Zephyrex framework',
    defaultTheme: 'dark',
  },
  auth: {
    privateRoutes: ['/rpg', '/settings', '/team'],
  },
  extensions: [rpgExtension, genealogyExtension, rpgStateExtension],
};

export default config;
