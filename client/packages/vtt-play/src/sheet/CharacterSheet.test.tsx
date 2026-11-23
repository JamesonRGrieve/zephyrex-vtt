// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const post = vi.fn();
const client = { post };
vi.mock('zephyrex', () => ({ useClient: () => client }));

const { CharacterSheet } = await import('./CharacterSheet');

function problem(status: number): Error {
  return Object.assign(new Error(`status ${status}`), { status });
}

const SHEET = {
  sheet: {
    person_id: 'osk',
    name: 'Osk Halleran',
    system: 'percentile-test',
    has_sheet: true,
    characteristics: [
      { trait_id: 'ne', slug: 'nerve', name: 'Nerve', kind: 'characteristic', value: 45 },
      { trait_id: 'wp', slug: 'willpower', name: 'Willpower', kind: 'characteristic', value: 40 },
    ],
    skills: [
      { trait_id: 'cl', slug: 'lore', name: 'Lore', kind: 'skill', rank: 1, specialisation: 'Old Kingdoms' },
      { trait_id: 'ch', slug: 'charm', name: 'Charm', kind: 'skill', rank: 2 },
    ],
    resources: [{ trait_id: 'w', slug: 'wounds', name: 'Wounds', kind: 'resource', value: 10 }],
    origins: [{ trait_id: 'hw', slug: 'shrine-world', name: 'Shrine World', kind: 'homeworld' }],
    abilities: [
      { trait_id: 'wt', slug: 'weapon-training', name: 'Weapon Training', kind: 'talent', specialisation: 'Flame' },
    ],
    gear: [{ id: 'g1', item_id: 'i1', name: 'Torch', quantity: 1 }],
  },
};

// A block body: a function returned from beforeEach is a cleanup hook vitest would call.
beforeEach(() => {
  post.mockReset();
});

describe('the character sheet', () => {
  it('shows characteristics, tracks, skills with specialisations, origin, talents and gear', async () => {
    post.mockResolvedValue(SHEET);
    render(<CharacterSheet personId='osk' />);
    const characteristics = await screen.findByRole('region', { name: 'Characteristics' });
    expect(within(characteristics).getByText('45')).toBeInTheDocument();
    expect(screen.getByText('Lore (Old Kingdoms)')).toBeInTheDocument();
    expect(screen.getByText('Rank 2')).toBeInTheDocument();
    expect(screen.getByText('Shrine World')).toBeInTheDocument();
    expect(screen.getByText('Weapon Training (Flame)')).toBeInTheDocument();
    expect(screen.getByText('Torch')).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith('/v1/dice/sheet', { sheet: { person_id: 'osk' } });
  });

  it('says there is no sheet yet, for a sheet without characteristics or a character it can’t read', async () => {
    post.mockResolvedValueOnce({ sheet: { ...SHEET.sheet, has_sheet: false } });
    const { unmount } = render(<CharacterSheet personId='osk' />);
    expect(await screen.findByText('No character sheet yet.')).toBeInTheDocument();
    unmount();
    post.mockRejectedValueOnce(problem(404));
    render(<CharacterSheet personId='osk' />);
    expect(await screen.findByText('No character sheet yet.')).toBeInTheDocument();
  });

  it('says what failed to load otherwise', async () => {
    post.mockRejectedValueOnce(problem(500));
    render(<CharacterSheet personId='osk' />);
    expect(await screen.findByRole('button', { name: /try again/i })).toBeInTheDocument();
  });
});
