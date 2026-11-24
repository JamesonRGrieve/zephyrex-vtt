// SPDX-License-Identifier: AGPL-3.0-or-later
/** The map at a scope, house to town to region (@zephyrex/vtt-play's ScopeMap). */
import type { Meta, StoryObj } from '@storybook/nextjs';
import { expect, userEvent, within } from 'storybook/test';
import { ScopeMap } from '../../../packages/vtt-play/src/scene/ScopeMap';
import { StoryClient, type Routes } from './StoryClient';

const COAST = { id: 'coast', name: 'The Salt Coast', kind: 'region', picture: null };
const TOWN = { id: 'saltmere', name: 'Saltmere', kind: 'city', picture: null };
const HOUSE = { id: 'halloway', name: 'Halloway house', kind: 'building', picture: null };

const person = (id: string, name: string) => ({ person_id: id, name, picture: null });

const SCOPES: Record<string, unknown> = {
  saltmere: {
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
        y: 0.35,
        placed: true,
        people: [person('mara', 'Mara Halloway'), person('hesk', 'Old Hesk'), person('tobin', 'Tobin Halloway')],
        count: 3,
      },
      {
        location_id: 'inn',
        name: 'The Drowned Lantern',
        kind: 'building',
        picture: null,
        x: 0.68,
        y: 0.62,
        placed: false,
        people: [person('rusk', 'Innkeeper Rusk')],
        count: 1,
      },
    ],
    parties: [{ location_id: 'inn', x: 0.78, y: 0.62, people: [person('brann', 'Brann'), person('sefa', 'Sefa')] }],
    here: [person('crier', 'Town crier')],
  },
  halloway: {
    campaign_id: 'k1',
    location: HOUSE,
    scope: 'building',
    parent: TOWN,
    path: [COAST, TOWN, HOUSE],
    background: { url: null, scene_id: null, label: 'Halloway house' },
    markers: [
      {
        location_id: 'parlour',
        name: 'The parlour',
        kind: 'room',
        picture: null,
        x: 0.5,
        y: 0.5,
        placed: false,
        people: [person('hesk', 'Old Hesk'), person('tobin', 'Tobin Halloway')],
        count: 2,
      },
    ],
    parties: [],
    here: [person('mara', 'Mara Halloway')],
  },
  coast: {
    campaign_id: 'k1',
    location: COAST,
    scope: 'region',
    parent: null,
    path: [COAST],
    background: { url: null, scene_id: null, label: 'The Salt Coast' },
    markers: [
      {
        location_id: 'saltmere',
        name: 'Saltmere',
        kind: 'city',
        picture: null,
        x: 0.5,
        y: 0.5,
        placed: false,
        people: ['mara', 'hesk', 'tobin', 'rusk', 'crier'].map((id) => person(id, id)),
        count: 5,
      },
    ],
    parties: [{ location_id: 'saltmere', x: 0.56, y: 0.5, people: [person('brann', 'Brann'), person('sefa', 'Sefa')] }],
    here: [],
  },
};

const ROUTES: Routes = {
  'POST /v1/scene/scope': (body: unknown) => {
    const wanted = (body as { scope: { location_id: string | null } }).scope.location_id ?? 'saltmere';
    return SCOPES[wanted] ?? SCOPES.saltmere;
  },
};

function Map({ routes }: { routes: Routes }) {
  return (
    <StoryClient routes={routes}>
      <ScopeMap campaignId='k1' locationId='saltmere' />
    </StoryClient>
  );
}

const meta: Meta<typeof Map> = { title: 'VTT/Scope map', component: Map, args: { routes: ROUTES } };
export default meta;
type Story = StoryObj<typeof Map>;

/** The town: a group token per occupied building, the party beside the inn's keeper, who is in each. */
export const Town: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Halloway house, 3 people' }));
    await expect(canvas.getByRole('region', { name: 'Who is at Halloway house' })).toHaveTextContent('Old Hesk');
    await expect(canvas.getByRole('button', { name: 'The party, 2 people' })).toBeInTheDocument();
  },
};

/** Going inside the house, out past the town to the coast, and back in. */
export const ScopeOutAndIn: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(await canvas.findByRole('button', { name: 'Halloway house, 3 people' }));
    await userEvent.click(canvas.getByRole('button', { name: 'Go inside' }));
    await userEvent.click(await canvas.findByRole('button', { name: 'Scope out to Saltmere' }));
    await userEvent.click(await canvas.findByRole('button', { name: 'Scope out to The Salt Coast' }));
    await expect(await canvas.findByRole('button', { name: 'Saltmere, 5 people' })).toBeInTheDocument();
    await userEvent.click(canvas.getByRole('button', { name: 'Back in' }));
    await expect(await canvas.findByRole('button', { name: 'Scope out to The Salt Coast' })).toBeInTheDocument();
  },
};
