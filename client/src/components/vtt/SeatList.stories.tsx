// SPDX-License-Identifier: AGPL-3.0-or-later
/** A table's seats (@zephyrex/vtt-play's SeatList): who plays whom, and the NPCs the GM holds. */
import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, within } from 'storybook/test';
import { SeatList } from '../../../packages/vtt-play/src/seats/SeatList';
import { StoryClient, type Routes } from './StoryClient';

const ROUTES: Routes = {
  'LIST /v1/table': [{ id: 't1', conversation_id: 'c1', campaign_id: 'camp', created_by_user_id: 'gm' }],
  'LIST /v1/table_seat': [
    { id: 's1', person_id: 'brann', name: 'Brann Holt', controller_id: 'ada', updated_at: '2026-11-21T10:00:00Z' },
    { id: 's2', person_id: 'vell', name: 'Sergeant Vell', controller_id: null, updated_at: '2026-11-21T10:00:00Z' },
  ],
  'LIST /v1/person': [
    { id: 'brann', name: 'Brann Holt', user_id: 'ada' },
    { id: 'vell', name: 'Sergeant Vell', user_id: null },
  ],
};

function Seats() {
  return (
    <StoryClient routes={ROUTES}>
      <SeatList conversationId='c1' personHref={(id) => `#person-${id}`} />
    </StoryClient>
  );
}

const meta: Meta<typeof Seats> = { title: 'VTT/Seats', component: Seats };
export default meta;
type Story = StoryObj<typeof Seats>;

/** A player's character and an NPC at the table, each linking to its wiki page. */
export const AtTheTable: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const brann = await canvas.findByRole('link', { name: 'Brann Holt' });
    await expect(within(brann.closest('li')!).getByText('Player')).toBeInTheDocument();
    await expect(
      within(canvas.getByRole('link', { name: 'Sergeant Vell' }).closest('li')!).getByText('NPC'),
    ).toBeInTheDocument();
  },
};
