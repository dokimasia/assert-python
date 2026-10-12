"""The spec of _prop/engine/edge.py tests the value of each choice at each boundary."""

from __future__ import annotations

import math

from dokimi_assert import check
from dokimi_assert._prop.engine.case import Request
from dokimi_assert._prop.engine.choice import (
    Bounds,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
    Value,
)
from dokimi_assert._prop.engine.edge import BOUNDARIES, Edge
from dokimi_assert.seat import Collector
from helpers import no_draw


def take(bounds: Bounds, edge: int | None = None) -> list[Value]:
    """Return the values that a request with bounds takes at the boundaries."""
    request = Request(bounds, no_draw, edge)
    return [Edge(boundary).value(request, 0) for boundary in BOUNDARIES]


class TestBoundaries:
    """BOUNDARIES has the edge cases in the order that a run tries them."""

    def test_orders_the_edge_cases_from_min_to_below(self, seat: Collector) -> None:
        """The bounds come first."""
        check.equal(
            seat,
            BOUNDARIES,
            ("min", "max", "above", "below"),
            "the boundaries are in order",
        )


class TestEdgeValue:
    """Edge.value returns the value of a choice at the boundary of the provider."""

    def test_gives_an_integer_its_bounds_and_the_neighbours_of_its_target(
        self, seat: Collector
    ) -> None:
        """The bounds -5 and 5 are around the target 0."""
        check.equal(
            seat,
            take(IntegerBounds(-5, 5)),
            [-5, 5, 1, -1],
            "the choice takes the four values",
        )

    def test_gives_an_integer_its_target_for_a_neighbour_outside_the_bounds(
        self, seat: Collector
    ) -> None:
        """-1 is outside [0, 10]."""
        check.equal(
            seat,
            take(IntegerBounds(0, 10)),
            [0, 10, 1, 0],
            "below takes the target",
        )

    def test_gives_an_integer_of_one_value_that_value_at_every_boundary(
        self, seat: Collector
    ) -> None:
        """The bounds contain 3 alone."""
        check.equal(
            seat, take(IntegerBounds(3, 3)), [3, 3, 3, 3], "every boundary takes 3"
        )

    def test_gives_a_float_its_bounds_and_the_next_floats_around_its_target(
        self, seat: Collector
    ) -> None:
        """The smallest subnormals are around 0."""
        check.equal(
            seat,
            take(FloatBounds(-1.0, 1.0)),
            [-1.0, 1.0, 5e-324, -5e-324],
            "the choice takes the four values",
        )

    def test_gives_a_float_its_target_for_the_next_float_below_the_bounds(
        self, seat: Collector
    ) -> None:
        """The target 0.5 is the lower bound."""
        above, below = take(FloatBounds(0.5, 0.75))[2:]
        check.equal(
            seat,
            [above, below],
            [math.nextafter(0.5, math.inf), 0.5],
            "above takes the next float, and below takes the target",
        )

    def test_gives_a_float_of_width_32_the_next_float_of_that_width(
        self, seat: Collector
    ) -> None:
        """The value above 0 is the smallest subnormal of width 32."""
        above = take(FloatBounds(-1.0, 1.0, False, 32))[2]
        check.equal(
            seat,
            above,
            2.0**-149,
            "above takes the smallest subnormal of width 32",
        )

    def test_gives_a_sequence_one_element_at_the_boundary(
        self, seat: Collector
    ) -> None:
        """The elements are 0, k - 1, 1 and 0."""
        check.equal(
            seat,
            take(SequenceBounds(256)),
            [(0,), (255,), (1,), (0,)],
            "the sequence takes one element at each boundary",
        )

    def test_gives_a_sequence_min_size_elements(self, seat: Collector) -> None:
        """The sequence takes three elements at max."""
        check.equal(
            seat,
            take(SequenceBounds(4, 3))[1],
            (3, 3, 3),
            "the sequence has three elements",
        )

    def test_gives_a_sequence_of_at_most_0_elements_an_empty_value(
        self, seat: Collector
    ) -> None:
        """The max_size is 0."""
        check.equal(
            seat,
            take(SequenceBounds(4, 0, 0)),
            [(), (), (), ()],
            "every boundary takes the empty sequence",
        )

    def test_gives_the_element_0_above_for_a_k_of_1(self, seat: Collector) -> None:
        """1 is outside [0, 1)."""
        check.equal(seat, take(SequenceBounds(1))[2], (0,), "above takes the element 0")

    def test_gives_a_structure_choice_its_edge_at_every_boundary(
        self, seat: Collector
    ) -> None:
        """The edge of a free flag is 1."""
        check.equal(
            seat,
            take(IntegerBounds(0, 1), 1),
            [1, 1, 1, 1],
            "every boundary takes the edge",
        )

    def test_gives_a_structure_choice_its_target_for_an_edge_outside_the_bounds(
        self, seat: Collector
    ) -> None:
        """The bounds force the flag to 1."""
        check.equal(
            seat,
            take(IntegerBounds(1, 1), 0),
            [1, 1, 1, 1],
            "every boundary takes the target",
        )
