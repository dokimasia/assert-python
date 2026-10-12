r"""The parser of the portable pattern subset.

The subset has the constructs that the regular expression engines of every
target language interpret in the same way:

- A literal is any character but the metacharacters \ . ^ $ | ? * + ( ) [ ]
  { }, or a metacharacter after a backslash.
- The dot matches any character but the line terminators \n, \r, U+0085,
  U+2028 and U+2029.
- \d matches the ASCII digits. \w matches the ASCII letters, the digits and
  the underscore. \s matches space, \t, \n, \f and \r.
- A class [...] contains characters, ranges and those three escapes, and a
  leading ^ negates it. Inside a class, \, [, ] and a hyphen that does not
  form a range take a backslash. A hyphen can also be first or last. A
  class cannot contain &&, --, || or ~~.
- A group is (...) or (?:...), and groups nest at most 100 deep. | separates
  the branches of an alternation.
- The quantifiers are *, +, ?, {m}, {m,} and {m,n}. A count is at most
  1,000 and does not have a leading zero, and a quantifier does not follow
  another. Along every chain of nested quantifiers, the counts multiply to
  at most 1,000. Each count is the upper one, or the lower one when there is
  no upper one, and a count of 0 counts as 1.
- ^ can be the first character of the pattern, and $ can be its last.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from dokimi_assert._record.literal import quoted

__all__ = [
    "LINE_TERMINATORS",
    "SHORTHANDS",
    "Alternation",
    "Class",
    "Concat",
    "Literal",
    "Node",
    "Pattern",
    "PatternError",
    "Repeat",
    "parse",
]

#: An inclusive range of code points.
Range = tuple[int, int]


@dataclass(frozen=True, slots=True)
class Literal:
    """One character.

    Attributes:
        char: The character.
    """

    char: str


@dataclass(frozen=True, slots=True)
class Class:
    """A set of characters.

    Attributes:
        ranges: The sorted, merged, inclusive ranges of the code points of
            the class.
    """

    ranges: tuple[Range, ...]


@dataclass(frozen=True, slots=True)
class Concat:
    """Pieces that follow one another.

    Attributes:
        items: The pieces in order.
    """

    items: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class Alternation:
    """Branches of which one matches.

    Attributes:
        branches: The branches in order.
    """

    branches: tuple[Node, ...]


@dataclass(frozen=True, slots=True)
class Repeat:
    """A piece that repeats.

    Attributes:
        item: The piece.
        min: The fewest repetitions.
        max: The most repetitions, or None for no limit.
    """

    item: Node
    min: int
    max: int | None


#: A parsed piece of a pattern.
Node = Literal | Class | Concat | Alternation | Repeat


@dataclass(frozen=True, slots=True)
class Pattern:
    """A parsed pattern with its tree and its anchors.

    Attributes:
        node: The tree of the pattern between its anchors.
        start: When True, the pattern starts with ^.
        end: When True, the pattern ends with $.
    """

    node: Node
    start: bool
    end: bool


class PatternError(ValueError):
    """A pattern outside the portable subset.

    The text of the error contains the pattern, the position in the pattern
    in code points, and the construct that the parser refuses there.
    """


#: The characters that are literal only after a backslash.
_METACHARACTERS = frozenset("\\.^$|?*+()[]{}")

#: The characters that a backslash makes literal inside a class.
_CLASS_ESCAPES = _METACHARACTERS | {"-"}

#: The pairs that a class cannot contain. Java reads && as an intersection,
#: and other engines reserve the rest.
_RESERVED_PAIRS = frozenset({"&&", "--", "||", "~~"})

#: The characters that the dot leaves out, because the dot of some engine
#: does not match them.
LINE_TERMINATORS = "\n\r\x85" + chr(0x2028) + chr(0x2029)

#: The members of \d, \w and \s that the class of every engine has.
SHORTHANDS = {
    "d": "0123456789",
    "w": "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_",
    "s": " \t\n\f\r",
}

#: The largest count, and the largest product of the counts of nested
#: quantifiers. RE2 refuses a larger one.
_MAX_COUNT = 1000

#: The deepest that groups nest. The engine of Python refuses a pattern whose
#: groups nest 495 deep.
_MAX_DEPTH = 100

#: The characters that start a quantifier.
_QUANTIFIERS = frozenset("*+?{")

#: The digits of a count.
_DIGITS = frozenset("0123456789")

#: The highest code point.
_LAST_CODE_POINT = 0x10FFFF

#: The surrogates. No scalar value is a surrogate.
_SURROGATES: Range = (0xD800, 0xDFFF)


def _merge(ranges: Sequence[Range]) -> tuple[Range, ...]:
    """Return ranges sorted and merged. Adjacent ranges join."""
    out: list[list[int]] = []
    for first, last in sorted(ranges):
        if out and first <= out[-1][1] + 1:
            out[-1][1] = max(out[-1][1], last)
            continue
        out.append([first, last])
    return tuple((first, last) for first, last in out)


def _complement(ranges: Sequence[Range]) -> tuple[Range, ...]:
    """Return the scalar values outside ranges."""
    out: list[Range] = []
    start = 0
    for first, last in _merge([*ranges, _SURROGATES]):
        if first > start:
            out.append((start, first - 1))
        start = last + 1
    if start <= _LAST_CODE_POINT:
        out.append((start, _LAST_CODE_POINT))
    return tuple(out)


def _members(chars: str) -> list[Range]:
    """Return the ranges of each character of chars."""
    return [(ord(c), ord(c)) for c in chars]


def _class_of(ranges: Sequence[Range]) -> Class:
    """Return the class of ranges."""
    return Class(_merge(ranges))


#: The class of the dot.
DOT = _class_of(_complement(_members(LINE_TERMINATORS)))


def _weight(node: Node) -> int:
    """Return the largest product of quantifier counts along a path through node."""
    if isinstance(node, Repeat):
        count = node.max if node.max is not None else node.min
        return max(count, 1) * _weight(node.item)
    if isinstance(node, Concat):
        return max([1, *(_weight(item) for item in node.items)])
    if isinstance(node, Alternation):
        return max(_weight(branch) for branch in node.branches)
    return 1


class _Parser:
    """A recursive-descent parser of one pattern.

    It reads the pattern by code point.
    """

    def __init__(self, text: str) -> None:
        """Return the parser of text.

        Raises:
            PatternError: text contains a surrogate code point.
        """
        self._text: str = text
        self._at: int = 0
        self._depth: int = 0
        for at, char in enumerate(text):
            if _SURROGATES[0] <= ord(char) <= _SURROGATES[1]:
                self._at = at
                raise self._fail("a lone surrogate is not a character")

    def _fail(self, what: str) -> PatternError:
        """Return the error of what is wrong at the current position."""
        return PatternError(f"pattern {quoted(self._text)} at {self._at}: {what}")

    def _peek(self, ahead: int = 0) -> str:
        """Return the character ahead of the current one, or "" past the end."""
        at = self._at + ahead
        return self._text[at] if at < len(self._text) else ""

    def _next(self, missing: str) -> str:
        """Return the current character and move past it."""
        if self._at >= len(self._text):
            raise self._fail(missing)
        char = self._text[self._at]
        self._at += 1
        return char

    def _closing_anchor(self) -> bool:
        """Report whether the current character is a $ that ends the pattern."""
        return self._peek() == "$" and self._at == len(self._text) - 1

    def pattern(self) -> Pattern:
        """Parse the whole pattern and its anchors."""
        start = self._peek() == "^"
        if start:
            self._at += 1
        node = self._alternation()
        end = self._closing_anchor()
        if end:
            self._at += 1
        if self._at != len(self._text):
            raise self._fail(f"{quoted(self._peek())} is not expected")
        return Pattern(node, start, end)

    def _alternation(self) -> Node:
        """Parse branches separated by |."""
        branches = [self._sequence()]
        while self._peek() == "|":
            self._at += 1
            branches.append(self._sequence())
        return branches[0] if len(branches) == 1 else Alternation(tuple(branches))

    def _sequence(self) -> Node:
        """Parse pieces up to a |, a ), the closing anchor or the end.

        A $ that ends the pattern inside a group stops the sequence. The
        group then fails, because the pattern does not have the ) that closes
        it.
        """
        items: list[Node] = []
        while self._peek() not in ("", "|", ")") and not self._closing_anchor():
            items.append(self._quantified())
        return items[0] if len(items) == 1 else Concat(tuple(items))

    def _quantified(self) -> Node:
        """Parse an atom and the quantifier after it, when it has one.

        The parser then parses a second quantifier as an atom, and refuses it
        as a metacharacter that is not escaped.
        """
        item = self._atom()
        if self._peek() not in _QUANTIFIERS:
            return item
        low, high = self._quantifier()
        repeat = Repeat(item, low, high)
        product = _weight(repeat)
        if product > _MAX_COUNT:
            raise self._fail(f"nested counts multiply to {product}, above {_MAX_COUNT}")
        return repeat

    def _quantifier(self) -> tuple[int, int | None]:
        """Parse *, +, ?, {m}, {m,} or {m,n} into the repetitions that it allows."""
        char = self._next("a quantifier is missing")
        if char == "*":
            return 0, None
        if char == "+":
            return 1, None
        if char == "?":
            return 0, 1
        low = self._count()
        high: int | None = low
        if self._peek() == ",":
            self._at += 1
            high = None if self._peek() == "}" else self._count()
        if self._next("a count is not closed") != "}":
            raise self._fail("a count is not closed by }")
        if high is not None and high < low:
            raise self._fail(f"the count {{{low},{high}}} runs backwards")
        return low, high

    def _count(self) -> int:
        """Parse the digits of a count of at most 1,000.

        RE2 reads a count with a leading zero as literal text, such as {007}.
        A count of two or more digits therefore does not start with 0.
        """
        start = self._at
        while self._peek() in _DIGITS:
            self._at += 1
        if start == self._at:
            raise self._fail("a count does not have a digit")
        digits = self._text[start : self._at]
        if len(digits) > 1 and digits.startswith("0"):
            raise self._fail(f"the count {digits} has a leading zero")
        count = int(digits)
        if count > _MAX_COUNT:
            raise self._fail(f"the count {count} is above {_MAX_COUNT}")
        return count

    def _atom(self) -> Node:
        """Parse a literal, a dot, an escape, a class or a group."""
        char = self._next("the pattern ends where a character belongs")
        if char == "(":
            return self._group()
        if char == "[":
            return self._class()
        if char == ".":
            return DOT
        if char == "\\":
            escaped = self._next("the pattern ends with a backslash")
            shorthand = SHORTHANDS.get(escaped)
            if shorthand is not None:
                return _class_of(_members(shorthand))
            if escaped not in _METACHARACTERS:
                raise self._fail(f"\\{escaped} is not in the portable subset")
            return Literal(escaped)
        if char in _METACHARACTERS:
            raise self._fail(f"{quoted(char)} must be escaped here")
        return Literal(char)

    def _group(self) -> Node:
        """Parse a group after its (. Groups nest at most 100 deep."""
        self._depth += 1
        if self._depth > _MAX_DEPTH:
            raise self._fail(f"groups nest deeper than {_MAX_DEPTH}")
        if self._peek() == "?":
            if self._peek(1) != ":":
                raise self._fail("only the (?: group is in the portable subset")
            self._at += 2
        node = self._alternation()
        if self._next("a group is not closed") != ")":
            raise self._fail("a group is not closed by )")
        self._depth -= 1
        return node

    def _class(self) -> Node:
        """Parse a class after its [."""
        negated = self._peek() == "^"
        if negated:
            self._at += 1
        ranges: list[Range] = []
        previous = ""
        first = True
        char = self._next("a class is not closed")
        while char != "]":
            previous = self._member(char, previous, first, ranges)
            first = False
            char = self._next("a class is not closed")
        if first:
            raise self._fail("a class is empty")
        return _class_of(_complement(ranges) if negated else ranges)

    def _member(
        self, char: str, previous: str, first: bool, ranges: list[Range]
    ) -> str:
        """Parse the member of a class that starts with char, and add its ranges.

        Returns:
            The character that the next member reads as the one before it,
            and the empty string after a shorthand, an escape and a range.
        """
        shorthand = SHORTHANDS.get(self._peek()) if char == "\\" else None
        if shorthand is not None:
            self._at += 1
            ranges.extend(_members(shorthand))
            return ""
        low = self._class_char(char, previous, first)
        before = "" if char == "\\" else char
        if self._peek() != "-" or self._peek(1) in ("", "]"):
            ranges.extend(_members(low))
            return before
        if f"{before}-" in _RESERVED_PAIRS:
            raise self._fail("'--' is reserved inside a class")
        self._at += 1
        high = self._class_char(self._next("a class is not closed"), "-", False)
        if ord(high) < ord(low):
            raise self._fail(f"the range {low}-{high} runs backwards")
        ranges.append((ord(low), ord(high)))
        return ""

    def _class_char(self, char: str, previous: str, first: bool) -> str:
        """Return the character of a member of a class without its escape.

        It fails for a [, a reserved pair, a misplaced hyphen, and an escape
        that the subset does not have.
        """
        if char == "\\":
            escaped = self._next("a class ends inside an escape")
            if escaped not in _CLASS_ESCAPES:
                raise self._fail(f"\\{escaped} is not in the portable subset")
            return escaped
        if char == "[":
            raise self._fail("[ must be escaped inside a class")
        if previous + char in _RESERVED_PAIRS:
            raise self._fail(f"'{previous + char}' is reserved inside a class")
        if char == "-" and not first and self._peek() != "]":
            raise self._fail("a hyphen inside a class must be escaped")
        return char


def parse(text: str) -> Pattern:
    """Return the parse of a pattern of the portable subset.

    Args:
        text: The pattern.

    Returns:
        Its tree and its anchors.

    Raises:
        PatternError: The pattern is outside the subset. The text of the
            error contains the position in the pattern and the construct that
            the parser refuses there.
    """
    return _Parser(text).pattern()
