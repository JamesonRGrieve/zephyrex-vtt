# SPDX-License-Identifier: AGPL-3.0-or-later
"""Dice notation: parse a formula and roll it, the VTT as referee.

A pure function of the formula, the stats it names and a draw source, so the server rolls with
``secrets.SystemRandom`` and the tests (and ``contract/roll-cases.json``) roll with injected draws.
The lite edition's twin is ``client/src/features/dice/roll.ts``; both answer the same cases.

Grammar (whitespace is ignored)::

    expr    := term (("+" | "-") term)*
    term    := factor (("*" | "/") factor)*          # "/" divides and rounds down
    factor  := "-" factor | "(" expr ")" | dice | integer | "@" name
    dice    := [integer] "d" (integer | "%" | "F") modifier*
    modifier:= "kh" [n] | "kl" [n] | "dh" [n] | "dl" [n]   # keep or drop highest/lowest (n = 1)
             | "!"                                          # explode: a die at its highest adds a die
             | "r<" n                                       # reroll, once, a die showing under n
             | "cs>=" n                                     # count dice at n or more, not their sum

A die draws a face from 1 to its sides; ``dF`` draws 1 to 3 and reads it as -1, 0 or +1, and
``d%`` is ``d100``. Modifiers apply in a fixed order whatever order they are written in: reroll,
explode, keep or drop, then success counting. A stat (``@dex``) is rounded down to a whole number.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

MAX_FORMULA_LENGTH = 200
MAX_DICE_PER_TERM = 100
MAX_EXPLOSIONS_PER_TERM = 20
MAX_SIDES = 10_000
MAX_INTEGER = 1_000_000
MAX_NESTING = 10
FATE_FACES = 3

Draw = Callable[[int], int]
"""A draw source: given a die's sides, a face from 1 to sides."""

_TOKEN = re.compile(
    r"\s*(?:(?P<int>\d+)|(?P<cs>cs>=)|(?P<rr>r<)|(?P<kd>kh|kl|dh|dl)|(?P<ref>@[A-Za-z_][A-Za-z0-9_]*)"
    r"|(?P<sym>[-+*/()%!dF]))"
)


class DiceError(ValueError):
    """A formula that can't be rolled. ``code`` is the same in both twins; ``message`` is for people."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Die:
    value: int
    kept: bool = True
    note: str | None = None
    """Why it isn't counted, or how it came to be: rerolled, exploded, dropped."""

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"value": self.value, "kept": self.kept}
        if self.note is not None:
            out["note"] = self.note
        return out


@dataclass
class Term:
    notation: str
    dice: list[Die] = field(default_factory=list)
    value: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {"notation": self.notation, "dice": [die.as_dict() for die in self.dice], "value": self.value}


@dataclass
class Roll:
    formula: str
    total: int
    terms: list[Term]
    stats: dict[str, int]

    def as_dict(self) -> dict[str, Any]:
        return {
            "formula": self.formula,
            "total": self.total,
            "terms": [term.as_dict() for term in self.terms],
            "stats": dict(self.stats),
        }


