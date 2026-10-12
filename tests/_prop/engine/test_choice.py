"""The spec of _prop/engine/choice.py tests the bounds, targets and keys of choices."""

from __future__ import annotations

import math
from typing import Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.choice import (
    INT64_MAX,
    INT64_MIN,
    UINT64_MAX,
    Choice,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
    choice_of,
    same_choice,
)
from dokimi_assert._prop.engine.float import (
    NAN_BITS,
    Width,
    bits_of,
    from_bits32,
    same_float,
)
from dokimi_assert.seat import Collector
from helpers import refusal

#: The smallest positive value of width 32.
TINY32 = from_bits32(1)

INF = math.inf

#: The integer bounds of the rank cases.
RANKED = [(-5, 10), (-10, 5), (3, 9), (-9, -3), (-4, 4), (7, 7), (-1, 0)]


def by_key(bounds: IntegerBounds, lo: int, hi: int) -> list[int]:
    """Return the integers from lo to hi, sorted by the keys of bounds."""
    return sorted(range(lo, hi + 1), key=bounds.key)


class TestInt64Min:
    """INT64_MIN is the smallest signed 64-bit integer."""

    def test_contains_minus_2_to_the_63(self, seat: Collector) -> None:
        """The signed range starts at -2^63."""
        check.equal(seat, INT64_MIN, -(2**63), "the bound is -2^63")


class TestInt64Max:
    """INT64_MAX is the largest signed 64-bit integer."""

    def test_contains_2_to_the_63_less_1(self, seat: Collector) -> None:
        """The signed range ends at 2^63 - 1."""
        check.equal(seat, INT64_MAX, 2**63 - 1, "the bound is 2^63 - 1")


class TestUint64Max:
    """UINT64_MAX is the largest unsigned 64-bit integer."""

    def test_contains_2_to_the_64_less_1(self, seat: Collector) -> None:
        """The unsigned range ends at 2^64 - 1."""
        check.equal(seat, UINT64_MAX, 2**64 - 1, "the bound is 2^64 - 1")


class TestChoice:
    """Choice is one recorded decision."""

    def test_keeps_its_kind_and_its_value(self, seat: Collector) -> None:
        """A choice is a kind and a value."""
        choice = Choice("sequence", (1, 2))
        check.equal(
            seat,
            (choice.kind, choice.value),
            ("sequence", (1, 2)),
            "the choice keeps its kind and its value",
        )


class TestChoiceOf:
    """choice_of returns the choice of the kind of some bounds."""

    def test_returns_the_choice_of_the_kind_of_the_bounds(
        self, seat: Collector
    ) -> None:
        """Sequence bounds make a sequence choice."""
        choice = choice_of(SequenceBounds(4), (1, 2))
        check.equal(
            seat,
            (choice.kind, choice.value),
            ("sequence", (1, 2)),
            "the choice is a sequence",
        )


