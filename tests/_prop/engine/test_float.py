# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/float.py tests the values of a float choice.

It checks their bits, their neighbours and their sort keys.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.float import (
    INTEGRAL_LIMIT,
    NAN_BITS,
    Width,
    bits_of,
    float_key,
    from_bits,
    from_bits32,
    fround,
    next_down,
    next_up,
    representable,
    same_float,
    simplest_float,
)

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

#: The largest finite value of width 32, and the smallest positive one.
MAX_FLOAT32 = from_bits32(0x7F7FFFFF)
MIN_FLOAT32 = from_bits32(1)

INF = math.inf
NAN = math.nan

#: The smallest positive subnormal binary64.
MIN_VALUE = 5e-324


class TestNanBits:
    """NAN_BITS contains the bits of the canonical quiet NaN."""

    def test_contains_the_bits_of_the_quiet_nan(self, seat: Collector) -> None:
        """Every NaN in a choice has these bits."""
        check.equal(
            seat, NAN_BITS, 0x7FF8000000000000, "the bits are those of the quiet NaN"
        )


class TestIntegralLimit:
    """INTEGRAL_LIMIT is the end of the integral group of the sort key."""

    def test_contains_2_to_the_53(self, seat: Collector) -> None:
        """Integral floats below 2^53 sort first."""
        check.equal(seat, INTEGRAL_LIMIT, 2**53, "the limit is 2^53")


class TestBitsOf:
    """bits_of returns the binary64 bits of a float."""

    def test_returns_the_binary64_bits_of_a_float(self, seat: Collector) -> None:
        """1.0, -0.0 and NaN have the bits that IEEE 754 defines."""
        check.equal(
            seat,
            [bits_of(1.0), bits_of(-0.0), bits_of(NAN)],
            [0x3FF0000000000000, 1 << 63, NAN_BITS],
            "each float has its binary64 bits",
        )


class TestFromBits:
    """from_bits returns the float of binary64 bits."""

    def test_returns_the_float_of_binary64_bits(self, seat: Collector) -> None:
        """from_bits decodes the bits of 1.0 and of the smallest subnormal."""
        check.equal(
            seat,
            [from_bits(0x3FF0000000000000), from_bits(1)],
            [1.0, MIN_VALUE],
            "the bits decode to the floats",
        )


class TestFromBits32:
    """from_bits32 returns the float of binary32 bits."""

    def test_returns_the_float_of_binary32_bits(self, seat: Collector) -> None:
        """from_bits32 decodes 1.0 and the smallest and the largest binary32."""
        check.equal(
            seat,
            [from_bits32(0x3F800000), MIN_FLOAT32, MAX_FLOAT32],
            [1.0, 2.0**-149, (2 - 2**-23) * 2.0**127],
            "the bits decode to the floats",
        )


