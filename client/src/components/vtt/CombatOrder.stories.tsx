// SPDX-License-Identifier: AGPL-3.0-or-later
/** The initiative order of a campaign's fight (@zephyrex/vtt-play's CombatOrder). */
import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, userEvent, within } from 'storybook/test';
import { CombatOrder } from '../../../packages/vtt-play/src/combat/CombatOrder';
import { StoryClient, type Routes } from './StoryClient';

function order(round: number, current: string) {
  return {
    encounter: {
      id: 'e1',
      name: 'Ambush at the ford',
      status: 'running',
      round,
      current_combatant_id: current,
      gm: true,
      combatants: [
        { id: 'c1', name: 'Bandit', initiative: 14, is_defeated: false, is_hidden: false, controlled: true },
        { id: 'c2', name: 'Brann', initiative: 9, is_defeated: false, is_hidden: false, controlled: true },
        { id: 'c3', name: 'Guard', initiative: 6, is_defeated: true, is_hidden: false, controlled: true },
      ],
      unrolled: [],
    },
  };
}
const FIGHT: Routes = { 'POST /v1/encounter/current': order(2, 'c2'), 'POST /v1/encounter/e1/next': order(3, 'c1') };
const QUIET: Routes = { 'POST /v1/encounter/current': { encounter: null } };

function Order({ routes }: { routes: Routes }) {
  return (
    <StoryClient routes={routes}>
      <CombatOrder campaignId='k1' />
    </StoryClient>
  );
}

const meta: Meta<typeof Order> = { title: 'VTT/Combat order', component: Order, args: { routes: FIGHT } };
export default meta;
type Story = StoryObj<typeof Order>;

/** The GM's view of a running fight: whose turn it is, a defeated combatant, and passing the turn. */
export const Running: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(await canvas.findByText('Round 2')).toBeInTheDocument();
    await userEvent.click(canvas.getByRole('button', { name: 'Next turn' }));
    await expect(await canvas.findByText('Round 3')).toBeInTheDocument();
  },
};

/** No fight in progress. */
export const NoFight: Story = {
  args: { routes: QUIET },
  play: async ({ canvasElement }) => {
    await expect(await within(canvasElement).findByText('No fight in progress.')).toBeInTheDocument();
  },
};
