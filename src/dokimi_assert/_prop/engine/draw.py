# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The draws of a generated case from its random source.

The definition fixes the order in which every draw consumes the source. The
same seed gives the same values in every language only when every
implementation consumes the stream in the same way as these functions. That
includes the draws that they skip. Equal bounds, a forced collection flag
and a range of one element consume nothing.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from dokimi_assert._prop.engine.choice import (
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
)
from dokimi_assert._prop.engine.float import (
    BINARY64,
    from_bits,
    from_bits32,
    next_down,
    next_up,
    same_float,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from fractions import Fraction

    from dokimi_assert._prop.engine.source import Source

__all__ = [
    "REUSE_ODDS",
    "average_length",
    "boolean",
    "flag",
    "flag_bounds",
    "float_edges",
    "float_value",
    "integer",
    "integer_edges",
    "keep",
    "sequence",
    "weighted",
]

#: One integer draw in _EDGE_ODDS takes an edge value.
_EDGE_ODDS = 8

#: The odds 1 in REUSE_ODDS that a reusable integer draw takes an earlier
#: value of its case with the same bounds.
REUSE_ODDS = 4

#: The caps of the offset of an integer draw. The draw chooses a cap with
#: even odds. Small offsets from the target are then common, and the largest
#: cap lets the draw return every value of the bounds.
_OFFSET_CAPS = (1 << 4, 1 << 8, 1 << 16, 1 << 64)

#: The smallest average number of extra elements of a collection without a
#: close maximum.
_DEFAULT_EXTRA = 5

#: The number of branches of a float draw and the last integral branch.
#: Branch 0 takes an edge value. Branches 1 to 3 take an integral value. The
#: other branches assemble the bits.
_FLOAT_BRANCHES = 8
_FLOAT_LAST_INTEGRAL_BRANCH = 3

#: The magnitude below which every integer is a value of the width.
_EXACT_INTEGERS = {32: 2**24, 64: 2**53}

#: The widths of the exponent and the mantissa fields of a float.
_EXPONENT_BITS = {32: 8, 64: 11}
_MANTISSA_BITS = {32: 23, 64: 52}


def integer_edges(bounds: IntegerBounds) -> list[int]:
    """Return the edge values of integer bounds.

    The candidates are the target, lo, hi, the value above the target and the
    value below it. The edges are the candidates inside the bounds in that
    order, without repeats.

    Args:
        bounds: The bounds.

    Returns:
        The edges.
    """
    target = bounds.target
    values: list[int] = []
    for value in (target, bounds.lo, bounds.hi, target + 1, target - 1):
        if bounds.admits(value) and value not in values:
            values.append(value)
    return values


def integer(source: Source, bounds: IntegerBounds) -> int:
    """Draw an integer inside the bounds.

    Equal bounds return their value and consume nothing. Otherwise a coin of
    1 in 8 decides whether the draw takes an edge value. below(number of
    edges) chooses the edge. Any other draw moves away from the target.

    - It moves up when the target is lo.
    - It moves down when the target is hi.
    - A coin of 1 in 2 chooses the direction when the target is strictly
      between the bounds.

    The offset is below(min(span, cap - 1) + 1). span is the distance to the
    bound in that direction. cap is one of four caps, and below(4) chooses
    it.

    Args:
        source: The source of the case.
        bounds: The bounds.

    Returns:
        The value.
    """
    if bounds.lo == bounds.hi:
        return bounds.lo
    if source.coin(1, _EDGE_ODDS):
        values = integer_edges(bounds)
        return values[source.below(len(values))]
    target = bounds.target
    if target == bounds.lo:
        up = True
    elif target == bounds.hi:
        up = False
    else:
        up = source.coin(1, 2)
    span = bounds.hi - target if up else target - bounds.lo
    cap = _OFFSET_CAPS[source.below(len(_OFFSET_CAPS))]
    offset = source.below(min(span, cap - 1) + 1)
    return target + offset if up else target - offset


def boolean(source: Source, p: Fraction) -> int:
    """Draw 1 with the probability p and 0 otherwise. The draw tosses one coin.

    Args:
        source: The source of the case.
        p: The probability of 1.

    Returns:
        1 or 0.
    """
    return 1 if source.coin(p.numerator, p.denominator) else 0


def weighted(source: Source, weights: Sequence[int]) -> int:
    """Draw an index with a probability proportional to its weight.

    One weight returns 0 and consumes nothing. Otherwise the draw is
    below(sum of the weights). The index is the first index whose running
    sum of weights exceeds the draw.

    Args:
        source: The source of the case.
        weights: The positive weights.

    Returns:
        The index.
    """
    if len(weights) == 1:
        return 0
    point = source.below(sum(weights))
    total = 0
    index = 0
    while True:
        total += weights[index]
        if point < total:
            return index
        index += 1


def keep(source: Source, p: Fraction, kept: bool, remaining: int) -> int:
    """Decide whether swarm keeps an action. 1 keeps it, and 0 disables it.

    Once an earlier action is kept, one coin of the probability decides.
    While no earlier action is kept, the last action is kept and consumes
    nothing. For an action before the last, the draw tosses one coin for
    this action and one for each later action. It repeats the round until a
    coin comes up. It keeps the action when the coin of the action came up.

    Args:
        source: The source of the case.
        p: The probability that a coin comes up.
        kept: When True, an earlier action is kept.
        remaining: The number of actions from this action to the last.

    Returns:
        1 or 0.
    """
    if kept:
        return boolean(source, p)
    if remaining == 1:
        return 1
    while True:
        coins = [boolean(source, p) for _ in range(remaining)]
        if 1 in coins:
            return coins[0]


def average_length(min_size: int, max_size: int | None) -> int:
    """Return the average length of a collection.

    The average is min + min(max(min, 5), ceil((max - min) / 2)). Without a
    maximum, it is min + max(min, 5).

    Args:
        min_size: The smallest number of elements.
        max_size: The largest number of elements, or None without a bound.

    Returns:
        The average as an integer.
    """
    extra = max(min_size, _DEFAULT_EXTRA)
    if max_size is not None:
        extra = min(extra, -(-(max_size - min_size) // 2))
    return min_size + extra


#: The bounds of a forced continue, a forced stop and a free decision.
_FORCED_ON = IntegerBounds(1, 1)
_FORCED_OFF = IntegerBounds(0, 0)
_FREE = IntegerBounds(0, 1)


def flag_bounds(count: int, min_size: int, max_size: int | None) -> IntegerBounds:
    """Return the bounds of the decision whether a collection gets another element.

    - The bounds are [1, 1] while count is below the minimum.
    - They are [0, 0] once count is at the maximum.
    - They are [0, 1] otherwise.

    Args:
        count: The number of elements so far.
        min_size: The smallest number of elements.
        max_size: The largest number of elements, or None without a bound.

    Returns:
        The bounds.
    """
    if count < min_size:
        return _FORCED_ON
    if max_size is not None and count >= max_size:
        return _FORCED_OFF
    return _FREE


def flag(
    source: Source, count: int, min_size: int, max_size: int | None, average: int
) -> int:
    """Decide whether a collection of count elements gets another.

    A forced decision returns the one value that its bounds allow and
    consumes nothing. A free decision continues by a coin of (average - min)
    in (average - min + 1).

    Args:
        source: The source of the case.
        count: The number of elements so far.
        min_size: The smallest number of elements.
        max_size: The largest number of elements, or None without a bound.
        average: The average length.

    Returns:
        1 to continue and 0 to stop.
    """
    bounds = flag_bounds(count, min_size, max_size)
    if bounds.lo == bounds.hi:
        return bounds.lo
    extra = average - min_size
    return 1 if source.coin(extra, extra + 1) else 0


def float_edges(bounds: FloatBounds) -> list[float]:
    """Return the edge values of float bounds.

    The candidates are the target, lo, hi, the next value above the target
    and the next value below it. The edges are the candidates that the
    bounds admit in that order, without repeats. NaN follows them when the
    bounds allow it.

    Args:
        bounds: The bounds.

    Returns:
        The edges.
    """
    target = bounds.target
    values: list[float] = []
    candidates = (
        target,
        bounds.lo,
        bounds.hi,
        next_up(target, bounds.width),
        next_down(target, bounds.width),
    )
    for value in candidates:
        if bounds.admits(value) and not any(same_float(v, value) for v in values):
            values.append(value)
    if bounds.allow_nan:
        values.append(math.nan)
    return values


def _integral_bounds(bounds: FloatBounds) -> IntegerBounds | None:
    """Return the integers that the bounds admit and that are exact values of the width.

    The result is None when no such integer exists. The bounds of one
    infinity are an example.
    """
    if bounds.lo == math.inf or bounds.hi == -math.inf:
        return None
    limit = _EXACT_INTEGERS[bounds.width] - 1
    lo = -limit if bounds.lo < -limit else math.ceil(bounds.lo)
    hi = limit if bounds.hi > limit else math.floor(bounds.hi)
    return None if lo > hi else IntegerBounds(lo, hi)


def _from_parts(source: Source, bounds: FloatBounds) -> float:
    """Assemble a float from a sign, an exponent and a mantissa.

    The draw takes the parts in order as below(2), below(2^exponent bits)
    and below(2^mantissa bits). A NaN stays NaN when the bounds allow it and
    becomes the target otherwise. A value below lo becomes lo, and a value
    above hi becomes hi. The comparison is numeric, so the draw returns -0.0
    unchanged when lo is 0.0.
    """
    exponent_bits = _EXPONENT_BITS[bounds.width]
    mantissa_bits = _MANTISSA_BITS[bounds.width]
    sign = source.below(2)
    exponent = source.below(1 << exponent_bits)
    mantissa = source.below(1 << mantissa_bits)
    bits = (
        (sign << (exponent_bits + mantissa_bits))
        | (exponent << mantissa_bits)
        | mantissa
    )
    value = from_bits(bits) if bounds.width == BINARY64 else from_bits32(bits)
    if math.isnan(value):
        return math.nan if bounds.allow_nan else bounds.target
    if value < bounds.lo:
        return bounds.lo
    if value > bounds.hi:
        return bounds.hi
    return value


def float_value(source: Source, bounds: FloatBounds) -> float:
    """Draw a float inside the bounds.

    below(8) picks the branch. Branch 0 takes an edge value, and
    below(number of edges) chooses the edge. Branches 1 to 3 draw an integer
    in the same way as integer. They draw over the integers that the bounds
    admit and that are exact values of the width. The other branches
    assemble the value from its bits. An integral branch does the same when
    its bounds do not admit such an integer.

    Args:
        source: The source of the case.
        bounds: The bounds.

    Returns:
        The value.
    """
    branch = source.below(_FLOAT_BRANCHES)
    if branch == 0:
        values = float_edges(bounds)
        return values[source.below(len(values))]
    if branch <= _FLOAT_LAST_INTEGRAL_BRANCH:
        integral = _integral_bounds(bounds)
        if integral is not None:
            return float(integer(source, integral))
    return _from_parts(source, bounds)


def sequence(source: Source, bounds: SequenceBounds) -> tuple[int, ...]:
    """Draw a sequence inside the bounds.

    Each position first takes the decision that flag makes for a collection.
    When the decision continues, the position takes an element that integer
    draws over [0, k - 1]. A byte string therefore consumes the stream in
    the same way as a list of integers in [0, 255] with the same sizes. It
    gets the same values.

    Args:
        source: The source of the case.
        bounds: The bounds.

    Returns:
        The elements.
    """
    average = average_length(bounds.min_size, bounds.max_size)
    element = IntegerBounds(0, bounds.k - 1)
    elements: list[int] = []
    while flag(source, len(elements), bounds.min_size, bounds.max_size, average) == 1:
        elements.append(integer(source, element))
    return tuple(elements)
