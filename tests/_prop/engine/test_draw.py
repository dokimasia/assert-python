"""The spec of _prop/engine/draw.py tests what each draw consumes and returns.

The pinned draws are the draws of the reference implementation of the
definition.
"""

from __future__ import annotations

import math
from collections import Counter
from fractions import Fraction
from typing import ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.choice import (
    INT64_MAX,
    INT64_MIN,
    UINT64_MAX,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
)
from dokimi_assert._prop.engine.draw import (
    REUSE_ODDS,
    average_length,
    boolean,
    flag,
    flag_bounds,
    float_edges,
    float_value,
    integer,
    integer_edges,
    keep,
    sequence,
    weighted,
)
from dokimi_assert._prop.engine.float import bits_of, from_bits32, representable
from dokimi_assert._prop.engine.source import Source
from dokimi_assert.seat import Collector

#: The number of draws that a property check of a draw makes. With this many
#: draws, every branch of the draw runs.
DRAWS = 2000

#: The probability of one half.
HALF = Fraction(1, 2)

INF = math.inf


class TestReuseOdds:
    """REUSE_ODDS is the odds that a draw reuses an earlier value."""

    def test_contains_4(self, seat: Collector) -> None:
        """One reusable draw in four takes an earlier value."""
        check.equal(seat, REUSE_ODDS, 4, "the odds are 1 in 4")


