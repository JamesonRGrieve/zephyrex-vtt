// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * The dice tray: a test under the campaign's rules pack (a characteristic or skill, a difficulty,
 * modifiers, and for 5e Advantage or Disadvantage) or dice from the rack, rolled on the server;
 * the result as a large card with how it was reached, the dice tumbling in 3D, and the last few
 * rolls. rpg-ai's "Roll it" opens it prefilled (`prefill`). A campaign whose system has no rules
 * pack offers the rack only. DiceTrayView is the tray without its data, for a story.
 */
import { lazy, Suspense, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react';
import { chipGroup } from 'zephyrex/hooks/chipKeys';
import { Button } from 'zephyrex/ui/button';
import { ChoiceChip } from 'zephyrex/ui/choice-chip';
import { Input } from 'zephyrex/ui/input';
import { Label } from 'zephyrex/ui/label';
import { LoadProblem } from 'zephyrex/ui/load-problem';
import { SkeletonRows } from 'zephyrex/ui/skeleton';
import type { RollResult, TestOptions, TestResult } from './schemas';
import { canDrawDice } from '../dice3d/canDraw';
import { useDiceAnimation } from '../dice3d/useDiceAnimation';
import { DiceRack } from './DiceRack';
import { poolOf, type Pool } from './pool';
import { useDiceTray, type TestInput } from './useDiceTray';

// three.js and cannon-es load only when a tray first shows a result.
const DiceStage = lazy(() => import('../dice3d/DiceStage'));

export interface DiceTrayProps {
  personId: string;
  prefill?: TestInput;
  onResult?: (result: TestResult | RollResult) => void;
}

export type DiceTrayState = ReturnType<typeof useDiceTray>;

const DIFFICULTY_LABELS: Record<string, string> = { 'very-hard': 'Very hard' };

function label(slug: string): string {
  return DIFFICULTY_LABELS[slug] ?? slug.charAt(0).toUpperCase() + slug.slice(1);
}

function signed(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}

/** "+10, -20" → [10, -20]; null when a part isn't a whole number. */
export function parseModifiers(text: string): number[] | null {
  const parts = text.split(/[\s,]+/).filter(Boolean);
  const numbers = parts.map((part) => Number(part));
  return numbers.every((value) => Number.isInteger(value)) ? numbers : null;
}

function isTest(result: TestResult | RollResult): result is TestResult {
  return 'degrees' in result;
}

/** One die as a chip: a dropped one (kept low or high away) struck through. */
function DieChip({ value, dropped }: { value: number; dropped?: boolean }): ReactNode {
  return (
    <li
      className={`flex size-9 items-center justify-center rounded-md border text-sm font-semibold tabular-nums ${dropped ? 'text-muted-foreground line-through opacity-60' : 'bg-card'}`}
    >
      {value}
      {dropped && <span className='sr-only'> (dropped)</span>}
    </li>
  );
}

/** A roll's result card: the total large, then a test's outcome and how its target was made, or a formula's dice. */
export function DiceResult({ result }: { result: TestResult | RollResult }): ReactNode {
  if (!isTest(result)) {
    return (
      <div role='status' className='bg-card space-y-2 rounded-xl border p-4'>
        <p className='flex items-baseline gap-3'>
          <span className='text-5xl font-bold tabular-nums'>{result.total}</span>{' '}
          <span className='text-muted-foreground'>({result.formula})</span>
        </p>
        {result.terms.some((term) => term.dice.length > 0) && (
          <div className='space-y-1'>
            {result.terms
              .filter((term) => term.dice.length > 0)
              .map((term, index) => (
                <div key={index} className='flex flex-wrap items-center gap-2'>
                  <span className='text-muted-foreground w-16 text-xs'>{term.notation}</span>
                  <ul className='flex flex-wrap gap-1' aria-label={`${term.notation} dice`}>
                    {term.dice.map((die, at) => (
                      <DieChip key={at} value={die.value} dropped={!die.kept} />
                    ))}
                  </ul>
                </div>
              ))}
          </div>
        )}
      </div>
    );
  }
  const outcome = result.success ? 'Success' : 'Failure';
  const tone = result.success ? 'text-primary' : 'text-destructive';
  const degrees = `${result.degrees} degree${result.degrees === 1 ? '' : 's'} of ${result.success ? 'success' : 'failure'}`;
  const added = (result.total ?? result.roll) - result.roll;
  const edged = result.advantage != null && result.rolls.length > 1;
  return (
    <div role='status' className='bg-card space-y-2 rounded-xl border p-4'>
      <p className='flex items-baseline gap-3'>
        <span className='text-5xl font-bold tabular-nums'>{result.total ?? result.roll}</span>
        <span className={`text-2xl font-bold ${tone}`}>{outcome}</span>
      </p>
      {result.test_kind === 'd20-over' ? (
        <p className='text-lg'>
          rolled {result.roll} {added < 0 ? '−' : '+'} {Math.abs(added)} = {result.total ?? result.roll} against DC{' '}
          {result.target}
          {edged ? ` (${result.advantage === 'advantage' ? 'Advantage' : 'Disadvantage'})` : ''}
          {result.natural_roll ? `, a natural ${result.natural_roll}` : ''}
        </p>
      ) : (
        <p className='text-lg'>
          rolled {result.roll} against {result.target}, {degrees}
          {result.natural ? ` (a natural ${result.natural === 'success' ? '1' : '100'})` : ''}
        </p>
      )}
      {edged && (
        <ul className='flex gap-1' aria-label='The d20s rolled'>
          {result.rolls.map((value, at) => (
            <DieChip key={at} value={value} dropped={at !== result.rolls.indexOf(result.roll)} />
          ))}
        </ul>
      )}
      {result.no_sheet && <p className='text-muted-foreground text-sm'>No sheet: tested at the rules’ average.</p>}
      <ul className='text-muted-foreground text-sm'>
        {result.steps.map((one, index) => (
          <li key={index}>
            {one.step.replace('_', ' ')}: {index === 0 ? one.value : signed(one.value)}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** One line for a past roll. */
export function summary(result: TestResult | RollResult): string {
  if (!isTest(result)) return `${result.formula}: ${result.total}`;
  return `${result.name}: ${result.total ?? result.roll}, ${result.success ? 'success' : 'failure'}`;
}

/** The last rolls, newest first. */
export function DiceHistory({ entries }: { entries: (TestResult | RollResult)[] }): ReactNode {
  if (entries.length === 0) return null;
  return (
    <section aria-label='Roll history' className='space-y-1'>
      <h3 className='text-muted-foreground text-xs font-medium tracking-wide uppercase'>Recent rolls</h3>
      <ol className='divide-y rounded-lg border text-sm'>
        {entries.map((entry, index) => (
          <li key={index} className='flex min-h-11 items-center px-3 tabular-nums'>
            {summary(entry)}
          </li>
        ))}
      </ol>
    </section>
  );
}

const EDGES = [
  { edge: undefined, label: 'Normal' },
  { edge: 'advantage', label: 'Advantage' },
  { edge: 'disadvantage', label: 'Disadvantage' },
] as const;

function TestForm({
  options,
  prefill,
  busy,
  onTest,
}: {
  options: TestOptions;
  prefill?: TestInput;
  busy: boolean;
  onTest: (input: TestInput) => void;
}): ReactNode {
  const [name, setName] = useState(prefill?.name ?? options.characteristics[0]?.slug ?? '');
  const [difficulty, setDifficulty] = useState(prefill?.difficulty ?? options.default_difficulty);
  const [modifiers, setModifiers] = useState((prefill?.modifiers ?? []).map(signed).join(', '));
  const [specialisation, setSpecialisation] = useState(prefill?.specialisation ?? '');
  const [edge, setEdge] = useState<TestInput['advantage']>(prefill?.advantage);
  const skill = options.skills.find((one) => one.slug === name);
  const specialist = skill?.untrainable === true;
  const d20 = options.test_kind === 'd20-over';
  const chips = useRef<HTMLDivElement>(null);
  const edges = useRef<HTMLDivElement>(null);
  useEffect(() => chipGroup(chips.current), []);
  useEffect(() => chipGroup(edges.current), [d20]);
  const parsed = parseModifiers(modifiers);
  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if (parsed === null || !name || (specialist && !specialisation.trim())) return;
    onTest({
      name,
      difficulty,
      modifiers: parsed,
      ...(specialist ? { specialisation: specialisation.trim() } : {}),
      ...(d20 && edge ? { advantage: edge } : {}),
    });
  };
  return (
    <form onSubmit={submit} className='space-y-3'>
      {!options.has_sheet && (
        <p className='text-muted-foreground text-sm'>No character sheet yet: tests use the rules’ average.</p>
      )}
      <div className='space-y-1'>
        <Label htmlFor='dice-tray-name'>Test</Label>
        <select
          id='dice-tray-name'
          value={name}
          onChange={(event) => setName(event.target.value)}
          className='border-input bg-background h-11 w-full rounded-md border px-3'
        >
          <optgroup label='Characteristics'>
            {options.characteristics.map((one) => (
              <option key={one.slug} value={one.slug}>
                {one.name}
              </option>
            ))}
          </optgroup>
          <optgroup label='Skills'>
            {options.skills.map((one) => (
              <option key={one.slug} value={one.slug}>
                {one.name}
                {one.untrainable ? ' (trained only)' : ''}
              </option>
            ))}
          </optgroup>
        </select>
      </div>
      {specialist && skill && (
        <div className='space-y-1'>
          <Label htmlFor='dice-tray-specialisation'>Which {skill.name}</Label>
          <Input
            id='dice-tray-specialisation'
            list='dice-tray-specialisations'
            value={specialisation}
            placeholder={skill.specialisations[0] ?? 'Stars'}
            onChange={(event) => setSpecialisation(event.target.value)}
          />
          <datalist id='dice-tray-specialisations'>
            {skill.specialisations.map((one) => (
              <option key={one} value={one} />
            ))}
          </datalist>
        </div>
      )}
      <fieldset className='space-y-1'>
        <legend className='text-sm font-medium'>Difficulty</legend>
        <div ref={chips} role='radiogroup' aria-label='Difficulty' className='flex flex-wrap gap-2'>
          {options.difficulties.map((one) => (
            <ChoiceChip key={one.slug} checked={difficulty === one.slug} onClick={() => setDifficulty(one.slug)}>
              {label(one.slug)} ({one.dc != null ? `DC ${one.dc}` : signed(one.modifier)})
            </ChoiceChip>
          ))}
        </div>
      </fieldset>
      {d20 && (
        <div ref={edges} role='radiogroup' aria-label='Advantage' className='flex flex-wrap gap-2'>
          {EDGES.map((one) => (
            <ChoiceChip key={one.label} checked={edge === one.edge} onClick={() => setEdge(one.edge)}>
              {one.label}
            </ChoiceChip>
          ))}
        </div>
      )}
      <div className='space-y-1'>
        <Label htmlFor='dice-tray-modifiers'>Other modifiers</Label>
        <Input
          id='dice-tray-modifiers'
          value={modifiers}
          placeholder={d20 ? '+2, -1' : '+10, -20'}
          inputMode='numeric'
          aria-invalid={parsed === null}
          aria-describedby='dice-tray-modifiers-help'
          onChange={(event) => setModifiers(event.target.value)}
        />
        <p id='dice-tray-modifiers-help' className='text-muted-foreground text-xs'>
          {parsed === null
            ? 'Whole numbers only, separated by commas.'
            : d20
              ? 'Added to the roll.'
              : 'Added together, then held within ±60.'}
        </p>
      </div>
      <Button
        type='submit'
        disabled={busy || parsed === null || !name || (specialist && !specialisation.trim())}
        className='min-h-11 w-full'
      >
        Roll the test
      </Button>
    </form>
  );
}

/** The free roll's starting dice: a d100 for the percentile packs, else a d20 (5e, or no pack). */
export function defaultFormula(options: TestOptions | null): string {
  return options !== null && options.test_kind === 'd100-under' ? '1d100' : '1d20';
}

function FreeRoll({ tray }: { tray: DiceTrayState }): ReactNode {
  const [pool, setPool] = useState<Pool>(() =>
    poolOf(defaultFormula(tray.options.state === 'ready' ? tray.options.options : null)),
  );
  return (
    <section aria-label='Roll dice' className='space-y-2'>
      <h3 className='text-sm font-medium'>Roll dice</h3>
      <DiceRack pool={pool} onChange={setPool} onRoll={tray.roll} busy={tray.busy} />
    </section>
  );
}

/** The tray with its data passed in: the hook's state (DiceTray) or a story's. */
export function DiceTrayView({ tray, prefill }: { tray: DiceTrayState; prefill?: TestInput }): ReactNode {
  const { result } = tray;
  const motion = useDiceAnimation();
  return (
    <section aria-label='Dice tray' className='space-y-5'>
      {tray.options.state === 'loading' && <SkeletonRows rows={3} label='Loading the test choices' />}
      {tray.options.state === 'failed' && (
        <LoadProblem what='the test choices' error={tray.options.error} onRetry={tray.retry} />
      )}
      {tray.options.state === 'formula-only' && (
        <p className='text-muted-foreground text-sm'>
          {tray.options.reason === 'no-sheet'
            ? 'No character sheet yet: roll a formula'
            : 'This campaign’s game system has no rules pack yet, so roll the dice yourself.'}
        </p>
      )}
      {result !== null && <DiceResult result={result} />}
      {result !== null && canDrawDice() && (
        <Suspense fallback={null}>
          <DiceStage result={result} seed={tray.seed} animate={motion.animate} />
        </Suspense>
      )}
      {tray.problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {tray.problem}
        </p>
      )}
      {tray.options.state === 'ready' && (
        <TestForm options={tray.options.options} prefill={prefill} busy={tray.busy} onTest={tray.test} />
      )}
      {tray.options.state !== 'loading' && <FreeRoll key={tray.options.state} tray={tray} />}
      <DiceHistory entries={tray.history} />
      <label className='text-muted-foreground flex min-h-11 items-center gap-2 text-sm'>
        <input
          type='checkbox'
          checked={motion.chosen}
          disabled={motion.reduced}
          onChange={(event) => motion.choose(event.target.checked)}
          className='size-4'
        />
        {motion.reduced ? 'Dice appear at rest (your system asks for less motion)' : 'Animate dice'}
      </label>
    </section>
  );
}

export function DiceTray({ personId, prefill, onResult }: DiceTrayProps): ReactNode {
  const tray = useDiceTray(personId);
  const { result } = tray;
  useEffect(() => {
    if (result !== null) onResult?.(result);
  }, [result, onResult]);
  return <DiceTrayView tray={tray} prefill={prefill} />;
}
