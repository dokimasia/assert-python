# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The generators of the property engine.

Each generator has a domain, and it decodes a value of the domain from the
choices of a case. The definition specifies the decoding. The same seed gives
the same values in every language, and a failing case shrinks to the same
counterexample. A size or a flag of a generator is a keyword argument.

The functions float, list, dict and bytes shadow builtins inside this
module, so the module refers to the builtins through the module builtins.
"""

from __future__ import annotations

import builtins
import numbers
from collections.abc import Callable, Mapping
from fractions import Fraction
from typing import Any, Literal, TypeVar

from dokimi_assert._prop.case import Case, case_of
from dokimi_assert._prop.engine import alphabet as default_alphabet
from dokimi_assert._prop.engine.choice import (
    INT64_MAX,
    INT64_MIN,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
)
from dokimi_assert._prop.engine.collection import Sizes
from dokimi_assert._prop.engine.generator import (
    Bool,
    Bytes,
    Composite,
    Dict,
    Float,
    Generator,
    Integer,
    Just,
    List,
    Mapped,
    Matching,
    OneOf,
    Optional,
    Permutation,
    Recursive,
    SampledFrom,
    Text,
)
from dokimi_assert._prop.engine.pattern import piece
from dokimi_assert._prop.engine.value import Pairs
from dokimi_assert._prop.registry import Extending

__all__ = [
    "boolean",
    "bytes",
    "composite",
    "dict",
    "duration",
    "float",
    "integer",
    "just",
    "list",
    "one_of",
    "optional",
    "permutation",
    "recursive",
    "sampled_from",
    "string",
    "string_matching",
]

_T = TypeVar("_T")
_K = TypeVar("_K")
_V = TypeVar("_V")

#: The number of values of a byte.
_BYTE_VALUES = 256

#: The probability of True when a call of boolean does not set one.
_HALF = Fraction(1, 2)


def _checked(call: str, make: Callable[[], _T]) -> _T:
    """Return the result of make, and put the call at the start of a refusal.

    Raises:
        ValueError: The engine refuses the arguments of the call.
    """
    try:
        return make()
    except ValueError as error:
        reason = str(error).removeprefix("prop: ")
        msg = f"prop: {call}: {reason}"
        raise ValueError(msg) from error


def _sizes(call: str, min_size: int, max_size: int | None) -> Sizes:
    """Return the sizes of a collection.

    Raises:
        ValueError: A size is not an int, or the sizes do not admit a length.
    """
    text = f"{call}(min_size={min_size!r}, max_size={max_size!r})"
    if type(min_size) is not int or not (max_size is None or type(max_size) is int):
        msg = f"prop: {text} needs sizes that are ints"
        raise ValueError(msg)
    return _checked(text, lambda: Sizes(min_size, max_size))


def integer(lo: int, hi: int) -> Generator[int]:
    """Return the generator of the integers from lo to hi.

    The generator makes one integer choice. Its target is the value closest
    to zero. The bounds are both inside the signed or both inside the
    unsigned 64-bit range.

    Args:
        lo: The smallest value.
        hi: The largest value.

    Returns:
        The generator.

    Raises:
        ValueError: A bound is not an int, lo is above hi, or the bounds are
            inside neither 64-bit range.
    """
    call = f"integer({lo!r}, {hi!r})"
    if type(lo) is not int or type(hi) is not int:
        msg = f"prop: {call} needs two ints"
        raise ValueError(msg)
    return Integer(_checked(call, lambda: IntegerBounds(lo, hi)))


def float(
    lo: builtins.float,
    hi: builtins.float,
    *,
    allow_nan: bool = False,
    width: Literal[32, 64] = 64,
) -> Generator[builtins.float]:
    """Return the generator of the floats from lo to hi.

    The generator makes one float choice. Its target is the simplest value
    in the range. A bound can be an infinity. NaN is a value only when
    allow_nan is True. A value of width 32 is a float that the format f of
    struct keeps unchanged.

    Args:
        lo: The smallest value.
        hi: The largest value.
        allow_nan: When True, NaN is a value.
        width: The width of the values, 32 or 64.

    Returns:
        The generator.

    Raises:
        ValueError: A bound is not a number, the range does not contain a
            value of the width, or the width is neither 32 nor 64.
    """
    call = f"float({lo!r}, {hi!r})"
    if type(lo) not in (int, builtins.float) or type(hi) not in (int, builtins.float):
        msg = f"prop: {call} needs two numbers"
        raise ValueError(msg)
    low = builtins.float(lo)
    high = builtins.float(hi)
    return Float(_checked(call, lambda: FloatBounds(low, high, allow_nan, width)))


def boolean(p: Fraction | int = _HALF) -> Generator[bool]:
    """Return the generator of bools that are True with the probability p.

    The generator makes one integer choice from 0 to 1. Its target is False.

    Args:
        p: The probability of True, from 0 to 1. The default is 1/2.

    Returns:
        The generator.

    Raises:
        ValueError: p is not a Fraction or an int from 0 to 1.
    """
    if isinstance(p, bool) or not isinstance(p, numbers.Rational) or not 0 <= p <= 1:
        msg = f"prop: boolean({p!r}) needs a Fraction or an int from 0 to 1"
        raise ValueError(msg)
    return Bool(Fraction(p))


def just(value: _T) -> Generator[_T]:
    """Return the generator of value alone.

    The generator does not make a choice.

    Args:
        value: The value.

    Returns:
        The generator.
    """
    return Just(value)


def sampled_from(*values: _T) -> Generator[_T]:
    """Return the generator of one of values.

    The generator makes one integer choice of an index. The index decides
    structure, and its target is the first value.

    Args:
        *values: One value or more.

    Returns:
        The generator.

    Raises:
        ValueError: values is empty.
    """
    if not values:
        msg = "prop: sampled_from() needs a value"
        raise ValueError(msg)
    return SampledFrom(values)


def one_of(*generators: Generator[_T]) -> Generator[_T]:
    """Return the generator of a value of one of generators.

    The generator makes one integer choice of an index, and then the choices
    of that generator. The index decides structure. The target is the
    simplest value of the first generator.

    Args:
        *generators: One generator or more.

    Returns:
        The generator.

    Raises:
        ValueError: generators is empty.
    """
    if not generators:
        msg = "prop: one_of() needs a generator"
        raise ValueError(msg)
    return OneOf(generators)


def optional(of: Generator[_T]) -> Generator[_T | None]:
    """Return the generator of a value of of, or None.

    The generator makes a choice of presence, and then the choices of the
    value when it is present. Its target is None.

    Args:
        of: The generator of the value.

    Returns:
        The generator.
    """
    return Optional(of)


def list(
    of: Generator[_T],
    *,
    min_size: int = 0,
    max_size: int | None = None,
    unique: bool = False,
) -> Generator[builtins.list[_T]]:
    """Return the generator of lists of the values of of.

    For each element, the generator makes a continue choice and the choices
    of the element. Then it makes a stop choice. A unique list discards an
    element that equals an earlier one, and ten discards in a row end the
    list. Without max_size, the cap on the choices of a case bounds the size.

    Args:
        of: The generator of the elements.
        min_size: The smallest number of elements.
        max_size: The largest number of elements, or None.
        unique: When True, the elements of a list are distinct.

    Returns:
        The generator.

    Raises:
        ValueError: A size is not an int, or the sizes do not admit a length.
    """
    return List(of, _sizes("list", min_size, max_size), unique)


def dict(
    keys: Generator[_K],
    values: Generator[_V],
    *,
    min_size: int = 0,
    max_size: int | None = None,
) -> Generator[builtins.dict[_K, _V]]:
    """Return the generator of dicts from the values of keys to the values of values.

    For each entry, the generator makes a continue choice, the choices of the
    key and the choices of the value. Then it makes a stop choice. The
    generator discards an entry whose key equals an earlier key. The keys
    must be hashable. Python counts 0.0 and -0.0 as equal keys, and 1 and
    True too. The definition counts each such pair as two keys, and a dict
    keeps one key of the pair.

    Args:
        keys: The generator of the keys.
        values: The generator of the values.
        min_size: The smallest number of entries.
        max_size: The largest number of entries, or None.

    Returns:
        The generator.

    Raises:
        ValueError: A size is not an int, or the sizes do not admit a length.
    """

    def back(value: Any) -> Any:
        return Pairs(tuple(value.items())) if isinstance(value, Mapping) else value

    entries = Dict(keys, values, _sizes("dict", min_size, max_size))
    return Mapped(entries, lambda pairs: builtins.dict(pairs.items), back)


def string(
    *,
    alphabet: str | None = None,
    min_size: int = 0,
    max_size: int | None = None,
) -> Generator[str]:
    """Return the generator of strings.

    The generator makes one sequence choice of indices into the alphabet. The
    default alphabet starts with the digits, the lowercase and the uppercase
    letters, space and the ASCII punctuation. Every other Unicode scalar
    value follows them, so a string shrinks towards "0". A string never
    contains a lone surrogate.

    Args:
        alphabet: The characters of the strings in order from the simplest,
            or None for the default alphabet.
        min_size: The smallest number of characters.
        max_size: The largest number of characters, or None.

    Returns:
        The generator.

    Raises:
        ValueError: A size is not an int, the sizes do not admit a length,
            or the alphabet is empty, repeats a character or contains a lone
            surrogate.
    """
    sizes = _sizes("string", min_size, max_size)
    if alphabet is None:
        bounds = SequenceBounds(default_alphabet.SIZE, sizes.min_size, sizes.max_size)
        return Text(None, bounds)
    call = f"string(alphabet={alphabet!r})"
    characters = builtins.list(alphabet)
    if not characters:
        msg = f"prop: {call}: the alphabet is empty"
        raise ValueError(msg)
    if len(set(characters)) != len(characters):
        msg = f"prop: {call}: the alphabet repeats a character"
        raise ValueError(msg)
    if any(default_alphabet.index_of(char) is None for char in characters):
        msg = f"prop: {call}: the alphabet contains a lone surrogate"
        raise ValueError(msg)
    return Text(
        characters, SequenceBounds(len(characters), sizes.min_size, sizes.max_size)
    )


def bytes(
    *, min_size: int = 0, max_size: int | None = None
) -> Generator[builtins.bytes]:
    """Return the generator of byte strings.

    The generator makes one sequence choice over 256 element values.

    Args:
        min_size: The smallest number of bytes.
        max_size: The largest number of bytes, or None.

    Returns:
        The generator.

    Raises:
        ValueError: A size is not an int, or the sizes do not admit a length.
    """
    sizes = _sizes("bytes", min_size, max_size)
    return Bytes(SequenceBounds(_BYTE_VALUES, sizes.min_size, sizes.max_size))


def duration(lo: int, hi: int) -> Generator[int]:
    """Return the generator of the durations from lo to hi nanoseconds.

    The generator makes one integer choice of nanoseconds. Its target is the
    duration closest to zero. A duration is an int of nanoseconds, the same
    unit as the result of time.monotonic_ns.

    Args:
        lo: The shortest duration in nanoseconds.
        hi: The longest duration in nanoseconds.

    Returns:
        The generator.

    Raises:
        ValueError: A bound is not an int, lo is above hi, or a bound is
            outside the signed 64-bit range.
    """
    call = f"duration({lo!r}, {hi!r})"
    if type(lo) is not int or type(hi) is not int:
        msg = f"prop: {call} needs two ints"
        raise ValueError(msg)
    if not INT64_MIN <= lo <= hi <= INT64_MAX:
        msg = f"prop: {call} needs bounds in order inside the signed 64-bit range"
        raise ValueError(msg)
    return Integer(IntegerBounds(lo, hi), "duration")


def permutation(*values: _T) -> Generator[builtins.list[_T]]:
    """Return the generator of the orderings of values.

    The generator makes one choice of a swap for each position. Its targets
    leave the values in their order.

    Args:
        *values: The values.

    Returns:
        The generator.
    """
    return Permutation(values)


def string_matching(pattern: str) -> Generator[str]:
    """Return the generator of the strings that pattern matches in full.

    The pattern is in the portable subset. An alternation chooses a branch,
    a quantifier chooses its repetitions as a collection, and a class
    chooses a character by its index in the order of the default alphabet.
    The class [A0a] then shrinks to 0.

    Args:
        pattern: The pattern.

    Returns:
        The generator.

    Raises:
        ValueError: The pattern is outside the portable subset, or a class of
            the pattern does not have a member.
    """
    return Matching(_checked(f"string_matching({pattern!r})", lambda: piece(pattern)))


def recursive(
    base: Generator[_T],
    extend: Callable[[Generator[_T]], Generator[_T]],
    *,
    max_leaves: int = 100,
) -> Generator[_T]:
    """Return the generator of recursive values.

    Each position of a value takes the base or an extension, and each
    position of an extension is itself a recursive value. Once a value has
    taken max_leaves values from the base, every further position takes the
    base. The target is the simplest value of the base.

    A run of using(t, generator), where generator is the recursive generator
    as it is or through filter, changes what a draw of of decodes in the
    extension. Inside the stated generator of t, the draw takes each t from
    the generator of the position. That applies to a draw of t, to a draw of
    a type that contains t, and to the draws inside the stated generator of
    another type. The base takes t without the stated generator, as using
    states:

        nodes = prop.recursive(
            prop.just(Leaf()),
            lambda _: prop.composite(lambda c: Branch(c.draw(prop.of(list[Node])))),
        )
        prop.for_all(t, "a tree has a depth", body, prop.using(Node, nodes))

    Args:
        base: The generator of a leaf.
        extend: The function that returns the extension of the generator of
            one position.
        max_leaves: The largest number of values that one value takes from
            the base.

    Returns:
        The generator.

    Raises:
        ValueError: max_leaves is not an int of 1 or more.
    """
    if type(max_leaves) is not int or max_leaves < 1:
        msg = f"prop: recursive(max_leaves={max_leaves!r}) needs an int of 1 or more"
        raise ValueError(msg)
    return Recursive(
        base, max_leaves, lambda position: Extending(extend(position), position)
    )


def composite(f: Callable[[Case], _T]) -> Generator[_T]:
    """Return the generator of the values that f returns.

    f takes its values from other generators through the case that it
    receives. One span contains all its draws. The generator does not have
    an inverse, so an example of it runs on its value.

    Args:
        f: The function.

    Returns:
        The generator.
    """
    return Composite(lambda engine: f(case_of(engine)))