class TestFround:
    """fround rounds a float to binary32."""

    tests: ClassVar[list[tuple[str, float, float]]] = [
        ("returns a value of width 32 unchanged", 0.5, 0.5),
        ("rounds a value to the nearest binary32", 0.1, 0.10000000149011612),
        ("rounds a value past the largest binary32 to infinity", 1e300, INF),
        (
            "rounds a value below the lowest binary32 to negative infinity",
            -1e300,
            -INF,
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_nearest_binary32(
        self, seat: Collector, give: float, want: float
    ) -> None:
        """The result is the nearest binary32 value."""
        check.is_true(seat, same_float(fround(give), want), f"the value is {want}")


class TestRepresentable:
    """representable reports whether a float is a value of a width."""

    tests: ClassVar[list[tuple[str, float, Width, bool]]] = [
        ("returns true for any float of width 64", 0.1, 64, True),
        ("returns true for a value of width 32", 0.5, 32, True),
        ("returns false for a float that is not a value of width 32", 0.1, 32, False),
        ("returns true for nan at width 32", NAN, 32, True),
        ("returns true for infinity at width 32", INF, 32, True),
    ]

    @pytest.mark.parametrize(
        ("give", "width", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_verdict(
        self, seat: Collector, give: float, width: Width, want: bool
    ) -> None:
        """NaN and the infinities are values of both widths."""
        check.equal(seat, representable(give, width), want, f"the verdict is {want}")


class TestNextUp:
    """next_up returns the smallest value of a width above a float."""

    tests: ClassVar[list[tuple[str, float, Width, float]]] = [
        ("steps one unit up from 1 at width 32", 1.0, 32, 1 + 2**-23),
        ("steps from zero to the smallest subnormal at width 32", 0.0, 32, MIN_FLOAT32),
        (
            "steps from negative zero to the smallest subnormal at width 32",
            -0.0,
            32,
            MIN_FLOAT32,
        ),
        (
            "steps from the largest negative subnormal to negative zero at width 32",
            -MIN_FLOAT32,
            32,
            -0.0,
        ),
        (
            "steps from the largest finite value to infinity at width 32",
            MAX_FLOAT32,
            32,
            INF,
        ),
        (
            "steps from negative infinity to the lowest finite value at width 32",
            -INF,
            32,
            -MAX_FLOAT32,
        ),
        ("returns infinity for infinity", INF, 32, INF),
        ("returns nan for nan", NAN, 64, NAN),
        ("steps from zero to the smallest subnormal at width 64", 0.0, 64, MIN_VALUE),
        (
            "steps from negative zero to the smallest subnormal at width 64",
            -0.0,
            64,
            MIN_VALUE,
        ),
        ("steps one unit up from -1 at width 64", -1.0, 64, -1 + 2**-53),
        ("steps one unit up from 1 at width 64", 1.0, 64, 1 + 2**-52),
    ]

    @pytest.mark.parametrize(
        ("give", "width", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_next_value_up(
        self, seat: Collector, give: float, width: Width, want: float
    ) -> None:
        """The step is one value of the width."""
        got = next_up(give, width)
        check.is_true(seat, same_float(got, want), f"the next value is {want}")


class TestNextDown:
    """next_down returns the largest value of a width below a float."""

    tests: ClassVar[list[tuple[str, float, Width, float]]] = [
        (
            "steps from zero to the largest negative subnormal at width 32",
            0.0,
            32,
            -MIN_FLOAT32,
        ),
        ("steps one unit down from 1 at width 64", 1.0, 64, 1 - 2**-53),
    ]

    @pytest.mark.parametrize(
        ("give", "width", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_next_value_down(
        self, seat: Collector, give: float, width: Width, want: float
    ) -> None:
        """The step is one value of the width."""
        got = next_down(give, width)
        check.is_true(seat, same_float(got, want), f"the next value is {want}")


class TestSameFloat:
    """same_float reports whether two floats are one value."""

    tests: ClassVar[list[tuple[str, float, float, bool]]] = [
        ("returns false for the two zeros", 0.0, -0.0, False),
        ("returns true for two nans", NAN, -NAN, True),
        ("returns false for nan and zero", NAN, 0.0, False),
        ("returns false for zero and nan", 0.0, NAN, False),
        ("returns true for one value", 1.5, 1.5, True),
        ("returns false for two values", 1.5, 2.5, False),
    ]

    @pytest.mark.parametrize(
        ("a", "b", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_verdict(
        self, seat: Collector, a: float, b: float, want: bool
    ) -> None:
        """All NaNs are one value. The two zeros are two values."""
        check.equal(seat, same_float(a, b), want, f"the verdict is {want}")


class TestFloatKey:
    """float_key returns the sort key of a float."""

    def test_orders_the_groups_of_floats_from_integral_values_to_nan(
        self, seat: Collector
    ) -> None:
        """A sort by key puts the simplest values first."""
        ordered = [
            0.0,
            -0.0,
            1.0,
            -1.0,
            2.0,
            2.0**53,
            0.5,
            -0.5,
            1.5,
            0.25,
            INF,
            -INF,
            NAN,
        ]
        got = sorted(ordered, key=float_key)
        check.equal(
            seat,
            [bits_of(x) for x in got],
            [bits_of(x) for x in ordered],
            "the floats sort from the simplest",
        )

    tests: ClassVar[list[tuple[str, float, tuple[int, ...]]]] = [
        ("returns an integral key below 2^53", 2.0**52 + 1, (0, 2**52 + 1, 0)),
        (
            "returns a fraction key without fractional bits at 2^53",
            2.0**53,
            (1, 0, 2**53, 0),
        ),
        ("returns the fractional bits and the numerator of -0.5", -0.5, (1, 1, 1, 1)),
        (
            "returns the infinite group with the sign of negative infinity",
            -INF,
            (2, 1),
        ),
        ("returns the nan group alone for nan", NAN, (3,)),
        ("returns the integral key of zero", 0.0, (0, 0, 0)),
        ("returns the integral key of negative zero", -0.0, (0, 0, 1)),
        ("returns the key of a subnormal", MIN_VALUE, (1, 1074, 1, 0)),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_key(
        self, seat: Collector, give: float, want: tuple[int, ...]
    ) -> None:
        """The key starts with the group."""
        check.equal(seat, float_key(give), want, f"the key is {want}")


class TestSimplestFloat:
    """simplest_float returns the value of a range with the smallest sort key."""

    tests: ClassVar[list[tuple[str, float, float, Width, float | None]]] = [
        ("returns zero for a range around zero", -1.0, 1.0, 64, 0.0),
        ("returns the smallest integer for a range of integers", 2.5, 7.0, 64, 3.0),
        ("returns the fraction with the fewest bits", 0.6, 0.7, 64, 0.625),
        (
            "returns the lower bound when it is the simplest value of the range",
            2.5,
            2.75,
            64,
            2.5,
        ),
        ("returns a mirrored value for a negative range", -0.7, -0.6, 64, -0.625),
        (
            "returns the lower bound of a range of integers above 2^53",
            2.0**53 + 2,
            2.0**60,
            64,
            2.0**53 + 2,
        ),
        (
            "returns 2^53 for a range of width 32 whose first integer rounds up",
            2.0**53 - 2**28,
            2.0**60,
            32,
            2.0**53,
        ),
        (
            "returns the next value of width 32 above a lower bound of width 64",
            2.0**53 + 2**30 + 2,
            2.0**60,
            32,
            2.0**53 + 2**31,
        ),
        ("returns infinity for a range from infinity", INF, INF, 64, INF),
        ("returns 1 for a range from 0.3 to infinity", 0.3, INF, 64, 1.0),
        (
            "returns the subnormal of a range of the smallest subnormal",
            MIN_VALUE,
            MIN_VALUE,
            64,
            MIN_VALUE,
        ),
        (
            "returns none for a range without a value of width 32",
            2.0**30 + 0.25,
            2.0**30 + 0.75,
            32,
            None,
        ),
        (
            "returns none for a negative range without a value of width 32",
            -(2.0**30) - 0.75,
            -(2.0**30) - 0.25,
            32,
            None,
        ),
        (
            "returns none for a range of integers between two values of width 32",
            2.0**53 + 2**31 + 4,
            2.0**53 + 2**31 + 8,
            32,
            None,
        ),
    ]

    @pytest.mark.parametrize(
        ("lo", "hi", "width", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_returns_the_simplest_value(
        self, seat: Collector, lo: float, hi: float, width: Width, want: float | None
    ) -> None:
        """The simplest value has the smallest sort key."""
        got = simplest_float(lo, hi, width)
        if want is None:
            check.is_none(seat, got, "the range does not contain a value of the width")
            return
        check.is_true(
            seat, got is not None and same_float(got, want), f"the value is {want}"
        )
