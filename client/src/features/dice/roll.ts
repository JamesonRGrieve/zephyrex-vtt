// SPDX-License-Identifier: AGPL-3.0-or-later
/**
 * Dice notation: the lite edition's twin of server/extensions/rpg_dice/Dice.py. Both parse the same
 * grammar, apply modifiers in the same order and answer contract/roll-cases.json the same way, so a
 * roll means the same thing on either back end. The grammar and its rules are documented there.
 */

export const MAX_FORMULA_LENGTH = 200;
export const MAX_DICE_PER_TERM = 100;
export const MAX_EXPLOSIONS_PER_TERM = 20;
export const MAX_SIDES = 10_000;
export const MAX_INTEGER = 1_000_000;
export const MAX_NESTING = 10;
const FATE_FACES = 3;

/** A draw source: given a die's sides, a face from 1 to sides. */
export type Draw = (sides: number) => number;

export interface Die {
  value: number;
  kept: boolean;
  /** Why it isn't counted, or how it came to be: rerolled, reroll, exploded, dropped. */
  note?: string;
}

export interface Term {
  notation: string;
  dice: Die[];
  value: number;
}

export interface Roll {
  formula: string;
  total: number;
  terms: Term[];
  stats: Record<string, number>;
}

/** A formula that can't be rolled. `code` is the same in both twins; `message` is for people. */
export class DiceError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = 'DiceError';
  }
}

const TOKEN = /\s*(?:(\d+)|(cs>=)|(r<)|(kh|kl|dh|dl)|(@[A-Za-z_][A-Za-z0-9_]*)|([-+*/()%!dF]))/y;
const KEEP_DROP = new Set(['kh', 'kl', 'dh', 'dl']);
const MODIFIERS = new Set(['kh', 'kl', 'dh', 'dl', '!', 'r<', 'cs>=']);
const DIGITS = /^\d+$/;

function tokenize(formula: string): string[] {
  const tokens: string[] = [];
  let position = 0;
  while (position < formula.length) {
    if (formula.slice(position).trim() === '') break;
    TOKEN.lastIndex = position;
    const match = TOKEN.exec(formula);
    if (match === null) {
      throw new DiceError('bad_token', `Can't read the formula at “${formula.slice(position).trim().slice(0, 10)}”`);
    }
    tokens.push(match[0].trim());
    position = TOKEN.lastIndex;
  }
  return tokens;
}

class Parser {
  private readonly tokens: string[];
  private index = 0;
  private depth = 0;
  readonly terms: Term[] = [];
  readonly used: Record<string, number> = {};

  constructor(
    formula: string,
    private readonly stats: Readonly<Record<string, number>>,
    private readonly draw: Draw,
  ) {
    this.tokens = tokenize(formula);
  }

  peek(): string | undefined {
    return this.tokens[this.index];
  }

  private take(): string {
    const token = this.peek();
    if (token === undefined) throw new DiceError('bad_token', 'The formula ends too soon');
    this.index += 1;
    return token;
  }

  private integer(): number {
    const token = this.take();
    if (!DIGITS.test(token)) throw new DiceError('bad_token', `Expected a number, not “${token}”`);
    const value = Number(token);
    if (value > MAX_INTEGER) throw new DiceError('too_large', `${value} is larger than ${MAX_INTEGER}`);
    return value;
  }

  expr(): number {
    let value = this.term();
    while (this.peek() === '+' || this.peek() === '-') {
      const operator = this.take();
      const right = this.term();
      value = operator === '+' ? value + right : value - right;
    }
    return value;
  }

  private term(): number {
    let value = this.factor();
    while (this.peek() === '*' || this.peek() === '/') {
      const operator = this.take();
      const right = this.factor();
      if (operator === '*') {
        value *= right;
      } else {
        if (right === 0) throw new DiceError('division_by_zero', 'The formula divides by zero');
        value = Math.floor(value / right);
      }
    }
    return value;
  }

  private factor(): number {
    const token = this.peek();
    if (token === undefined) throw new DiceError('bad_token', 'The formula ends too soon');
    if (token === '-') {
      this.take();
      return -this.factor();
    }
    if (token === '(') {
      this.take();
      this.depth += 1;
      if (this.depth > MAX_NESTING) throw new DiceError('too_deep', `Brackets nest more than ${MAX_NESTING} deep`);
      const value = this.expr();
      if (this.take() !== ')') throw new DiceError('bad_token', "A bracket isn't closed");
      this.depth -= 1;
      return value;
    }
    if (token.startsWith('@')) {
      this.take();
      const name = token.slice(1);
      const stat = Object.hasOwn(this.stats, name) ? this.stats[name] : undefined;
      if (stat === undefined) throw new DiceError('unknown_stat', `There is no stat called @${name}`);
      const value = Math.floor(stat);
      this.used[name] = value;
      return value;
    }
    if (token === 'd') return this.dice(1, this.index);
    if (DIGITS.test(token)) {
      const start = this.index;
      const count = this.integer();
      return this.peek() === 'd' ? this.dice(count, start) : count;
    }
    throw new DiceError('bad_token', `Unexpected “${token}”`);
  }

