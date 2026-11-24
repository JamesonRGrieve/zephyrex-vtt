// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const post = vi.fn();
const client = { post };
vi.mock('zephyrex', () => ({ useClient: () => client }));
vi.mock('@zephyrex/rooms', () => ({ useRoom: () => 'live' }));

const { ScopeMap } = await import('./ScopeMap');

const COAST = { id: 'coast', name: 'The Salt Coast', kind: 'region', picture: null };
const TOWN = { id: 'saltmere', name: 'Saltmere', kind: 'city', picture: null };
const HOUSE = { id: 'halloway', name: 'Halloway house', kind: 'building', picture: null };

function town(over: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    campaign_id: 'k1',
    location: TOWN,
    scope: 'city',
    parent: COAST,
    path: [COAST, TOWN],
    background: { url: null, scene_id: null, label: 'Saltmere' },
    markers: [
      {
        location_id: 'halloway',
        name: 'Halloway house',
        kind: 'building',
        picture: null,
        x: 0.3,
        y: 0.4,
        placed: true,
        people: [
          { person_id: 'mara', name: 'Mara Halloway', picture: 'https://pictures.example/mara.webp' },
          { person_id: 'hesk', name: 'Old Hesk', picture: null },
          { person_id: 'tobin', name: 'Tobin Halloway', picture: null },
        ],
        count: 3,
      },
    ],
    parties: [{ location_id: 'inn', x: 0.7, y: 0.6, people: [{ person_id: 'brann', name: 'Brann', picture: null }] }],
    here: [{ person_id: 'crier', name: 'Town crier', picture: null }],
    ...over,
  };
}

function house(): Record<string, unknown> {
  return town({
    location: HOUSE,
    scope: 'building',
    parent: TOWN,
    path: [COAST, TOWN, HOUSE],
    markers: [],
    parties: [],
    here: [],
  });
}

beforeEach(() => {
  post.mockReset();
});

describe('the map at a scope', () => {
  it('shows a group token per building, the party, and a labelled placeholder with no art', async () => {
    post.mockResolvedValue(town());
    render(<ScopeMap campaignId='k1' locationId='saltmere' />);
    expect(await screen.findByRole('button', { name: 'Halloway house, 3 people' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'The party, 1 person' })).toBeInTheDocument();
    expect(screen.getByText('No map of this place yet')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Where' })).toHaveTextContent('The Salt Coast › Saltmere');
    expect(post).toHaveBeenCalledWith('/v1/scene/scope', { scope: { campaign_id: 'k1', location_id: 'saltmere' } });
  });

  it('lists who is in a building when its group is tapped, and a name opens their record', async () => {
    post.mockResolvedValue(town());
    const opened = vi.fn();
    render(<ScopeMap campaignId='k1' locationId='saltmere' onOpenRecord={opened} />);
    await userEvent.click(await screen.findByRole('button', { name: 'Halloway house, 3 people' }));
    const list = screen.getByRole('region', { name: 'Who is at Halloway house' });
    expect(list).toHaveTextContent('Mara Halloway');
    await userEvent.click(screen.getByRole('button', { name: 'Old Hesk' }));
    expect(opened).toHaveBeenCalledWith('hesk');
  });

  it('goes inside a building, scopes out to the town, and comes back in', async () => {
    post.mockImplementation(async (_path: string, body: { scope: { location_id: string | null } }) =>
      body.scope.location_id === 'halloway' ? house() : town(),
    );
    render(<ScopeMap campaignId='k1' locationId='saltmere' />);
    await userEvent.click(await screen.findByRole('button', { name: 'Halloway house, 3 people' }));
    await userEvent.click(screen.getByRole('button', { name: 'Go inside' }));
    expect(await screen.findByRole('button', { name: 'Scope out to Saltmere' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Back in' }));
    expect(await screen.findByRole('button', { name: 'Scope out to The Salt Coast' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Back in' })).toBeDisabled();
  });

  it('draws the scene art when the place has a map, and offers to play there', async () => {
    post.mockResolvedValue(
      town({ background: { url: 'https://maps.example/saltmere.webp', scene_id: 's1', label: 'Saltmere' } }),
    );
    const play = vi.fn();
    render(<ScopeMap campaignId='k1' onOpenScene={play} />);
    expect(await screen.findByRole('img', { name: 'Map of Saltmere' })).toHaveAttribute(
      'src',
      'https://maps.example/saltmere.webp',
    );
    await userEvent.click(screen.getByRole('button', { name: 'Play here' }));
    expect(play).toHaveBeenCalledWith('s1');
  });
});
