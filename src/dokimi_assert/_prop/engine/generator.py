"""The generators and how they decode a value from a case.

The decode method of a generator asks the case for its choices in a fixed
order. It returns the value that the choices decode to. The definition fixes
the order of the requests, their bounds, the requests that decide structure,
and the spans around them. Two implementations that agree on them decode the
same value from the same choices.

Every generator but a map decodes inside a span labelled with its id. A map
makes the choices of its source and does not open a span of its own. A list
and a dict decode their elements by the rules of collection.collect. Each
element has a span that starts at its continue flag.
"""

from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from fractions import Fraction
from typing import ClassVar, Generic, Protocol, TypeVar, cast

from dokimi_assert._prop.engine import alphabet, draw
from dokimi_assert._prop.engine.case import Case, Request
from dokimi_assert._prop.engine.choice import (
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
)
from dokimi_assert._prop.engine.collection import ELEMENT, ENTRY, Sizes, collect
from dokimi_assert._prop.engine.value import Pairs, canonical

__all__ = [
    "Bool",
    "Bound",
    "Bytes",
    "Composite",
    "Deferred",
    "Dict",
    "Filter",
    "Float",
    "Generator",
    "Integer",
    "Just",
    "List",
    "Mapped",
    "Matching",
    "OneOf",
    "Optional",
    "Permutation",
    "Piece",
    "Position",
    "Recursive",
    "SampledFrom",
    "Text",
]

#: The number of attempts that a filter makes before it rejects the case.
_FILTER_ATTEMPTS = 3

#: The bounds of a choice of 0 or 1, and of a choice that admits 0 alone.
_BIT = IntegerBounds(0, 1)
_NONE = IntegerBounds(0, 0)

_T = TypeVar("_T")
_T_co = TypeVar("_T_co", covariant=True)
_U = TypeVar("_U")
_K = TypeVar("_K")
_V = TypeVar("_V")


class Generator(ABC, Generic[_T_co]):
    """The decoder of the values of a domain."""

    @abstractmethod
    def decode(self, c: Case) -> _T_co:
        """Ask the case for choices, and return the value that they decode to.

        Args:
            c: The case.

        Returns:
            The value.

        Raises:
            Rejected: The choices do not decode to a value of the domain.
        """

    def map(self, f: Callable[[_T_co], _U]) -> Generator[_U]:
        """Return the generator of f of each value of this one.

        The new generator makes the choices of this generator, so it shrinks
        in the same way. It does not have an inverse, so an example of it
        runs on its value.

        Args:
            f: The function to apply to each value.

        Returns:
            The generator.
        """
        return Mapped(self, f)

    def filter(self, keep: Callable[[_T_co], bool]) -> Generator[_T_co]:
        """Return the generator of the values of this one that keep accepts.

        The new generator tries three times. It rejects the case when keep
        does not accept any attempt.

        Args:
            keep: The predicate.

        Returns:
            The generator.
        """
        return Filter(self, keep)

    def bind(self, f: Callable[[_T_co], Generator[_U]]) -> Generator[_U]:
        """Return the generator of the values of the generators that f returns.

        The new generator decodes a value of this one first. f returns the
        generator of the second value. Both values decode in one span.

        Args:
            f: The function from a value to a generator.

        Returns:
            The generator.
        """
        return Bound(self, f)


class Deferred(Generator[_T_co], ABC):
    """A generator that picks the generator of its values where it is used.

    A draw of the generator of a type picks the generator that its run gives
    the type. The engine decodes, inverts and walks the picked generator
    inside the context of the pick, so a pick inside the picked generator
    reads the same context. The decode does not open a span of its own.
    """

    @abstractmethod
    def picked(self) -> AbstractContextManager[Generator[_T_co]]:
        """Return the context of the pick.

        Returns:
            A context manager. Entering it returns the picked generator.
        """

    def decode(self, c: Case) -> _T_co:
        """Return the value that the picked generator decodes from the case.

        Args:
            c: The case.

        Returns:
            The value.
        """
        with self.picked() as generator:
            return generator.decode(c)


class Integer(Generator[int]):
    """An integer in its bounds from one integer choice that can reuse an earlier one.

    Attributes:
        bounds: The bounds.
        id: The id of the generator. It is integer, or duration for a
            duration in nanoseconds.
    """

    def __init__(self, bounds: IntegerBounds, id: str = "integer") -> None:
        """Return the generator of the integers in bounds.

        Args:
            bounds: The bounds.
            id: The id of the span. It is integer or duration.
        """
        self.bounds: IntegerBounds = bounds
        self.id: str = id

    def decode(self, c: Case) -> int:
        """Return the integer that the case chooses.

        Args:
            c: The case.

        Returns:
            The integer.
        """
        with c.span(self.id):
            return c.integer(self.bounds, None, True)


