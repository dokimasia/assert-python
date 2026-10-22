# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The bits, the neighbours and the sort key of the values of a float choice.

A float choice has a width of 32 or 64 bits. A value of width 32 is a float
that rounding to binary32 leaves unchanged. The sort key orders the values
of a float choice from the simplest.
"""

from __future__ import annotations

import math
import struct
from typing import Literal

__all__ = [
    "BINARY64",
    "INTEGRAL_LIMIT",
    "NAN_BITS",
    "Key",
    "Width",
    "bits_of",
    "float_key",
    "from_bits",
    "from_bits32",
    "fround",
    "next_down",
    "next_up",
    "representable",
    "same_float",
    "simplest_float",
]

#: The widths of a float choice.
Width = Literal[32, 64]

#: The width of binary64, the format of a Python float.
BINARY64: Width = 64

#: A sort key. Python compares two keys element by element. A prefix sorts
#: before a longer key.
Key = tuple[int, ...]

#: The bits of the canonical quiet NaN. Every NaN in a choice has these bits.
NAN_BITS = 0x7FF8000000000000

#: The integral floats below this magnitude sort first. They sort by
#: magnitude.
INTEGRAL_LIMIT = 2**53

#: The most fractional bits that a finite float of each width has.
_MAX_FRACTION_BITS = {32: 149, 64: 1074}

#: The number of bits in the significand of a binary64. The count includes
#: the implicit bit.
_SIGNIFICAND_BITS = 53

#: The first element of the sort key of each group. A simpler group has a
#: smaller value.
_GROUP_INTEGRAL = 0
_GROUP_FRACTION = 1
_GROUP_INFINITE = 2
_GROUP_NAN = 3


def bits_of(x: float) -> int:
    """Return the IEEE 754 binary64 bits of x.

    Args:
        x: The float.

    Returns:
        The bits as an unsigned 64-bit integer.
    """
    return int.from_bytes(struct.pack("<d", x), "little")


def from_bits(bits: int) -> float:
    """Return the binary64 float of bits.

    Args:
        bits: An unsigned 64-bit integer.

    Returns:
        The float.
    """
    value: float = struct.unpack("<d", bits.to_bytes(8, "little"))[0]
    return value


def from_bits32(bits: int) -> float:
    """Return the binary32 float of bits as a Python float.

    Args:
        bits: An unsigned 32-bit integer.

    Returns:
        The float.
    """
    value: float = struct.unpack("<f", bits.to_bytes(4, "little"))[0]
    return value


def _bits32_of(x: float) -> int:
    """Return the binary32 bits of a value x of width 32."""
    return int.from_bytes(struct.pack("<f", x), "little")


def fround(x: float) -> float:
    """Return x rounded to the nearest binary32 value.

    A finite value that rounds past the largest binary32 rounds to the
    infinity of its sign.

    Args:
        x: The float.

    Returns:
        The binary32 value as a Python float.
    """
    try:
        value: float = struct.unpack("<f", struct.pack("<f", x))[0]
    except OverflowError:
        return math.copysign(math.inf, x)
    return value


def representable(x: float, width: Width) -> bool:
    """Report whether x is a value of the width.

    NaN and the infinities are values of both widths.

    Args:
        x: The float.
        width: The width.

    Returns:
        True when x is a value of the width.
    """
    return width == BINARY64 or math.isnan(x) or fround(x) == x


def next_up(x: float, width: Width) -> float:
    """Return the smallest value of the width above x.

    The smallest positive subnormal is the next value up from both zeros.
    Positive infinity and NaN are their own next value up.

    Args:
        x: A value of the width.
        width: The width.

    Returns:
        The next value up.
    """
    if math.isnan(x) or x == math.inf:
        return x
    if width == BINARY64:
        return math.nextafter(x, math.inf)
    if x == 0:
        return from_bits32(1)
    bits = _bits32_of(x)
    return from_bits32(bits + 1 if x > 0 else bits - 1)


def next_down(x: float, width: Width) -> float:
    """Return the largest value of the width below x.

    Args:
        x: A value of the width.
        width: The width.

    Returns:
        The next value down.
    """
    return -next_up(-x, width)


def _ceil_width(x: float, width: Width) -> float:
    """Return the smallest value of the width that is x or more."""
    if width == BINARY64:
        return x
    rounded = fround(x)
    return rounded if rounded >= x else next_up(rounded, width)


def same_float(a: float, b: float) -> bool:
    """Report whether two floats are one value.

    All NaNs are one value. The two zeros are two values.

    Args:
        a: A float.
        b: Another float.

    Returns:
        True when a and b are one value.
    """
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return a == b and math.copysign(1.0, a) == math.copysign(1.0, b)


def _exact_of(x: float) -> tuple[int, int]:
    """Return a finite float x exactly as numerator * 2^exponent.

    The numerator is odd. Zero has the numerator 0 and the exponent 0.
    """
    bits = bits_of(x)
    negative = bits >> 63 == 1
    field = (bits >> 52) & 0x7FF
    fraction = bits & ((1 << 52) - 1)
    numerator = fraction if field == 0 else fraction | (1 << 52)
    exponent = -1074 if field == 0 else field - 1075
    if numerator == 0:
        return 0, 0
    while numerator & 1 == 0:
        numerator >>= 1
        exponent += 1
    return (-numerator if negative else numerator), exponent


def float_key(x: float) -> Key:
    """Return the sort key of a float. The key of a simpler value is smaller.

    The keys order the floats from the simplest.

    - The integral values below 2^53 in magnitude come first. They sort by
      magnitude.
    - The other finite values follow. They sort by their number of
      fractional bits and then by their numerator.
    - The infinities follow them.
    - NaN comes last.

    Within a group, a positive value precedes the negative value of the
    same magnitude. 0.0 precedes -0.0.

    Args:
        x: The float.

    Returns:
        The key.
    """
    if math.isnan(x):
        return (_GROUP_NAN,)
    negative = 1 if math.copysign(1.0, x) < 0 else 0
    if math.isinf(x):
        return (_GROUP_INFINITE, negative)
    numerator, exponent = _exact_of(x)
    magnitude = abs(numerator)
    if exponent >= 0:
        whole = magnitude << exponent
        if abs(x) < INTEGRAL_LIMIT:
            return (_GROUP_INTEGRAL, whole, negative)
        return (_GROUP_FRACTION, 0, whole, negative)
    return (_GROUP_FRACTION, -exponent, magnitude, negative)


def _ceil_scaled(numerator: int, exponent: int) -> int:
    """Return the smallest integer at or above numerator * 2^exponent.

    The numerator is positive and odd. An odd numerator is not a multiple of
    2^-exponent when the exponent is negative, so the quotient rounds up.
    """
    if exponent >= 0:
        return numerator << exponent
    return (numerator >> -exponent) + 1


def _above(n: int, f: int, bound: tuple[int, int]) -> bool:
    """Report whether n * 2^-f is above the exact value of a finite bound."""
    numerator, exponent = bound
    shift = exponent + f
    if shift >= 0:
        return n > numerator << shift
    return n << -shift > numerator


def _simplest_integral(lo: float, hi: float, width: Width) -> float | None:
    """Return the simplest integral value of the width in [lo, hi], or None.

    The range is 0 < lo <= hi < infinity.
    """
    smallest = math.ceil(lo)
    if smallest < INTEGRAL_LIMIT:
        candidate = _ceil_width(float(smallest), width)
        if candidate <= hi and candidate < INTEGRAL_LIMIT:
            return candidate
    # Every value of either width at 2^53 or above is an integer. These
    # integers precede every fraction.
    if hi < INTEGRAL_LIMIT:
        return None
    candidate = _ceil_width(max(lo, float(INTEGRAL_LIMIT)), width)
    return candidate if candidate <= hi else None


def _simplest_fraction(lo: float, hi: float, width: Width) -> float | None:
    """Return the fraction of the width in [lo, hi] with the fewest fractional bits.

    Of those fractions, the function returns the one with the smallest
    numerator. The range is 0 < lo <= hi < infinity. A fraction n / 2^f in
    lowest terms has an odd n. At one f, the smallest odd n in range has the
    fewest significant bits. When n / 2^f is not a value of the width, no
    larger n at that f gives a value of the width.
    """
    low = _exact_of(lo)
    high = _exact_of(hi)
    for f in range(1, _MAX_FRACTION_BITS[width] + 1):
        n = _ceil_scaled(low[0], low[1] + f)
        if n % 2 == 0:
            n += 1
        # float(n) raises OverflowError for a numerator above the largest
        # float, so the loop checks the size of n first.
        if _above(n, f, high) or n.bit_length() > _SIGNIFICAND_BITS:
            continue
        candidate = math.ldexp(float(n), -f)
        if representable(candidate, width):
            return candidate
    return None


def _simplest_positive(lo: float, hi: float, width: Width) -> float | None:
    """Return the simplest value of the width in [lo, hi], or None.

    The range is 0 < lo <= hi. A range to infinity always contains an
    integer, so _simplest_fraction runs only for a finite range.
    """
    if lo == math.inf:
        return lo
    integral = _simplest_integral(lo, hi, width)
    return integral if integral is not None else _simplest_fraction(lo, hi, width)


def simplest_float(lo: float, hi: float, width: Width) -> float | None:
    """Return the value of the width in [lo, hi] with the smallest sort key.

    Args:
        lo: The lower bound. It can be an infinity.
        hi: The upper bound. It is at least lo.
        width: The width.

    Returns:
        The simplest value, or None when the range does not contain a value
        of the width.
    """
    if lo <= 0 <= hi:
        return 0.0
    if lo > 0:
        return _simplest_positive(lo, hi, width)
    mirrored = _simplest_positive(-hi, -lo, width)
    return None if mirrored is None else -mirrored