class TestIntegerBounds:
    """IntegerBounds describes the bounds of an integer choice."""

    tests: ClassVar[list[tuple[str, int, int, int]]] = [
        ("targets zero for bounds around zero", -5, 5, 0),
        ("targets zero for bounds from zero", 0, 9, 0),
        ("targets the lower bound for positive bounds", 3, 9, 3),
        ("targets the upper bound for negative bounds", -9, -3, -3),
        ("targets the one value of bounds of one value", 7, 7, 7),
    ]

    @pytest.mark.parametrize(
        ("lo", "hi", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_targets_the_value_closest_to_zero(
        self, seat: Collector, lo: int, hi: int, want: int
    ) -> None:
        """The target is the simplest value."""
        check.equal(seat, IntegerBounds(lo, hi).target, want, f"the target is {want}")

    def test_accepts_the_whole_signed_and_the_whole_unsigned_64_bit_range(
        self, seat: Collector
    ) -> None:
        """The id has both bounds."""
        check.equal(
            seat,
            [IntegerBounds(INT64_MIN, INT64_MAX).id, IntegerBounds(0, UINT64_MAX).id],
            [f"integer {INT64_MIN} {INT64_MAX}", f"integer 0 {UINT64_MAX}"],
            "both ranges have their ids",
        )

    def test_equals_bounds_of_the_same_range(self, seat: Collector) -> None:
        """Equal bounds have the same hash."""
        check.equal(
            seat, IntegerBounds(1, 3), IntegerBounds(1, 3), "the bounds are equal"
        )
        check.equal(
            seat,
            hash(IntegerBounds(1, 3)),
            hash(IntegerBounds(1, 3)),
            "the hashes are equal",
        )
        check.not_equal(
            seat,
            IntegerBounds(1, 3),
            IntegerBounds(1, 4),
            "bounds of two ranges differ",
        )
        check.not_equal(
            seat, IntegerBounds(0, 1), SequenceBounds(2), "bounds of two kinds differ"
        )

    refusals: ClassVar[list[tuple[str, int, int, str]]] = [
        (
            "raises value error for empty bounds",
            5,
            4,
            "prop: integer bounds [5, 4] are empty",
        ),
        (
            "raises value error for bounds that span both ranges",
            -1,
            UINT64_MAX,
            f"prop: integer bounds [-1, {UINT64_MAX}] are inside neither the signed "
            "nor the unsigned 64-bit range",
        ),
        (
            "raises value error for bounds below the signed range",
            INT64_MIN - 1,
            0,
            f"prop: integer bounds [{INT64_MIN - 1}, 0] are inside neither the "
            "signed nor the unsigned 64-bit range",
        ),
    ]

    @pytest.mark.parametrize(
        ("lo", "hi", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_value_error_for_bounds_that_it_refuses(
        self, seat: Collector, lo: int, hi: int, want: str
    ) -> None:
        """The error has the bounds."""
        check.equal(
            seat,
            refusal(seat, lambda: IntegerBounds(lo, hi)),
            want,
            "the error has the reason",
        )


class TestIntegerBoundsKey:
    """IntegerBounds.key returns the sort key of an integer."""

    def test_orders_values_by_their_distance_to_the_target_above_first(
        self, seat: Collector
    ) -> None:
        """One above the target comes before one below."""
        bounds = IntegerBounds(-2, 2)
        check.equal(
            seat,
            by_key(bounds, -2, 2),
            [0, 1, -1, 2, -2],
            "the values sort by their distance to the target",
        )


class TestIntegerBoundsRank:
    """IntegerBounds.rank returns the position of a value in the key order."""

    def test_numbers_the_values_in_key_order(self, seat: Collector) -> None:
        """The ranks of the sorted values count from 0."""
        got = [
            [
                IntegerBounds(lo, hi).rank(v)
                for v in by_key(IntegerBounds(lo, hi), lo, hi)
            ]
            for lo, hi in RANKED
        ]
        want = [list(range(hi - lo + 1)) for lo, hi in RANKED]
        check.equal(seat, got, want, "the ranks of the sorted values count from 0")

    def test_returns_the_last_rank_for_the_largest_unsigned_value(
        self, seat: Collector
    ) -> None:
        """The order has 2^64 positions."""
        rank = IntegerBounds(0, UINT64_MAX).rank(UINT64_MAX)
        check.equal(seat, rank, UINT64_MAX, "the largest value has the last rank")


class TestIntegerBoundsAtRank:
    """IntegerBounds.at_rank returns the value at a position of the key order."""

    def test_returns_the_values_in_key_order(self, seat: Collector) -> None:
        """at_rank inverts rank."""
        got = [
            [IntegerBounds(lo, hi).at_rank(r) for r in range(hi - lo + 1)]
            for lo, hi in RANKED
        ]
        want = [by_key(IntegerBounds(lo, hi), lo, hi) for lo, hi in RANKED]
        check.equal(seat, got, want, "the values at the ranks are the sorted values")

    def test_continues_on_the_longer_side_past_the_end_of_the_shorter_one(
        self, seat: Collector
    ) -> None:
        """3, 4 and 5 follow -2."""
        bounds = IntegerBounds(-2, 9)
        check.equal(
            seat,
            [bounds.at_rank(r) for r in (4, 5, 6, 7)],
            [-2, 3, 4, 5],
            "3, 4 and 5 follow -2",
        )

    def test_continues_below_the_target_past_a_shorter_side_above(
        self, seat: Collector
    ) -> None:
        """-3, -4 and -5 follow -2."""
        bounds = IntegerBounds(-9, 2)
        check.equal(
            seat,
            [bounds.at_rank(r) for r in (4, 5, 6, 7)],
            [-2, -3, -4, -5],
            "-3, -4 and -5 follow -2",
        )

    def test_returns_the_largest_unsigned_value_at_the_last_rank(
        self, seat: Collector
    ) -> None:
        """The last position has the largest value."""
        value = IntegerBounds(0, UINT64_MAX).at_rank(UINT64_MAX)
        check.equal(seat, value, UINT64_MAX, "the last rank has the largest value")


class TestIntegerBoundsAdmits:
    """IntegerBounds.admits reports whether a value is an integer inside the bounds."""

    tests: ClassVar[list[tuple[str, object, bool]]] = [
        ("returns true for an integer inside the bounds", 4, True),
        ("returns false for an integer above the bounds", 10, False),
        ("returns false for a float", 4.0, False),
        ("returns false for a bool", True, False),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_verdict(
        self, seat: Collector, give: object, want: bool
    ) -> None:
        """A bool is not an integer."""
        check.equal(
            seat, IntegerBounds(1, 9).admits(give), want, f"the verdict is {want}"
        )


class TestIntegerBoundsCoerce:
    """IntegerBounds.coerce fits a recorded value to the bounds."""

    def test_returns_a_recorded_integer_inside_the_bounds(
        self, seat: Collector
    ) -> None:
        """The recorded value fits."""
        value = IntegerBounds(0, 9).coerce(Choice("integer", 4))
        check.equal(seat, value, 4, "the value is the recorded value")

    tests: ClassVar[list[tuple[str, Choice]]] = [
        ("returns the target for an integer outside the bounds", Choice("integer", 10)),
        ("returns the target for a float", Choice("float", 4.0)),
        ("returns the target for a sequence", Choice("sequence", (4,))),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in tests], ids=[t[0] for t in tests])
    def test_returns_the_target_for_a_value_that_does_not_fit(
        self, seat: Collector, give: Choice
    ) -> None:
        """A value of another kind or outside the bounds becomes the target."""
        check.equal(
            seat, IntegerBounds(3, 9).coerce(give), 3, "the value is the target"
        )


class TestFloatBounds:
    """FloatBounds describes the bounds of a float choice."""

    tests: ClassVar[list[tuple[str, float, float, Width, float]]] = [
        ("targets zero inside -1 to 1", -1.0, 1.0, 64, 0.0),
        ("targets the simplest integer inside 2.5 to 7", 2.5, 7.0, 64, 3.0),
        (
            "targets the simplest negative integer inside -7 to -2.5",
            -7.0,
            -2.5,
            64,
            -3.0,
        ),
        (
            "targets the fraction with the fewest bits inside 0.1 to 0.9",
            0.1,
            0.9,
            64,
            0.5,
        ),
        (
            "targets the fraction with the fewest bits inside 0.6 to 0.7",
            0.6,
            0.7,
            64,
            0.625,
        ),
        (
            "targets the fraction with the fewest bits of width 32",
            0.5625,
            0.6875,
            32,
            0.625,
        ),
        (
            "targets the lower bound of integers above 2^53",
            2.0**53 + 2,
            2.0**60,
            64,
            2.0**53 + 2,
        ),
        ("targets the lower bound of a range to infinity", 1e300, INF, 64, 1e300),
        ("targets infinity for bounds of infinity alone", INF, INF, 64, INF),
        ("targets negative infinity for bounds of it alone", -INF, -INF, 64, -INF),
        (
            "targets the smallest positive value of width 32 for bounds of it alone",
            TINY32,
            TINY32,
            32,
            TINY32,
        ),
    ]

    @pytest.mark.parametrize(
        ("lo", "hi", "width", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_targets_the_simplest_value(
        self, seat: Collector, lo: float, hi: float, width: Width, want: float
    ) -> None:
        """The target has the smallest sort key."""
        target = FloatBounds(lo, hi, False, width).target
        check.is_true(seat, same_float(target, want), f"the target is {want}")

    def test_has_its_bounds_in_its_id(self, seat: Collector) -> None:
        """The id has the range, the NaN rule and the width."""
        check.equal(
            seat,
            FloatBounds(-1.0, 1.0, True, 32).id,
            "float -1.0 1.0 True 32",
            "the id has the bounds",
        )

    def test_equals_bounds_of_the_same_range_nan_and_width(
        self, seat: Collector
    ) -> None:
        """Equal bounds have the same hash."""
        a, b = FloatBounds(0.0, 1.0, True, 32), FloatBounds(0.0, 1.0, True, 32)
        check.equal(seat, a, b, "the bounds are equal")
        check.equal(seat, hash(a), hash(b), "the hashes are equal")
        check.not_equal(
            seat,
            a,
            FloatBounds(0.0, 1.0, False, 32),
            "bounds of two NaN rules differ",
        )
        check.not_equal(seat, a, IntegerBounds(0, 1), "bounds of two kinds differ")

    refusals: ClassVar[list[tuple[str, float, float, Any, str]]] = [
        (
            "raises value error for a width of 16",
            0.0,
            1.0,
            16,
            "prop: float width 16 is neither 32 nor 64",
        ),
        (
            "raises value error for a nan bound",
            math.nan,
            1.0,
            64,
            "prop: float bounds [nan, 1.0] are empty",
        ),
        (
            "raises value error for a lower bound above the upper",
            1.0,
            0.0,
            64,
            "prop: float bounds [1.0, 0.0] are empty",
        ),
        (
            "raises value error for a bound that is not a value of the width",
            0.1,
            1.0,
            32,
            "prop: float bound 0.1 is not a value of width 32",
        ),
    ]

    @pytest.mark.parametrize(
        ("lo", "hi", "width", "want"),
        [t[1:] for t in refusals],
        ids=[t[0] for t in refusals],
    )
    def test_raises_value_error_for_bounds_that_it_refuses(
        self, seat: Collector, lo: float, hi: float, width: Any, want: str
    ) -> None:
        """The error has the bounds."""
        got = refusal(seat, lambda: FloatBounds(lo, hi, False, width))
        check.equal(seat, got, want, "the error has the reason")


class TestFloatBoundsKey:
    """FloatBounds.key returns the sort key of a float."""

    def test_orders_the_keys_of_floats_from_integral_values_to_nan(
        self, seat: Collector
    ) -> None:
        """The order is the order of float_key."""
        bounds = FloatBounds(-INF, INF, True)
        ordered = [0.0, -0.0, 1.0, -1.0, 2.0, 2.0**53, 0.5, -0.5, 1.5, 0.25]
        ordered += [INF, -INF, math.nan]
        got = sorted(reversed(ordered), key=bounds.key)
        check.equal(
            seat,
            [bits_of(x) for x in got],
            [bits_of(x) for x in ordered],
            "the floats sort in the order of float_key",
        )


class TestFloatBoundsAdmits:
    """FloatBounds.admits reports whether a value is a float of the bounds."""

    tests: ClassVar[list[tuple[str, object, bool]]] = [
        ("returns true for a float inside the bounds", 1.5, True),
        ("returns false for a float outside the bounds", 3.0, False),
        ("returns false for a float that is not a value of the width", 1.1, False),
        ("returns false for nan that the bounds refuse", math.nan, False),
        ("returns false for an int", 1, False),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_verdict(
        self, seat: Collector, give: object, want: bool
    ) -> None:
        """A value of the bounds is a float of the width inside them."""
        bounds = FloatBounds(1.0, 2.0, False, 32)
        check.equal(seat, bounds.admits(give), want, f"the verdict is {want}")

    def test_returns_true_for_nan_where_the_bounds_allow_it(
        self, seat: Collector
    ) -> None:
        """NaN is a value."""
        check.is_true(
            seat,
            FloatBounds(0.0, 1.0, True).admits(math.nan),
            "NaN is a value of the bounds",
        )


class TestFloatBoundsCoerce:
    """FloatBounds.coerce fits a recorded value to the bounds."""

    def test_returns_a_recorded_float_inside_the_bounds_with_its_sign(
        self, seat: Collector
    ) -> None:
        """The value -0.0 keeps its sign."""
        value = FloatBounds(-1.0, 1.0).coerce(Choice("float", -0.0))
        check.equal(
            seat, bits_of(value), bits_of(-0.0), "the value has the bits of -0.0"
        )

    def test_returns_the_canonical_nan_for_a_recorded_nan_with_a_payload(
        self, seat: Collector
    ) -> None:
        """The value does not keep the payload."""
        value = FloatBounds(0.0, 1.0, True).coerce(Choice("float", -math.nan))
        check.equal(
            seat,
            bits_of(value),
            NAN_BITS,
            "the value has the bits of the canonical NaN",
        )

    tests: ClassVar[list[tuple[str, Choice]]] = [
        ("returns the target for a float outside the bounds", Choice("float", 3.0)),
        (
            "returns the target for nan that the bounds refuse",
            Choice("float", math.nan),
        ),
        (
            "returns the target for a float that is not a value of the width",
            Choice("float", 1.1),
        ),
        ("returns the target for an integer", Choice("integer", 1)),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in tests], ids=[t[0] for t in tests])
    def test_returns_the_target_for_a_value_that_does_not_fit(
        self, seat: Collector, give: Choice
    ) -> None:
        """A value of another kind or outside the bounds becomes the target."""
        check.equal(
            seat,
            FloatBounds(1.0, 2.0, False, 32).coerce(give),
            1.0,
            "the value is the target",
        )


class TestSequenceBounds:
    """SequenceBounds describes the bounds of a sequence choice."""

    def test_targets_min_size_zeros(self, seat: Collector) -> None:
        """A minimum of three has a target of three zeros."""
        check.equal(
            seat,
            SequenceBounds(256, 3, 8).target,
            (0, 0, 0),
            "the target is three zeros",
        )

    def test_has_its_bounds_in_its_id(self, seat: Collector) -> None:
        """The id has the elements and the sizes."""
        check.equal(
            seat,
            SequenceBounds(256, 1).id,
            "sequence 256 1 None",
            "the id has the bounds",
        )

    def test_equals_bounds_of_the_same_elements_and_sizes(
        self, seat: Collector
    ) -> None:
        """Equal bounds have the same hash."""
        check.equal(
            seat,
            SequenceBounds(4, 1, 2),
            SequenceBounds(4, 1, 2),
            "the bounds are equal",
        )
        check.equal(
            seat,
            hash(SequenceBounds(4, 1, 2)),
            hash(SequenceBounds(4, 1, 2)),
            "the hashes are equal",
        )
        check.not_equal(
            seat,
            SequenceBounds(4, 1, 2),
            SequenceBounds(4, 1),
            "bounds of two sizes differ",
        )
        check.not_equal(
            seat, SequenceBounds(2), IntegerBounds(0, 1), "bounds of two kinds differ"
        )

    refusals: ClassVar[list[tuple[str, int, int, int | None, str]]] = [
        (
            "raises value error for a k of 0",
            0,
            0,
            None,
            "prop: a sequence with k = 0 cannot have an element",
        ),
        (
            "raises value error for a negative minimum",
            2,
            -1,
            None,
            "prop: sequence sizes [-1, None] are empty",
        ),
        (
            "raises value error for a maximum below the minimum",
            2,
            3,
            2,
            "prop: sequence sizes [3, 2] are empty",
        ),
    ]

    @pytest.mark.parametrize(
        ("k", "min_size", "max_size", "want"),
        [t[1:] for t in refusals],
        ids=[t[0] for t in refusals],
    )
    def test_raises_value_error_for_bounds_that_it_refuses(
        self,
        seat: Collector,
        k: int,
        min_size: int,
        max_size: int | None,
        want: str,
    ) -> None:
        """The error has the bounds."""
        got = refusal(seat, lambda: SequenceBounds(k, min_size, max_size))
        check.equal(seat, got, want, "the error has the reason")


class TestSequenceBoundsKey:
    """SequenceBounds.key returns the sort key of a sequence."""

    def test_orders_sequences_by_length_before_their_elements(
        self, seat: Collector
    ) -> None:
        """A shorter sequence is simpler."""
        bounds = SequenceBounds(4)
        got = sorted([(1, 0), (0, 0), (1,), (0, 1)], key=bounds.key)
        check.equal(
            seat,
            got,
            [(1,), (0, 0), (0, 1), (1, 0)],
            "the sequences sort by length before their elements",
        )


class TestSequenceBoundsAdmits:
    """SequenceBounds.admits reports whether a value is a sequence of the bounds."""

    tests: ClassVar[list[tuple[str, object, bool]]] = [
        ("returns true for a sequence of the sizes", (2,), True),
        ("returns false for a sequence below the minimum", (), False),
        ("returns false for a sequence above the maximum", (0, 0, 0), False),
        ("returns false for an element of k", (3,), False),
        ("returns false for an element that is not an int", (1.5,), False),
        ("returns false for a bool element", (True,), False),
        ("returns false for a value that is not a tuple", 1, False),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_verdict(
        self, seat: Collector, give: object, want: bool
    ) -> None:
        """A sequence of the bounds has their sizes and elements below k."""
        check.equal(
            seat, SequenceBounds(3, 1, 2).admits(give), want, f"the verdict is {want}"
        )

    def test_returns_true_for_a_long_sequence_without_a_maximum(
        self, seat: Collector
    ) -> None:
        """Without a maximum, the length is unbounded."""
        check.is_true(
            seat, SequenceBounds(3).admits((2,) * 100), "the bounds admit 100 elements"
        )


class TestSequenceBoundsCoerce:
    """SequenceBounds.coerce fits a recorded sequence to the bounds."""

    tests: ClassVar[list[tuple[str, tuple[int, ...], tuple[int, ...]]]] = [
        ("cuts a recorded sequence to the maximum", (1, 2, 3, 4, 5), (1, 2, 3, 4)),
        ("extends a recorded sequence with zeros to the minimum", (7,), (7, 0)),
        ("replaces each element outside the range with 0", (11, -1, 3), (0, 0, 3)),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_fits_the_recorded_sequence(
        self, seat: Collector, give: tuple[int, ...], want: tuple[int, ...]
    ) -> None:
        """The fitted sequence has the sizes and the elements of the bounds."""
        got = SequenceBounds(10, 2, 4).coerce(Choice("sequence", give))
        check.equal(seat, got, want, "the sequence fits the bounds")

    def test_keeps_every_element_without_a_maximum(self, seat: Collector) -> None:
        """The method does not cut the sequence."""
        got = SequenceBounds(10).coerce(Choice("sequence", (1, 2, 3, 4, 5)))
        check.equal(seat, got, (1, 2, 3, 4, 5), "the sequence keeps every element")

    def test_returns_the_target_for_another_kind(self, seat: Collector) -> None:
        """An integer is not a sequence."""
        got = SequenceBounds(10, 1).coerce(Choice("integer", 5))
        check.equal(seat, got, (0,), "the value is the target")


class TestSameChoice:
    """same_choice reports whether two choices are one choice."""

    tests: ClassVar[list[tuple[str, Choice, Choice, bool]]] = [
        (
            "returns true for two nan floats",
            Choice("float", math.nan),
            Choice("float", -math.nan),
            True,
        ),
        (
            "returns false for the two zeros",
            Choice("float", 0.0),
            Choice("float", -0.0),
            False,
        ),
        (
            "returns true for two equal sequences",
            Choice("sequence", (1, 2)),
            Choice("sequence", (1, 2)),
            True,
        ),
        (
            "returns false for sequences of two lengths",
            Choice("sequence", (1,)),
            Choice("sequence", (1, 2)),
            False,
        ),
        (
            "returns false for sequences with another element",
            Choice("sequence", (1, 3)),
            Choice("sequence", (1, 2)),
            False,
        ),
        (
            "returns true for two equal integers",
            Choice("integer", 5),
            Choice("integer", 5),
            True,
        ),
        (
            "returns false for two kinds",
            Choice("integer", 1),
            Choice("float", 1.0),
            False,
        ),
    ]

    @pytest.mark.parametrize(
        ("a", "b", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_verdict(
        self, seat: Collector, a: Choice, b: Choice, want: bool
    ) -> None:
        """Floats compare by their bits."""
        check.equal(seat, same_choice(a, b), want, f"the verdict is {want}")