def _tokenize(formula: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    while position < len(formula):
        if formula[position:].strip() == "":
            break
        match = _TOKEN.match(formula, position)
        if match is None:
            raise DiceError("bad_token", f"Can't read the formula at “{formula[position:].strip()[:10]}”")
        tokens.append(match.group(0).strip())
        position = match.end()
    return tokens


class _Parser:
    def __init__(self, formula: str, stats: Mapping[str, float], draw: Draw) -> None:
        self.tokens = _tokenize(formula)
        self.index = 0
        self.stats = stats
        self.draw = draw
        self.terms: list[Term] = []
        self.used: dict[str, int] = {}
        self.depth = 0

    def peek(self) -> str | None:
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise DiceError("bad_token", "The formula ends too soon")
        self.index += 1
        return token

    def integer(self) -> int:
        token = self.take()
        if not token.isdigit():
            raise DiceError("bad_token", f"Expected a number, not “{token}”")
        value = int(token)
        if value > MAX_INTEGER:
            raise DiceError("too_large", f"{value} is larger than {MAX_INTEGER}")
        return value

    def expr(self) -> int:
        value = self.term()
        while self.peek() in ("+", "-"):
            operator = self.take()
            right = self.term()
            value = value + right if operator == "+" else value - right
        return value

    def term(self) -> int:
        value = self.factor()
        while self.peek() in ("*", "/"):
            operator = self.take()
            right = self.factor()
            if operator == "*":
                value = value * right
            else:
                if right == 0:
                    raise DiceError("division_by_zero", "The formula divides by zero")
                value = value // right
        return value

    def factor(self) -> int:
        token = self.peek()
        if token is None:
            raise DiceError("bad_token", "The formula ends too soon")
        if token == "-":
            self.take()
            return -self.factor()
        if token == "(":
            self.take()
            self.depth += 1
            if self.depth > MAX_NESTING:
                raise DiceError("too_deep", f"Brackets nest more than {MAX_NESTING} deep")
            value = self.expr()
            if self.take() != ")":
                raise DiceError("bad_token", "A bracket isn't closed")
            self.depth -= 1
            return value
        if token.startswith("@"):
            self.take()
            name = token[1:]
            if name not in self.stats:
                raise DiceError("unknown_stat", f"There is no stat called @{name}")
            value = math.floor(self.stats[name])
            self.used[name] = value
            return value
        if token == "d":
            return self.dice(1, self.index)
        if token.isdigit():
            start = self.index
            count = self.integer()
            if self.peek() == "d":
                return self.dice(count, start)
            return count
        raise DiceError("bad_token", f"Unexpected “{token}”")

    def dice(self, count: int, start: int) -> int:
        self.take()  # "d"
        if count < 1:
            raise DiceError("bad_dice", "Roll at least one die")
        if count > MAX_DICE_PER_TERM:
            raise DiceError("too_many_dice", f"A term rolls at most {MAX_DICE_PER_TERM} dice")
        fate = False
        size = self.take()
        if size == "%":
            sides = 100
        elif size == "F":
            fate, sides = True, FATE_FACES
        elif size.isdigit():
            sides = int(size)
            if sides < 1 or sides > MAX_SIDES:
                raise DiceError("bad_dice", f"A die has 1 to {MAX_SIDES} sides")
        else:
            raise DiceError("bad_token", f"Expected the die's sides, not “{size}”")

        keep: tuple[str, int] | None = None
        explode = False
        reroll_under: int | None = None
        success_at: int | None = None
        while (token := self.peek()) in ("kh", "kl", "dh", "dl", "!", "r<", "cs>="):
            self.take()
            if token in ("kh", "kl", "dh", "dl"):
                if keep is not None:
                    raise DiceError("bad_modifier", "A term keeps or drops only once")
                amount = self.integer() if (self.peek() or "").isdigit() else 1
                keep = (token, amount)
            elif token == "!":
                if explode:
                    raise DiceError("bad_modifier", "A term explodes only once")
                if fate or sides == 1:
                    raise DiceError("bad_modifier", "This die can't explode")
                explode = True
            elif token == "r<":
                if reroll_under is not None:
                    raise DiceError("bad_modifier", "A term rerolls only once")
                reroll_under = self.integer()
            else:
                if success_at is not None:
                    raise DiceError("bad_modifier", "A term counts successes only once")
                success_at = self.integer()

        notation = "".join(self.tokens[start : self.index])
        term = Term(notation=notation)

        def face() -> int:
            drawn = self.draw(sides)
            if not 1 <= drawn <= sides:
                raise DiceError("bad_draw", f"A d{sides} drew {drawn}")
            return drawn - 2 if fate else drawn

        top = 1 if fate else sides
        active: list[Die] = []
        for _ in range(count):
            die = Die(face())
            if reroll_under is not None and die.value < reroll_under:
                die.kept, die.note = False, "rerolled"
                term.dice.append(die)
                die = Die(face(), note="reroll")
            term.dice.append(die)
            active.append(die)
        if explode:
            explosions = 0
            pending = [die for die in active if die.value == top]
            while pending and explosions < MAX_EXPLOSIONS_PER_TERM:
                pending.pop(0)
                extra = Die(face(), note="exploded")
                explosions += 1
                term.dice.append(extra)
                active.append(extra)
                if extra.value == top:
                    pending.append(extra)
        if keep is not None:
            kind, amount = keep
            # Stable order: equal faces keep their roll order, so both twins drop the same die.
            ranked = sorted(range(len(active)), key=lambda i: (active[i].value, i))
            size = len(active)
            if kind == "kh":  # keep the highest n: drop the lowest size - n
                dropped = ranked[: max(0, size - amount)]
            elif kind == "kl":  # keep the lowest n: drop the rest
                dropped = ranked[min(amount, size) :]
            elif kind == "dl":  # drop the lowest n
                dropped = ranked[: min(amount, size)]
            else:  # "dh": drop the highest n
                dropped = ranked[size - min(amount, size) :]
            for i in dropped:
                active[i].kept, active[i].note = False, "dropped"
        counted = [die for die in active if die.kept]
        if success_at is not None:
            term.value = sum(1 for die in counted if die.value >= success_at)
        else:
            term.value = sum(die.value for die in counted)
        self.terms.append(term)
        return term.value


def roll(formula: str, draw: Draw, stats: Mapping[str, float] | None = None) -> Roll:
    """Rolls ``formula``, drawing each die from ``draw``; ``stats`` are the values ``@name`` reads."""
    text = formula.strip()
    if not text:
        raise DiceError("empty", "The formula is empty")
    if len(text) > MAX_FORMULA_LENGTH:
        raise DiceError("too_long", f"A formula is at most {MAX_FORMULA_LENGTH} characters")
    parser = _Parser(text, stats or {}, draw)
    total = parser.expr()
    if parser.peek() is not None:
        raise DiceError("bad_token", f"Unexpected “{parser.peek()}”")
    return Roll(formula=text, total=total, terms=parser.terms, stats=parser.used)


def drawing_from(draws: list[int]) -> Draw:
    """A draw source that hands out ``draws`` in order (tests and the shared cases)."""
    remaining = list(draws)

    def draw(sides: int) -> int:
        if not remaining:
            raise DiceError("bad_draw", f"No draw left for a d{sides}")
        return remaining.pop(0)

    return draw
