// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * Character creation's ability score step (rpg_builder), by the campaign's pack's own methods (the 5e
 * 2024: standard array, point buy, or 4d6 keep 3 rolled on the server). The player picks a method,
 * gives each ability a score, and the server checks it against the method and saves it; this form
 * only helps (what's left of the array, points spent), it never decides.
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useClient, writeProblem } from 'zephyrex';
import { Button } from 'zephyrex/ui/button';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import { z } from 'zod';

const builderSchema = z.object({
  builder: z.object({
    person_id: z.string(),
    system: z.string(),
    gm: z.boolean(),
    abilities: z.array(
      z.object({ slug: z.string(), name: z.string(), short: z.string().nullish(), score: z.number().nullish() }),
    ),
    methods: z.object({
      standard_array: z.array(z.number()),
      point_buy: z.object({ pool: z.number(), costs: z.record(z.string(), z.number()) }),
      roll: z.object({ formula: z.string(), count: z.number() }),
    }),
    rolled: z.object({ scores: z.array(z.number()), dice: z.array(z.array(z.number())), used: z.boolean() }).nullable(),
    can_set: z.boolean(),
  }),
});
const rolledSchema = z.object({ scores: z.array(z.number()), dice: z.array(z.array(z.number())), used: z.boolean() });

export type BuilderOptions = z.infer<typeof builderSchema>['builder'];
type Method = 'standard_array' | 'point_buy' | 'roll';

const METHOD_NAMES: Record<Method, string> = {
  standard_array: 'Standard array',
  point_buy: 'Point buy',
  roll: 'Roll',
};

export interface AbilityScoresProps {
  personId: string;
  /** Called with the saved options once the scores are set. */
  onDone?: (options: BuilderOptions) => void;
}

/** What's still free of a pool of values once some are assigned (each value once). */
export function remaining(pool: number[], chosen: (number | undefined)[]): number[] {
  const left = [...pool];
  for (const value of chosen) {
    const at = value === undefined ? -1 : left.indexOf(value);
    if (at >= 0) left.splice(at, 1);
  }
  return left;
}

export function AbilityScores({ personId, onDone }: AbilityScoresProps): ReactNode {
  const client = useClient();
  const [data, setData] = useState<
    { state: 'loading' } | { state: 'failed'; error: Error } | { state: 'ready'; options: BuilderOptions }
  >({
    state: 'loading',
  });
  const [method, setMethod] = useState<Method>('standard_array');
  const [scores, setScores] = useState<Record<string, number | undefined>>({});
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const read = useCallback(async (): Promise<void> => {
    try {
      const answer = await client.post('/v1/builder/options', { options: { person_id: personId } });
      setData({ state: 'ready', options: builderSchema.parse(answer).builder });
    } catch (error) {
      setData({ state: 'failed', error: error instanceof Error ? error : new Error(String(error)) });
    }
  }, [client, personId]);

  useEffect(() => {
    const first = window.setTimeout(() => void read(), 0);
    return () => window.clearTimeout(first);
  }, [read]);

  const options = data.state === 'ready' ? data.options : null;
  const pool = useMemo((): number[] => {
    if (!options) return [];
    if (method === 'standard_array') return options.methods.standard_array;
    if (method === 'roll') return options.rolled && !options.rolled.used ? options.rolled.scores : [];
    return Object.keys(options.methods.point_buy.costs).map(Number);
  }, [options, method]);

  if (data.state === 'loading') return <SkeletonRows rows={6} label='Loading the ability scores' />;
  if (data.state === 'failed') return <LoadProblem what='the ability scores' error={data.error} onRetry={read} />;
  const current = data.options;
  if (!current.can_set) {
    return (
      <ul aria-label='Ability scores' className='grid grid-cols-3 gap-2 text-sm'>
        {current.abilities.map((one) => (
          <li key={one.slug}>
            {one.short ?? one.name} <span className='font-semibold'>{one.score ?? '–'}</span>
          </li>
        ))}
      </ul>
    );
  }

  const costs = current.methods.point_buy.costs;
  const chosen = current.abilities.map((one) => scores[one.slug]);
  const spent = chosen.reduce<number>((sum, value) => sum + (value === undefined ? 0 : (costs[String(value)] ?? 0)), 0);
  const complete = chosen.every((value) => value !== undefined);

  const choose = (next: Method): void => {
    setMethod(next);
    setScores({});
    setProblem(null);
  };

  const roll = async (): Promise<void> => {
    setBusy(true);
    const write = client.post('/v1/builder/ability-roll', { roll: { person_id: personId } }).then((answer) => {
      const rolled = rolledSchema.parse(answer);
      setData({ state: 'ready', options: { ...current, rolled } });
    });
    setProblem(await writeProblem(write, 'The scores weren’t rolled'));
    setBusy(false);
  };

  const save = async (): Promise<void> => {
    setBusy(true);
    const write = client
      .post('/v1/builder/abilities', { abilities: { person_id: personId, method, scores } })
      .then((answer) => {
        const saved = builderSchema.parse(answer).builder;
        setData({ state: 'ready', options: saved });
        onDone?.(saved);
      });
    setProblem(await writeProblem(write, 'The scores weren’t saved'));
    setBusy(false);
  };

  return (
    <section aria-label='Ability scores' className='space-y-3'>
      <div role='radiogroup' aria-label='Method' className='flex flex-wrap gap-2'>
        {(Object.keys(METHOD_NAMES) as Method[]).map((one) => (
          <Button
            key={one}
            type='button'
            role='radio'
            aria-checked={method === one}
            variant={method === one ? 'default' : 'outline'}
            className='min-h-11'
            onClick={() => choose(one)}
          >
            {METHOD_NAMES[one]}
          </Button>
        ))}
      </div>
      {method === 'roll' && (!current.rolled || current.rolled.used) && (
        <Button type='button' className='min-h-11' disabled={busy} onClick={() => void roll()}>
          Roll {current.methods.roll.formula.replace('kh3', ', keep 3')} × {current.methods.roll.count}
        </Button>
      )}
      {method === 'roll' && current.rolled && !current.rolled.used && (
        <p className='text-sm'>Rolled: {current.rolled.scores.join(', ')}</p>
      )}
      {method === 'point_buy' && (
        <p className='text-sm' aria-live='polite'>
          Points spent: {spent} of {current.methods.point_buy.pool}
        </p>
      )}
      {pool.length > 0 && (
        <div className='grid grid-cols-2 gap-2 sm:grid-cols-3'>
          {current.abilities.map((one) => {
            const others = current.abilities.filter((other) => other.slug !== one.slug).map((other) => scores[other.slug]);
            const free = method === 'point_buy' ? pool : remaining(pool, others);
            const choices = [...new Set(free)].sort((a, b) => b - a);
            return (
              <label key={one.slug} className='flex flex-col text-sm'>
                {one.name}
                <select
                  className='border-input bg-background h-11 rounded-md border px-2'
                  value={scores[one.slug] ?? ''}
                  onChange={(event) =>
                    setScores((before) => ({
                      ...before,
                      [one.slug]: event.target.value === '' ? undefined : Number(event.target.value),
                    }))
                  }
                >
                  <option value=''>–</option>
                  {choices.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
            );
          })}
        </div>
      )}
      <Button
        type='button'
        className='min-h-11'
        disabled={busy || !complete || pool.length === 0}
        onClick={() => void save()}
      >
        Save scores
      </Button>
      {problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {problem}
        </p>
      )}
    </section>
  );
}
