// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const list = vi.fn();
const get = vi.fn();
const put = vi.fn();
const client = { list, get, put };
vi.mock('zephyrex', () => ({
  useClient: () => client,
  writeProblem: async (write: Promise<unknown>, fallback: string) =>
    write.then(
      () => null,
      () => fallback,
    ),
}));

const { Loot } = await import('./Loot');

const V = { updated_at: '2026-11-21T10:00:00Z' };
const LYING = [
  { id: 'i1', item_id: 'torch', location_id: 'chapel', owner_person_id: 'wren', quantity: 1, ...V },
  { id: 'i2', item_id: 'coin', location_id: 'chapel', owner_person_id: null, quantity: 12, ...V },
];
const NAMES: Record<string, string> = { torch: 'Torch', coin: 'Silver coin' };

function serve(at: string | null): void {
  get.mockImplementation((path: string) => {
    if (path === '/v1/person/osk') return Promise.resolve({ person: { id: 'osk', location_id: at } });
    if (path === '/v1/location/chapel') return Promise.resolve({ location: { id: 'chapel', name: 'Chapel' } });
    const id = path.split('/').pop() ?? '';
    return Promise.resolve({ item: { id, name: NAMES[id] } });
  });
  list.mockResolvedValue(LYING);
}

// A block body: a function returned from beforeEach is a cleanup hook vitest would call.
beforeEach(() => {
  [list, get, put].forEach((mock) => mock.mockReset());
  put.mockResolvedValue({});
});

describe('loot', () => {
  it('lists what lies where the character stands', async () => {
    serve('chapel');
    render(<Loot personId='osk' />);
    expect(await screen.findByText('Torch')).toBeInTheDocument();
    expect(screen.getByText('×12')).toBeInTheDocument();
    expect(screen.getByText('Chapel')).toBeInTheDocument();
    expect(list).toHaveBeenCalledWith('/v1/item_instance', 'item_instances', expect.anything(), { location_id: 'chapel' });
  });

  it('takes one onto them: theirs, carried, and tells the host what was taken', async () => {
    serve('chapel');
    const taken = vi.fn();
    render(<Loot personId='osk' onTaken={taken} />);
    await screen.findByText('Torch');
    await userEvent.click(screen.getAllByRole('button', { name: 'Take' })[0]!);
    expect(taken).toHaveBeenCalledWith({ id: 'i1', item_id: 'torch', name: 'Torch', quantity: 1 });
    expect(put).toHaveBeenCalledWith(
      '/v1/item_instance/i1',
      { item_instance: { owner_person_id: 'osk', location_id: null } },
      expect.objectContaining({ id: 'i1' }),
    );
  });

  it('takes all, and says which were refused', async () => {
    serve('chapel');
    put.mockImplementation((path: string) => (path.endsWith('i1') ? Promise.reject(new Error('403')) : Promise.resolve({})));
    render(<Loot personId='osk' />);
    await screen.findByText('Torch');
    await userEvent.click(screen.getByRole('button', { name: 'Take all' }));
    expect(put).toHaveBeenCalledTimes(2);
    expect(await screen.findByRole('alert')).toHaveTextContent('Not taken: Torch');
  });

  it('says so when they are nowhere, or nothing lies here', async () => {
    serve(null);
    const { unmount } = render(<Loot personId='osk' />);
    expect(await screen.findByText('They aren’t anywhere to search.')).toBeInTheDocument();
    unmount();
    serve('chapel');
    list.mockResolvedValue([]);
    render(<Loot personId='osk' />);
    expect(await screen.findByText('Nothing lies here.')).toBeInTheDocument();
  });
});
