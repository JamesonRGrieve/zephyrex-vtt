// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * A campaign's fight in initiative order (rpg_combat): the round, whose turn it is, each combatant's
 * initiative, and who is down. The campaign's GM rolls initiative, starts it, passes the turn and
 * ends it; a player sees the order (never a hidden combatant) with their own character marked. Live
 * through the campaign's room (a fight starting or ending) and the encounter's (every change).
 */
import { useRoom } from '@zephyrex/rooms';
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useClient, writeProblem } from 'zephyrex';
import { Button } from 'zephyrex/ui/button';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import { z } from 'zod';

const combatantSchema = z.object({
  id: z.string(),
  name: z.string().nullish(),
  person_id: z.string().nullish(),
  initiative: z.number().nullish(),
  is_defeated: z.boolean(),
  is_hidden: z.boolean(),
  controlled: z.boolean(),
});
const orderSchema = z.object({
  id: z.string(),
  name: z.string().nullish(),
  status: z.enum(['setup', 'running', 'ended']),
  round: z.number(),
  current_combatant_id: z.string().nullish(),
  gm: z.boolean(),
  combatants: z.array(combatantSchema),
  unrolled: z.array(z.object({ combatant_id: z.string(), name: z.string().nullish(), reason: z.string() })).default([]),
});
const currentSchema = z.object({ encounter: orderSchema.nullable() });

export type EncounterOrder = z.infer<typeof orderSchema>;

export interface CombatOrderProps {
  campaignId: string;
}

type Loaded = { state: 'loading' } | { state: 'failed'; error: Error } | { state: 'ready'; order: EncounterOrder | null };

export function CombatOrder({ campaignId }: CombatOrderProps): ReactNode {
  const client = useClient();
  const [data, setData] = useState<Loaded>({ state: 'loading' });
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const read = useCallback(async (): Promise<void> => {
    try {
      const answer = await client.post('/v1/encounter/current', { current: { campaign_id: campaignId } });
      setData({ state: 'ready', order: currentSchema.parse(answer).encounter });
    } catch (error) {
      setData({ state: 'failed', error: error instanceof Error ? error : new Error(String(error)) });
    }
  }, [client, campaignId]);

  useEffect(() => {
    const first = window.setTimeout(() => void read(), 0);
    return () => window.clearTimeout(first);
  }, [read]);

  const encounterId = data.state === 'ready' ? (data.order?.id ?? null) : null;
  const campaignRoom = useMemo(() => ({ type: 'campaign', id: campaignId }), [campaignId]);
  const encounterRoom = useMemo(() => (encounterId ? { type: 'encounter', id: encounterId } : null), [encounterId]);
  useRoom(campaignRoom, () => void read(), { onReset: () => void read() });
  useRoom(encounterRoom, () => void read(), { onReset: () => void read() });

  if (data.state === 'loading') return <SkeletonRows rows={3} label='Loading the combat order' />;
  if (data.state === 'failed') return <LoadProblem what='the combat order' error={data.error} onRetry={read} />;
  const order = data.order;
  if (order === null) return <p className='text-muted-foreground text-sm'>No fight in progress.</p>;

  const control = async (action: 'initiative' | 'start' | 'next' | 'end', fallback: string): Promise<void> => {
    setBusy(true);
    const body = action === 'initiative' ? { roll: { reroll: false } } : { control: {} };
    const write = client.post(`/v1/encounter/${order.id}/${action}`, body).then((answer) => {
      setData({ state: 'ready', order: orderSchema.parse((answer as { encounter: unknown }).encounter) });
    });
    setProblem(await writeProblem(write, fallback));
    setBusy(false);
  };

  return (
    <section aria-label='Combat order' className='space-y-2'>
      <p className='text-sm font-medium'>
        {order.name ?? 'Encounter'}
        <span className='text-muted-foreground ms-2 font-normal'>
          {order.status === 'running' ? `Round ${order.round}` : order.status === 'setup' ? 'Not started' : 'Ended'}
        </span>
      </p>
      <ol className='divide-border divide-y'>
        {order.combatants.map((one) => {
          const acting = one.id === order.current_combatant_id;
          return (
            <li
              key={one.id}
              aria-current={acting ? 'step' : undefined}
              className={`flex min-h-11 items-center gap-2 py-1 ${acting ? 'bg-accent font-semibold' : ''} ${
                one.is_defeated ? 'text-muted-foreground line-through' : ''
              }`}
            >
              <span className='w-8 text-end tabular-nums'>{one.initiative ?? '–'}</span>
              <span>{one.name ?? 'Unnamed'}</span>
              {one.controlled && !order.gm && <span className='text-muted-foreground text-xs'>(you)</span>}
              {one.is_hidden && <span className='text-muted-foreground text-xs'>hidden</span>}
              {acting && <span className='sr-only'>, acting now</span>}
            </li>
          );
        })}
      </ol>
      {order.gm && order.unrolled.length > 0 && (
        <ul className='text-muted-foreground text-sm'>
          {order.unrolled.map((one) => (
            <li key={one.combatant_id}>
              {one.name ?? 'Unnamed'}: {one.reason}
            </li>
          ))}
        </ul>
      )}
      {order.gm && order.status !== 'ended' && (
        <div className='flex flex-wrap gap-2'>
          {order.status === 'setup' && (
            <>
              <Button
                type='button'
                variant='outline'
                className='min-h-11'
                disabled={busy}
                onClick={() => void control('initiative', 'Initiative wasn’t rolled')}
              >
                Roll initiative
              </Button>
              <Button
                type='button'
                className='min-h-11'
                disabled={busy}
                onClick={() => void control('start', 'The fight didn’t start')}
              >
                Start
              </Button>
            </>
          )}
          {order.status === 'running' && (
            <Button
              type='button'
              className='min-h-11'
              disabled={busy}
              onClick={() => void control('next', 'The turn didn’t pass')}
            >
              Next turn
            </Button>
          )}
          <Button
            type='button'
            variant='ghost'
            className='min-h-11'
            disabled={busy}
            onClick={() => void control('end', 'The fight didn’t end')}
          >
            End
          </Button>
        </div>
      )}
      {problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {problem}
        </p>
      )}
    </section>
  );
}
