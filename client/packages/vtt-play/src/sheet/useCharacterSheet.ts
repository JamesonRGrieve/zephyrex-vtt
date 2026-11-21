// SPDX-License-Identifier: AGPL-3.0-or-later
import { useCallback, useEffect, useState } from 'react';
import { useClient } from 'zephyrex';
import { sheetSchema, type Sheet } from './schemas';

export type SheetState =
  { state: 'loading' } | { state: 'failed'; error: Error } | { state: 'empty' } | { state: 'ready'; sheet: Sheet };

function status(error: unknown): number | undefined {
  const found = (error as { status?: unknown } | null)?.status;
  return typeof found === 'number' ? found : undefined;
}

/**
 * A character's sheet from the server (POST /v1/dice/sheet). No characteristics yet, a character
 * this person can't read (404) or one outside a campaign (422) is the empty state, never an error.
 */
export function useCharacterSheet(personId: string) {
  const client = useClient();
  const [data, setData] = useState<SheetState>({ state: 'loading' });

  const read = useCallback(
    (): Promise<void> =>
      client
        .post('/v1/dice/sheet', { sheet: { person_id: personId } })
        .then((answer: unknown) => {
          const sheet = sheetSchema.parse(answer).sheet;
          setData(sheet.has_sheet ? { state: 'ready', sheet } : { state: 'empty' });
        })
        .catch((error: unknown) => {
          const code = status(error);
          setData(
            code === 404 || code === 422
              ? { state: 'empty' }
              : { state: 'failed', error: error instanceof Error ? error : new Error(String(error)) },
          );
        }),
    [client, personId],
  );

  useEffect(() => {
    const first = window.setTimeout(() => void read(), 0);
    return () => window.clearTimeout(first);
  }, [read]);

  return {
    data,
    retry: (): Promise<void> => {
      setData({ state: 'loading' });
      return read();
    },
  };
}