class Float(Generator[float]):
    """A float in its bounds from one float choice.

    Attributes:
        bounds: The bounds.
    """

    #: The id of the span.
    ID: ClassVar[str] = "float"

    def __init__(self, bounds: FloatBounds) -> None:
        """Return the generator of the floats in bounds.

        Args:
            bounds: The bounds.
        """
        self.bounds: FloatBounds = bounds

    def decode(self, c: Case) -> float:
        """Return the float that the case chooses.

        Args:
            c: The case.

        Returns:
            The float.
        """
        bounds = self.bounds
        request = Request(bounds, lambda source: draw.float_value(source, bounds))
        with c.span(Float.ID):
            return cast("float", c.choose(request))


class Bool(Generator[bool]):
    """A bool that is True with the probability p.

    The bool is one integer choice in [0, 1]. One coin draws the choice.

    Attributes:
        p: The probability of True.
    """

    #: The id of the span.
    ID: ClassVar[str] = "boolean"

    def __init__(self, p: Fraction) -> None:
        """Return the generator of the bools that are True with the probability p.

        Args:
            p: The probability.
        """
        self.p: Fraction = p

    def decode(self, c: Case) -> bool:
        """Return True when the case chooses 1.

        Args:
            c: The case.

        Returns:
            True for the choice 1, and False for the choice 0.
        """
        p = self.p
        request = Request(_BIT, lambda source: draw.boolean(source, p))
        with c.span(Bool.ID):
            return c.choose(request) == 1


class Just(Generator[_T]):
    """One given value. The generator does not make a choice.

    Attributes:
        value: The value.
    """

    #: The id of the span.
    ID: ClassVar[str] = "just"

    def __init__(self, value: _T) -> None:
        """Return the generator of value.

        Args:
            value: The value.
        """
        self.value: _T = value

    def decode(self, c: Case) -> _T:
        """Return the given value.

        Args:
            c: The case.

        Returns:
            The value.
        """
        with c.span(Just.ID):
            return self.value


class SampledFrom(Generator[_T]):
    """One of the given values. An integer index that decides structure chooses it.

    Attributes:
        values: The values. There is at least one.
    """

    #: The id of the span.
    ID: ClassVar[str] = "sampled-from"

    def __init__(self, values: Sequence[_T]) -> None:
        """Return the generator of one of the values.

        Args:
            values: The values. There is at least one.
        """
        self.values: tuple[_T, ...] = tuple(values)
        self._bounds: IntegerBounds = IntegerBounds(0, len(values) - 1)

    def decode(self, c: Case) -> _T:
        """Return the value at the index that the case chooses.

        Args:
            c: The case.

        Returns:
            The value at the index.
        """
        with c.span(SampledFrom.ID):
            return self.values[c.integer(self._bounds, 0)]


class OneOf(Generator[_T]):
    """A value of one of the alternatives.

    An index that decides structure chooses the alternative.

    Attributes:
        of: The alternatives. There is at least one.
    """

    #: The id of the span.
    ID: ClassVar[str] = "one-of"

    def __init__(self, of: Sequence[Generator[_T]]) -> None:
        """Return the generator of a value of one of the alternatives.

        Args:
            of: The alternatives. There is at least one.
        """
        self.of: tuple[Generator[_T], ...] = tuple(of)
        self._bounds: IntegerBounds = IntegerBounds(0, len(of) - 1)

    def decode(self, c: Case) -> _T:
        """Return the value that the chosen alternative decodes.

        Args:
            c: The case.

        Returns:
            The value of the alternative.
        """
        with c.span(OneOf.ID):
            return self.of[c.integer(self._bounds, 0)].decode(c)


class Optional(Generator[_T | None]):
    """A value or None.

    A presence choice in [0, 1] comes first. The value follows when the
    choice is 1. The presence choice decides structure. Its target is
    absent, and the edge phase makes it present.

    Attributes:
        of: The generator of the value.
    """

    #: The id of the span.
    ID: ClassVar[str] = "optional"

    def __init__(self, of: Generator[_T]) -> None:
        """Return the generator of a value of of, or None.

        Args:
            of: The generator of the value.
        """
        self.of: Generator[_T] = of

    def decode(self, c: Case) -> _T | None:
        """Return None when absent, and the decoded value when present.

        Args:
            c: The case.

        Returns:
            The value, or None for a presence choice of 0.
        """
        with c.span(Optional.ID):
            return self.of.decode(c) if c.integer(_BIT, 1) == 1 else None


