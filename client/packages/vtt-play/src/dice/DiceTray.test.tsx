// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const post = vi.fn();
const client = { post };
vi.mock('zephyrex', () => ({
  useClient: () => client,
  writeProblem: async (write: Promise<void>, fallback: string) =>
    write.then(
      () => null,
      () => fallback,
    ),
}));

const { DiceTray, parseModifiers } = await import('./DiceTray');

const OPTIONS = {
  options: {
    person_id: 'p1',
    system: 'redacted',
    characteristics: [{ slug: '[redacted]', name: '[redacted]', short: 'WS' }],
    skills: [
      { slug: 'awareness', name: 'Awareness', characteristic: 'perception', untrainable: false },
      {
        slug: '[redacted]',
        name: '[redacted]',
        characteristic: 'intelligence',
        untrainable: true,
        specialisations: ['[redacted]'],
      },
    ],
    difficulties: [
      { slug: 'challenging', modifier: 0 },
      { slug: 'hard', modifier: -20 },
    ],
    default_difficulty: 'challenging',
  },
};

const RESULT = {
  test: {
    person_id: 'p1',
    system: 'redacted',
    name: 'Awareness',
    kind: 'skill',
    skill_rank: 1,
    trained: true,
    target: 40,
    roll: 23,
    success: true,
    degrees: 2,
    natural: null,
    steps: [
      { step: 'characteristic', value: 40 },
      { step: 'difficulty', value: -20 },
      { step: 'modifier', value: 20 },
    ],
  },
};

function problem(status: number): Error {
  return Object.assign(new Error(`status ${status}`), { status });
}

// A block body: a function returned from beforeEach is a cleanup hook vitest would call.
beforeEach(() => {
  post.mockReset();
});

describe('modifiers typed as text', () => {
  it('reads signed whole numbers separated by commas or spaces', () => {
    expect(parseModifiers('+10, -20 5')).toEqual([10, -20, 5]);
    expect(parseModifiers('')).toEqual([]);
    expect(parseModifiers('+10, a lot')).toBeNull();
    expect(parseModifiers('2.5')).toBeNull();
  });
});

describe('the dice tray', () => {
  it('rolls a prefilled test with the chosen difficulty and shows how the target was reached', async () => {
    post.mockImplementation((path: string) => Promise.resolve(path === '/v1/dice/test-options' ? OPTIONS : RESULT));
    render(<DiceTray personId='p1' prefill={{ name: 'awareness', modifiers: [20] }} />);
    expect(await screen.findByLabelText('Test')).toHaveValue('awareness');
    expect(screen.getByRole('option', { name: '[redacted] (trained only)' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Hard (-20)' }));
    await userEvent.click(screen.getByRole('button', { name: 'Roll the test' }));
    expect(post).toHaveBeenLastCalledWith('/v1/dice/test', {
      test: { person_id: 'p1', modifiers: [20], name: 'awareness', difficulty: 'hard' },
    });
    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent('Success: rolled 23 against 40, 2 degrees of success');
    expect(status).toHaveTextContent('difficulty: -20');
  });

  it('offers formulas only when the campaign has no rules pack', async () => {
    post.mockImplementation((path: string) =>
      path === '/v1/dice/test-options'
        ? Promise.reject(problem(422))
        : Promise.resolve({ roll: { formula: '2d6', total: 9, terms: [], stats: {} } }),
    );
    render(<DiceTray personId='p1' />);
    expect(await screen.findByText(/no rules pack yet/)).toBeInTheDocument();
    expect(screen.queryByLabelText('Test')).toBeNull();
    const dice = screen.getByLabelText('Dice');
    await userEvent.clear(dice);
    await userEvent.type(dice, '2d6');
    await userEvent.click(screen.getByRole('button', { name: 'Roll' }));
    expect(await screen.findByRole('status')).toHaveTextContent('9 (2d6)');
  });

  it('offers formulas only, saying so, when the character has no sheet yet', async () => {
    post.mockImplementation((path: string) =>
      Promise.resolve(path === '/v1/dice/test-options' ? { options: { ...OPTIONS.options, has_sheet: false } } : {}),
    );
    render(<DiceTray personId='p1' />);
    expect(await screen.findByText('No character sheet yet: roll a formula')).toBeInTheDocument();
    expect(screen.queryByLabelText('Test')).toBeNull();
    expect(screen.getByLabelText('Dice')).toBeInTheDocument();
  });

  it('offers formulas only when the character can’t be read (404), not an error', async () => {
    post.mockRejectedValueOnce(problem(404));
    render(<DiceTray personId='p1' />);
    expect(await screen.findByText('No character sheet yet: roll a formula')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /try again/i })).toBeNull();
  });

  it('says what failed to load, with a way to try again', async () => {
    post.mockRejectedValueOnce(problem(500)).mockResolvedValueOnce(OPTIONS);
    render(<DiceTray personId='p1' />);
    await userEvent.click(await screen.findByRole('button', { name: /try again/i }));
    await waitFor(() => expect(screen.getByLabelText('Test')).toBeInTheDocument());
  });

  it('asks which specialisation of a specialist skill, offering the character’s own', async () => {
    post.mockImplementation((path: string) => Promise.resolve(path === '/v1/dice/test-options' ? OPTIONS : RESULT));
    render(<DiceTray personId='p1' />);
    await userEvent.selectOptions(await screen.findByLabelText('Test'), '[redacted]');
    const which = screen.getByLabelText('Which [redacted]');
    expect(screen.getByRole('button', { name: 'Roll the test' })).toBeDisabled();
    expect(document.querySelector('#dice-tray-specialisations option[value="[redacted]"]')).not.toBeNull();
    await userEvent.type(which, '[redacted]');
    await userEvent.click(screen.getByRole('button', { name: 'Roll the test' }));
    expect(post).toHaveBeenLastCalledWith('/v1/dice/test', {
      test: { person_id: 'p1', modifiers: [], name: '[redacted]', difficulty: 'challenging', specialisation: '[redacted]' },
    });
  });

  it('keeps the device’s dice animation setting', async () => {
    post.mockResolvedValue(OPTIONS);
    window.localStorage.clear();
    const { unmount } = render(<DiceTray personId='p1' />);
    const toggle = await screen.findByRole('checkbox', { name: 'Animate dice' });
    expect(toggle).toBeChecked();
    await userEvent.click(toggle);
    expect(toggle).not.toBeChecked();
    expect(window.localStorage.getItem('zephyrex-vtt:dice-animation')).toBe('off');
    unmount();
    render(<DiceTray personId='p1' />);
    expect(await screen.findByRole('checkbox', { name: 'Animate dice' })).not.toBeChecked();
  });

  it('refuses modifiers that are not whole numbers', async () => {
    post.mockResolvedValue(OPTIONS);
    render(<DiceTray personId='p1' />);
    await userEvent.type(await screen.findByLabelText('Other modifiers'), 'lots');
    expect(screen.getByRole('button', { name: 'Roll the test' })).toBeDisabled();
    expect(screen.getByText('Whole numbers only, separated by commas.')).toBeInTheDocument();
  });
});
