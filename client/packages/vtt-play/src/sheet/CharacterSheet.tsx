// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * A character's sheet, read-only: characteristics, wounds and fate (and the line's other tracks),
 * skills with their rank and specialisation, origin steps, talents and other abilities, and gear.
 * Without a sheet yet (a pregen before its import), it says so instead of failing.
 */
import { type ReactNode } from 'react';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import type { SheetEntry } from './schemas';
import { useCharacterSheet } from './useCharacterSheet';

export interface CharacterSheetProps {
  personId: string;
}

function label(entry: SheetEntry): string {
  return entry.specialisation ? `${entry.name} (${entry.specialisation})` : entry.name;
}

function Section({ title, children }: { title: string; children: ReactNode }): ReactNode {
  return (
    <section aria-label={title} className='space-y-2'>
      <h3 className='text-sm font-semibold'>{title}</h3>
      {children}
    </section>
  );
}

export function CharacterSheet({ personId }: CharacterSheetProps): ReactNode {
  const { data, retry } = useCharacterSheet(personId);
  if (data.state === 'loading') return <SkeletonRows rows={5} label='Loading the character sheet' />;
  if (data.state === 'failed') return <LoadProblem what='the character sheet' error={data.error} onRetry={retry} />;
  if (data.state === 'empty') return <p className='text-muted-foreground text-sm'>No character sheet yet.</p>;
  const { sheet } = data;

  return (
    <article aria-label={sheet.name ? `${sheet.name}’s sheet` : 'Character sheet'} className='space-y-5'>
      <Section title='Characteristics'>
        <dl className='grid grid-cols-3 gap-2 sm:grid-cols-5'>
          {sheet.characteristics.map((one) => (
            <div key={one.trait_id} className='border-border rounded-md border p-2 text-center'>
              <dt className='text-muted-foreground text-xs'>{one.name}</dt>
              <dd className='text-lg font-semibold'>{one.value ?? '—'}</dd>
            </div>
          ))}
        </dl>
      </Section>
      {sheet.resources.length > 0 && (
        <Section title='Wounds, fate and tracks'>
          <dl className='flex flex-wrap gap-x-6 gap-y-1'>
            {sheet.resources.map((one) => (
              <div key={one.trait_id} className='flex gap-2'>
                <dt className='text-muted-foreground'>{one.name}</dt>
                <dd className='font-medium'>{one.value ?? '—'}</dd>
              </div>
            ))}
          </dl>
        </Section>
      )}
      {sheet.skills.length > 0 && (
        <Section title='Skills'>
          <ul className='divide-border divide-y'>
            {sheet.skills.map((one) => (
              <li key={`${one.trait_id}:${one.specialisation ?? ''}`} className='flex justify-between py-1'>
                <span>{label(one)}</span>
                <span className='text-muted-foreground'>{one.rank ? `Rank ${one.rank}` : 'Untrained'}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}
      {sheet.origins.length > 0 && (
        <Section title='Origin'>
          <p>{sheet.origins.map(label).join(' · ')}</p>
        </Section>
      )}
      {sheet.abilities.length > 0 && (
        <Section title='Talents and abilities'>
          <ul className='flex flex-wrap gap-2'>
            {sheet.abilities.map((one) => (
              <li key={`${one.trait_id}:${one.specialisation ?? ''}`} className='bg-muted rounded-md px-2 py-1 text-sm'>
                {label(one)}
              </li>
            ))}
          </ul>
        </Section>
      )}
      <Section title='Gear'>
        {sheet.gear.length === 0 ? (
          <p className='text-muted-foreground text-sm'>No gear yet.</p>
        ) : (
          <ul className='list-disc ps-5'>
            {sheet.gear.map((one) => (
              <li key={one.id}>
                {one.name ?? 'Unnamed item'}
                {one.quantity > 1 ? ` ×${one.quantity}` : ''}
              </li>
            ))}
          </ul>
        )}
      </Section>
    </article>
  );
}