class List(Generator[list[_T]]):
    """A list of the values of the generator of its elements.

    When unique is set, the list discards an element whose canonical form
    equals the canonical form of an earlier element. The rules are those of
    collection.collect.

    Attributes:
        of: The generator of the elements.
        sizes: The sizes.
        unique: When True, the elements are unique.
    """

    #: The id of the span.
    ID: ClassVar[str] = "list"

    def __init__(self, of: Generator[_T], sizes: Sizes, unique: bool = False) -> None:
        """Return the generator of lists of of.

        Args:
            of: The generator of the elements.
            sizes: The sizes.
            unique: When True, the elements are unique.
        """
        self.of: Generator[_T] = of
        self.sizes: Sizes = sizes
        self.unique: bool = unique

    def decode(self, c: Case) -> list[_T]:
        """Return the list that the flags and the elements of the case decode to.

        Args:
            c: The case.

        Returns:
            The list.

        Raises:
            Rejected: The list stops below its minimum size.
        """

        def element() -> tuple[_T, str | None]:
            value = self.of.decode(c)
            return value, canonical(value) if self.unique else None

        with c.span(List.ID):
            return collect(c, self.sizes, ELEMENT, element)


class Dict(Generator[Pairs], Generic[_K, _V]):
    """Entries of a key and a value with distinct keys.

    The dict discards an entry whose key has the canonical form of an
    earlier key. The rules are those of collection.collect.

    Attributes:
        keys: The generator of the keys.
        values: The generator of the values.
        sizes: The sizes.
    """

    #: The id of the span.
    ID: ClassVar[str] = "dict"

    def __init__(
        self, keys: Generator[_K], values: Generator[_V], sizes: Sizes
    ) -> None:
        """Return the generator of dicts from keys to values.

        Args:
            keys: The generator of the keys.
            values: The generator of the values.
            sizes: The sizes.
        """
        self.keys: Generator[_K] = keys
        self.values: Generator[_V] = values
        self.sizes: Sizes = sizes

    def decode(self, c: Case) -> Pairs:
        """Return the entries that the flags, keys and values of the case decode to.

        Args:
            c: The case.

        Returns:
            The entries.

        Raises:
            Rejected: The dict stops below its minimum size.
        """

        def entry() -> tuple[tuple[_K, _V], str]:
            key = self.keys.decode(c)
            return (key, self.values.decode(c)), canonical(key)

        with c.span(Dict.ID):
            return Pairs(tuple(collect(c, self.sizes, ENTRY, entry)))


class Text(Generator[str]):
    """A string from one sequence of indices into its alphabet.

    Without characters, the alphabet is the default alphabet. Otherwise the
    alphabet is the given characters in their order, so the first character
    is the simplest.

    Attributes:
        characters: The characters of a given alphabet, or None for the
            default alphabet.
        bounds: The bounds of the sequence.
    """

    #: The id of the span.
    ID: ClassVar[str] = "string"

    def __init__(
        self, characters: Sequence[str] | None, bounds: SequenceBounds
    ) -> None:
        """Return the generator of strings over characters.

        Args:
            characters: The characters of a given alphabet, or None for the
                default alphabet. Each character is one code point.
            bounds: The bounds of the sequence.
        """
        self.characters: tuple[str, ...] | None = (
            None if characters is None else tuple(characters)
        )
        self.bounds: SequenceBounds = bounds

    def decode(self, c: Case) -> str:
        """Return the string of the indices that the case chooses.

        Args:
            c: The case.

        Returns:
            The string.
        """
        with c.span(Text.ID):
            indices = c.sequence(self.bounds)
        characters = self.characters
        if characters is None:
            return "".join(map(alphabet.character, indices))
        return "".join(characters[i] for i in indices)


class Bytes(Generator[bytes]):
    """A byte string from one sequence of 256 element values.

    Attributes:
        bounds: The bounds of the sequence.
    """

    #: The id of the span.
    ID: ClassVar[str] = "bytes"

    def __init__(self, bounds: SequenceBounds) -> None:
        """Return the generator of byte strings.

        Args:
            bounds: The bounds of the sequence, with a k of 256.
        """
        self.bounds: SequenceBounds = bounds

    def decode(self, c: Case) -> bytes:
        """Return the bytes of the sequence of the case.

        Args:
            c: The case.

        Returns:
            The byte string.
        """
        with c.span(Bytes.ID):
            return bytes(c.sequence(self.bounds))


