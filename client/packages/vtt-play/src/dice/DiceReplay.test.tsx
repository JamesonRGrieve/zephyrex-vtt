// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

vi.mock('zephyrex', () => ({ useClient: () => ({}), writeProblem: async () => null }));

const { DiceReplay, readResult } = await import('./DiceReplay');

const TEST = {
  person_id: 'p1',
  system: 'percentile-test',
  name: 'charm',
  kind: 'skill',
  skill_rank: 2,
  trained: true,
  target: 55,
  roll: 23,
  success: true,
  degrees: 4,
  natural: null,
  steps: [{ step: 'characteristic', value: 45 }],
};

describe('a replayed roll', () => {
  it('reads a result as the routes answer it, or bare', () => {
    expect(readResult({ test: TEST })?.roll).toBe(23);
    expect(readResult(TEST)?.roll).toBe(23);
    expect(readResult({ roll: { formula: '2d6', total: 9, terms: [] } })).toMatchObject({ formula: '2d6', total: 9 });
    expect(readResult({ nothing: true })).toBeNull();
  });

  it('shows the result card with no new roll', () => {
    render(<DiceReplay result={{ test: TEST }} />);
    expect(screen.getByRole('status')).toHaveTextContent('Success: rolled 23 against 55, 4 degrees of success');
  });

  it('says when it isn’t a roll', () => {
    render(<DiceReplay result={{ nothing: true }} />);
    expect(screen.getByText('Not a roll this tray can show.')).toBeInTheDocument();
  });
});
