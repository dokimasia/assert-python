# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/collection.py tests the decoding of a collection.

The raises assertion does not catch Rejected, because Rejected derives from
BaseException. The spec takes it with pytest.raises.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.case import (
    Case,
    Generating,
    Rejected,
    Replaying,
    Span,
)
from dokimi_assert._prop.engine.choice import IntegerBounds
from dokimi_assert._prop.engine.collection import (
    ELEMENT,
    ENTRY,
    Sizes,
    collect,
    more,
)
from dokimi_assert._prop.engine.edge import Edge
from dokimi_assert._prop.engine.source import Source
from helpers import integers, refusal

if TYPE_CHECKING:
    from collections.abc import Callable

    from dokimi_assert.seat import Collector

#: The number of discards in a row that stop a collection in the definition.
DISCARD_LIMIT = 10

#: The bounds of each element that the cases decode.
DIGIT = IntegerBounds(0, 9)


def replay(*values: int) -> Case:
    """Return a case that replays integer values."""
    return Case(Replaying(integers(*values)))


def digits(
    c: Case, sizes: Sizes, unique: bool, stop: Callable[[], bool] | None = None
) -> list[int]:
    """Collect digits. Each digit is unique by its value when unique is set."""

    def decode() -> tuple[int, str | None]:
        value = c.integer(DIGIT)
        return value, str(value) if unique else None

    return collect(c, sizes, ELEMENT, decode, stop)


def test_exports_the_labels_of_an_element_and_an_entry(seat: Collector) -> None:
    """The constants are the span labels of an element and of an entry of a dict."""
    check.equal(
        seat, [ELEMENT, ENTRY], ["element", "entry"], "the labels are element and entry"
    )


