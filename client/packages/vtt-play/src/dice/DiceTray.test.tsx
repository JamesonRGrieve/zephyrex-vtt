// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen, waitFor, within } from '@testing-library/react';
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

const { DiceResult, DiceTray, defaultFormula, parseModifiers } = await import('./DiceTray');
const { testOptionsSchema } = await import('./schemas');

const OPTIONS = {
  options: {
    person_id: 'p1',
    system: 'percentile-test',
    characteristics: [{ slug: 'might', name: 'Might', short: 'MT' }],
    skills: [
      { slug: 'awareness', name: 'Awareness', characteristic: 'perception', untrainable: false },
      {
        slug: 'lore',
        name: 'Lore',
        characteristic: 'intelligence',
        untrainable: true,
        specialisations: ['Sea Lanes'],
      },
    ],
    difficulties: [
      { slug: 'standard', modifier: 0 },
      { slug: 'hard', modifier: -20 },
    ],
    default_difficulty: 'standard',
  },
};

const RESULT = {
  test: {
    person_id: 'p1',
    system: 'percentile-test',
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
    expect(screen.getByRole('option', { name: 'Lore (trained only)' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('radio', { name: 'Hard (-20)' }));
    await userEvent.click(screen.getByRole('button', { name: 'Roll the test' }));
    expect(post).toHaveBeenLastCalledWith('/v1/dice/test', {
      test: { person_id: 'p1', modifiers: [20], name: 'awareness', difficulty: 'hard' },
    });
    const status = await screen.findByRole('status');
    expect(status).toHaveTextContent('Success');
    expect(status).toHaveTextContent('rolled 23 against 40, 2 degrees of success');
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
    // The rack starts on the system's die (a d20 with no pack); swap it for two d6.
    await userEvent.click(screen.getByRole('button', { name: 'Remove a d20' }));
    await userEvent.click(screen.getByRole('button', { name: 'Add a d6' }));
    await userEvent.click(screen.getByRole('button', { name: 'Add a d6' }));
    await userEvent.click(screen.getByRole('button', { name: 'Roll 2d6' }));
    expect(post).toHaveBeenLastCalledWith('/v1/dice/roll', { roll: { formula: '2d6' } });
    expect(await screen.findByRole('status')).toHaveTextContent('9 (2d6)');
  });

  it('still offers the system’s tests when the character has no sheet, saying so', async () => {
    post.mockImplementation((path: string) =>
      Promise.resolve(path === '/v1/dice/test-options' ? { options: { ...OPTIONS.options, has_sheet: false } } : {}),
    );
    render(<DiceTray personId='p1' />);
    expect(await screen.findByText('No character sheet yet: tests use the rules’ average.')).toBeInTheDocument();
    expect(screen.getByLabelText('Test')).toBeInTheDocument();
  });

  it('shows a d20 check as roll + modifiers against the DC, flagged when sheetless', () => {
    render(
      <DiceResult
        result={{
          person_id: 'p1',
          system: 'srd-5e',
          name: 'stealth',
          kind: 'skill',
          skill_rank: null,
          trained: false,
          target: 15,
          roll: 12,
          success: false,
          degrees: 0,
          natural: null,
          test_kind: 'd20-over',
          total: 12,
          no_sheet: true,
          rolls: [12],
          steps: [
            { step: 'no_sheet', value: 10 },
            { step: 'ability_modifier', value: 0 },
            { step: 'dc', value: 15 },
          ],
        }}
      />,
    );
    expect(screen.getByRole('status')).toHaveTextContent('Failure');
    expect(screen.getByRole('status')).toHaveTextContent('rolled 12 + 0 = 12 against DC 15');
    expect(screen.getByText('No sheet: tested at the rules’ average.')).toBeInTheDocument();
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
    await userEvent.selectOptions(await screen.findByLabelText('Test'), 'lore');
    const which = screen.getByLabelText('Which Lore');
    expect(screen.getByRole('button', { name: 'Roll the test' })).toBeDisabled();
    expect(document.querySelector('#dice-tray-specialisations option[value="Sea Lanes"]')).not.toBeNull();
    await userEvent.type(which, 'Sea Lanes');
    await userEvent.click(screen.getByRole('button', { name: 'Roll the test' }));
    expect(post).toHaveBeenLastCalledWith('/v1/dice/test', {
      test: { person_id: 'p1', modifiers: [], name: 'lore', difficulty: 'standard', specialisation: 'Sea Lanes' },
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

  it('builds a 5e roll on the rack: a d20 with Advantage and a modifier', async () => {
    post.mockImplementation((path: string) =>
      path === '/v1/dice/test-options'
        ? Promise.reject(problem(422))
        : Promise.resolve({ roll: { formula: '2d20kh1+2', total: 19, terms: [], stats: {} } }),
    );
    render(<DiceTray personId='p1' />);
    await screen.findByText(/no rules pack yet/);
    await userEvent.click(
      within(screen.getByRole('radiogroup', { name: 'Advantage on the d20' })).getByRole('radio', { name: 'Advantage' }),
    );
    await userEvent.click(screen.getByRole('button', { name: 'Raise the modifier' }));
    await userEvent.click(screen.getByRole('button', { name: 'Raise the modifier' }));
    await userEvent.click(screen.getByRole('button', { name: 'Roll 2d20kh1+2' }));
    expect(post).toHaveBeenLastCalledWith('/v1/dice/roll', { roll: { formula: '2d20kh1+2' } });
  });

  it('sends Advantage with a 5e test and shows both d20s, the dropped one struck', async () => {
    const d20 = {
      options: {
        ...OPTIONS.options,
        test_kind: 'd20-over',
        difficulties: [{ slug: 'medium', modifier: 0, dc: 15 }],
        default_difficulty: 'medium',
      },
    };
    post.mockImplementation((path: string) =>
      path === '/v1/dice/test-options'
        ? Promise.resolve(d20)
        : Promise.resolve({
            test: {
              ...RESULT.test,
              system: 'srd-5e',
              test_kind: 'd20-over',
              roll: 17,
              total: 17,
              target: 15,
              degrees: 0,
              advantage: 'advantage',
              rolls: [4, 17],
              steps: [],
            },
          }),
    );
    render(<DiceTray personId='p1' />);
    const edge = await screen.findByRole('radiogroup', { name: 'Advantage' });
    await userEvent.click(within(edge).getByRole('radio', { name: 'Advantage' }));
    await userEvent.click(screen.getByRole('button', { name: 'Roll the test' }));
    expect(post).toHaveBeenLastCalledWith('/v1/dice/test', {
      test: { person_id: 'p1', modifiers: [], name: 'might', difficulty: 'medium', advantage: 'advantage' },
    });
    const card = await screen.findByRole('status');
    expect(card).toHaveTextContent('(Advantage)');
    expect(screen.getByRole('list', { name: 'The d20s rolled' })).toHaveTextContent('4 (dropped)17');
  });

  it('keeps the last rolls, newest first', async () => {
    let total = 0;
    post.mockImplementation((path: string) =>
      path === '/v1/dice/test-options'
        ? Promise.reject(problem(422))
        : Promise.resolve({ roll: { formula: '1d20', total: (total += 1), terms: [], stats: {} } }),
    );
    render(<DiceTray personId='p1' />);
    await screen.findByText(/no rules pack yet/);
    await userEvent.click(screen.getByRole('button', { name: 'Roll 1d20' }));
    await screen.findByText('1d20: 1');
    await userEvent.click(screen.getByRole('button', { name: 'Roll 1d20' }));
    const history = await screen.findByRole('region', { name: 'Roll history' });
    await waitFor(() => expect(history.querySelectorAll('li')).toHaveLength(2));
    expect([...history.querySelectorAll('li')].map((one) => one.textContent)).toEqual(['1d20: 2', '1d20: 1']);
  });

  it('starts the free roll on the system’s die: a d20 for 5e or no pack, a d100 for the percentile packs', () => {
    expect(defaultFormula(null)).toBe('1d20');
    expect(defaultFormula(testOptionsSchema.parse({ options: { ...OPTIONS.options, test_kind: 'd20-over' } }).options)).toBe(
      '1d20',
    );
    expect(
      defaultFormula(testOptionsSchema.parse({ options: { ...OPTIONS.options, test_kind: 'd100-under' } }).options),
    ).toBe('1d100');
  });
});