class TestIntegerEdges:
    """integer_edges returns the edge values of integer bounds."""

    tests: ClassVar[list[tuple[str, int, int, list[int]]]] = [
        ("returns one neighbour of a target at the lower bound", 0, 10, [0, 10, 1]),
        (
            "returns both neighbours of a target between the bounds",
            -5,
            5,
            [0, -5, 5, 1, -1],
        ),
        ("returns each value once", 1, 2, [1, 2]),
        ("returns the one value of bounds of one value", 3, 3, [3]),
    ]

    @pytest.mark.parametrize(
        ("lo", "hi", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_edges(
        self, seat: Collector, lo: int, hi: int, want: list[int]
    ) -> None:
        """The edges are inside the bounds and appear once each."""
        check.equal(
            seat,
            integer_edges(IntegerBounds(lo, hi)),
            want,
            "the bounds have the edges",
        )


class TestInteger:
    """integer draws an integer inside its bounds."""

    def test_returns_the_value_of_equal_bounds_without_consuming_the_stream(
        self, seat: Collector
    ) -> None:
        """The draw does not consume the stream."""
        source, twin = Source(1), Source(1)
        got = [integer(source, IntegerBounds(7, 7)), source.next()]
        check.equal(seat, got, [7, twin.next()], "the stream continues where it was")

    def test_returns_a_value_inside_the_bounds_for_every_draw(
        self, seat: Collector
    ) -> None:
        """Every value is inside its bounds."""
        ranges = [
            (-100, 100),
            (0, 1),
            (5, 9),
            (-9, -5),
            (INT64_MIN, INT64_MAX),
            (0, UINT64_MAX),
        ]
        outside: list[int] = []
        for lo, hi in ranges:
            bounds = IntegerBounds(lo, hi)
            source = Source(lo & UINT64_MAX)
            drawn = [integer(source, bounds) for _ in range(DRAWS)]
            outside += [v for v in drawn if not bounds.admits(v)]
        check.is_empty(seat, outside, "every value is inside its bounds")

    def test_draws_an_edge_or_a_capped_offset_for_a_target_at_the_lower_bound(
        self, seat: Collector
    ) -> None:
        """The draws and the stream after them follow the rules for 50 seeds."""
        bounds = IntegerBounds(0, 1000)
        got: list[list[int]] = []
        want: list[list[int]] = []
        for seed in range(50):
            source = Source(seed)
            got.append([integer(source, bounds), source.next()])
            twin = Source(seed)
            if twin.coin(1, 8):
                edges = integer_edges(bounds)
                value = edges[twin.below(len(edges))]
            else:
                cap = [1 << 4, 1 << 8, 1 << 16, 1 << 64][twin.below(4)]
                value = twin.below(min(cap - 1, 1000) + 1)
            want.append([value, twin.next()])
        check.equal(seat, got, want, "the draws follow the rules for 50 seeds")

    def test_returns_the_pinned_draws_of_seed_42(self, seat: Collector) -> None:
        """Seed 42 gives ten pinned draws over -100 to 100."""
        source = Source(42)
        bounds = IntegerBounds(-100, 100)
        check.equal(
            seat,
            [integer(source, bounds) for _ in range(10)],
            [11, 24, 14, 62, -71, -5, 8, -21, -29, -69],
            "the ten draws are the pinned draws",
        )

    def test_returns_the_pinned_draws_of_seed_42_over_the_whole_signed_range(
        self, seat: Collector
    ) -> None:
        """Seed 42 gives ten pinned draws over the signed 64-bit range."""
        source = Source(42)
        bounds = IntegerBounds(INT64_MIN, INT64_MAX)
        check.equal(
            seat,
            [integer(source, bounds) for _ in range(10)],
            [
                11,
                49,
                14,
                31_993,
                -207,
                -49_792,
                -10,
                INT64_MIN,
                3_534_659_902_462_096_457,
                51_818,
            ],
            "the ten draws are the pinned draws",
        )

    def test_moves_down_from_a_target_at_the_upper_bound(self, seat: Collector) -> None:
        """Every value is at or below -1."""
        bounds = IntegerBounds(-1000, -1)
        source = Source(5)
        drawn = [integer(source, bounds) for _ in range(DRAWS)]
        check.is_true(
            seat, all(-1000 <= v <= -1 for v in drawn), "every value is in [-1000, -1]"
        )


class TestBoolean:
    """boolean draws 1 with a probability and 0 otherwise."""

    def test_returns_the_certain_outcome_of_a_probability_of_0_or_1(
        self, seat: Collector
    ) -> None:
        """The probabilities 0 and 1 give certain draws."""
        source = Source(2)
        got = [
            [boolean(source, Fraction(0)), boolean(source, Fraction(1))]
            for _ in range(100)
        ]
        check.equal(seat, got, [[0, 1]] * 100, "the draws are certain")

    def test_returns_1_exactly_when_the_coin_comes_up(self, seat: Collector) -> None:
        """Each draw tosses one coin."""
        source, twin = Source(3), Source(3)
        got = [boolean(source, Fraction(1, 3)) for _ in range(100)]
        want = [1 if twin.coin(1, 3) else 0 for _ in range(100)]
        check.equal(seat, got, want, "each draw tosses one coin")


class TestWeighted:
    """weighted draws an index with a probability proportional to its weight."""

    def test_returns_0_for_one_weight_without_consuming_the_stream(
        self, seat: Collector
    ) -> None:
        """The draw does not consume the stream."""
        source, twin = Source(4), Source(4)
        got = [weighted(source, [3]), source.next()]
        check.equal(seat, got, [0, twin.next()], "the stream continues where it was")

    def test_returns_the_first_index_whose_running_sum_of_weights_exceeds_the_draw(
        self, seat: Collector
    ) -> None:
        """Weights 1, 2 and 1 split below(4) into [0], [1, 2] and [3]."""
        source, twin = Source(6), Source(6)
        got = [weighted(source, [1, 2, 1]) for _ in range(DRAWS)]
        want = [[0, 1, 1, 2][twin.below(4)] for _ in range(DRAWS)]
        check.equal(seat, got, want, "the indices follow the running sums")


class TestKeep:
    """keep decides whether swarm keeps an action."""

    def test_tosses_one_coin_after_a_kept_action(self, seat: Collector) -> None:
        """Each decision tosses one coin of the probability."""
        source, twin = Source(8), Source(8)
        got = [keep(source, HALF, True, r) for r in (1, 3) for _ in range(50)]
        want = [boolean(twin, HALF) for _ in range(100)]
        check.equal(seat, got, want, "each decision tosses one coin")

    def test_keeps_the_last_action_without_a_draw_when_no_action_is_kept(
        self, seat: Collector
    ) -> None:
        """The draw does not consume the stream."""
        source, twin = Source(8), Source(8)
        got = [keep(source, HALF, False, 1), source.next()]
        check.equal(seat, got, [1, twin.next()], "the stream continues where it was")

    def test_tosses_a_coin_per_remaining_action_until_one_comes_up(
        self, seat: Collector
    ) -> None:
        """The decision is the first coin of the first round with a coin up."""
        got: list[list[int]] = []
        want: list[list[int]] = []
        for seed in range(100):
            source = Source(seed)
            got.append([keep(source, HALF, False, 3), source.next()])
            twin = Source(seed)
            coins = [boolean(twin, HALF) for _ in range(3)]
            while 1 not in coins:
                coins = [boolean(twin, HALF) for _ in range(3)]
            want.append([coins[0], twin.next()])
        check.equal(seat, got, want, "the decisions follow the rounds for 100 seeds")

    def test_keeps_each_nonempty_set_of_two_actions_about_a_third_of_the_time(
        self, seat: Collector
    ) -> None:
        """Each share is within 0.03 of a third."""
        source = Source(10)
        counts: Counter[tuple[int, int]] = Counter()
        for _ in range(DRAWS * 3):
            first = keep(source, HALF, False, 2)
            second = keep(source, HALF, first == 1, 1)
            counts[(first, second)] += 1
        shares = [counts[kept] / (DRAWS * 3) for kept in ((1, 0), (0, 1), (1, 1))]
        check.is_true(
            seat,
            all(abs(s - 1 / 3) <= 0.03 for s in shares),
            "each share is within 0.03 of a third",
        )


class TestAverageLength:
    """average_length returns the average length of a collection."""

    tests: ClassVar[list[tuple[str, int, int | None, int]]] = [
        ("returns 5 without a maximum", 0, None, 5),
        ("returns 5 for a maximum of 16", 0, 16, 5),
        ("returns 2 for a maximum of 3", 0, 3, 2),
        ("returns 1 for a maximum of 1", 0, 1, 1),
        ("returns 3 for sizes from 2 to 4", 2, 4, 3),
        ("returns 3 for sizes of 3 alone", 3, 3, 3),
        ("returns 20 for a minimum of 10 without a maximum", 10, None, 20),
    ]

    @pytest.mark.parametrize(
        ("min_size", "max_size", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_returns_the_average(
        self, seat: Collector, min_size: int, max_size: int | None, want: int
    ) -> None:
        """The extra is the smaller of half the room and max(minimum, 5)."""
        check.equal(
            seat, average_length(min_size, max_size), want, f"the average is {want}"
        )


class TestFlagBounds:
    """flag_bounds returns the bounds of the decision to continue a collection."""

    tests: ClassVar[list[tuple[str, int, int, int | None, tuple[int, int]]]] = [
        ("returns 1 to 1 below the minimum", 1, 2, 9, (1, 1)),
        ("returns 0 to 0 at the maximum", 9, 2, 9, (0, 0)),
        ("returns 0 to 1 without a maximum", 3, 0, None, (0, 1)),
        ("returns 0 to 1 between the sizes", 2, 2, 3, (0, 1)),
    ]

    @pytest.mark.parametrize(
        ("count", "min_size", "max_size", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_returns_the_bounds(
        self,
        seat: Collector,
        count: int,
        min_size: int,
        max_size: int | None,
        want: tuple[int, int],
    ) -> None:
        """A forced decision has bounds of one value."""
        bounds = flag_bounds(count, min_size, max_size)
        check.equal(seat, (bounds.lo, bounds.hi), want, f"the bounds are {want}")


class TestFlag:
    """flag decides whether a collection gets another element."""

    def test_continues_below_the_minimum_without_consuming_the_stream(
        self, seat: Collector
    ) -> None:
        """The decision to continue is forced."""
        source, twin = Source(5), Source(5)
        got = [flag(source, 1, 2, 9, 7), source.next()]
        check.equal(seat, got, [1, twin.next()], "the stream continues where it was")

    def test_stops_at_the_maximum_without_consuming_the_stream(
        self, seat: Collector
    ) -> None:
        """The decision to stop is forced."""
        source, twin = Source(5), Source(5)
        got = [flag(source, 9, 2, 9, 7), source.next()]
        check.equal(seat, got, [0, twin.next()], "the stream continues where it was")

    def test_continues_by_a_coin_of_the_extra_length_in_one_more(
        self, seat: Collector
    ) -> None:
        """The decision tosses a coin of 5 in 6."""
        source, twin = Source(5), Source(5)
        got = [flag(source, 3, 0, None, 5) for _ in range(100)]
        want = [1 if twin.coin(5, 6) else 0 for _ in range(100)]
        check.equal(seat, got, want, "each decision is the coin")


class TestSequence:
    """sequence draws a sequence inside its bounds."""

    def test_draws_as_a_list_of_integers_with_the_same_sizes_draws(
        self, seat: Collector
    ) -> None:
        """The sequence and the list are the same for 100 seeds."""
        bounds = SequenceBounds(256, 0, 16)
        element = IntegerBounds(0, 255)
        got = [sequence(Source(seed), bounds) for seed in range(100)]
        want: list[tuple[int, ...]] = []
        for seed in range(100):
            twin = Source(seed)
            elements: list[int] = []
            while flag(twin, len(elements), 0, 16, average_length(0, 16)) == 1:
                elements.append(integer(twin, element))
            want.append(tuple(elements))
        check.equal(
            seat, got, want, "the sequence and the list are the same for 100 seeds"
        )

    def test_returns_a_sequence_that_the_bounds_admit_for_every_draw(
        self, seat: Collector
    ) -> None:
        """The bounds admit every sequence."""
        bounds = SequenceBounds(3, 2, 6)
        source = Source(11)
        drawn = [sequence(source, bounds) for _ in range(DRAWS)]
        check.is_true(
            seat,
            all(bounds.admits(v) for v in drawn),
            "the bounds admit every sequence",
        )


class TestFloatEdges:
    """float_edges returns the edge values of float bounds."""

    def test_returns_six_edges_of_bounds_that_allow_nan(self, seat: Collector) -> None:
        """The target, the bounds, the neighbours of the target and NaN."""
        edges = float_edges(FloatBounds(-1.0, 1.0, True))
        want = [0.0, -1.0, 1.0, 5e-324, -5e-324, math.nan]
        check.equal(
            seat,
            [bits_of(e) for e in edges],
            [bits_of(w) for w in want],
            "the bounds have six edges",
        )

    def test_returns_each_edge_once(self, seat: Collector) -> None:
        """Bounds of one value have one edge."""
        check.equal(
            seat, float_edges(FloatBounds(2.0, 2.0)), [2.0], "the bounds have one edge"
        )


class TestFloatValue:
    """float_value draws a float inside its bounds."""

    tests: ClassVar[list[tuple[str, FloatBounds]]] = [
        ("returns values inside -1 to 1", FloatBounds(-1.0, 1.0)),
        ("returns values inside 0.5 to 0.75", FloatBounds(0.5, 0.75)),
        ("returns values of every float", FloatBounds(-INF, INF)),
        ("returns values from 1e300 to infinity", FloatBounds(1e300, INF)),
        ("returns infinity for bounds of infinity", FloatBounds(INF, INF)),
        ("returns negative infinity for its bounds", FloatBounds(-INF, -INF)),
        ("returns values of width 32", FloatBounds(-10.0, 10.0, False, 32)),
        ("returns values or nan of every float", FloatBounds(-INF, INF, True)),
        (
            "returns values or nan of every float of width 32",
            FloatBounds(-INF, INF, True, 32),
        ),
        (
            "returns subnormals of width 32",
            FloatBounds(from_bits32(1), from_bits32(2), False, 32),
        ),
    ]

    @pytest.mark.parametrize("bounds", [t[1] for t in tests], ids=[t[0] for t in tests])
    def test_returns_values_that_the_bounds_admit(
        self, seat: Collector, bounds: FloatBounds
    ) -> None:
        """Every value is inside the bounds."""
        source = Source(17)
        drawn = [float_value(source, bounds) for _ in range(DRAWS)]
        outside = [
            v
            for v in drawn
            if not bounds.admits(v) or not representable(v, bounds.width)
        ]
        check.is_empty(seat, outside, "every value is inside the bounds")

    def test_returns_nan_for_some_draws_of_bounds_that_allow_it(
        self, seat: Collector
    ) -> None:
        """The draws include a NaN."""
        source = Source(23)
        bounds = FloatBounds(-INF, INF, True)
        drawn = [float_value(source, bounds) for _ in range(DRAWS)]
        check.is_true(
            seat, any(math.isnan(v) for v in drawn), "the draws include a NaN"
        )

    def test_does_not_return_nan_for_bounds_that_refuse_it(
        self, seat: Collector
    ) -> None:
        """The draws do not include a NaN."""
        source = Source(23)
        bounds = FloatBounds(-INF, INF)
        drawn = [float_value(source, bounds) for _ in range(DRAWS)]
        check.is_false(
            seat, any(math.isnan(v) for v in drawn), "the draws do not include a NaN"
        )
