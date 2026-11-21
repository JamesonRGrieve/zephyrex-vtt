// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * A table's seats: who sits at it, who plays each seat, and the seat actions. The table's host (its
 * GM) seats any of the campaign's characters, NPCs included, and clears seats; a player seats their
 * own characters. From your own seat you can open a whisper with another. Each character links to
 * its wiki page when the app gives `personHref` (the VTT includes the wiki; rpg-ai composes it).
 */
import { type ReactNode } from 'react';
import { Button } from 'zephyrex/ui/button';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import type { Person, Seat } from './schemas';
import { useTableSeats } from './useTableSeats';

export interface SeatListProps {
  /** The table, by its conversation (rpg_table's key). */
  conversationId: string;
  /** A character's wiki page, for its name to link to. */
  personHref?: (personId: string) => string | null;
  /** A whisper was opened: its conversation, for the app to show. */
  onWhisper?: (conversationId: string) => void;
}

function Name({ seat, href }: { seat: Seat; href: string | null }): ReactNode {
  const name = seat.name ?? 'Unnamed';
  return href ? (
    <a href={href} className='font-medium underline-offset-4 hover:underline'>
      {name}
    </a>
  ) : (
    <span className='font-medium'>{name}</span>
  );
}

export function SeatList({ conversationId, personHref, onWhisper }: SeatListProps): ReactNode {
  const table = useTableSeats(conversationId);
  const { data } = table;
  if (data.state === 'loading') return <SkeletonRows rows={3} avatar label='Loading the seats' />;
  if (data.state === 'failed') return <LoadProblem what='the seats' error={data.error} onRetry={table.retry} />;

  const mine = data.seats.find((seat) => table.me !== null && seat.controller_id === table.me) ?? null;
  const seated = new Set(data.seats.map((seat) => seat.person_id));
  const seatable = data.people.filter(
    (person: Person) => !seated.has(person.id) && (table.host || (table.me !== null && person.user_id === table.me)),
  );

  return (
    <section aria-label='Seats' className='space-y-3'>
      {data.seats.length === 0 ? (
        <p className='text-muted-foreground text-sm'>No one is seated yet.</p>
      ) : (
        <ul className='divide-border divide-y'>
          {data.seats.map((seat) => (
            <li key={seat.id} className='flex min-h-11 flex-wrap items-center gap-2 py-2'>
              <Name seat={seat} href={seat.person_id ? (personHref?.(seat.person_id) ?? null) : null} />
              <span className='text-muted-foreground text-xs'>
                {seat === mine ? 'You' : seat.controller_id ? 'Player' : 'NPC'}
              </span>
              <span className='ms-auto flex gap-2'>
                {/* From your seat to any other: a player whispers to an NPC to talk privately with the GM. */}
                {mine && seat !== mine && (
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    className='min-h-11'
                    disabled={table.busy}
                    onClick={() => {
                      void table.whisper(mine, seat).then((opened) => {
                        if (opened) onWhisper?.(opened);
                      });
                    }}
                  >
                    Whisper
                  </Button>
                )}
                {(table.host || seat === mine) && (
                  <Button
                    type='button'
                    variant='ghost'
                    size='sm'
                    className='min-h-11'
                    disabled={table.busy}
                    aria-label={`Clear ${seat.name ?? 'this'} seat`}
                    onClick={() => void table.unseat(seat)}
                  >
                    Clear
                  </Button>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      {seatable.length > 0 && (
        <div className='space-y-2'>
          <h3 className='text-sm font-medium'>{table.host ? 'Seat a character' : 'Take a seat'}</h3>
          <div className='flex flex-wrap gap-2'>
            {seatable.map((person) => (
              <Button
                key={person.id}
                type='button'
                variant='secondary'
                size='sm'
                className='min-h-11'
                disabled={table.busy}
                onClick={() => void table.seat(person)}
              >
                {person.name ?? 'Unnamed'}
                {person.user_id ? '' : ' (NPC)'}
              </Button>
            ))}
          </div>
        </div>
      )}
      {table.problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {table.problem}
        </p>
      )}
    </section>
  );
}
