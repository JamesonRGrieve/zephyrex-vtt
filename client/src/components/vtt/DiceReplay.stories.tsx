// SPDX-License-Identifier: AGPL-3.0-or-later
/** A decided roll shown again (@zephyrex/vtt-play's DiceReplay): a table line's dice, with no server. */
import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, within } from 'storybook/test';
import { DiceReplay } from '../../../packages/vtt-play/src/dice/DiceReplay';

const meta: Meta<typeof DiceReplay> = {
  title: 'VTT/Dice replay',
  component: DiceReplay,
  args: {
    seed: 7,
    result: {
      person_id: 'brann',
      system: 'srd-5e',
      name: 'athletics',
      kind: 'skill',
      skill_rank: 1,
      trained: true,
      target: 15,
      roll: 17,
      success: true,
      degrees: 0,
      natural: null,
      test_kind: 'd20-over',
      total: 20,
      rolls: [17],
      steps: [{ step: 'ability_modifier', value: 3 }],
    },
  },
};
export default meta;
type Story = StoryObj<typeof DiceReplay>;

/** A 5e Athletics check, shown as its result card. */
export const AthleticsCheck: Story = {
  play: async ({ canvasElement }) => {
    const card = within(canvasElement).getByRole('status');
    await expect(card).toHaveTextContent('Success');
    await expect(card).toHaveTextContent('against DC 15');
  },
};

/** Something that isn't a roll says so, rather than drawing nothing. */
export const NotARoll: Story = {
  args: { result: { hello: 'world' } },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByText('Not a roll this tray can show.')).toBeInTheDocument();
  },
};
