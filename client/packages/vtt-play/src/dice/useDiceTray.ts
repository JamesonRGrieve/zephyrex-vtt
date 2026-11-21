// SPDX-License-Identifier: AGPL-3.0-or-later
import { useCallback, useEffect, useState } from 'react';
import { useClient, writeProblem } from 'zephyrex';
import {
  rollResultSchema,
  testOptionsSchema,
  testResultSchema,
  type RollResult,
  type TestOptions,
  type TestResult,
} from './schemas';

/** What the tray can offer: still loading, failed to load, no rules pack (formulas only), or ready. */
export type OptionsState =
  | { state: 'loading' }
  | { state: 'failed'; error: Error }
  | { state: 'formula-only' }
  | { state: 'ready'; options: TestOptions };

export interface TestInput {
  name: string;
  difficulty?: string;
  modifiers?: number[];
  /** Which one of a specialist skill ([redacted]: "[redacted]"). */
  specialisation?: string;
}

function status(error: unknown): number | undefined {
  const found = (error as { status?: unknown } | null)?.status;
  return typeof found === 'number' ? found : undefined;
}

/**
 * The dice tray's data: a character's test choices under the campaign's rules pack, and the two
 * rolls (a test, a formula), both rolled on the server (rpg_dice). A campaign whose system has no
 * pack answers 422 for the choices, and the tray then offers formulas only.
 */
export function useDiceTray(personId: string) {
  const client = useClient();
  const [options, setOptions] = useState<OptionsState>({ state: 'loading' });
  const [result, setResult] = useState<TestResult | RollResult | null>(null);
  // A new seed with each result: the dice's tumble, shared by every seat that replays it.
  const [seed, setSeed] = useState(0);
  const show = (next: TestResult | RollResult): void => {
    setResult(next);
    setSeed(Math.floor(Math.random() * 2 ** 31));
  };
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const fetchOptions = useCallback(
    (): Promise<void> =>
      client
        .post('/v1/dice/test-options', { options: { person_id: personId } })
        .then((answer: unknown) => setOptions({ state: 'ready', options: testOptionsSchema.parse(answer).options }))
        .catch((error: unknown) =>
          setOptions(
            status(error) === 422
              ? { state: 'formula-only' }
              : { state: 'failed', error: error instanceof Error ? error : new Error(String(error)) },
          ),
        ),
    [client, personId],
  );

  useEffect(() => {
    void fetchOptions();
  }, [fetchOptions]);

  const retry = (): Promise<void> => {
    setOptions({ state: 'loading' });
    return fetchOptions();
  };

  const run = async (write: Promise<void>, fallback: string): Promise<void> => {
    setBusy(true);
    setProblem(await writeProblem(write, fallback));
    setBusy(false);
  };

  return {
    options,
    retry,
    result,
    seed,
    problem,
    busy,
    test: (input: TestInput) =>
      run(
        client
          .post('/v1/dice/test', { test: { person_id: personId, modifiers: [], ...input } })
          .then((answer: unknown) => show(testResultSchema.parse(answer).test)),
        'The test was not rolled',
      ),
    roll: (formula: string) =>
      run(
        client
          .post('/v1/dice/roll', { roll: { formula } })
          .then((answer: unknown) => show(rollResultSchema.parse(answer).roll)),
        'The dice were not rolled',
      ),
  };
}
