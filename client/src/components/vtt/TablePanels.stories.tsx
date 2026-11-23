// SPDX-License-Identifier: AGPL-3.0-or-later
/** The campaign table's panels (@zephyrex/vtt-play's TablePanel): the scenes, the current scene's tokens, the seats. */
import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, userEvent, within } from 'storybook/test';
import { CampaignSeats, CurrentSceneTokens, SceneList } from '../../../packages/vtt-play/src/table/TablePanel';
import { StoryClient, type Routes } from './StoryClient';

const SCENES = [
  { id: 's1', name: 'The Ford', is_active: true },
  { id: 's2', name: 'The Mill', is_active: false },
];
const ROUTES: Routes = {
  'GET /v1/campaign/c1': { campaign: { id: 'c1', user_id: 'gm', created_by_user_id: 'gm' } },
  'LIST /v1/scene': SCENES,
  'POST /v1/scene/s2/activate': { scene: {} },
  'POST /v1/scene/current': { scene: { id: 's1' } },
  'POST /v1/scene/s1/view': {
    view: {
      scene_id: 's1',
      name: 'The Ford',
      width: 1200,
      height: 900,
      grid_size: 100,
      grid_distance: 5,
      grid_units: 'ft',
      background_color: null,
      gm: false,
      viewer: 'brann',
      lit: true,
      tokens: [
        {
          id: 'brann',
          name: 'Brann',
          person_id: 'p-brann',
          disposition: 'friendly',
          x: 200,
          y: 400,
          width: 1,
          height: 1,
          rotation: 0,
          is_hidden: false,
          mine: true,
        },
      ],
      walls: [],
    },
  },
  'LIST /v1/table': [{ id: 't1', conversation_id: 'conv1', campaign_id: 'c1', created_by_user_id: 'gm' }],
  'LIST /v1/table_seat': [
    { id: 's1', person_id: 'p-brann', name: 'Brann Holt', controller_id: 'ada', updated_at: '2026-11-21T10:00:00Z' },
  ],
  'LIST /v1/person': [{ id: 'p-brann', name: 'Brann Holt', user_id: 'ada' }],
};

function Panel({ panel }: { panel: 'scenes' | 'tokens' | 'seats' }) {
  return (
    <StoryClient routes={ROUTES}>
      {panel === 'scenes' && <SceneList campaignId='c1' />}
      {panel === 'tokens' && <CurrentSceneTokens campaignId='c1' personHref={(id) => `#person-${id}`} />}
      {panel === 'seats' && <CampaignSeats campaignId='c1' personHref={(id) => `#person-${id}`} />}
    </StoryClient>
  );
}

const meta: Meta<typeof Panel> = { title: 'VTT/Table panels', component: Panel, args: { panel: 'scenes' } };
export default meta;
type Story = StoryObj<typeof Panel>;

/** The campaign's scenes, the current one marked; the GM can make another current. */
export const Scenes: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(await canvas.findByText('The Mill')).toBeInTheDocument();
    await expect(canvas.getByText('Current')).toBeInTheDocument();
    await userEvent.click(await canvas.findByRole('button', { name: 'Make current' }));
  },
};

/** Who is on the current scene, with step buttons for the player's own token. */
export const CurrentSceneTokensPanel: Story = {
  name: 'Current scene tokens',
  args: { panel: 'tokens' },
  play: async ({ canvasElement }) => {
    await expect(await within(canvasElement).findByRole('button', { name: 'Move Brann east' })).toBeInTheDocument();
  },
};

/** The campaign table's seats. */
export const Seats: Story = {
  args: { panel: 'seats' },
  play: async ({ canvasElement }) => {
    await expect(await within(canvasElement).findByRole('link', { name: 'Brann Holt' })).toBeInTheDocument();
  },
};