  private dice(count: number, start: number): number {
    this.take(); // "d"
    if (count < 1) throw new DiceError('bad_dice', 'Roll at least one die');
    if (count > MAX_DICE_PER_TERM) throw new DiceError('too_many_dice', `A term rolls at most ${MAX_DICE_PER_TERM} dice`);
    let fate = false;
    let sides: number;
    const size = this.take();
    if (size === '%') {
      sides = 100;
    } else if (size === 'F') {
      fate = true;
      sides = FATE_FACES;
    } else if (DIGITS.test(size)) {
      sides = Number(size);
      if (sides < 1 || sides > MAX_SIDES) throw new DiceError('bad_dice', `A die has 1 to ${MAX_SIDES} sides`);
    } else {
      throw new DiceError('bad_token', `Expected the die's sides, not “${size}”`);
    }

    let keep: [string, number] | undefined;
    let explode = false;
    let rerollUnder: number | undefined;
    let successAt: number | undefined;
    for (let token = this.peek(); token !== undefined && MODIFIERS.has(token); token = this.peek()) {
      this.take();
      if (KEEP_DROP.has(token)) {
        if (keep !== undefined) throw new DiceError('bad_modifier', 'A term keeps or drops only once');
        const amount = DIGITS.test(this.peek() ?? '') ? this.integer() : 1;
        keep = [token, amount];
      } else if (token === '!') {
        if (explode) throw new DiceError('bad_modifier', 'A term explodes only once');
        if (fate || sides === 1) throw new DiceError('bad_modifier', "This die can't explode");
        explode = true;
      } else if (token === 'r<') {
        if (rerollUnder !== undefined) throw new DiceError('bad_modifier', 'A term rerolls only once');
        rerollUnder = this.integer();
      } else {
        if (successAt !== undefined) throw new DiceError('bad_modifier', 'A term counts successes only once');
        successAt = this.integer();
      }
    }

    const term: Term = { notation: this.tokens.slice(start, this.index).join(''), dice: [], value: 0 };
    const face = (): number => {
      const drawn = this.draw(sides);
      if (!Number.isInteger(drawn) || drawn < 1 || drawn > sides)
        throw new DiceError('bad_draw', `A d${sides} drew ${drawn}`);
      return fate ? drawn - 2 : drawn;
    };

    const top = fate ? 1 : sides;
    const active: Die[] = [];
    for (let i = 0; i < count; i += 1) {
      let die: Die = { value: face(), kept: true };
      if (rerollUnder !== undefined && die.value < rerollUnder) {
        term.dice.push({ ...die, kept: false, note: 'rerolled' });
        die = { value: face(), kept: true, note: 'reroll' };
      }
      term.dice.push(die);
      active.push(die);
    }
    if (explode) {
      let explosions = 0;
      const pending = active.filter((die) => die.value === top);
      while (pending.length > 0 && explosions < MAX_EXPLOSIONS_PER_TERM) {
        pending.shift();
        const extra: Die = { value: face(), kept: true, note: 'exploded' };
        explosions += 1;
        term.dice.push(extra);
        active.push(extra);
        if (extra.value === top) pending.push(extra);
      }
    }
    if (keep !== undefined) {
      const [kind, amount] = keep;
      // Stable order: equal faces keep their roll order, so both twins drop the same die.
      const ranked = active.map((_, i) => i).sort((a, b) => active[a].value - active[b].value || a - b);
      const size = active.length;
      let dropped: number[];
      if (kind === 'kh') dropped = ranked.slice(0, Math.max(0, size - amount));
      else if (kind === 'kl') dropped = ranked.slice(Math.min(amount, size));
      else if (kind === 'dl') dropped = ranked.slice(0, Math.min(amount, size));
      else dropped = ranked.slice(size - Math.min(amount, size));
      for (const i of dropped) {
        active[i].kept = false;
        active[i].note = 'dropped';
      }
    }
    const counted = active.filter((die) => die.kept);
    term.value =
      successAt === undefined
        ? counted.reduce((sum, die) => sum + die.value, 0)
        : counted.filter((die) => die.value >= (successAt as number)).length;
    this.terms.push(term);
    return term.value;
  }
}

/** Rolls `formula`, drawing each die from `draw`; `stats` are the values `@name` reads. */
export function roll(formula: string, draw: Draw, stats: Readonly<Record<string, number>> = {}): Roll {
  const text = formula.trim();
  if (text === '') throw new DiceError('empty', 'The formula is empty');
  if (text.length > MAX_FORMULA_LENGTH)
    throw new DiceError('too_long', `A formula is at most ${MAX_FORMULA_LENGTH} characters`);
  const parser = new Parser(text, stats, draw);
  const total = parser.expr();
  const rest = parser.peek();
  if (rest !== undefined) throw new DiceError('bad_token', `Unexpected “${rest}”`);
  return { formula: text, total, terms: parser.terms, stats: parser.used };
}

/** A draw source that hands out `draws` in order (tests and the shared cases). */
export function drawingFrom(draws: readonly number[]): Draw {
  const remaining = [...draws];
  return (sides) => {
    const next = remaining.shift();
    if (next === undefined) throw new DiceError('bad_draw', `No draw left for a d${sides}`);
    return next;
  };
}

/** The live draw source: a uniform face from the platform's cryptographic generator. */
export function cryptoDraw(sides: number): number {
  // Rejection sampling: no face is likelier than another, whatever the sides.
  const limit = Math.floor(0x1_0000_0000 / sides) * sides;
  const buffer = new Uint32Array(1);
  for (;;) {
    crypto.getRandomValues(buffer);
    if (buffer[0] < limit) return (buffer[0] % sides) + 1;
  }
}
