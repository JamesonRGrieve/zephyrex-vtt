// SPDX-License-Identifier: AGPL-3.0-or-later
/** What a character carries (Inventory) and what lies where they stand (Loot), in @zephyrex/vtt-play. */
import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, within } from 'storybook/test';
import { Inventory } from '../../../packages/vtt-play/src/inventory/Inventory';
import { Loot } from '../../../packages/vtt-play/src/loot/Loot';
import { StoryClient, type Routes } from './StoryClient';

const V = { updated_at: '2026-11-21T10:00:00Z' };
const NAMES: Record<string, string> = { torch: 'Torch', rope: 'Rope (50 feet)', coin: 'Silver coin', crate: 'Crate' };
const ROUTES: Routes = {
  'GET /v1/person/brann': { person: { id: 'brann', campaign_id: 'c1', location_id: 'ford' } },
  'GET /v1/location/ford': { location: { id: 'ford', name: 'The Ford' } },
  'GET /v1/item/torch': { item: { id: 'torch', name: NAMES.torch } },
  'GET /v1/item/rope': { item: { id: 'rope', name: NAMES.rope } },
  'GET /v1/item/coin': { item: { id: 'coin', name: NAMES.coin } },
  'GET /v1/item/crate': { item: { id: 'crate', name: NAMES.crate } },
  'LIST /v1/item_instance': (query: unknown) =>
    (query as { location_id?: string } | undefined)?.location_id === 'ford'
      ? [
          { id: 'l1', item_id: 'coin', location_id: 'ford', owner_person_id: null, quantity: 12, ...V },
          { id: 'l2', item_id: 'crate', location_id: 'ford', owner_person_id: null, quantity: 1, ...V },
        ]
      : [
          { id: 'i1', item_id: 'torch', location_id: null, owner_person_id: 'brann', quantity: 1, ...V },
          { id: 'i2', item_id: 'rope', location_id: null, owner_person_id: 'brann', quantity: 2, ...V },
        ],
  'LIST /v1/location': [],
  'LIST /v1/person': [
    { id: 'brann', name: 'Brann' },
    { id: 'wren', name: 'Wren' },
  ],
};

function Belongings({ which }: { which: 'inventory' | 'loot' }) {
  return (
    <StoryClient routes={ROUTES}>
      {which === 'inventory' ? <Inventory personId='brann' /> : <Loot personId='brann' />}
    </StoryClient>
  );
}

const meta: Meta<typeof Belongings> = { title: 'VTT/Belongings', component: Belongings, args: { which: 'inventory' } };
export default meta;
type Story = StoryObj<typeof Belongings>;

/** What Brann carries, with counts. */
export const Carried: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(await canvas.findByText('Torch')).toBeInTheDocument();
    await expect(canvas.getByText('×2')).toBeInTheDocument();
  },
};

/** What lies at the ford, for the taking. */
export const LyingHere: Story = {
  args: { which: 'loot' },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(await canvas.findByText('Silver coin')).toBeInTheDocument();
    await expect(canvas.getByText('×12')).toBeInTheDocument();
  },
};