class TestSizes:
    """Sizes has the bounds of the length of a collection."""

    tests: ClassVar[list[tuple[str, int, int | None, str]]] = [
        (
            "raises value error for a negative minimum",
            -1,
            None,
            "prop: sizes [-1, None] are empty",
        ),
        (
            "raises value error for a maximum below the minimum",
            3,
            2,
            "prop: sizes [3, 2] are empty",
        ),
    ]

    @pytest.mark.parametrize(
        ("min_size", "max_size", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_raises_value_error_for_sizes_without_a_length(
        self, seat: Collector, min_size: int, max_size: int | None, want: str
    ) -> None:
        """The error has the sizes."""
        got = refusal(seat, lambda: Sizes(min_size, max_size))
        check.equal(seat, got, want, "the error has the sizes")


class TestSizesAverage:
    """Sizes.average is the average length of a collection in the random phase."""

    def test_returns_the_average_length_of_the_sizes(self, seat: Collector) -> None:
        """The sizes are open, at most one element, and at least ten elements."""
        check.equal(
            seat,
            [Sizes().average, Sizes(0, 1).average, Sizes(10).average],
            [5, 1, 20],
            "the averages are 5, 1 and 20",
        )


class TestMore:
    """more decides whether a collection grows."""

    def test_forces_the_flag_below_the_minimum_and_at_the_maximum(
        self, seat: Collector
    ) -> None:
        """The replayed values do not fit the forced bounds."""
        c = replay(0, 0, 1)
        sizes = Sizes(1, 2)
        decided = [more(c, count, sizes) for count in range(3)]
        check.equal(
            seat,
            [
                decided,
                [request.bounds for request in c.requests],
                [request.edge for request in c.requests],
            ],
            [
                [True, False, False],
                [IntegerBounds(1, 1), IntegerBounds(0, 1), IntegerBounds(0, 0)],
                [1, 0, 0],
            ],
            "the bounds force the flags",
        )

    def test_stops_a_stopped_collection_as_one_at_its_maximum(
        self, seat: Collector
    ) -> None:
        """A replayed 1 does not fit the bounds."""
        c = replay(1)
        check.equal(
            seat,
            [more(c, 3, Sizes(), True), c.requests[0].bounds],
            [False, IntegerBounds(0, 0)],
            "the bounds force a stop",
        )

    def test_continues_by_a_coin_of_the_given_average(self, seat: Collector) -> None:
        """The average is 30, and the minimum is 0."""
        c = Case(Generating(Source(12)))
        twin = Source(12)
        got = [more(c, count, Sizes(0, 100), False, 30) for count in range(50)]
        check.equal(
            seat,
            got,
            [twin.coin(30, 31) for _ in got],
            "each flag is a coin of 30 in 31",
        )

    def test_gives_the_first_flag_the_edge_1(self, seat: Collector) -> None:
        """The edge phase gives a collection one element."""
        c = Case(Edge("min"))
        check.equal(
            seat,
            [more(c, 0, Sizes()), more(c, 1, Sizes())],
            [True, False],
            "the collection gets one element",
        )


class TestCollect:
    """collect decodes the elements of a collection one at a time."""

    def test_opens_the_span_of_each_element_at_its_flag(self, seat: Collector) -> None:
        """Each span has a flag and an element."""
        c = replay(1, 7, 1, 3, 0)
        check.equal(
            seat,
            [digits(c, Sizes(), False), c.spans],
            [
                [7, 3],
                [Span(ELEMENT, 0, 2, 0, None), Span(ELEMENT, 2, 4, 0, None)],
            ],
            "each span starts at its flag",
        )

    def test_keeps_duplicates_without_a_key(self, seat: Collector) -> None:
        """The case decodes two fours."""
        got = digits(replay(1, 4, 1, 4, 0), Sizes(), False)
        check.equal(seat, got, [4, 4], "the collection keeps both fours")

    def test_discards_an_element_whose_key_repeats(self, seat: Collector) -> None:
        """The case decodes two fours and a five."""
        got = digits(replay(1, 4, 1, 4, 1, 5, 0), Sizes(), True)
        check.equal(seat, got, [4, 5], "the second four is discarded")

    def test_continues_after_one_discard_fewer_than_the_limit(
        self, seat: Collector
    ) -> None:
        """The case has nine discards in a row."""
        values = [1, 4, *[1, 4] * (DISCARD_LIMIT - 1), 1, 5, 0]
        got = digits(replay(*values), Sizes(), True)
        check.equal(seat, got, [4, 5], "the collection continues after nine discards")

    def test_stops_at_the_limit_of_discards_without_another_flag(
        self, seat: Collector
    ) -> None:
        """The flag after the tenth discard is not decided."""
        c = replay(1, 4, *[1, 4] * DISCARD_LIMIT, 1, 5, 0)
        check.equal(
            seat,
            [digits(c, Sizes(), True), len(c.choices)],
            [[4], 2 + 2 * DISCARD_LIMIT],
            "the collection stops after ten discards",
        )

    def test_restarts_the_count_of_discards_after_a_new_element(
        self, seat: Collector
    ) -> None:
        """The case has nine discards, a five and one discard."""
        values = [1, 4, *[1, 4] * (DISCARD_LIMIT - 1), 1, 5, 1, 5, 1, 6, 0]
        got = digits(replay(*values), Sizes(), True)
        check.equal(seat, got, [4, 5, 6], "the count of discards restarts at the five")

    def test_keeps_a_collection_that_stops_at_its_minimum(
        self, seat: Collector
    ) -> None:
        """Ten discards follow one element."""
        c = replay(1, 4, *[1, 4] * DISCARD_LIMIT)
        check.equal(
            seat,
            digits(c, Sizes(1), True),
            [4],
            "the collection keeps its one element",
        )

    def test_raises_rejected_for_a_collection_that_stops_below_its_minimum(
        self, seat: Collector
    ) -> None:
        """The targets repeat."""
        c = replay()
        with pytest.raises(Rejected):
            digits(c, Sizes(2), True)
        check.length(
            seat, c.choices, 2 + 2 * DISCARD_LIMIT, "the case has ten discards"
        )

    def test_stops_when_stop_returns_true_at_the_minimum(self, seat: Collector) -> None:
        """The flag after the minimum admits only 0."""
        c = replay(1, 4, 1, 5, 1, 6)
        check.equal(
            seat,
            digits(c, Sizes(1), False, lambda: True),
            [4],
            "the collection has one four",
        )

    def test_calls_stop_only_from_the_minimum_on(self, seat: Collector) -> None:
        """The flag of the first element is forced."""
        asked: list[int] = []
        c = replay(1, 4, 1, 5, 0)

        def stop() -> bool:
            asked.append(len(c.choices))
            return False

        digits(c, Sizes(1), False, stop)
        check.equal(
            seat,
            asked,
            [2, 4],
            "stop is called before the second and the third flag",
        )
