// SPDX-License-Identifier: AGPL-3.0-or-later
import { existsSync } from 'node:fs';
import path from 'path';
import type { StorybookConfig } from '@storybook/nextjs';

const APP_SRC = path.resolve(import.meta.dirname, '../src');
// public/ holds only what is fetched into it , so it may not exist.
const PUBLIC = path.resolve(import.meta.dirname, '../public');

const config: StorybookConfig = {
  // Stories, and the MDX docs pages (the VTT's user guide and developer docs, under src/docs).
  stories: ['../src/**/*.mdx', '../src/**/*.stories.@(js|jsx|mjs|ts|tsx)'],
  // Storybook 10 folds actions/controls/interactions/viewport into core; links, a11y and docs (the
  // MDX pages) remain as separate addons here.
  addons: ['@storybook/addon-links', '@storybook/addon-a11y', '@storybook/addon-docs'],
  framework: {
    name: '@storybook/nextjs',
    options: {},
  },
  staticDirs: existsSync(PUBLIC) ? ['../public'] : [],
  core: {
    disableTelemetry: true,
  },
  webpackFinal: async (webpackConfig) => {
    webpackConfig.resolve = webpackConfig.resolve || {};
    // This app's `~/*` alias (tsconfig paths); the framework is a compiled package.
    webpackConfig.resolve.alias = { ...(webpackConfig.resolve.alias || {}), '~': APP_SRC };
    return webpackConfig;
  },
};

export default config;
