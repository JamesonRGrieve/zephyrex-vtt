// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * The dice rack: tap a die to add it, build the pool with a modifier and (on a lone d20) Advantage
 * or Disadvantage, and roll the formula it makes on the server. A typed formula is there for
 * anything the rack doesn't build. Phone-first: every target is at least 44 px.
 */
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { chipGroup } from 'zephyrex/hooks/chipKeys';
import { Button } from 'zephyrex/ui/button';
import { ChoiceChip } from 'zephyrex/ui/choice-chip';
import { Input } from 'zephyrex/ui/input';
import { Label } from 'zephyrex/ui/label';
import { add, canEdge, count, formulaOf, isEmpty, remove, SIDES, type Edge, type Pool, type Sides } from './pool';

/** Each die's outline, as the solid looks face-on (a 24-unit box). */
const OUTLINES: Record<Sides, string> = {
  4: '12,3 22,20 2,20',
  6: '4,4 20,4 20,20 4,20',
  8: '12,2 22,12 12,22 2,12',
  10: '12,2 21,10 12,22 3,10',
  12: '12,2 21.5,9 18,20.5 6,20.5 2.5,9',
  20: '12,2 21,7 21,17 12,22 3,17 3,7',
  100: '12,2 21,10 12,22 3,10',
};

function DieShape({ sides }: { sides: Sides }): ReactNode {
  return (
    <svg viewBox='0 0 24 24' aria-hidden='true' className='size-7'>
      <polygon
        points={OUTLINES[sides]}
        className='fill-primary/15 stroke-primary'
        strokeWidth='1.5'
        strokeLinejoin='round'
      />
      {sides === 100 && <polygon points='12,6 17,11 12,18 7,11' className='fill-none stroke-primary' strokeWidth='1' />}
    </svg>
  );
}

const EDGES: { edge: Edge; label: string }[] = [
  { edge: 'none', label: 'Normal' },
  { edge: 'advantage', label: 'Advantage' },
  { edge: 'disadvantage', label: 'Disadvantage' },
];

export interface DiceRackProps {
  pool: Pool;
  onChange: (pool: Pool) => void;
  onRoll: (formula: string) => void;
  busy: boolean;
}

export function DiceRack({ pool, onChange, onRoll, busy }: DiceRackProps): ReactNode {
  const formula = formulaOf(pool);
  const [typed, setTyped] = useState('');
  const edges = useRef<HTMLDivElement>(null);
  const edgeable = canEdge(pool);
  useEffect(() => chipGroup(edges.current), [edgeable]);
  return (
    <div className='space-y-3'>
      <div role='group' aria-label='Dice rack' className='grid grid-cols-4 gap-2 sm:grid-cols-7'>
        {SIDES.map((sides) => {
          const many = count(pool, sides);
          return (
            // The count sits beside the button, not in it, so the button's name is its visible text.
            <div key={sides} className='relative'>
              <button
                type='button'
                onClick={() => onChange(add(pool, sides))}
                aria-label={`Add a d${sides}`}
                className='border-input bg-card hover:bg-accent focus-visible:ring-ring flex min-h-14 w-full flex-col items-center justify-center rounded-lg border text-sm font-medium focus-visible:ring-2 focus-visible:outline-none'
              >
                <DieShape sides={sides} />
                <span>d{sides}</span>
              </button>
              {many > 0 && (
                <span
                  aria-hidden='true'
                  className='bg-primary text-primary-foreground pointer-events-none absolute top-1 right-1 rounded-full px-1.5 text-xs'
                >
                  {many}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {!isEmpty(pool) && (
        <ul aria-label='In the pool' className='flex flex-wrap gap-2'>
          {SIDES.filter((sides) => count(pool, sides) > 0).map((sides) => (
            <li key={sides} className='bg-muted flex items-center gap-1 rounded-full pl-3 text-sm'>
              {count(pool, sides)}d{sides}
              <button
                type='button'
                onClick={() => onChange(remove(pool, sides))}
                aria-label={`Remove a d${sides}`}
                className='hover:bg-accent flex size-11 items-center justify-center rounded-full'
              >
                <span aria-hidden='true'>−</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className='flex flex-wrap items-center gap-3'>
        <div className='flex items-center gap-1' role='group' aria-label='Modifier'>
          <Button
            type='button'
            variant='outline'
            className='size-11'
            aria-label='Lower the modifier'
            onClick={() => onChange({ ...pool, modifier: pool.modifier - 1 })}
          >
            −
          </Button>
          <span data-testid='dice-modifier' className='min-w-12 text-center text-lg font-semibold tabular-nums'>
            {pool.modifier > 0 ? `+${pool.modifier}` : pool.modifier}
          </span>
          <Button
            type='button'
            variant='outline'
            className='size-11'
            aria-label='Raise the modifier'
            onClick={() => onChange({ ...pool, modifier: pool.modifier + 1 })}
          >
            +
          </Button>
        </div>
        {edgeable && (
          <div ref={edges} role='radiogroup' aria-label='Advantage on the d20' className='flex flex-wrap gap-2'>
            {EDGES.map((one) => (
              <ChoiceChip
                key={one.edge}
                checked={pool.edge === one.edge}
                onClick={() => onChange({ ...pool, edge: one.edge })}
              >
                {one.label}
              </ChoiceChip>
            ))}
          </div>
        )}
      </div>

      <div className='flex flex-wrap gap-2'>
        <Button type='button' className='min-h-11 flex-1' disabled={busy || isEmpty(pool)} onClick={() => onRoll(formula)}>
          {isEmpty(pool) ? 'Pick some dice' : `Roll ${formula}`}
        </Button>
        <Button
          type='button'
          variant='outline'
          className='min-h-11'
          disabled={isEmpty(pool) && pool.modifier === 0}
          onClick={() => onChange({ counts: {}, modifier: 0, edge: 'none' })}
        >
          Clear
        </Button>
      </div>

      <details className='text-sm'>
        <summary className='text-muted-foreground flex min-h-11 cursor-pointer items-center'>Type a formula</summary>
        <form
          className='flex flex-wrap items-end gap-2'
          onSubmit={(event) => {
            event.preventDefault();
            if (typed.trim()) onRoll(typed.trim());
          }}
        >
          <div className='min-w-0 flex-1 space-y-1'>
            <Label htmlFor='dice-tray-formula'>Formula</Label>
            <Input
              id='dice-tray-formula'
              value={typed}
              placeholder='4d6kh3'
              onChange={(event) => setTyped(event.target.value)}
            />
          </div>
          <Button type='submit' disabled={busy || !typed.trim()} className='min-h-11'>
            Roll it
          </Button>
        </form>
      </details>
    </div>
  );
}
