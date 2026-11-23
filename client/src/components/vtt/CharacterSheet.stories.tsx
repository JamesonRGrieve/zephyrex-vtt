// SPDX-License-Identifier: AGPL-3.0-or-later
/** The character sheet (@zephyrex/vtt-play's CharacterSheet), read-only, on a story's own sheet. */
import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, within } from 'storybook/test';
import { CharacterSheet } from '../../../packages/vtt-play/src/sheet/CharacterSheet';
import { StoryClient, type Routes } from './StoryClient';

const SHEET = {
  sheet: {
    person_id: 'brann',
    name: 'Brann Holt',
    system: 'srd-5e',
    has_sheet: true,
    characteristics: [
      { trait_id: 'str', slug: 'strength', name: 'Strength', kind: 'characteristic', value: 16 },
      { trait_id: 'dex', slug: 'dexterity', name: 'Dexterity', kind: 'characteristic', value: 14 },
      { trait_id: 'con', slug: 'constitution', name: 'Constitution', kind: 'characteristic', value: 13 },
    ],
    skills: [
      { trait_id: 'ath', slug: 'athletics', name: 'Athletics', kind: 'skill', rank: 1 },
      { trait_id: 'ste', slug: 'stealth', name: 'Stealth', kind: 'skill', rank: 2 },
    ],
    resources: [{ trait_id: 'hp', slug: 'hit-points', name: 'Hit Points', kind: 'resource', value: 12 }],
    origins: [{ trait_id: 'sol', slug: 'soldier', name: 'Soldier', kind: 'background' }],
    abilities: [{ trait_id: 'sw', slug: 'second-wind', name: 'Second Wind', kind: 'class-feature' }],
    gear: [{ id: 'g1', item_id: 'i1', name: 'Longsword', quantity: 1 }],
  },
};
const WITH_SHEET: Routes = { 'POST /v1/dice/sheet': SHEET };
const NO_SHEET: Routes = {
  'POST /v1/dice/sheet': { sheet: { ...SHEET.sheet, has_sheet: false, characteristics: [], skills: [] } },
};

function Sheet({ routes }: { routes: Routes }) {
  return (
    <StoryClient routes={routes}>
      <CharacterSheet personId='brann' />
    </StoryClient>
  );
}

const meta: Meta<typeof Sheet> = { title: 'VTT/Character sheet', component: Sheet, args: { routes: WITH_SHEET } };
export default meta;
type Story = StoryObj<typeof Sheet>;

/** A 5e fighter: abilities, skills (Expertise as rank 2), hit points, background, a feature and gear. */
export const Fighter: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const abilities = await canvas.findByRole('region', { name: 'Characteristics' });
    await expect(within(abilities).getByText('16')).toBeInTheDocument();
    await expect(canvas.getByText('Soldier')).toBeInTheDocument();
    await expect(canvas.getByText('Longsword')).toBeInTheDocument();
  },
};

/** A character with no sheet yet says so. */
export const NoSheetYet: Story = {
  args: { routes: NO_SHEET },
  play: async ({ canvasElement }) => {
    await expect(await within(canvasElement).findByText(/no character sheet|no sheet/i)).toBeInTheDocument();
  },
};