class Piece(Protocol):
    """A piece of a pattern that decodes characters from a case."""

    def emit(self, c: Case, out: list[str]) -> None:
        """Append the characters that this piece decodes from its choices to out.

        Args:
            c: The case.
            out: The characters that the pattern decoded so far.
        """
        ...


class Matching(Generator[str]):
    """A string that a pattern of the portable subset matches in full.

    Attributes:
        piece: The piece of the pattern.
    """

    #: The id of the span.
    ID: ClassVar[str] = "string-matching"

    def __init__(self, piece: Piece) -> None:
        """Return the generator of the strings that piece decodes.

        Args:
            piece: The piece of the pattern.
        """
        self.piece: Piece = piece

    def decode(self, c: Case) -> str:
        """Return the characters that the pieces of the pattern decode.

        Args:
            c: The case.

        Returns:
            The string.
        """
        out: list[str] = []
        with c.span(Matching.ID):
            self.piece.emit(c, out)
        return "".join(out)


class Permutation(Generator[list[_T]]):
    """An ordering of the given values from one swap choice per position.

    For each i from 0 to n - 2, position i swaps with the index that the
    case chooses in [i, n - 1]. The target of that choice is i, so the
    targets leave the values in their given order.

    Attributes:
        values: The values.
    """

    #: The id of the span.
    ID: ClassVar[str] = "permutation"

    def __init__(self, values: Sequence[_T]) -> None:
        """Return the generator of orderings of the values.

        Args:
            values: The values.
        """
        self.values: tuple[_T, ...] = tuple(values)

    def decode(self, c: Case) -> list[_T]:
        """Return the values in the order that the swaps of the case give.

        Args:
            c: The case.

        Returns:
            The values in their new order.
        """
        ordered = list(self.values)
        last = len(ordered) - 1
        with c.span(Permutation.ID):
            for i in range(last):
                j = c.integer(IntegerBounds(i, last))
                ordered[i], ordered[j] = ordered[j], ordered[i]
        return ordered


class Filter(Generator[_T]):
    """A value of the source generator that a predicate keeps.

    Each attempt decodes in a span labelled with the id. The filter removes
    a rejected attempt from the record of the case, so a replay of the
    record decodes the kept value at its first attempt. The removed choices
    still count towards the cap of the case, and the case tree keeps them.
    The filter tries three times. It rejects the case when the predicate is
    also false for the last attempt.

    Attributes:
        of: The source generator.
        keep: The predicate.
    """

    #: The id of the span of each attempt.
    ID: ClassVar[str] = "filter"

    def __init__(self, of: Generator[_T], keep: Callable[[_T], bool]) -> None:
        """Return the generator of the values of of that keep accepts.

        Args:
            of: The source generator.
            keep: The predicate.
        """
        self.of: Generator[_T] = of
        self.keep: Callable[[_T], bool] = keep

    def decode(self, c: Case) -> _T:
        """Return the value of the first attempt that the predicate keeps.

        Args:
            c: The case.

        Returns:
            The kept value.

        Raises:
            Rejected: The predicate keeps no attempt.
        """
        mark = c.mark()
        value = self._attempt(c)
        for _ in range(1, _FILTER_ATTEMPTS):
            if self.keep(value):
                return value
            c.rewind(mark)
            value = self._attempt(c)
        c.assume(self.keep(value))
        return value

    def _attempt(self, c: Case) -> _T:
        """Decode one attempt in its own span."""
        with c.span(Filter.ID):
            return self.of.decode(c)


class Mapped(Generator[_U], Generic[_T, _U]):
    """The value that a function returns for the value of the source.

    It makes the choices of the source and does not open a span of its own.
    back is the inverse of the function. With back, the generator runs
    backwards.

    Attributes:
        of: The source generator.
        f: The function.
        back: The inverse of the function, or None for a function that the
            engine cannot run backwards. It raises for a value that f does
            not return.
    """

    def __init__(
        self,
        of: Generator[_T],
        f: Callable[[_T], _U],
        back: Callable[[_U], _T] | None = None,
    ) -> None:
        """Return the generator of f of the values of of.

        Args:
            of: The source generator.
            f: The function.
            back: The inverse of the function, or None.
        """
        self.of: Generator[_T] = of
        self.f: Callable[[_T], _U] = f
        self.back: Callable[[_U], _T] | None = back

    def decode(self, c: Case) -> _U:
        """Return the function of the value that the source decodes.

        Args:
            c: The case.

        Returns:
            The value of the function.
        """
        return self.f(self.of.decode(c))


