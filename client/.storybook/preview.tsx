// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Preview } from '@storybook/react';
import '../src/app/globals.css';

const preview: Preview = {
  parameters: {
    controls: {
      matchers: { color: /(background|color)$/i, date: /Date$/ },
    },
    nextjs: {
      appDirectory: true,
    },
    // An accessibility violation fails the story's test (the test-runner and the gate), as the e2e
    // axe pass does: nothing is excused here; a shared primitive is fixed upstream.
    a11y: { test: 'error' },
  },
};

export default preview;
