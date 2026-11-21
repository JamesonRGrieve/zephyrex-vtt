// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const list = vi.fn();
const get = vi.fn();
const put = vi.fn();
const remove = vi.fn();
const client = { list, get, put, delete: remove };
vi.mock('zephyrex', () => ({
  useClient: () => client,
  writeProblem: async (write: Promise<unknown>, fallback: string) =>
    write.then(
      () => null,
      () => fallback,
    ),
}));

const { Inventory } = await import('./Inventory');

const V = { updated_at: '2026-11-21T10:00:00Z' };
const INSTANCES = [
  { id: 'i1', item_id: 'flamer', location_id: null, owner_person_id: 'osk', quantity: 1, ...V },
  { id: 'i2', item_id: '[redacted]', location_id: 'belt', owner_person_id: 'osk', quantity: 3, ...V },
  { id: 'i3', item_id: 'crate', location_id: 'hold', owner_person_id: 'osk', quantity: 1, ...V },
];

function serve(): void {
  get.mockImplementation((path: string) =>
    Promise.resolve(
      path === '/v1/person/osk'
        ? { person: { id: 'osk', campaign_id: 'c1', location_id: 'chapel' } }
        : {
            item: {
              id: path.split('/').pop(),
              name: { flamer: '[redacted]', [redacted]: '[redacted]', crate: 'Crate' }[path.split('/').pop() ?? ''],
            },
          },
    ),
  );
  list.mockImplementation((path: string) =>
    Promise.resolve(
      path === '/v1/item_instance'
        ? INSTANCES
        : path === '/v1/location'
          ? [{ id: 'belt' }]
          : [
              { id: 'osk', name: 'Osk' },
              { id: 'wren', name: 'Wren' },
            ],
    ),
  );
}

// A block body: a function returned from beforeEach is a cleanup hook vitest would call.
beforeEach(() => {
  [list, get, put, remove].forEach((mock) => mock.mockReset());
  put.mockResolvedValue({});
  remove.mockResolvedValue({});
  serve();
});

describe('the inventory', () => {
  it('shows what they carry (on them or in their slots), not what they left elsewhere', async () => {
    render(<Inventory personId='osk' />);
    expect(await screen.findByText('[redacted]')).toBeInTheDocument();
    expect(screen.getByText('[redacted]')).toBeInTheDocument();
    expect(screen.getByText('×3')).toBeInTheDocument();
    expect(screen.queryByText('Crate')).toBeNull();
  });

  it('uses one of several, and the last one is gone', async () => {
    render(<Inventory personId='osk' />);
    await screen.findByText('[redacted]');
    const [flamerUse, [redacted]Use] = screen.getAllByRole('button', { name: 'Use' });
    await userEvent.click([redacted]Use!);
    expect(put).toHaveBeenCalledWith(
      '/v1/item_instance/i2',
      { item_instance: { quantity: 2 } },
      expect.objectContaining({ id: 'i2' }),
    );
    await userEvent.click(flamerUse!);
    expect(remove).toHaveBeenCalledWith('/v1/item_instance/i1', expect.objectContaining({ id: 'i1' }));
  });

  it('drops where they stand and gives to another character, on them', async () => {
    render(<Inventory personId='osk' />);
    await screen.findByText('[redacted]');
    await userEvent.click(screen.getAllByRole('button', { name: 'Drop' })[0]!);
    expect(put).toHaveBeenCalledWith(
      '/v1/item_instance/i1',
      { item_instance: { location_id: 'chapel' } },
      expect.anything(),
    );
    await userEvent.selectOptions(screen.getByRole('combobox', { name: 'Give [redacted] to' }), 'wren');
    expect(put).toHaveBeenCalledWith(
      '/v1/item_instance/i2',
      { item_instance: { owner_person_id: 'wren', location_id: null } },
      expect.anything(),
    );
  });

  it('says when a write was refused', async () => {
    put.mockRejectedValue(new Error('403'));
    render(<Inventory personId='osk' />);
    await screen.findByText('[redacted]');
    await userEvent.click(screen.getAllByRole('button', { name: 'Use' })[1]!);
    expect(await screen.findByRole('alert')).toHaveTextContent("[redacted] wasn't used");
  });
});
