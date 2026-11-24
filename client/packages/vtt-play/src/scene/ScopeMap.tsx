// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * The map at a scope (operator, 2026-11-24: "It also needs a scope-out mode that shows, for example,
 * the town instead of the house, with a group token for each group of notable NPCs if multiple
 * occupy the same building"). The server's scene_scope decides everything shown: the place, its
 * parent (Scope out) and path, its map art or a labelled placeholder (never a bare grid), a group
 * token per place inside it that NPCs are in, and the party as its own group. Tapping a group lists
 * who is there; a name opens their record (onOpenRecord), and Go inside scopes into the place.
 * Back in returns down the way the reader came. Live through the campaign's room.
 */
import { useRoom } from '@zephyrex/rooms';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useClient } from 'zephyrex';
import { Button } from 'zephyrex/ui/button';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import { z } from 'zod';
import { pictureUrl } from './pictures';

const personSchema = z.object({ person_id: z.string(), name: z.string(), picture: z.string().nullish() });
const placeSchema = z.object({
  id: z.string(),
  name: z.string(),
  kind: z.string().nullish(),
  picture: z.string().nullish(),
});
const scopeSchema = z.object({
  campaign_id: z.string(),
  location: placeSchema,
  scope: z.string().nullish(),
  parent: placeSchema.nullish(),
  path: z.array(placeSchema),
  background: z.object({ url: z.string().nullish(), scene_id: z.string().nullish(), label: z.string() }),
  markers: z.array(
    z.object({
      location_id: z.string(),
      name: z.string(),
      kind: z.string().nullish(),
      picture: z.string().nullish(),
      x: z.number(),
      y: z.number(),
      placed: z.boolean(),
      people: z.array(personSchema),
      count: z.number(),
    }),
  ),
  parties: z
    .array(z.object({ location_id: z.string(), x: z.number(), y: z.number(), people: z.array(personSchema) }))
    .default([]),
  here: z.array(personSchema).default([]),
});

export type ScopeData = z.infer<typeof scopeSchema>;
type ScopePerson = z.infer<typeof personSchema>;

export interface ScopeMapProps {
  campaignId: string;
  /** The place to open at; none is the current scene's, else the party's. */
  locationId?: string | null;
  /** A name in a group was tapped: open that person's record. */
  onOpenRecord?: (personId: string) => void;
  /** Play on this place's scene (shown when the place has one). */
  onOpenScene?: (sceneId: string) => void;
}

type Loaded = { state: 'loading' } | { state: 'failed'; error: Error } | { state: 'ready'; scope: ScopeData };
/** A group shown in the list under the map: a place's NPCs, or the party. */
type Open = { key: string; title: string; people: ScopePerson[]; placeId: string | null };

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const first = words[0]?.[0] ?? '?';
  const last = words.length > 1 ? (words[words.length - 1]?.[0] ?? '') : '';
  return (first + last).toUpperCase();
}

function Portrait({ person, size }: { person: ScopePerson; size: 'small' | 'large' }): ReactNode {
  const box = size === 'small' ? 'size-8 text-[0.65rem]' : 'size-10 text-xs';
  if (person.picture) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- an embeddable package showing wiki picture links from any host, with no referrer (hosts refuse hotlinks that send one): next/image does neither
      <img
        src={person.picture}
        alt=''
        referrerPolicy='no-referrer'
        className={`${box} border-background shrink-0 rounded-full border-2 object-cover`}
      />
    );
  }
  return (
    // The initials are drawn by CSS, not text: a face is decoration, so a group's name is only its
    // label (every accessible-name reader agrees; jsdom reads aria-hidden text that browsers skip).
    <span
      aria-hidden
      data-initials={initials(person.name)}
      className={`${box} border-background bg-muted text-foreground flex shrink-0 items-center justify-center rounded-full border-2 font-semibold before:content-[attr(data-initials)]`}
    />
  );
}

