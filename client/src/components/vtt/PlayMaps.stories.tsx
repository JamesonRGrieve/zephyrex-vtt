// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * The play maps as a table sees them, from real cartography: the Halloway parlour (2200×1700, a 100 px
 * grid, its imported walls and doors) and the town of Saltmere (4096×2867, its places), drawn by the
 * scene view and the scope map. The walls, doors and places are the server's own reading of the
 * exports (rpg_scene.Uvtt), in fixtures/maps.json. The art is served at /review-art/ only where a
 * review build provides it (it isn't in this public repo); without it the map shows its placeholder.
 */
import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, userEvent, within } from 'storybook/test';
import { SceneView } from '../../../packages/vtt-play/src/scene/SceneView';
import { ScopeMap } from '../../../packages/vtt-play/src/scene/ScopeMap';
import maps from './fixtures/maps.json';
import { StoryClient, type Routes } from './StoryClient';

const PARLOUR_ART = '/review-art/halloway-parlour.0.png';
const SALTMERE_ART = '/review-art/saltmere.0.webp';

/** A stand-in portrait: a coloured bust, as a picture link would draw. */
function portrait(hue: number): string {
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='64' height='64' viewBox='0 0 64 64'><rect width='64' height='64' fill='hsl(${hue} 45% 35%)'/><circle cx='32' cy='24' r='12' fill='hsl(${hue} 30% 80%)'/><path d='M10 64c2-16 12-22 22-22s20 6 22 22z' fill='hsl(${hue} 30% 80%)'/></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

type Wall = { id: string; points: number[][]; door_type: string; door_state: string };
const ground = maps.hallowayGround as { width: number; height: number; grid_size: number; walls: Wall[] };
const town = maps.saltmere as { width: number; height: number; grid_size: number; walls: Wall[] };

function token(id: string, name: string, x: number, y: number, disposition: string, hue: number | null, mine = false) {
  return {
    id,
    name,
    person_id: `p-${id}`,
    disposition,
    x,
    y,
    width: 1,
    height: 1,
    rotation: 0,
    is_hidden: false,
    mine,
    picture_url: hue === null ? null : portrait(hue),
  };
}

// The party in the hall by the front door; the Halloways and Old Hesk in the parlour (the room with
// the round rug), on the cells the art leaves free.
const PARLOUR_TOKENS = [
  token('brann', 'Brann', 1000, 1100, 'friendly', 210, true),
  token('sefa', 'Sefa', 1000, 900, 'friendly', 140),
  token('mara', 'Mara Halloway', 500, 1100, 'neutral', 30),
  token('hesk', 'Old Hesk', 400, 700, 'neutral', 0),
  token('tobin', 'Tobin Halloway', 700, 700, 'neutral', null),
];

function sceneView(gm: boolean, art: string | null, data: typeof ground, name: string, tokens: ReturnType<typeof token>[]) {
  return {
    view: {
      scene_id: 's1',
      name,
      width: data.width,
      height: data.height,
      grid_size: data.grid_size,
      grid_distance: 5,
      grid_units: 'ft',
      background_color: null,
      gm,
      viewer: gm ? null : 'brann',
      lit: true,
      background_url: art,
      tokens: gm ? tokens : tokens.map((one) => ({ ...one, mine: one.id === 'brann' })),
      // A player is sent only the doors their token sees (the server's sight); the GM every wall.
      walls: gm ? data.walls : data.walls.filter((one) => one.door_type !== 'none').slice(0, 2),
    },
  };
}

function Scene({ routes }: { routes: Routes }) {
  return (
    <StoryClient routes={routes}>
      <SceneView sceneId='s1' />
    </StoryClient>
  );
}

const meta: Meta<typeof Scene> = { title: 'VTT/Play maps', component: Scene };
export default meta;
type Story = StoryObj<typeof Scene>;

/** The GM at the Halloway parlour: the battle map, every wall and door, the cast with portraits and names. */
export const ParlourGameMaster: Story = {
  args: {
    routes: {
      'POST /v1/scene/s1/view': sceneView(true, PARLOUR_ART, ground, 'Halloway house, ground floor', PARLOUR_TOKENS),
    },
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await expect(await canvas.findByRole('application', { name: /Halloway house, ground floor/ })).toBeInTheDocument();
  },
};

/** A player at the parlour: their token, who they see, and only the doors they see. */
export const ParlourPlayer: Story = {
  args: {
    routes: {
      'POST /v1/scene/s1/view': sceneView(false, PARLOUR_ART, ground, 'Halloway house, ground floor', PARLOUR_TOKENS),
    },
  },
  play: async ({ canvasElement }) => {
    await expect(
      await within(canvasElement).findByRole('application', { name: /Halloway house, ground floor/ }),
    ).toBeInTheDocument();
  },
};

/** A player at the parlour on a phone, the map filling the screen under the host's own controls
 * (rpg-ai's MapView gives it the height): opened filled by the map's width or height. */
export const ParlourPlayerFilling: Story = {
  render: () => (
    <StoryClient
      routes={{
        'POST /v1/scene/s1/view': sceneView(false, PARLOUR_ART, ground, 'Halloway house, ground floor', PARLOUR_TOKENS),
      }}
    >
      <div className='h-[80svh]'>
        <SceneView sceneId='s1' fill />
      </div>
    </StoryClient>
  ),
  play: async ({ canvasElement }) => {
    const map = await within(canvasElement).findByRole('application', { name: /Halloway house, ground floor/ });
    await expect(map.getBoundingClientRect().height).toBeGreaterThan(300);
  },
};

/** Saltmere as a battle scene: the town map at its own scale (68 px squares). */
export const SaltmereScene: Story = {
  args: {
    routes: {
      'POST /v1/scene/s1/view': sceneView(true, SALTMERE_ART, town, 'Saltmere', [
        token('brann', 'Brann', 1365, 1092, 'friendly', 210, true),
      ]),
    },
  },
  play: async ({ canvasElement }) => {
    await expect(await within(canvasElement).findByRole('application', { name: /Saltmere/ })).toBeInTheDocument();
  },
};

/** A place with no map yet: named, never a bare grid. */
export const NoArt: Story = {
  args: {
    routes: {
      'POST /v1/scene/s1/view': sceneView(
        true,
        null,
        { ...ground, walls: [] },
        'The Drowned Lantern',
        PARLOUR_TOKENS.slice(0, 2),
      ),
    },
  },
  play: async ({ canvasElement }) => {
    await expect(await within(canvasElement).findByRole('application', { name: /The Drowned Lantern/ })).toBeInTheDocument();
  },
};

const places = (maps.saltmerePlaces as { boxes_px_x0_y0_x1_y1: Record<string, number[]> }).boxes_px_x0_y0_x1_y1;
const centre = (name: string) => {
  const [x0 = 0, y0 = 0, x1 = 0, y1 = 0] = places[name] ?? [];
  return { x: (x0 + x1) / 2 / town.width, y: (y0 + y1) / 2 / town.height };
};
const person = (id: string, name: string, hue: number | null) => ({
  person_id: id,
  name,
  picture: hue === null ? null : portrait(hue),
});
const COAST = { id: 'coast', name: 'The Salt Coast', kind: 'region', picture: null };
const SALTMERE = { id: 'saltmere', name: 'Saltmere', kind: 'city', picture: null };
const HOUSE = { id: 'halloway', name: 'Halloway house', kind: 'building', picture: null };

const SCOPES: Record<string, unknown> = {
  saltmere: {
    campaign_id: 'k1',
    location: SALTMERE,
    scope: 'city',
    parent: COAST,
    path: [COAST, SALTMERE],
    background: { url: SALTMERE_ART, scene_id: 's-town', label: 'Saltmere' },
    markers: [
      {
        location_id: 'halloway',
        name: 'Halloway house',
        kind: 'building',
        picture: null,
        ...centre('Halloway house'),
        placed: true,
        people: [
          person('mara', 'Mara Halloway', 30),
          person('hesk', 'Old Hesk', 0),
          person('tobin', 'Tobin Halloway', null),
        ],
        count: 3,
      },
      {
        location_id: 'spice',
        name: 'Halloway & Marr Spice House',
        kind: 'building',
        picture: null,
        ...centre('Halloway & Marr Spice House'),
        placed: true,
        people: [person('marr', 'Jessa Marr', 280)],
        count: 1,
      },
      {
        location_id: 'watch',
        name: 'Watch house',
        kind: 'building',
        picture: null,
        ...centre('Watch house'),
        placed: true,
        people: [person('cpt', 'Captain Ord', 90), person('w1', 'Watchman Bell', null)],
        count: 2,
      },
    ],
    parties: [
      {
        location_id: 'halloway',
        ...centre('Halloway house'),
        x: centre('Halloway house').x + 0.06,
        people: [person('brann', 'Brann', 210), person('sefa', 'Sefa', 140)],
      },
    ],
    here: [person('crier', 'Town crier', null)],
  },
  halloway: {
    campaign_id: 'k1',
    location: HOUSE,
    scope: 'building',
    parent: SALTMERE,
    path: [COAST, SALTMERE, HOUSE],
    background: { url: PARLOUR_ART, scene_id: 's1', label: 'Halloway house' },
    markers: [
      {
        location_id: 'parlour',
        name: 'The parlour',
        kind: 'room',
        picture: null,
        x: 0.27,
        y: 0.55,
        placed: true,
        people: [person('hesk', 'Old Hesk', 0), person('tobin', 'Tobin Halloway', null)],
        count: 2,
      },
    ],
    parties: [
      { location_id: 'halloway', x: 0.47, y: 0.62, people: [person('brann', 'Brann', 210), person('sefa', 'Sefa', 140)] },
    ],
    here: [person('mara', 'Mara Halloway', 30)],
  },
};
const SCOPE_ROUTES: Routes = {
  'POST /v1/scene/scope': (body: unknown) =>
    SCOPES[(body as { scope: { location_id: string | null } }).scope.location_id ?? 'saltmere'] ?? SCOPES.saltmere,
};

function Scope({ at }: { at: string }) {
  return (
    <StoryClient routes={SCOPE_ROUTES}>
      <ScopeMap campaignId='k1' locationId={at} />
    </StoryClient>
  );
}

/** Saltmere at town scope over its map: a group token per occupied building, the party beside its NPCs. */
export const TownScope: StoryObj<typeof Scope> = {
  render: () => <Scope at='saltmere' />,
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Halloway house, 3 people' }));
    await expect(canvas.getByRole('region', { name: 'Who is at Halloway house' })).toHaveTextContent('Old Hesk');
  },
};

/** The Halloway house at building scope over its battle map. */
export const HouseScope: StoryObj<typeof Scope> = {
  render: () => <Scope at='halloway' />,
  play: async ({ canvasElement }) => {
    await expect(await within(canvasElement).findByRole('button', { name: 'The parlour, 2 people' })).toBeInTheDocument();
  },
};
