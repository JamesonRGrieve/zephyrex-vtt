// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * A character's inventory (the wiki's world_inventory): what they carry (their items on them, in
 * their equipment slots or containers), with use (one fewer; the last one is gone), drop (left where
 * they stand) and give (to another character of the campaign, on them). Every write goes through the
 * wiki's own item routes under their rules; a refused one says so.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useClient, writeProblem } from 'zephyrex';
import { Button } from 'zephyrex/ui/button';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import { z } from 'zod';

const versioned = { created_at: z.string().nullish(), updated_at: z.string().nullish() };
const instanceSchema = z
  .object({
    id: z.string(),
    item_id: z.string().nullish(),
    location_id: z.string().nullish(),
    owner_person_id: z.string().nullish(),
    quantity: z.number().nullish(),
    ...versioned,
  })
  .passthrough();
const itemSchema = z.object({ item: z.object({ id: z.string(), name: z.string().nullish() }).passthrough() });
const personSchema = z.object({
  person: z.object({ id: z.string(), campaign_id: z.string().nullish(), location_id: z.string().nullish() }).passthrough(),
});
const memberSchema = z.object({ id: z.string(), name: z.string().nullish() }).passthrough();
const locationSchema = z.object({ id: z.string() }).passthrough();

type Instance = z.infer<typeof instanceSchema>;
type Member = z.infer<typeof memberSchema>;

interface Loaded {
  carried: Instance[];
  names: Record<string, string>;
  here: string | null;
  others: Member[];
}

/** What the character did, for the host's action line ("Fennick drops the torch", "Fennick hands
 * Brakka the rope"). */
export interface InventoryAction {
  kind: 'drop' | 'give' | 'use';
  item: { id: string; name: string };
  to?: { personId: string; name: string };
}

export interface InventoryProps {
  personId: string;
  /** Called after each action's write succeeds (the operator, 2026-11-26: the panel's actions
   * become chat lines as if typed). */
  onAction?: (action: InventoryAction) => void;
}

function asError(error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error));
}

export function Inventory({ personId, onAction }: InventoryProps): ReactNode {
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
      const [owned, bound, members] = await Promise.all([
        client.list('/v1/item_instance', 'item_instances', instanceSchema, { owner_person_id: personId }),
        client.list('/v1/location', 'locations', locationSchema, { associated_person_id: personId }),
        person.campaign_id ? client.list('/v1/person', 'persons', memberSchema, { campaign_id: person.campaign_id }) : [],
      ]);
      const onThem = new Set(bound.map((one) => one.id));
      const carried = owned.filter((one) => !one.location_id || onThem.has(one.location_id));
      const names: Record<string, string> = {};
      await Promise.all(
        [...new Set(carried.map((one) => one.item_id).filter((id): id is string => Boolean(id)))].map(async (id) => {
          try {
            names[id] = itemSchema.parse(await client.get(`/v1/item/${id}`)).item.name ?? 'Unnamed item';
          } catch {
            names[id] = 'Unknown item';
          }
        }),
      );
      setData({
        state: 'ready',
        value: { carried, names, here: person.location_id ?? null, others: members.filter((one) => one.id !== personId) },
      });
    } catch (error) {
      setData({ state: 'failed', error: asError(error) });
    }
  }, [client, personId]);

  useEffect(() => {
    const first = window.setTimeout(() => void read(), 0);
    return () => window.clearTimeout(first);
  }, [read]);

  const act = async (write: Promise<unknown>, fallback: string, done?: InventoryAction): Promise<void> => {
    setBusy(true);
    setProblem(
      await writeProblem(
        write.then(() => {
          if (done) onAction?.(done);
          return read();
        }),
        fallback,
      ),
    );
    setBusy(false);
  };

  if (data.state === 'loading') return <SkeletonRows rows={3} label='Loading the inventory' />;
  if (data.state === 'failed') return <LoadProblem what='the inventory' error={data.error} onRetry={read} />;
  const { carried, names, here, others } = data.value;
  const name = (one: Instance): string => (one.item_id ? (names[one.item_id] ?? 'Unnamed item') : 'Unnamed item');

  return (
    <section aria-label='Inventory' className='space-y-2'>
      {carried.length === 0 ? (
        <p className='text-muted-foreground text-sm'>Carrying nothing.</p>
      ) : (
        <ul className='divide-border divide-y'>
          {carried.map((one) => {
            const quantity = one.quantity ?? 1;
            return (
              <li key={one.id} className='flex min-h-11 flex-wrap items-center gap-2 py-1'>
                <span className='font-medium'>{name(one)}</span>
                {quantity > 1 && <span className='text-muted-foreground text-sm'>×{quantity}</span>}
                <span className='ms-auto flex flex-wrap gap-1'>
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    className='min-h-11'
                    disabled={busy}
                    onClick={() =>
                      void act(
                        quantity > 1
                          ? client.put(`/v1/item_instance/${one.id}`, { item_instance: { quantity: quantity - 1 } }, one)
                          : client.delete(`/v1/item_instance/${one.id}`, one),
                        `${name(one)} wasn't used`,
                        { kind: 'use', item: { id: one.id, name: name(one) } },
                      )
                    }
                  >
                    Use
                  </Button>
                  <Button
                    type='button'
                    variant='ghost'
                    size='sm'
                    className='min-h-11'
                    disabled={busy || !here}
                    title={here ? undefined : 'They aren’t anywhere to leave it'}
                    onClick={() =>
                      void act(
                        client.put(`/v1/item_instance/${one.id}`, { item_instance: { location_id: here } }, one),
                        `${name(one)} wasn't dropped`,
                        { kind: 'drop', item: { id: one.id, name: name(one) } },
                      )
                    }
                  >
                    Drop
                  </Button>
                  {others.length > 0 && (
                    <select
                      aria-label={`Give ${name(one)} to`}
                      className='border-input bg-background h-11 rounded-md border px-2 text-sm'
                      value=''
                      disabled={busy}
                      onChange={(event) => {
                        const to = event.target.value;
                        if (to)
                          void act(
                            client.put(
                              `/v1/item_instance/${one.id}`,
                              { item_instance: { owner_person_id: to, location_id: null } },
                              one,
                            ),
                            `${name(one)} wasn't given`,
                            {
                              kind: 'give',
                              item: { id: one.id, name: name(one) },
                              to: { personId: to, name: others.find((other) => other.id === to)?.name ?? 'someone' },
                            },
                          );
                      }}
                    >
                      <option value=''>Give to…</option>
                      {others.map((member) => (
                        <option key={member.id} value={member.id}>
                          {member.name ?? 'Unnamed'}
                        </option>
                      ))}
                    </select>
                  )}
                </span>
              </li>
            );
          })}
        </ul>
      )}
      {problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {problem}
        </p>
      )}
    </section>
  );
}
