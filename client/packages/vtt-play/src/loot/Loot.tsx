// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * Loot: what lies where a character stands (the wiki's world_inventory: item instances at their
 * location), with Take (onto them: theirs, carried) and Take all. Inventory's Drop leaves things
 * here, so a dropped item is loot for whoever is in the place. Every take goes through the wiki's own
 * item routes under their rules, each with the row's version; a refused one says which.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useClient, writeProblem } from 'zephyrex';
import { Button } from 'zephyrex/ui/button';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import { z } from 'zod';

const instanceSchema = z
  .object({
    id: z.string(),
    item_id: z.string().nullish(),
    location_id: z.string().nullish(),
    owner_person_id: z.string().nullish(),
    quantity: z.number().nullish(),
    updated_at: z.string().nullish(),
  })
  .passthrough();
const itemSchema = z.object({ item: z.object({ id: z.string(), name: z.string().nullish() }).passthrough() });
const personSchema = z.object({ person: z.object({ id: z.string(), location_id: z.string().nullish() }).passthrough() });
const locationSchema = z.object({ location: z.object({ id: z.string(), name: z.string().nullish() }).passthrough() });

type Instance = z.infer<typeof instanceSchema>;

interface Loaded {
  here: { id: string; name: string } | null;
  lying: Instance[];
  names: Record<string, string>;
}

/** What was taken, for the host's action line ("Fennick picks up the silver key"). */
export interface TakenItem {
  id: string;
  item_id: string | null;
  name: string;
  quantity: number;
}

export interface LootProps {
  personId: string;
  /** Called after each take succeeds (the operator, 2026-11-26: the panel's actions become chat
   * lines as if typed). */
  onTaken?: (item: TakenItem) => void;
}

export function Loot({ personId, onTaken }: LootProps): ReactNode {
  const client = useClient();
  const [data, setData] = useState<
    { state: 'loading' } | { state: 'failed'; error: Error } | { state: 'ready'; value: Loaded }
  >({
    state: 'loading',
  });
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const read = useCallback(async (): Promise<void> => {
    try {
      const person = personSchema.parse(await client.get(`/v1/person/${personId}`)).person;
      if (!person.location_id) {
        setData({ state: 'ready', value: { here: null, lying: [], names: {} } });
        return;
      }
      const [place, lying] = await Promise.all([
        client.get(`/v1/location/${person.location_id}`),
        client.list('/v1/item_instance', 'item_instances', instanceSchema, { location_id: person.location_id }),
      ]);
      const names: Record<string, string> = {};
      await Promise.all(
        [...new Set(lying.map((one) => one.item_id).filter((id): id is string => Boolean(id)))].map(async (id) => {
          try {
            names[id] = itemSchema.parse(await client.get(`/v1/item/${id}`)).item.name ?? 'Unnamed item';
          } catch {
            names[id] = 'Unknown item';
          }
        }),
      );
      const location = locationSchema.parse(place).location;
      setData({
        state: 'ready',
        value: { here: { id: location.id, name: location.name ?? 'Here' }, lying, names },
      });
    } catch (error) {
      setData({ state: 'failed', error: error instanceof Error ? error : new Error(String(error)) });
    }
  }, [client, personId]);

  useEffect(() => {
    const first = window.setTimeout(() => void read(), 0);
    return () => window.clearTimeout(first);
  }, [read]);

  if (data.state === 'loading') return <SkeletonRows rows={3} label='Loading what lies here' />;
  if (data.state === 'failed') return <LoadProblem what='what lies here' error={data.error} onRetry={read} />;
  const { here, lying, names } = data.value;
  if (here === null) return <p className='text-muted-foreground text-sm'>They aren’t anywhere to search.</p>;
  const name = (one: Instance): string => (one.item_id ? (names[one.item_id] ?? 'Unnamed item') : 'Unnamed item');
  const take = (one: Instance): Promise<unknown> =>
    client
      .put(`/v1/item_instance/${one.id}`, { item_instance: { owner_person_id: personId, location_id: null } }, one)
      .then((written) => {
        onTaken?.({ id: one.id, item_id: one.item_id ?? null, name: name(one), quantity: one.quantity ?? 1 });
        return written;
      });

  const takeAll = async (): Promise<void> => {
    setBusy(true);
    const refused: string[] = [];
    for (const one of lying) {
      try {
        await take(one);
      } catch {
        refused.push(name(one));
      }
    }
    await read();
    setProblem(refused.length > 0 ? `Not taken: ${refused.join(', ')}` : null);
    setBusy(false);
  };

  return (
    <section aria-label={`Loot at ${here.name}`} className='space-y-2'>
      <p className='text-sm font-medium'>{here.name}</p>
      {lying.length === 0 ? (
        <p className='text-muted-foreground text-sm'>Nothing lies here.</p>
      ) : (
        <>
          <ul className='divide-border divide-y'>
            {lying.map((one) => (
              <li key={one.id} className='flex min-h-11 items-center gap-2 py-1'>
                <span className='font-medium'>{name(one)}</span>
                {(one.quantity ?? 1) > 1 && <span className='text-muted-foreground text-sm'>×{one.quantity}</span>}
                <Button
                  type='button'
                  variant='outline'
                  size='sm'
                  className='ms-auto min-h-11'
                  disabled={busy}
                  onClick={() => {
                    setBusy(true);
                    void writeProblem(
                      take(one).then(() => read()),
                      `${name(one)} wasn't taken`,
                    ).then((failed) => {
                      setProblem(failed);
                      setBusy(false);
                    });
                  }}
                >
                  Take
                </Button>
              </li>
            ))}
          </ul>
          {lying.length > 1 && (
            <Button type='button' className='min-h-11' disabled={busy} onClick={() => void takeAll()}>
              Take all
            </Button>
          )}
        </>
      )}
      {problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {problem}
        </p>
      )}
    </section>
  );
}
