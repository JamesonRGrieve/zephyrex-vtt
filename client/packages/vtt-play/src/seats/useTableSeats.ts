// SPDX-License-Identifier: AGPL-3.0-or-later
import { useCallback, useEffect, useState } from 'react';
import { useClient, useUser, writeProblem } from 'zephyrex';
import { personSchema, seatSchema, tableSchema, whisperSchema, type Person, type Seat, type Table } from './schemas';

/** How often a table's seats are read again while it's open, until live rooms replace polling. */
export const FEED_MS = 2000;

export type SeatsState =
  | { state: 'loading' }
  | { state: 'failed'; error: Error }
  | { state: 'ready'; table: Table; seats: Seat[]; people: Person[] };

function asError(error: unknown): Error {
  return error instanceof Error ? error : new Error(String(error));
}

/**
 * A table's seats, the campaign's characters who could take one, and the seat actions; read again
 * every FEED_MS while the page is visible (useTableFeed's polling, until the framework's live rooms
 * reach the client). The server decides every permission; `host` only decides which buttons show.
 */
export function useTableSeats(conversationId: string) {
  const client = useClient();
  const user = useUser();
  const [data, setData] = useState<SeatsState>({ state: 'loading' });
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const read = useCallback(async (): Promise<void> => {
    try {
      const tables = await client.list('/v1/table', 'tables', tableSchema, { conversation_id: conversationId });
      const table = tables[0];
      if (!table) throw new Error('This table no longer exists');
      const [seats, people] = await Promise.all([
        client.list('/v1/table_seat', 'table_seats', seatSchema, { conversation_id: conversationId }),
        table.campaign_id ? client.list('/v1/person', 'persons', personSchema, { campaign_id: table.campaign_id }) : [],
      ]);
      setData({ state: 'ready', table, seats, people });
    } catch (error) {
      setData((current) => (current.state === 'ready' ? current : { state: 'failed', error: asError(error) }));
    }
  }, [client, conversationId]);

  useEffect(() => {
    void read();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void read();
    }, FEED_MS);
    return () => window.clearInterval(timer);
  }, [read]);

  const me = user.data?.id ?? null;
  const host = data.state === 'ready' && (me === null ? !user.error : data.table.created_by_user_id === me);

  const act = async (write: Promise<unknown>, fallback: string): Promise<void> => {
    setBusy(true);
    setProblem(
      await writeProblem(
        write.then(() => read()),
        fallback,
      ),
    );
    setBusy(false);
  };

  return {
    data,
    me,
    host,
    busy,
    problem,
    retry: (): Promise<void> => {
      setData({ state: 'loading' });
      return read();
    },
    seat: (person: Person) =>
      act(
        client.post('/v1/table_seat', {
          table_seat: { conversation_id: conversationId, person_id: person.id, npc: !person.user_id },
        }),
        `${person.name ?? 'That character'} was not seated`,
      ),
    unseat: (seat: Seat) =>
      act(client.delete(`/v1/table_seat/${seat.id}`, seat), `${seat.name ?? 'That seat'} was not cleared`),
    whisper: async (from: Seat, to: Seat): Promise<string | null> => {
      let opened: string | null = null;
      await act(
        client
          .post('/v1/table_whisper', {
            table_whisper: { table_conversation_id: conversationId, from_seat_id: from.id, to_seat_id: to.id },
          })
          .then((answer: unknown) => {
            opened = whisperSchema.parse(answer).table_whisper.conversation_id ?? null;
          }),
        `The whisper to ${to.name ?? 'that seat'} was not opened`,
      );
      return opened;
    },
  };
}
