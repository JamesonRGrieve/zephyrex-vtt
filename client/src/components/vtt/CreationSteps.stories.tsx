// SPDX-License-Identifier: AGPL-3.0-or-later
/** Character creation by the pack's steps: CreationChoices (class, background, species) and AbilityScores. */
import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, userEvent, within } from 'storybook/test';
import { AbilityScores } from '../../../packages/vtt-play/src/builder/AbilityScores';
import { CreationChoices } from '../../../packages/vtt-play/src/builder/CreationChoices';
import { StoryClient, type Routes } from './StoryClient';

const SIX = ['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma'];
const OPTIONS = {
  builder: {
    person_id: 'p1',
    system: 'srd-5e',
    gm: false,
    abilities: SIX.map((slug) => ({
      slug,
      name: slug.charAt(0).toUpperCase() + slug.slice(1),
      short: slug.slice(0, 3).toUpperCase(),
      score: null,
    })),
    methods: {
      standard_array: [15, 14, 13, 12, 10, 8],
      point_buy: { pool: 27, costs: { 8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9 } },
      roll: { formula: '4d6kh3', count: 6 },
    },
    rolled: null,
    can_set: true,
  },
};
const FIGHTER = { trait_id: 't1', name: 'Fighter', description: 'A master of martial combat.' };
const WIZARD = { trait_id: 't2', name: 'Wizard', description: 'A scholar of arcane magic.' };
function steps(chosen: typeof FIGHTER | null) {
  return {
    builder: {
      person_id: 'p1',
      system: 'srd-5e',
      gm: false,
      steps: [
        { step: 1, name: 'Choose a Class', choices: [{ kind: 'class', chosen, options: [FIGHTER, WIZARD] }] },
        {
          step: 2,
          name: 'Character Origin',
          choices: [
            { kind: 'background', chosen: null, options: [{ trait_id: 'b1', name: 'Soldier', description: null }] },
            { kind: 'species', chosen: null, options: [{ trait_id: 's1', name: 'Human', description: null }] },
          ],
        },
        { step: 3, name: 'Ability Scores', choices: [] },
      ],
    },
  };
}
const ROUTES: Routes = {
  'POST /v1/builder/options': OPTIONS,
  'POST /v1/builder/abilities': OPTIONS,
  'POST /v1/builder/choices': steps(null),
  'POST /v1/builder/choose': steps(FIGHTER),
};

function Creation() {
  return (
    <StoryClient routes={ROUTES}>
      <div className='space-y-6'>
        <CreationChoices personId='p1' />
        <AbilityScores personId='p1' />
      </div>
    </StoryClient>
  );
}

const meta: Meta<typeof Creation> = { title: 'VTT/Character creation', component: Creation };
export default meta;
type Story = StoryObj<typeof Creation>;

/** The SRD's steps: choose a class, then place the standard array. */
export const FifthEdition: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(await canvas.findByText('1. Choose a Class')).toBeInTheDocument();
    await userEvent.selectOptions(canvas.getByLabelText('Class'), 't1');
    await expect(await canvas.findByText('Fighter')).toBeInTheDocument();
    await expect(await canvas.findByLabelText('Strength')).toBeInTheDocument();
  },
};
