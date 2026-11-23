// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The dice tray (@zephyrex/vtt-play's DiceTrayView) with a story's own tray state in place of the
 * server: a 5e character's tests with Advantage, the dice rack, the result card and the history.
 * Rolls here are the story's, never a real one; the server rolls in the app.
 */
import type { Meta, StoryObj } from '@storybook/nextjs';
import { useState, type ReactNode } from 'react';
import { expect, userEvent, within } from 'storybook/test';
import { DiceTrayView, type DiceTrayState } from '../../../packages/vtt-play/src/dice/DiceTray';
import type { RollResult, TestOptions, TestResult } from '../../../packages/vtt-play/src/dice/schemas';

const OPTIONS: TestOptions = {
  person_id: 'brann',
  system: 'srd-5e',
  characteristics: [
    { slug: 'strength', name: 'Strength', short: 'STR', untrainable: false, specialisations: [] },
    { slug: 'dexterity', name: 'Dexterity', short: 'DEX', untrainable: false, specialisations: [] },
  ],
  skills: [{ slug: 'athletics', name: 'Athletics', characteristic: 'strength', untrainable: false, specialisations: [] }],
  difficulties: [
    { slug: 'easy', modifier: 0, dc: 10 },
    { slug: 'medium', modifier: 0, dc: 15 },
    { slug: 'hard', modifier: 0, dc: 20 },
  ],
  default_difficulty: 'medium',
  has_sheet: true,
  test_kind: 'd20-over',
};

/** A stand-in for useDiceTray: the same state, with rolls made up by the story. */
function useStoryTray(withPack: boolean): DiceTrayState {
  const [result, setResult] = useState<TestResult | RollResult | null>(null);
  const [history, setHistory] = useState<(TestResult | RollResult)[]>([]);
  const show = (next: TestResult | RollResult): void => {
    setResult(next);
    setHistory((past) => [next, ...past].slice(0, 10));
  };
  return {
    options: withPack ? { state: 'ready', options: OPTIONS } : { state: 'formula-only', reason: 'no-pack' },
    retry: async () => {},
    result,
    history,
    seed: 7,
    problem: null,
    busy: false,
    test: async (input) => {
      const rolls = input.advantage ? [6, 17] : [14];
      const roll = input.advantage === 'disadvantage' ? Math.min(...rolls) : Math.max(...rolls);
      show({
        person_id: 'brann',
        system: 'srd-5e',
        name: input.name,
        specialisation: null,
        kind: 'characteristic',
        skill_rank: null,
        trained: true,
        target: 15,
        roll,
        success: roll + 3 >= 15,
        degrees: 0,
        natural: null,
        steps: [
          { step: 'ability_modifier', value: 3 },
          { step: 'dc', value: 15 },
        ],
        test_kind: 'd20-over',
        total: roll + 3,
        no_sheet: false,
        advantage: input.advantage ?? null,
        rolls,
      });
    },
    roll: async (formula) => {
      show({
        formula,
        total: 11,
        terms: [
          {
            notation: '2d6',
            value: 8,
            dice: [
              { value: 5, kept: true },
              { value: 3, kept: true },
            ],
          },
        ],
      });
    },
  };
}

function Tray({ withPack }: { withPack: boolean }): ReactNode {
  return (
    <div className='mx-auto max-w-md p-4'>
      <DiceTrayView tray={useStoryTray(withPack)} />
    </div>
  );
}

const meta: Meta<typeof Tray> = {
  title: 'VTT/Dice tray',
  component: Tray,
  args: { withPack: true },
};
export default meta;
type Story = StoryObj<typeof Tray>;

/** A 5e character's test with Advantage: both d20s on the card, the lower struck. */
export const FifthEditionTest: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    const edge = canvas.getByRole('radiogroup', { name: 'Advantage' });
    await userEvent.click(within(edge).getByRole('radio', { name: 'Advantage' }));
    await userEvent.click(canvas.getByRole('button', { name: 'Roll the test' }));
    const card = await canvas.findByRole('status');
    await expect(card).toHaveTextContent('Success');
    await expect(card).toHaveTextContent('(Advantage)');
    await expect(canvas.getByRole('region', { name: 'Roll history' })).toHaveTextContent('strength: 20, success');
  },
};

/** No rules pack: the rack builds the roll by taps. */
export const DiceRackOnly: Story = {
  args: { withPack: false },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole('button', { name: 'Remove a d20' }));
    await userEvent.click(canvas.getByRole('button', { name: 'Add a d6' }));
    await userEvent.click(canvas.getByRole('button', { name: 'Add a d6' }));
    await userEvent.click(canvas.getByRole('button', { name: 'Raise the modifier' }));
    await userEvent.click(canvas.getByRole('button', { name: 'Roll 2d6+1' }));
    await expect(await canvas.findByRole('status')).toHaveTextContent('11 (2d6+1)');
  },
};

/** The tray at phone width: the rack's dice are 44 px targets or larger. */
export const Phone: Story = {
  globals: { viewport: { value: 'mobile1' } },
  play: async ({ canvasElement }) => {
    for (const button of within(within(canvasElement).getByRole('group', { name: 'Dice rack' })).getAllByRole('button')) {
      await expect(button.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    }
  },
};
