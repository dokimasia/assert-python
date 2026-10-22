# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The three kinds of choice in a case.

A choice is one typed decision within bounds. Its kind is an integer, a
float or a sequence of small integers. Every choice has a target. The target
is the simplest value that its bounds allow. The sort key of a choice orders
its values from the simplest. The shrinker moves values towards their
targets. It accepts a candidate only when the case gets shortlex-smaller
under these keys.

A replay gives a generator the value that a case recorded. The bounds
coerce a value of another kind or a value outside the bounds that the
generator now requests. They cut, extend or clean a sequence, and they
replace any other value with the target. Every prefix of a recorded case is
therefore a valid case.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import ClassVar, Literal, TypeGuard, cast

from dokimi_assert._override import override
from dokimi_assert._prop.engine.float import (
    Key,
    Width,
    float_key,
    representable,
    same_float,
    simplest_float,
)

__all__ = [
    "INT64_MAX",
    "INT64_MIN",
    "UINT64_MAX",
    "Bounds",
    "Choice",
    "FloatBounds",
    "IntegerBounds",
    "Kind",
    "SequenceBounds",
    "Value",
    "choice_of",
    "same_choice",
]

#: The bounds of the signed and the unsigned 64-bit ranges.
INT64_MIN = -(1 << 63)
INT64_MAX = (1 << 63) - 1
UINT64_MAX = (1 << 64) - 1

#: The kind of a choice.
Kind = Literal["integer", "float", "sequence"]

#: The value of a choice of any kind.
Value = int | float | tuple[int, ...]


@dataclass(frozen=True, slots=True, eq=False)
class Choice:
    """One recorded decision with its kind and the value that the case used.

    same_choice compares two choices. It compares floats by their bits.

    Attributes:
        kind: The kind of the choice.
        value: An int for an integer, a float for a float, and a tuple of
            ints for a sequence.
    """

    kind: Kind
    value: Value