/** One group on the map: up to three faces, the count, and the place's name under them. */
function GroupToken({
  label,
  people,
  x,
  y,
  party,
  below = false,
  open,
  onToggle,
}: {
  label: string;
  people: ScopePerson[];
  x: number;
  y: number;
  party: boolean;
  /** Stacked under the group of the same place (the party where NPCs are too), not on it. */
  below?: boolean;
  open: boolean;
  onToggle: () => void;
}): ReactNode {
  const shown = people.slice(0, 3);
  const word = people.length === 1 ? 'person' : 'people';
  return (
    <button
      type='button'
      onClick={onToggle}
      aria-expanded={open}
      className='absolute flex min-h-11 min-w-11 -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1 focus-visible:outline-2'
      // Kept inside the map's edges, so a group near one isn't cut off.
      style={{
        left: `clamp(3rem, ${x * 100}%, calc(100% - 3rem))`,
        top: `clamp(2.5rem, calc(${y * 100}% + ${below ? '4.25rem' : '0rem'}), calc(100% - 2.5rem))`,
      }}
    >
      <span
        aria-hidden
        className={`flex rounded-full p-0.5 ${party ? 'bg-primary' : 'bg-card'} shadow ${open ? 'ring-ring ring-2' : ''}`}
      >
        {shown.map((one, index) => (
          <span key={one.person_id} className={index > 0 ? '-ms-3' : ''}>
            <Portrait person={one} size='small' />
          </span>
        ))}
        {people.length > shown.length && (
          <span
            data-more={`+${people.length - shown.length}`}
            className='bg-muted text-foreground -ms-3 flex size-8 items-center justify-center rounded-full border-2 text-xs font-semibold before:content-[attr(data-more)]'
          />
        )}
      </span>
      <span className='bg-card/90 text-foreground line-clamp-2 max-w-36 rounded px-1.5 py-0.5 text-center text-xs leading-tight font-medium shadow'>
        {label}
        <span className='text-muted-foreground'>, {people.length}</span>{' '}
        {/* The space is its own text node: a name drops a span's leading space. */}
        <span className='sr-only'>{word}</span>
      </span>
    </button>
  );
}

