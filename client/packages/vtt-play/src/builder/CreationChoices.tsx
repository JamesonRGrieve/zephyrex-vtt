// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * Character creation's choices (rpg_builder), in the pack's own steps (the 5e SRD: 1 Choose a Class;
 * 2 Character Origin, a background and a species). Each choice lists what the campaign offers; the
 * player picks once (the GM may change a pick), and the server checks and records it. Steps without
 * choices (ability scores: AbilityScores) are listed for orientation only.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import { useClient, writeProblem } from 'zephyrex';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import { z } from 'zod';

const optionSchema = z.object({ trait_id: z.string(), name: z.string(), description: z.string().nullish() });
const choicesSchema = z.object({
  builder: z.object({
    person_id: z.string(),
    system: z.string(),
    gm: z.boolean(),
    steps: z.array(
      z.object({
        step: z.number(),
        name: z.string(),
        choices: z
          .array(z.object({ kind: z.string(), chosen: optionSchema.nullable(), options: z.array(optionSchema) }))
          .default([]),
      }),
    ),
  }),
});

export type CreationSteps = z.infer<typeof choicesSchema>['builder'];

export interface CreationChoicesProps {
  personId: string;
  /** Called with the steps after each recorded choice. */
  onChange?: (steps: CreationSteps) => void;
}

function label(kind: string): string {
  return kind.charAt(0).toUpperCase() + kind.slice(1).replace(/-/g, ' ');
}

export function CreationChoices({ personId, onChange }: CreationChoicesProps): ReactNode {
  const client = useClient();
  const [data, setData] = useState<
    { state: 'loading' } | { state: 'failed'; error: Error } | { state: 'ready'; steps: CreationSteps }
  >({
    state: 'loading',
  });
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const read = useCallback(async (): Promise<void> => {
    try {
      const answer = await client.post('/v1/builder/choices', { choices: { person_id: personId } });
      setData({ state: 'ready', steps: choicesSchema.parse(answer).builder });
    } catch (error) {
      setData({ state: 'failed', error: error instanceof Error ? error : new Error(String(error)) });
    }
  }, [client, personId]);

  useEffect(() => {
    const first = window.setTimeout(() => void read(), 0);
    return () => window.clearTimeout(first);
  }, [read]);

  if (data.state === 'loading') return <SkeletonRows rows={4} label='Loading character creation' />;
  if (data.state === 'failed') return <LoadProblem what='character creation' error={data.error} onRetry={read} />;
  const { steps, gm } = data.steps;

  const choose = async (kind: string, traitId: string): Promise<void> => {
    setBusy(true);
    const write = client
      .post('/v1/builder/choose', { choose: { person_id: personId, kind, trait_id: traitId } })
      .then((answer) => {
        const next = choicesSchema.parse(answer).builder;
        setData({ state: 'ready', steps: next });
        onChange?.(next);
      });
    setProblem(await writeProblem(write, `The ${kind} wasn’t recorded`));
    setBusy(false);
  };

  return (
    <section aria-label='Character creation' className='space-y-4'>
      <ol className='space-y-3'>
        {steps.map((step) => (
          <li key={step.step} className='space-y-2'>
            <p className='font-medium'>
              {step.step}. {step.name}
            </p>
            {step.choices.map((choice) => {
              const locked = choice.chosen !== null && !gm;
              const id = `creation-${choice.kind}`;
              return (
                <div key={choice.kind} className='space-y-1'>
                  <label htmlFor={id} className='text-sm'>
                    {label(choice.kind)}
                  </label>
                  {locked ? (
                    <p id={id} className='text-sm font-semibold'>
                      {choice.chosen?.name}
                    </p>
                  ) : choice.options.length === 0 ? (
                    <p id={id} className='text-muted-foreground text-sm'>
                      This campaign offers no {choice.kind} yet.
                    </p>
                  ) : (
                    <select
                      id={id}
                      className='border-input bg-background h-11 w-full rounded-md border px-2'
                      value={choice.chosen?.trait_id ?? ''}
                      disabled={busy}
                      onChange={(event) => {
                        if (event.target.value) void choose(choice.kind, event.target.value);
                      }}
                    >
                      <option value=''>Choose a {choice.kind}…</option>
                      {choice.options.map((option) => (
                        <option key={option.trait_id} value={option.trait_id}>
                          {option.name}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              );
            })}
          </li>
        ))}
      </ol>
      {problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {problem}
        </p>
      )}
    </section>
  );
}
