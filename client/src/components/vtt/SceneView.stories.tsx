// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * A scene in play (@zephyrex/vtt-play's SceneView): the map the server lets this person see, the
 * move and measure tools, and for the GM the map controls and door taps. The view is the story's own.
 */
import type { Meta, StoryObj } from '@storybook/nextjs';
import { useState } from 'react';
import { expect, userEvent, within } from 'storybook/test';
import { SceneView } from '../../../packages/vtt-play/src/scene/SceneView';
import { StoryClient, type Routes } from './StoryClient';

function view(gm: boolean) {
  return {
    view: {
      scene_id: 's1',
      name: 'The Ford',
      width: 1200,
      height: 900,
      grid_size: 100,
      grid_distance: 5,
      grid_units: 'ft',
      background_color: null,
      gm,
      viewer: gm ? null : 'brann',
      lit: true,
      background_url: null,
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
          mine: !gm,
        },
        {
          id: 'bandit',
          name: 'Bandit',
          person_id: 'p-bandit',
          disposition: 'hostile',
          x: 700,
          y: 300,
          width: 1,
          height: 1,
          rotation: 0,
          is_hidden: false,
          mine: false,
        },
      ],
      walls: gm
        ? [
            {
              id: 'gate',
              points: [
                [500, 100],
                [500, 200],
              ],
              door_type: 'gate',
              door_state: 'closed',
            },
          ]
        : [],
    },
  };
}
const PLAYER: Routes = { 'POST /v1/scene/s1/view': view(false), 'POST /v1/scene_token/*': { scene_token: {} } };
const GM: Routes = {
  'POST /v1/scene/s1/view': view(true),
  'POST /v1/scene/s1/place': { token_id: 't-wren' },
  'POST /v1/scene/s1/activate': { scene: {} },
  'GET /v1/scene?campaign_id=c1': {
    scenes: [
      { id: 's1', name: 'The Ford', is_active: false },
      { id: 's2', name: 'The Mill', is_active: true },
    ],
  },
  'GET /v1/person?campaign_id=c1': {
    persons: [
      { id: 'p-brann', name: 'Brann', kind: 'pc' },
      { id: 'p-wren', name: 'Wren', kind: 'pc' },
    ],
  },
};

function Scene({ routes, campaignId }: { routes: Routes; campaignId?: string }) {
  return (
    <StoryClient routes={routes}>
      <SceneView sceneId='s1' campaignId={campaignId} showList />
    </StoryClient>
  );
}

const meta: Meta<typeof Scene> = { title: 'VTT/Scene', component: Scene, args: { routes: PLAYER } };
export default meta;
type Story = StoryObj<typeof Scene>;

/** A player sees their token and the bandit, and may move only their own. */
export const PlayersView: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(await canvas.findByRole('application', { name: /^Map of The Ford/ })).toBeInTheDocument();
    await expect(canvas.getByRole('button', { name: 'Move Brann east' })).toBeInTheDocument();
    await expect(canvas.queryByRole('button', { name: /Move Bandit/ })).toBeNull();
    await userEvent.click(canvas.getByRole('radio', { name: 'Measure' }));
    await expect(canvas.getByRole('radio', { name: 'Measure' })).toHaveAttribute('aria-checked', 'true');
  },
};

/** The GM's view with the map controls: the scene to show, and the cast not yet on the map. */
export const GameMastersView: Story = {
  args: { routes: GM, campaignId: 'c1' },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(await canvas.findByRole('region', { name: 'Map controls' })).toBeInTheDocument();
    await expect(await canvas.findByRole('button', { name: 'Place Wren on the map' })).toBeInTheDocument();
    await expect(canvas.queryByRole('button', { name: 'Place Brann on the map' })).toBeNull();
  },
};

/** The ford with a silver key lying by the bank, and the map's menu filled the way rpg-ai fills it:
 * each choice is the action line the chat would get. */
function WithMenu() {
  const [line, setLine] = useState('Nothing done yet');
  const ford = view(false);
  const routes: Routes = {
    ...PLAYER,
    'POST /v1/scene/s1/view': {
      view: { ...ford.view, items: [{ id: 'key', item_id: 'silver-key', name: 'Silver key', quantity: 1, x: 300, y: 600 }] },
    },
  };
  return (
    <StoryClient routes={routes}>
      <SceneView
        sceneId='s1'
        onContextAction={(target) =>
          target.kind === 'item'
            ? [{ label: `Pick up ${target.name}`, run: () => setLine(`Brann picks up the ${target.name?.toLowerCase()}`) }]
            : target.kind === 'token' && target.name !== 'Brann'
              ? [
                  { label: `Talk to ${target.name}`, run: () => setLine(`Brann talks to ${target.name}`) },
                  { label: `Attack ${target.name}`, run: () => setLine(`Brann attacks ${target.name}`) },
                ]
              : target.kind === 'token'
                ? [{ label: 'Look around', run: () => setLine('Brann looks around') }]
                : []
        }
      />
      <p role='status' aria-label='Action line'>
        {line}
      </p>
    </StoryClient>
  );
}

/** A player opens the map's menu from the keyboard (Enter selects Brann, Shift+F10 opens it at him),
 * moves through it and chooses: the choice becomes the action line. Right-click and long-press open
 * the same menu (the phone e2e covers them, with an item and a square's Move here). */
export const MapMenu: StoryObj<typeof WithMenu> = {
  render: () => <WithMenu />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const map = await canvas.findByRole('application', { name: /^Map of The Ford.*Shift\+F10 opens actions/ });
    map.focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard('{Shift>}{F10}{/Shift}');
    const menu = await canvas.findByRole('menu', { name: 'Actions: Brann' });
    await expect(within(menu).getByRole('menuitem', { name: 'Look around' })).toHaveFocus();
    await userEvent.keyboard('{Enter}');
    await expect(canvas.getByRole('status', { name: 'Action line' })).toHaveTextContent('Brann looks around');
    await expect(canvas.queryByRole('menu')).toBeNull();
  },
};

/** The menu left open on the bandit, as a player sees it (for the screenshot review): opened from
 * the keyboard at Brann, it lists what Brann can do there. */
export const MapMenuOpen: StoryObj<typeof WithMenu> = {
  render: () => <WithMenu />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const map = await canvas.findByRole('application', { name: /^Map of The Ford/ });
    map.focus();
    await userEvent.keyboard('{Enter}');
    await userEvent.keyboard('{Shift>}{F10}{/Shift}');
    await expect(await canvas.findByRole('menu', { name: 'Actions: Brann' })).toBeVisible();
  },
};
