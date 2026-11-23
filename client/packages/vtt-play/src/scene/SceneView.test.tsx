// SPDX-License-Identifier: AGPL-3.0-or-later
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const post = vi.fn();
const get = vi.fn();
const put = vi.fn();
const client = { post, get, put };
vi.mock('zephyrex', () => ({
  useClient: () => client,
  writeProblem: async (write: Promise<unknown>, fallback: string) =>
    write.then(
      () => null,
      () => fallback,
    ),
}));

const joined: { room?: unknown; onChange?: (change: unknown) => void } = {};
vi.mock('@zephyrex/rooms', () => ({
  useRoom: (room: unknown, onChange: (change: unknown) => void) => {
    joined.room = room;
    joined.onChange = onChange;
    return 'live';
  },
}));

const { SceneView } = await import('./SceneView');

function view(gm: boolean) {
  return {
    view: {
      scene_id: 's1',
      name: 'Bridge',
      width: 1000,
      height: 800,
      grid_size: 100,
      grid_distance: 5,
      grid_units: 'ft',
      background_color: null,
      gm,
      viewer: gm ? null : 'ada',
      lit: true,
      tokens: [
        {
          id: 'ada',
          name: 'Ada',
          person_id: 'p-ada',
          disposition: 'friendly',
          x: 0,
          y: 0,
          width: 1,
          height: 1,
          rotation: 0,
          is_hidden: false,
          mine: !gm,
        },
        {
          id: 'orc',
          name: 'Orc',
          person_id: null,
          disposition: 'hostile',
          x: 300,
          y: 0,
          width: 1,
          height: 1,
          rotation: 0,
          is_hidden: gm,
          mine: false,
        },
      ],
      walls: [],
    },
  };
}

// A block body: a function returned from beforeEach is a cleanup hook vitest would call.
beforeEach(() => {
  post.mockReset();
  get.mockReset();
  put.mockReset();
});

describe('the scene view', () => {
  it('lists what the player sees, linking characters to the wiki, and moves only their own token', async () => {
    post.mockImplementation((path: string) => Promise.resolve(path.endsWith('/view') ? view(false) : { scene_token: {} }));
    render(<SceneView showList sceneId='s1' personHref={(id) => `/w/harbour/person/${id}`} />);
    expect(await screen.findByRole('link', { name: 'Ada' })).toHaveAttribute('href', '/w/harbour/person/p-ada');
    expect(screen.getByRole('application', { name: /^Map of Bridge/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Move Orc/ })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Move Ada east' }));
    expect(post).toHaveBeenCalledWith('/v1/scene_token/ada/move', { move: { x: 100, y: 0 } });
  });

  it('lets the GM move any token, hidden ones marked', async () => {
    post.mockImplementation((path: string) => Promise.resolve(path.endsWith('/view') ? view(true) : { scene_token: {} }));
    render(<SceneView showList sceneId='s1' />);
    expect(await screen.findByText(/hidden/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Move Orc south' }));
    expect(post).toHaveBeenCalledWith('/v1/scene_token/orc/move', { move: { x: 300, y: 100 } });
  });

  it('says when the server refused a move, such as through a wall', async () => {
    post.mockImplementation((path: string) =>
      path.endsWith('/view') ? Promise.resolve(view(false)) : Promise.reject(new Error('422')),
    );
    render(<SceneView showList sceneId='s1' />);
    await userEvent.click(await screen.findByRole('button', { name: 'Move Ada south' }));
    expect(await screen.findByRole('alert')).toHaveTextContent("Ada didn't move");
  });

  it('reads the view again when the scene’s room hears a change', async () => {
    let answer = view(false);
    post.mockImplementation(() => Promise.resolve(answer));
    render(<SceneView showList sceneId='s1' />);
    await screen.findByText('Ada');
    expect(joined.room).toEqual({ type: 'scene', id: 's1' });
    answer = {
      view: { ...answer.view, tokens: [...answer.view.tokens, { ...answer.view.tokens[1]!, id: 'gob', name: 'Goblin' }] },
    };
    act(() => joined.onChange?.({ op: 'updated', record: { type: 'scene_token', id: 'gob' } }));
    expect(await screen.findByText('Goblin')).toBeInTheDocument();
  });

  it('says what failed to load', async () => {
    post.mockRejectedValue(new Error('down'));
    render(<SceneView showList sceneId='s1' />);
    await waitFor(() => expect(screen.getByRole('button', { name: /try again/i })).toBeInTheDocument());
  });
  it('switches between moving tokens and measuring', async () => {
    post.mockImplementation(() => Promise.resolve(view(false)));
    render(<SceneView sceneId='s1' />);
    const measure = await screen.findByRole('radio', { name: 'Measure' });
    expect(screen.getByRole('radio', { name: 'Move' })).toHaveAttribute('aria-checked', 'true');
    await userEvent.click(measure);
    expect(measure).toHaveAttribute('aria-checked', 'true');
  });

  it('gives the GM the map controls: the scene to show, and the cast to place', async () => {
    post.mockImplementation((path: string) => Promise.resolve(path.endsWith('/view') ? view(true) : {}));
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.startsWith('/v1/scene?')
          ? {
              scenes: [
                { id: 's1', name: 'Bridge', is_active: false },
                { id: 's2', name: 'Hold', is_active: true },
              ],
            }
          : {
              persons: [
                { id: 'p-ada', name: 'Ada', kind: 'pc' },
                { id: 'p-tam', name: 'Old Tam', kind: 'npc' },
              ],
            },
      ),
    );
    const picked = vi.fn();
    render(<SceneView sceneId='s1' campaignId='c1' onScene={picked} />);
    const controls = await screen.findByRole('region', { name: 'Map controls' });
    await waitFor(() => expect(get).toHaveBeenCalledWith('/v1/scene?campaign_id=c1'));
    // Ada has a token here; Old Tam doesn't.
    await userEvent.click(await screen.findByRole('button', { name: 'Place Old Tam on the map' }));
    expect(post).toHaveBeenCalledWith('/v1/scene/s1/place', { place: { person_id: 'p-tam' } });
    expect(screen.queryByRole('button', { name: 'Place Ada on the map' })).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Show to players' }));
    expect(post).toHaveBeenCalledWith('/v1/scene/s1/activate', { activate: {} });
    await userEvent.selectOptions(screen.getByLabelText('Scene'), 's2');
    expect(picked).toHaveBeenCalledWith('s2');
    expect(controls).toBeInTheDocument();
  });

  it('shows players no map controls', async () => {
    post.mockImplementation(() => Promise.resolve(view(false)));
    render(<SceneView sceneId='s1' campaignId='c1' />);
    await screen.findByRole('radio', { name: 'Measure' });
    expect(screen.queryByRole('region', { name: 'Map controls' })).toBeNull();
    expect(get).not.toHaveBeenCalled();
  });
});