class Bound(Generator[_U], Generic[_T, _U]):
    """A value of the generator that a function returns for a value of the source.

    The value of the source decodes first. Both values decode in one span.

    Attributes:
        of: The source generator.
        f: The function from a value to a generator.
    """

    #: The id of the span.
    ID: ClassVar[str] = "bind"

    def __init__(self, of: Generator[_T], f: Callable[[_T], Generator[_U]]) -> None:
        """Return the generator of the values of the generators that f returns.

        Args:
            of: The source generator.
            f: The function from a value to a generator.
        """
        self.of: Generator[_T] = of
        self.f: Callable[[_T], Generator[_U]] = f

    def decode(self, c: Case) -> _U:
        """Return the value of the second generator.

        Args:
            c: The case.

        Returns:
            The value of the generator that the function returned.
        """
        with c.span(Bound.ID):
            return self.f(self.of.decode(c)).decode(c)


class Composite(Generator[_T]):
    """The value of a function that draws from other generators in one span.

    Attributes:
        f: The function.
    """

    #: The id of the span.
    ID: ClassVar[str] = "composite"

    def __init__(self, f: Callable[[Case], _T]) -> None:
        """Return the generator of the values that f returns.

        Args:
            f: The function. It draws from the case.
        """
        self.f: Callable[[Case], _T] = f

    def decode(self, c: Case) -> _T:
        """Return the value of the function.

        Args:
            c: The case.

        Returns:
            The value that the function returns.
        """
        with c.span(Composite.ID):
            return self.f(c)


class _Leaves(threading.local):
    """The leaf counts of the values that one thread decodes. The innermost is last."""

    def __init__(self) -> None:
        self.counts: list[int] = []


class Recursive(Generator[_T]):
    """A base value, or an extension whose positions are recursive values.

    At each position, an integer choice that decides structure chooses
    between the base and the extension. The choice 0 takes the base, and 1
    takes the extension. Once one value has drawn max_leaves values from the
    base, every further position takes the base. Its choice then has the
    bounds [0, 0]. A Position inside the extension is one position.

    The count of leaves belongs to the decode that a thread runs, so each
    thread decodes one value at a time.

    Attributes:
        base: The base.
        max_leaves: The number of values that one value can draw from the
            base.
        extend: The extension.
    """

    #: The id of the span of each position.
    ID: ClassVar[str] = "recursive"

    def __init__(
        self,
        base: Generator[_T],
        max_leaves: int,
        extend: Callable[[Generator[_T]], Generator[_T]],
    ) -> None:
        """Return the generator of recursive values.

        Args:
            base: The base.
            max_leaves: The number of values that one value can draw from the
                base. It is at least 1.
            extend: Returns the extension from the generator of one position.
        """
        self.base: Generator[_T] = base
        self.max_leaves: int = max_leaves
        self._leaves: _Leaves = _Leaves()
        self.extend: Generator[_T] = extend(Position(self))

    def decode(self, c: Case) -> _T:
        """Return one recursive value. Its leaf count starts at zero.

        Args:
            c: The case.

        Returns:
            The value.
        """
        counts = self._leaves.counts
        counts.append(0)
        try:
            return self.position(c)
        finally:
            counts.pop()

    def position(self, c: Case) -> _T:
        """Decode one position of the value that is being decoded.

        Args:
            c: The case.

        Returns:
            The value of the position.
        """
        counts = self._leaves.counts
        exhausted = counts[-1] >= self.max_leaves
        with c.span(Recursive.ID):
            if c.integer(_NONE if exhausted else _BIT, 0) == 1:
                return self.extend.decode(c)
            counts[-1] += 1
            return self.base.decode(c)


class Position(Generator[_T]):
    """A position inside the extension of the recursive value that is being decoded.

    Attributes:
        owner: The recursive generator.
    """

    def __init__(self, owner: Recursive[_T]) -> None:
        """Return the position of the value of owner.

        Args:
            owner: The recursive generator.
        """
        self.owner: Recursive[_T] = owner

    def decode(self, c: Case) -> _T:
        """Decode the next position of the value of the owner.

        Args:
            c: The case.

        Returns:
            The value of the position.
        """
        return self.owner.position(c)