def _is_int(value: object) -> TypeGuard[int]:
    """Report whether value is an int that is not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


class IntegerBounds:
    """The inclusive bounds of an integer choice.

    Attributes:
        lo: The smallest value.
        hi: The largest value.
        target: The value closest to zero. It is zero when the bounds admit
            zero.
        id: The text of the bounds for a message.
    """

    #: The kind of the choices of these bounds.
    kind: ClassVar[Literal["integer"]] = "integer"

    def __init__(self, lo: int, hi: int) -> None:
        """Return the bounds [lo, hi].

        Args:
            lo: The smallest value.
            hi: The largest value.

        Raises:
            ValueError: The bounds are empty, or they are inside neither the
                signed nor the unsigned 64-bit range.
        """
        if lo > hi:
            msg = f"prop: integer bounds [{lo}, {hi}] are empty"
            raise ValueError(msg)
        signed = lo >= INT64_MIN and hi <= INT64_MAX
        unsigned = lo >= 0 and hi <= UINT64_MAX
        if not signed and not unsigned:
            msg = (
                f"prop: integer bounds [{lo}, {hi}] are inside neither the signed "
                "nor the unsigned 64-bit range"
            )
            raise ValueError(msg)
        self.lo: int = lo
        self.hi: int = hi
        self.target: int = 0 if lo <= 0 <= hi else (lo if lo > 0 else hi)
        self.id: str = f"integer {lo} {hi}"

    @override
    def __eq__(self, other: object) -> bool:
        """Report whether other is integer bounds of the same range."""
        return (
            isinstance(other, IntegerBounds)
            and self.lo == other.lo
            and self.hi == other.hi
        )

    @override
    def __hash__(self) -> int:
        """Return the hash of the range."""
        return hash((self.kind, self.lo, self.hi))

    def key(self, value: int) -> Key:
        """Return the sort key of a value.

        The key is the distance to the target and then the side. The side is
        1 below the target and 0 otherwise.

        Args:
            value: A value inside the bounds.

        Returns:
            The key.
        """
        return (abs(value - self.target), 1 if value < self.target else 0)

    def rank(self, value: int) -> int:
        """Return the position of a value in the key order of the bounds.

        The target is at 0. The order then takes the value one above the
        target, one below, two above and two below, and so on. Past the
        bound of the shorter side, it continues on the longer side.

        Args:
            value: A value inside the bounds.

        Returns:
            The position.
        """
        target = self.target
        shorter = min(self.hi - target, target - self.lo)
        distance = abs(value - target)
        if distance > shorter:
            return shorter + distance
        return 2 * distance - 1 if value > target else 2 * distance

    def at_rank(self, rank: int) -> int:
        """Return the value at a position of the key order. It inverts rank.

        Args:
            rank: A position from 0 to the number of values less one.

        Returns:
            The value.
        """
        target = self.target
        above = self.hi - target
        below = target - self.lo
        shorter = min(above, below)
        if rank > 2 * shorter:
            distance = rank - shorter
            return target + distance if above > below else target - distance
        distance = (rank + 1) // 2
        return target + distance if rank % 2 == 1 else target - distance

    def admits(self, value: object) -> TypeGuard[int]:
        """Report whether value is an int inside the bounds.

        Args:
            value: Any value.

        Returns:
            True for an int in [lo, hi], and False for a bool.
        """
        return _is_int(value) and self.lo <= value <= self.hi

    def coerce(self, recorded: Choice) -> int:
        """Return the recorded value when it fits, and the target otherwise.

        Args:
            recorded: A choice that a case recorded.

        Returns:
            The value.
        """
        value = recorded.value
        if recorded.kind == "integer" and self.admits(value):
            return value
        return self.target


class FloatBounds:
    """The bounds of a float choice with an inclusive range, a NaN rule and a width.

    An infinite bound admits that infinity. NaN is a value only when
    allow_nan is set.

    Attributes:
        lo: The smallest value. It can be negative infinity.
        hi: The largest value. It can be positive infinity.
        allow_nan: When True, NaN is a value.
        width: The width of the values.
        target: The value in the bounds with the smallest sort key.
        id: The text of the bounds for a message.
    """

    #: The kind of the choices of these bounds.
    kind: ClassVar[Literal["float"]] = "float"

    def __init__(
        self, lo: float, hi: float, allow_nan: bool = False, width: Width = 64
    ) -> None:
        """Return the bounds [lo, hi] of floats of a width.

        Args:
            lo: The smallest value.
            hi: The largest value.
            allow_nan: When True, NaN is a value.
            width: The width. It is 32 or 64.

        Raises:
            ValueError: The width is neither 32 nor 64, a bound is NaN or not
                a value of the width, or lo is above hi.
        """
        # A caller without type annotations can pass any width.
        if cast("int", width) not in (32, 64):
            msg = f"prop: float width {width} is neither 32 nor 64"
            raise ValueError(msg)
        if math.isnan(lo) or math.isnan(hi) or lo > hi:
            msg = f"prop: float bounds [{lo}, {hi}] are empty"
            raise ValueError(msg)
        for bound in (lo, hi):
            if not representable(bound, width):
                msg = f"prop: float bound {bound} is not a value of width {width}"
                raise ValueError(msg)
        self.lo: float = lo
        self.hi: float = hi
        self.allow_nan: bool = allow_nan
        self.width: Width = width
        # lo is a value of the width inside [lo, hi], so the range has a
        # simplest value.
        self.target: float = cast("float", simplest_float(lo, hi, width))
        self.id: str = f"float {lo} {hi} {allow_nan} {width}"

    @override
    def __eq__(self, other: object) -> bool:
        """Report whether other is float bounds with the same range, rule and width."""
        return (
            isinstance(other, FloatBounds)
            and self.lo == other.lo
            and self.hi == other.hi
            and self.allow_nan == other.allow_nan
            and self.width == other.width
        )

    @override
    def __hash__(self) -> int:
        """Return the hash of the range, the NaN rule and the width."""
        return hash((self.kind, self.lo, self.hi, self.allow_nan, self.width))

    def key(self, value: float) -> Key:
        """Return the sort key of a float.

        Args:
            value: A float.

        Returns:
            The key.
        """
        return float_key(value)

    def admits(self, value: object) -> TypeGuard[float]:
        """Report whether value is a float of the bounds.

        Args:
            value: Any value.

        Returns:
            True for a float of the width inside the bounds, and for NaN
            where the bounds allow it.
        """
        if not isinstance(value, float):
            return False
        if math.isnan(value):
            return self.allow_nan
        return self.lo <= value <= self.hi and representable(value, self.width)

    def coerce(self, recorded: Choice) -> float:
        """Return the recorded value when it fits, and the target otherwise.

        A recorded NaN becomes the canonical NaN. Its payload does not
        matter.

        Args:
            recorded: A choice that a case recorded.

        Returns:
            The value.
        """
        value = recorded.value
        if recorded.kind != "float" or not self.admits(value):
            return self.target
        return math.nan if math.isnan(value) else value


class SequenceBounds:
    """The bounds of the elements and the length of a sequence choice.

    Every element is an integer in [0, k). A max_size of None leaves the
    length unbounded. The cap on the choices of a case then bounds it.

    Attributes:
        k: The number of element values.
        min_size: The smallest number of elements.
        max_size: The largest number of elements, or None without a bound.
        target: A tuple of min_size zeros.
        id: The text of the bounds for a message.
    """

    #: The kind of the choices of these bounds.
    kind: ClassVar[Literal["sequence"]] = "sequence"

    def __init__(self, k: int, min_size: int = 0, max_size: int | None = None) -> None:
        """Return the bounds of sequences of min_size to max_size elements below k.

        Args:
            k: The number of element values. It is at least 1.
            min_size: The smallest number of elements.
            max_size: The largest number of elements, or None without a
                bound.

        Raises:
            ValueError: k is below 1, min_size is negative, or max_size is
                below min_size.
        """
        if k < 1:
            msg = f"prop: a sequence with k = {k} cannot have an element"
            raise ValueError(msg)
        if min_size < 0 or (max_size is not None and max_size < min_size):
            msg = f"prop: sequence sizes [{min_size}, {max_size}] are empty"
            raise ValueError(msg)
        self.k: int = k
        self.min_size: int = min_size
        self.max_size: int | None = max_size
        self.target: tuple[int, ...] = (0,) * min_size
        self.id: str = f"sequence {k} {min_size} {max_size}"

    @override
    def __eq__(self, other: object) -> bool:
        """Report whether other is sequence bounds of the same elements and sizes."""
        return (
            isinstance(other, SequenceBounds)
            and self.k == other.k
            and self.min_size == other.min_size
            and self.max_size == other.max_size
        )

    @override
    def __hash__(self) -> int:
        """Return the hash of the elements and the sizes."""
        return hash((self.kind, self.k, self.min_size, self.max_size))

    def key(self, value: tuple[int, ...]) -> Key:
        """Return the sort key of a sequence.

        The key is the length and then the elements.

        Args:
            value: A sequence.

        Returns:
            The key.
        """
        return (len(value), *value)

    def admits(self, value: object) -> TypeGuard[tuple[int, ...]]:
        """Report whether value is a sequence that the bounds admit.

        Args:
            value: Any value.

        Returns:
            True for a tuple of the sizes whose elements are ints in [0, k).
        """
        if not isinstance(value, tuple) or len(value) < self.min_size:
            return False
        stated: tuple[object, ...] = value
        if self.max_size is not None and len(stated) > self.max_size:
            return False
        return all(_is_int(e) and 0 <= e < self.k for e in stated)

    def coerce(self, recorded: Choice) -> tuple[int, ...]:
        """Fit a recorded sequence to the bounds.

        The method cuts a longer sequence to max_size. It extends a shorter
        sequence with zeros to min_size. An element outside [0, k) becomes 0.
        A value of another kind becomes the target.

        Args:
            recorded: A choice that a case recorded.

        Returns:
            The value.
        """
        value = recorded.value
        if recorded.kind != "sequence" or not isinstance(value, tuple):
            return self.target
        elements = [e if 0 <= e < self.k else 0 for e in value]
        kept = elements if self.max_size is None else elements[: self.max_size]
        kept.extend([0] * (self.min_size - len(kept)))
        return tuple(kept)


#: The bounds of a choice of any kind.
Bounds = IntegerBounds | FloatBounds | SequenceBounds


def choice_of(bounds: Bounds, value: Value) -> Choice:
    """Return the choice of the kind of the bounds with a value.

    Args:
        bounds: The bounds of the request of the choice.
        value: A value of the kind of the bounds.

    Returns:
        The choice.
    """
    return Choice(bounds.kind, value)


def same_choice(a: Choice, b: Choice) -> bool:
    """Report whether two choices are one choice.

    Two choices are one choice when their kinds and their values are the
    same. same_float compares floats.

    Args:
        a: A choice.
        b: Another choice.

    Returns:
        True when a and b are one choice.
    """
    if a.kind != b.kind:
        return False
    if isinstance(a.value, float) and isinstance(b.value, float):
        return same_float(a.value, b.value)
    return a.value == b.value
