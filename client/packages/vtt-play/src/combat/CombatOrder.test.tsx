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
vi.mock('@zephyrex/rooms', () => ({ useRoom: () => 'live' }));

const { CombatOrder } = await import('./CombatOrder');

function order(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: 'e1',
    name: 'Ambush',
    status: 'running',
    round: 2,
    current_combatant_id: 'c2',
    gm: true,
    combatants: [
      { id: 'c1', name: 'Cultist', initiative: 14, is_defeated: false, is_hidden: false, controlled: true },
      { id: 'c2', name: 'Rhia', initiative: 9, is_defeated: false, is_hidden: false, controlled: true },
      { id: 'c3', name: 'Osk', initiative: 6, is_defeated: true, is_hidden: false, controlled: true },
    ],
    unrolled: [],
    ...over,
  };
}

// A block body: a function returned from beforeEach is a cleanup hook vitest would call.
beforeEach(() => {
  post.mockReset();
});

describe('the combat order', () => {
  it('shows the round, the order and whose turn it is', async () => {
    post.mockResolvedValue({ encounter: order() });
    render(<CombatOrder campaignId='k1' />);
    expect(await screen.findByText('Round 2')).toBeInTheDocument();
    const rows = screen.getAllByRole('listitem');
    expect(rows.map((row) => row.textContent)).toEqual(['14Cultist', '9Rhia, acting now', '6Osk']);
    expect(rows[1]).toHaveAttribute('aria-current', 'step');
    expect(post).toHaveBeenCalledWith('/v1/encounter/current', { current: { campaign_id: 'k1' } });
  });

  it('says when there is no fight', async () => {
    post.mockResolvedValue({ encounter: null });
    render(<CombatOrder campaignId='k1' />);
    expect(await screen.findByText('No fight in progress.')).toBeInTheDocument();
  });

  it('lets the GM pass the turn, and shows the new order', async () => {
    post.mockResolvedValueOnce({ encounter: order() });
    post.mockResolvedValueOnce({ encounter: order({ round: 3, current_combatant_id: 'c1' }) });
    render(<CombatOrder campaignId='k1' />);
    await userEvent.click(await screen.findByRole('button', { name: 'Next turn' }));
    expect(post).toHaveBeenLastCalledWith('/v1/encounter/e1/next', { control: {} });
    expect(await screen.findByText('Round 3')).toBeInTheDocument();
  });

  it('gives a player no controls, and marks their own character', async () => {
    const mine = order({
      gm: false,
      combatants: [
        { id: 'c1', name: 'Cultist', initiative: 14, is_defeated: false, is_hidden: false, controlled: false },
        { id: 'c2', name: 'Rhia', initiative: 9, is_defeated: false, is_hidden: false, controlled: true },
      ],
    });
    post.mockResolvedValue({ encounter: mine });
    render(<CombatOrder campaignId='k1' />);
    expect(await screen.findByText('(you)')).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('in setup, lists who still needs initiative and says when a start is refused', async () => {
    post.mockResolvedValueOnce({
      encounter: order({
        status: 'setup',
        round: 0,
        current_combatant_id: null,
        unrolled: [{ combatant_id: 'c1', name: 'Cultist', reason: 'Cultist has no Agility to roll initiative with' }],
      }),
    });
    post.mockRejectedValueOnce(new Error('422'));
    render(<CombatOrder campaignId='k1' />);
    expect(await screen.findByText(/has no Agility/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Start' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('The fight didn’t start');
  });
});
