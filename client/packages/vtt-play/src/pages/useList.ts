// SPDX-License-Identifier: AGPL-3.0-or-later
import { useCallback, useEffect, useState } from 'react';
import { useClient } from 'zephyrex';
import type { z } from 'zod';

export type ListState<T> = { state: 'loading' } | { state: 'failed'; error: Error } | { state: 'ready'; rows: T[] };

/** A collection read once through the framework client, in the four states pages show. */
export function useList<T>(path: string, key: string, schema: z.ZodType<T>, params: Record<string, string> = {}) {
  const client = useClient();
  const [data, setData] = useState<ListState<T>>({ state: 'loading' });
  const query = JSON.stringify(params);
  const read = useCallback(
    (): Promise<void> =>
      client
        .list(path, key, schema, JSON.parse(query) as Record<string, string>)
        .then((rows: T[]) => setData({ state: 'ready', rows }))
        .catch((error: unknown) =>
          setData({ state: 'failed', error: error instanceof Error ? error : new Error(String(error)) }),
        ),
    [client, path, key, schema, query],
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
