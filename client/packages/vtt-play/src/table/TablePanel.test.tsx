// SPDX-License-Identifier: AGPL-3.0-or-later
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const list = vi.fn();
const get = vi.fn();
const post = vi.fn();
const client = { list, get, post, delete: vi.fn() };
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
vi.mock('@zephyrex/rooms', () => ({ useRoom: () => 'live' }));

const { SceneList, CampaignSeats, CurrentSceneTokens } = await import('./TablePanel');

const SCENES = [
  { id: 's1', name: 'Bridge', is_active: true },
  { id: 's2', name: 'Brig', is_active: false },
];

// A block body: a function returned from beforeEach is a cleanup hook vitest would call.
beforeEach(() => {
  list.mockReset();
  get.mockReset().mockResolvedValue({ campaign: { id: 'c1', user_id: 'gm' } });
  post.mockReset();
  user = { data: { id: 'gm' } };
});

describe('the table panel', () => {
  it('lists the scenes, marks the current one, and lets the GM make another current', async () => {
    list.mockResolvedValue(SCENES);
    post.mockResolvedValue({});
    render(<SceneList campaignId='c1' />);
    expect(await screen.findByText('Current')).toBeInTheDocument();
    await userEvent.click(await screen.findByRole('button', { name: 'Make current' }));
    expect(post).toHaveBeenCalledWith('/v1/scene/s2/activate', { activate: {} });
    expect(list).toHaveBeenCalledWith('/v1/scene', 'scenes', expect.anything(), { campaign_id: 'c1' });
  });

  it('shows a player the scenes without the GM’s button', async () => {
    user = { data: { id: 'ada' } };
    list.mockResolvedValue(SCENES);
    render(<SceneList campaignId='c1' />);
    expect(await screen.findByText('Brig')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Make current' })).toBeNull();
  });

  it('says when the campaign has no table', async () => {
    list.mockResolvedValue([]);
    render(<CampaignSeats campaignId='c1' />);
    expect(await screen.findByText('This campaign has no table yet.')).toBeInTheDocument();
  });

  it('says when there is no current scene for its token list', async () => {
    post.mockResolvedValue({ scene: null });
    render(<CurrentSceneTokens campaignId='c1' />);
    expect(await screen.findByText(/No current scene/)).toBeInTheDocument();
  });

  it('lists the current scene’s tokens', async () => {
    post.mockImplementation((path: string) =>
      Promise.resolve(
        path === '/v1/scene/current'
          ? { scene: { id: 's1' } }
          : {
              view: {
                scene_id: 's1',
                name: 'Bridge',
                width: 1000,
                height: 600,
                grid_size: 100,
                grid_distance: 5,
                grid_units: 'ft',
                background_color: null,
                gm: true,
                viewer: null,
                lit: true,
                walls: [],
                tokens: [
                  {
                    id: 't1',
                    name: 'Vell',
                    person_id: null,
                    disposition: 'neutral',
                    x: 0,
                    y: 0,
                    width: 1,
                    height: 1,
                    rotation: 0,
                    is_hidden: false,
                    mine: false,
                  },
                ],
              },
            },
      ),
    );
    render(<CurrentSceneTokens campaignId='c1' />);
    expect(await screen.findByText('Vell')).toBeInTheDocument();
  });
});
