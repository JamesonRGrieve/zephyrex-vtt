// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const post = vi.fn();
const client = { post };
vi.mock('zephyrex', () => ({
  useClient: () => client,
  writeProblem: async (write: Promise<unknown>, fallback: string) =>
    write.then(
      () => null,
      () => fallback,
    ),
}));

const { AbilityScores, remaining } = await import('./AbilityScores');

const SIX = ['strength', 'dexterity', 'constitution', 'intelligence', 'wisdom', 'charisma'];
const NAMES = ['Strength', 'Dexterity', 'Constitution', 'Intelligence', 'Wisdom', 'Charisma'];

function options(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    builder: {
      person_id: 'p1',
      system: 'srd-5e',
      gm: false,
      abilities: SIX.map((slug, index) => ({
        slug,
        name: NAMES[index],
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
      ...over,
    },
  };
}

// A block body: a function returned from beforeEach is a cleanup hook vitest would call.
beforeEach(() => {
  post.mockReset();
});

describe('remaining', () => {
  it('takes each chosen value out once', () => {
    expect(remaining([15, 14, 13, 12, 10, 8], [14, undefined, 8])).toEqual([15, 13, 12, 10]);
    expect(remaining([12, 12, 9], [12])).toEqual([12, 9]);
  });
});

describe('the ability score step', () => {
  it('assigns the standard array, each value once, and saves', async () => {
    post.mockResolvedValueOnce(options());
    post.mockResolvedValueOnce(options({ can_set: false }));
    const done = vi.fn();
    render(<AbilityScores personId='p1' onDone={done} />);
    const values = [15, 14, 13, 12, 10, 8];
    for (const [index, name] of NAMES.entries()) {
      await userEvent.selectOptions(await screen.findByLabelText(name), String(values[index]));
    }
    expect(
      within(screen.getByLabelText('Charisma'))
        .getAllByRole('option')
        .map((one) => one.textContent),
    ).toEqual(['–', '8']);
    await userEvent.click(screen.getByRole('button', { name: 'Save scores' }));
    expect(post).toHaveBeenLastCalledWith('/v1/builder/abilities', {
      abilities: {
        person_id: 'p1',
        method: 'standard_array',
        scores: Object.fromEntries(SIX.map((slug, index) => [slug, values[index]])),
      },
    });
    expect(done).toHaveBeenCalled();
  });

  it('counts point buy against the pool', async () => {
    post.mockResolvedValueOnce(options());
    render(<AbilityScores personId='p1' />);
    await userEvent.click(await screen.findByRole('radio', { name: 'Point buy' }));
    await userEvent.selectOptions(screen.getByLabelText('Strength'), '15');
    await userEvent.selectOptions(screen.getByLabelText('Dexterity'), '14');
    expect(screen.getByText('Points spent: 16 of 27')).toBeInTheDocument();
  });

  it('rolls on the server and assigns the kept roll', async () => {
    post.mockResolvedValueOnce(options());
    post.mockResolvedValueOnce({ scores: [16, 12, 11, 9, 14, 7], dice: [[6, 5, 5, 1]], used: false });
    render(<AbilityScores personId='p1' />);
    await userEvent.click(await screen.findByRole('radio', { name: 'Roll' }));
    await userEvent.click(screen.getByRole('button', { name: /Roll 4d6, keep 3 × 6/ }));
    expect(post).toHaveBeenLastCalledWith('/v1/builder/ability-roll', { roll: { person_id: 'p1' } });
    expect(await screen.findByText('Rolled: 16, 12, 11, 9, 14, 7')).toBeInTheDocument();
    expect(within(screen.getByLabelText('Strength')).getAllByRole('option')).toHaveLength(7);
  });

  it('shows set scores read-only, and says when saving is refused', async () => {
    post.mockResolvedValueOnce(
      options({
        can_set: false,
        abilities: SIX.map((slug, index) => ({
          slug,
          name: NAMES[index],
          short: slug.slice(0, 3).toUpperCase(),
          score: 10 + index,
        })),
      }),
    );
    const { unmount } = render(<AbilityScores personId='p1' />);
    expect(await screen.findByText('STR')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Save scores' })).toBeNull();
    unmount();
    post.mockResolvedValueOnce(options());
    post.mockRejectedValueOnce(new Error('422'));
    render(<AbilityScores personId='p1' />);
    for (const [index, name] of NAMES.entries()) {
      await userEvent.selectOptions(await screen.findByLabelText(name), String([15, 14, 13, 12, 10, 8][index]));
    }
    await userEvent.click(screen.getByRole('button', { name: 'Save scores' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The scores weren’t saved');
  });
});
