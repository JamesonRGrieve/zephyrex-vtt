// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen } from '@testing-library/react';
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

const { CreationChoices } = await import('./CreationChoices');

const FIGHTER = { trait_id: 't1', name: 'Fighter', description: null };
const WIZARD = { trait_id: 't2', name: 'Wizard', description: null };

function steps(classChosen: typeof FIGHTER | null = null, gm = false): Record<string, unknown> {
  return {
    builder: {
      person_id: 'p1',
      system: 'srd-5e',
      gm,
      steps: [
        { step: 1, name: 'Choose a Class', choices: [{ kind: 'class', chosen: classChosen, options: [FIGHTER, WIZARD] }] },
        {
          step: 2,
          name: 'Character Origin',
          choices: [
            { kind: 'background', chosen: null, options: [{ trait_id: 'b1', name: 'Soldier', description: null }] },
            { kind: 'species', chosen: null, options: [] },
          ],
        },
        { step: 3, name: 'Ability Scores', choices: [] },
      ],
    },
  };
}

// A block body: a function returned from beforeEach is a cleanup hook vitest would call.
beforeEach(() => {
  post.mockReset();
});

describe('creation choices', () => {
  it('lists the pack’s steps and records a pick', async () => {
    post.mockResolvedValueOnce(steps());
    post.mockResolvedValueOnce(steps(FIGHTER));
    const changed = vi.fn();
    render(<CreationChoices personId='p1' onChange={changed} />);
    expect(await screen.findByText('1. Choose a Class')).toBeInTheDocument();
    expect(screen.getByText('3. Ability Scores')).toBeInTheDocument();
    expect(screen.getByText('This campaign offers no species yet.')).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText('Class'), 't1');
    expect(post).toHaveBeenLastCalledWith('/v1/builder/choose', {
      choose: { person_id: 'p1', kind: 'class', trait_id: 't1' },
    });
    expect(await screen.findByText('Fighter')).toBeInTheDocument();
    expect(changed).toHaveBeenCalled();
  });

  it('shows a player’s pick as made, and lets the GM change it', async () => {
    post.mockResolvedValueOnce(steps(FIGHTER, true));
    render(<CreationChoices personId='p1' />);
    const select = await screen.findByLabelText('Class');
    expect(select).toHaveValue('t1');
  });

  it('says when a pick is refused', async () => {
    post.mockResolvedValueOnce(steps());
    post.mockRejectedValueOnce(new Error('422'));
    render(<CreationChoices personId='p1' />);
    await userEvent.selectOptions(await screen.findByLabelText('Class'), 't2');
    expect(await screen.findByRole('alert')).toHaveTextContent('The class wasn’t recorded');
  });
});
