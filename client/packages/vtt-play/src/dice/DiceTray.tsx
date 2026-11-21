// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';
/**
 * The dice tray: a test under the campaign's rules pack (a characteristic or skill, a difficulty,
 * extra modifiers) or a dice formula, rolled on the server, with the result and how its target was
 * reached. rpg-ai's "Roll it" opens it prefilled (`prefill`). A campaign whose system has no rules
 * pack offers formulas only.
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
import { useDiceTray, type TestInput } from './useDiceTray';

// three.js and cannon-es load only when a tray first shows a result.
const DiceStage = lazy(() => import('../dice3d/DiceStage'));

export interface DiceTrayProps {
  personId: string;
  prefill?: TestInput;
  onResult?: (result: TestResult | RollResult) => void;
}

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

/** A roll's result card: a test's outcome, degrees and the steps that made its target, or a formula's total. */
export function DiceResult({ result }: { result: TestResult | RollResult }): ReactNode {
  if (!isTest(result)) {
    return (
      <p role='status' className='text-lg'>
        <span className='font-semibold'>{result.total}</span>{' '}
        <span className='text-muted-foreground'>({result.formula})</span>
      </p>
    );
  }
  const outcome = result.success ? 'Success' : 'Failure';
  const degrees = `${result.degrees} degree${result.degrees === 1 ? '' : 's'} of ${result.success ? 'success' : 'failure'}`;
  return (
    <div role='status' className='space-y-1'>
      <p className='text-lg'>
        <span className='font-semibold'>{outcome}</span>: rolled {result.roll} against {result.target}, {degrees}
        {result.natural ? ` (a natural ${result.natural === 'success' ? '1' : '100'})` : ''}
      </p>
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
  const skill = options.skills.find((one) => one.slug === name);
  const specialist = skill?.untrainable === true;
  const chips = useRef<HTMLDivElement>(null);
  useEffect(() => chipGroup(chips.current), []);
  const parsed = parseModifiers(modifiers);
  const submit = (event: FormEvent): void => {
    event.preventDefault();
    if (parsed === null || !name || (specialist && !specialisation.trim())) return;
    onTest({ name, difficulty, modifiers: parsed, ...(specialist ? { specialisation: specialisation.trim() } : {}) });
  };
  return (
    <form onSubmit={submit} className='space-y-3'>
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
            placeholder={skill.specialisations[0] ?? '[redacted]'}
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
              {label(one.slug)} ({signed(one.modifier)})
            </ChoiceChip>
          ))}
        </div>
      </fieldset>
      <div className='space-y-1'>
        <Label htmlFor='dice-tray-modifiers'>Other modifiers</Label>
        <Input
          id='dice-tray-modifiers'
          value={modifiers}
          placeholder='+10, -20'
          inputMode='numeric'
          aria-invalid={parsed === null}
          aria-describedby='dice-tray-modifiers-help'
          onChange={(event) => setModifiers(event.target.value)}
        />
        <p id='dice-tray-modifiers-help' className='text-muted-foreground text-xs'>
          {parsed === null ? 'Whole numbers only, separated by commas.' : 'Added together, then held within ±60.'}
        </p>
      </div>
      <Button
        type='submit'
        disabled={busy || parsed === null || !name || (specialist && !specialisation.trim())}
        className='min-h-11'
      >
        Roll the test
      </Button>
    </form>
  );
}

function FormulaForm({ busy, onRoll }: { busy: boolean; onRoll: (formula: string) => void }): ReactNode {
  const [formula, setFormula] = useState('1d100');
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (formula.trim()) onRoll(formula.trim());
      }}
      className='flex flex-wrap items-end gap-2'
    >
      <div className='min-w-0 flex-1 space-y-1'>
        <Label htmlFor='dice-tray-formula'>Dice</Label>
        <Input id='dice-tray-formula' value={formula} onChange={(event) => setFormula(event.target.value)} />
      </div>
      <Button type='submit' disabled={busy || !formula.trim()} className='min-h-11'>
        Roll
      </Button>
    </form>
  );
}

export function DiceTray({ personId, prefill, onResult }: DiceTrayProps): ReactNode {
  const tray = useDiceTray(personId);
  const { result } = tray;
  const motion = useDiceAnimation();
  useEffect(() => {
    if (result !== null) onResult?.(result);
  }, [result, onResult]);
  return (
    <section aria-label='Dice tray' className='space-y-4'>
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
      {tray.options.state === 'ready' && (
        <TestForm options={tray.options.options} prefill={prefill} busy={tray.busy} onTest={tray.test} />
      )}
      {tray.options.state !== 'loading' && <FormulaForm busy={tray.busy} onRoll={tray.roll} />}
      {tray.problem !== null && (
        <p role='alert' className='text-destructive text-sm'>
          {tray.problem}
        </p>
      )}
      {result !== null && <DiceResult result={result} />}
      {result !== null && canDrawDice() && (
        <Suspense fallback={null}>
          <DiceStage result={result} seed={tray.seed} animate={motion.animate} />
        </Suspense>
      )}
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
