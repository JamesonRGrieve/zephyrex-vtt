// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const list = vi.fn();
const post = vi.fn();
const remove = vi.fn();
const client = { list, post, delete: remove };
let user: { data?: { id: string }; error?: Error } = { data: { id: 'gm' } };
vi.mock('zephyrex', () => ({
  useClient: () => client,
  useUser: () => user,
  writeProblem: async (write: Promise<unknown>, fallback: string) =>
    write.then(
      () => null,
      () => fallback,
    ),
}));

const { SeatList } = await import('./SeatList');

const TABLE = { id: 't1', conversation_id: 'c1', campaign_id: 'camp', created_by_user_id: 'gm' };
const SEATS = [
  { id: 's1', person_id: 'osk', name: 'Osk Halleran', controller_id: 'ada', updated_at: '2026-11-21T10:00:00Z' },
  { id: 's2', person_id: 'vell', name: 'Captain Vell', controller_id: null, updated_at: '2026-11-21T10:00:00Z' },
];
const PEOPLE = [
  { id: 'osk', name: 'Osk Halleran', user_id: 'ada' },
  { id: 'vell', name: 'Captain Vell', user_id: null },
  { id: 'wren', name: 'Wren Saltash', user_id: 'bram' },
  { id: 'rook', name: 'Dannic Rook', user_id: null },
];

function serve(seats = SEATS): void {
  list.mockImplementation((path: string) =>
    Promise.resolve(path === '/v1/table' ? [TABLE] : path === '/v1/table_seat' ? seats : PEOPLE),
  );
}

beforeEach(() => {
  list.mockReset();
  post.mockReset().mockResolvedValue({});
  remove.mockReset().mockResolvedValue({});
  user = { data: { id: 'gm' } };
});

describe('the seat list', () => {
  it('shows who sits where, linking each character to its wiki page', async () => {
    serve();
    render(<SeatList conversationId='c1' personHref={(id) => `/w/voidship/person/${id}`} />);
    const osk = await screen.findByRole('link', { name: 'Osk Halleran' });
    expect(osk).toHaveAttribute('href', '/w/voidship/person/osk');
    expect(within(osk.closest('li')!).getByText('Player')).toBeInTheDocument();
    expect(within(screen.getByRole('link', { name: 'Captain Vell' }).closest('li')!).getByText('NPC')).toBeInTheDocument();
  });

  it('lets the host seat any unseated character, an NPC as an NPC, and clear a seat', async () => {
    serve();
    render(<SeatList conversationId='c1' />);
    await userEvent.click(await screen.findByRole('button', { name: 'Dannic Rook (NPC)' }));
    expect(post).toHaveBeenCalledWith('/v1/table_seat', {
      table_seat: { conversation_id: 'c1', person_id: 'rook', npc: true },
    });
    await userEvent.click(screen.getByRole('button', { name: 'Clear Captain Vell seat' }));
    expect(remove).toHaveBeenCalledWith('/v1/table_seat/s2', expect.objectContaining({ updated_at: SEATS[1]!.updated_at }));
  });

  it('lets a player take a seat only with their own character, clear only their own, and whisper', async () => {
    user = { data: { id: 'ada' } };
    serve();
    post.mockResolvedValue({ table_whisper: { id: 'w1', conversation_id: 'whisper-1' } });
    const opened = vi.fn();
    render(<SeatList conversationId='c1' onWhisper={opened} />);
    await screen.findByText('You');
    expect(screen.queryByRole('button', { name: /Wren Saltash|Dannic Rook/ })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Clear Captain Vell seat' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Clear Osk Halleran seat' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Whisper' }));
    expect(post).toHaveBeenCalledWith('/v1/table_whisper', {
      table_whisper: { table_conversation_id: 'c1', from_seat_id: 's1', to_seat_id: 's2' },
    });
    await waitFor(() => expect(opened).toHaveBeenCalledWith('whisper-1'));
  });

  it('says when no one is seated, and what failed to load', async () => {
    serve([]);
    const { unmount } = render(<SeatList conversationId='c1' />);
    expect(await screen.findByText('No one is seated yet.')).toBeInTheDocument();
    unmount();
    list.mockRejectedValue(new Error('down'));
    render(<SeatList conversationId='c1' />);
    expect(await screen.findByRole('button', { name: /try again/i })).toBeInTheDocument();
  });

  it('reports a seat the server refused', async () => {
    serve();
    post.mockRejectedValue(new Error('403'));
    render(<SeatList conversationId='c1' />);
    await userEvent.click(await screen.findByRole('button', { name: 'Wren Saltash' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Wren Saltash was not seated');
  });
});
