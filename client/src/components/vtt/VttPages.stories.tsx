// SPDX-License-Identifier: AGPL-3.0-or-later
/** The VTT's own pages (@zephyrex/vtt-play's VttPages): the campaigns, the game systems, a setting's systems. */
import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, within } from 'storybook/test';
import { CampaignsPage, SettingSystems, SystemsPage } from '../../../packages/vtt-play/src/pages/VttPages';
import { StoryClient, type Routes } from './StoryClient';

const ROUTES: Routes = {
  'LIST /v1/campaign': [
    { id: 'c1', name: 'The Saltmere Road' },
    { id: 'c2', name: 'One-shot: The Ford' },
  ],
  'LIST /v1/game_system': [{ id: 'g1', name: 'SRD 5.2 (fifth-edition rules)', slug: 'srd-5e' }],
  'LIST /v1/content_module': [],
};

function Page({ page }: { page: 'campaigns' | 'systems' | 'setting' }) {
  return (
    <StoryClient routes={ROUTES}>
      {page === 'campaigns' && <CampaignsPage base='vtt' />}
      {page === 'systems' && <SystemsPage />}
      {page === 'setting' && <SettingSystems settingId='realms' />}
    </StoryClient>
  );
}

const meta: Meta<typeof Page> = { title: 'VTT/Pages', component: Page, args: { page: 'campaigns' } };
export default meta;
type Story = StoryObj<typeof Page>;

/** The campaigns this person may open, each linking to its table. */
export const Campaigns: Story = {
  play: async ({ canvasElement }) => {
    const link = await within(canvasElement).findByRole('link', { name: 'The Saltmere Road' });
    await expect(link).toHaveAttribute('href', expect.stringContaining('c1'));
  },
};

/** The game systems, and the modules this account has installed (none here). */
export const Systems: Story = {
  args: { page: 'systems' },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(await canvas.findByText('SRD 5.2 (fifth-edition rules)')).toBeInTheDocument();
    await expect(await canvas.findByText('No modules installed for your account.')).toBeInTheDocument();
  },
};

/** A setting's systems, as the wiki's setting page shows them. */
export const SettingSystemsPanel: Story = {
  name: 'Setting systems',
  args: { page: 'setting' },
  play: async ({ canvasElement }) => {
    await expect(await within(canvasElement).findByText('SRD 5.2 (fifth-edition rules)')).toBeInTheDocument();
  },
};