export function ScopeMap({ campaignId, locationId = null, onOpenRecord, onOpenScene }: ScopeMapProps): ReactNode {
  const client = useClient();
  // The way in: each scope the reader stepped out from, so Back in returns down it.
  const [trail, setTrail] = useState<(string | null)[]>([locationId]);
  const [data, setData] = useState<Loaded>({ state: 'loading' });
  const [open, setOpen] = useState<string | null>(null);
  // The map art's own shape, once it loads (16:10 until then, and for the placeholder).
  const [aspect, setAspect] = useState('16 / 10');
  const at = trail[trail.length - 1] ?? null;

  const read = useCallback(async (): Promise<void> => {
    try {
      const answer = await client.post('/v1/scene/scope', { scope: { campaign_id: campaignId, location_id: at } });
      const scope = scopeSchema.parse(answer);
      // An uploaded map or portrait is the API's: at the client's base, with the session cookie.
      const person = (one: ScopePerson): ScopePerson => ({ ...one, picture: pictureUrl(client, one.picture) });
      setData({
        state: 'ready',
        scope: {
          ...scope,
          background: { ...scope.background, url: pictureUrl(client, scope.background.url) },
          markers: scope.markers.map((one) => ({
            ...one,
            picture: pictureUrl(client, one.picture),
            people: one.people.map(person),
          })),
          parties: scope.parties.map((one) => ({ ...one, people: one.people.map(person) })),
          here: scope.here.map(person),
        },
      });
    } catch (error) {
      setData({ state: 'failed', error: error instanceof Error ? error : new Error(String(error)) });
    }
  }, [client, campaignId, at]);

  useEffect(() => {
    const first = window.setTimeout(() => void read(), 0);
    return () => window.clearTimeout(first);
  }, [read]);

  const room = useMemo(() => ({ type: 'campaign', id: campaignId }), [campaignId]);
  useRoom(room, () => void read(), { onReset: () => void read() });

  const go = (placeId: string): void => {
    setOpen(null);
    setAspect('16 / 10');
    setData({ state: 'loading' });
    setTrail((before) => [...before, placeId]);
  };
  const back = (): void => {
    setOpen(null);
    setAspect('16 / 10');
    setData({ state: 'loading' });
    setTrail((before) => before.slice(0, -1));
  };

  if (data.state === 'loading') return <SkeletonRows rows={4} label='Loading the map' />;
  if (data.state === 'failed') return <LoadProblem what='the map' error={data.error} onRetry={read} />;
  const scope = data.scope;
  const groups: Open[] = [
    ...scope.markers.map((one) => ({
      key: `place:${one.location_id}`,
      title: one.name,
      people: one.people,
      placeId: one.location_id,
    })),
    ...scope.parties.map((one) => ({
      key: `party:${one.location_id}`,
      title: 'The party',
      people: one.people,
      placeId: one.location_id === scope.location.id ? null : one.location_id,
    })),
  ];
  const shown = groups.find((one) => one.key === open) ?? null;
  const toggle = (key: string): void => setOpen((before) => (before === key ? null : key));

  return (
    <section aria-label={`Map of ${scope.location.name}`} className='space-y-2'>
      <div className='flex flex-wrap items-center gap-2'>
        <nav aria-label='Where' className='text-muted-foreground w-full text-sm'>
          {scope.path.map((one, index) => (
            <span key={one.id}>
              {index > 0 && <span aria-hidden> › </span>}
              {one.id === scope.location.id ? (
                <span aria-current='location' className='text-foreground font-medium'>
                  {one.name}
                </span>
              ) : (
                one.name
              )}
            </span>
          ))}
        </nav>
        <Button size='sm' variant='outline' onClick={back} disabled={trail.length < 2}>
          Back in
        </Button>
        <Button size='sm' variant='outline' onClick={() => scope.parent && go(scope.parent.id)} disabled={!scope.parent}>
          {scope.parent ? `Scope out to ${scope.parent.name}` : 'Scope out'}
        </Button>
        {scope.background.scene_id && onOpenScene && (
          <Button size='sm' onClick={() => onOpenScene(scope.background.scene_id ?? '')}>
            Play here
          </Button>
        )}
      </div>

      {/* Shaped like the art, so a marker's place (fractions of the map) is the building's on it. */}
      <div className='bg-muted relative w-full overflow-hidden rounded-lg border' style={{ aspectRatio: aspect }}>
        {scope.background.url ? (
          // eslint-disable-next-line @next/next/no-img-element -- scene art by link from any host (generated or the GM's), in an embeddable package: next/image can't load it
          <img
            referrerPolicy='no-referrer'
            src={scope.background.url}
            alt={`Map of ${scope.background.label}`}
            className='absolute inset-0 size-full'
            onLoad={(event) => {
              const { naturalWidth, naturalHeight } = event.currentTarget;
              if (naturalWidth > 0 && naturalHeight > 0) setAspect(`${naturalWidth} / ${naturalHeight}`);
            }}
          />
        ) : (
          // No map art yet: the place, named, never a bare grid.
          <div className='absolute inset-0 flex flex-col items-center justify-center gap-1 p-6 text-center'>
            <p className='text-foreground text-2xl font-semibold'>{scope.background.label}</p>
            {scope.scope && <p className='text-muted-foreground text-sm capitalize'>{scope.scope.replace(/_/g, ' ')}</p>}
            <p className='text-muted-foreground text-xs'>No map of this place yet</p>
          </div>
        )}
        {scope.markers.map((one) => (
          <GroupToken
            key={one.location_id}
            label={one.name}
            people={one.people}
            x={one.x}
            y={one.y}
            party={false}
            open={open === `place:${one.location_id}`}
            onToggle={() => toggle(`place:${one.location_id}`)}
          />
        ))}
        {scope.parties.map((one) => {
          // Where NPCs are in the same place, the party stacks under their group, at its spot.
          const shared = scope.markers.find((marker) => marker.location_id === one.location_id);
          return (
            <GroupToken
              key={one.location_id}
              label='The party'
              people={one.people}
              x={shared ? shared.x : one.x}
              y={shared ? shared.y : one.y}
              below={Boolean(shared)}
              party
              open={open === `party:${one.location_id}`}
              onToggle={() => toggle(`party:${one.location_id}`)}
            />
          );
        })}
      </div>

      {shown && (
        <div role='region' aria-label={`Who is at ${shown.title}`} className='bg-card rounded-lg border p-3'>
          <div className='mb-2 flex items-center justify-between gap-2'>
            <p className='font-medium'>{shown.title}</p>
            {shown.placeId && (
              <Button size='sm' variant='outline' onClick={() => go(shown.placeId ?? '')}>
                Go inside
              </Button>
            )}
          </div>
          <ul className='space-y-1'>
            {shown.people.map((one) => (
              <li key={one.person_id}>
                <button
                  type='button'
                  onClick={() => onOpenRecord?.(one.person_id)}
                  className='hover:bg-accent flex min-h-11 w-full items-center gap-2 rounded px-1 text-start'
                >
                  <Portrait person={one} size='large' />
                  <span>{one.name}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {scope.here.length > 0 && (
        <div className='text-sm'>
          <p className='text-muted-foreground'>Also here, in {scope.location.name}:</p>
          <ul className='flex flex-wrap gap-1'>
            {scope.here.map((one) => (
              <li key={one.person_id}>
                <button
                  type='button'
                  onClick={() => onOpenRecord?.(one.person_id)}
                  className='hover:bg-accent flex min-h-11 items-center gap-2 rounded px-1'
                >
                  <Portrait person={one} size='small' />
                  <span>{one.name}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {scope.markers.length === 0 && scope.parties.length === 0 && scope.here.length === 0 && (
        <p className='text-muted-foreground text-sm'>No one the story follows is here.</p>
      )}
    </section>
  );
}
