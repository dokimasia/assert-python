"""The spec of _history/cycle.py tests the searches of the dependency graph."""

from __future__ import annotations

from typing import ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._history.cycle import (
    RELATIONS,
    Graph,
    Walk,
    alternates,
    components,
    path,
    simple,
)
from dokimi_assert.seat import Collector


def graph(*edges: tuple[int, int]) -> Graph:
    """Return the graph of edges, with the sorted targets of each transaction."""
    out: dict[int, list[int]] = {}
    for a, b in edges:
        out.setdefault(a, []).append(b)
    return {node: sorted(targets) for node, targets in out.items()}


class TestRelations:
    """RELATIONS lists the relations in the order of an entry of a cycle."""

    def test_lists_ww_then_wr_then_rw(self, seat: Collector) -> None:
        """The order is ww, wr, rw."""
        check.equal(
            seat,
            RELATIONS,
            ("ww", "wr", "rw"),
            "RELATIONS lists ww, wr and rw in order",
        )


class TestComponents:
    """components returns the strongly connected components of a graph."""

    def test_returns_the_components_of_two_or_more_transactions_by_their_lowest(
        self, seat: Collector
    ) -> None:
        """Transactions 3 and 8 are not on a cycle."""
        g = graph((4, 6), (6, 4), (0, 2), (2, 0), (2, 3), (3, 8))
        check.equal(
            seat,
            components([6, 4, 3, 2, 0, 8], g),
            [[0, 2], [4, 6]],
            "the components are [0, 2] and [4, 6]",
        )

    def test_returns_one_component_of_a_cycle_through_three_transactions(
        self, seat: Collector
    ) -> None:
        """The cycle visits 0, 1 and 2."""
        check.equal(
            seat,
            components([0, 1, 2], graph((0, 1), (1, 2), (2, 0))),
            [[0, 1, 2]],
            "the three transactions form one component",
        )

    def test_returns_an_empty_list_for_a_graph_without_a_cycle(
        self, seat: Collector
    ) -> None:
        """The one edge leads from 0 to 1."""
        check.is_empty(
            seat,
            components([0, 1], graph((0, 1))),
            "the graph does not have a component",
        )


class TestPath:
    """path returns the shortest path between two transactions within members."""

    def test_returns_the_shortest_path_that_comes_first_in_the_order_of_the_targets(
        self, seat: Collector
    ) -> None:
        """Two paths of three edges lead from 0 to 4."""
        g = graph((0, 2), (0, 1), (1, 3), (2, 3), (3, 4))
        check.equal(
            seat,
            path(0, 4, g, {0, 1, 2, 3, 4}),
            [0, 1, 3, 4],
            "the path goes through 1",
        )

    def test_returns_a_path_within_the_members_alone(self, seat: Collector) -> None:
        """The members leave out 1."""
        g = graph((0, 1), (0, 2), (1, 3), (2, 3))
        check.equal(
            seat, path(0, 3, g, {0, 2, 3}), [0, 2, 3], "the path goes through 2"
        )

    def test_returns_none_for_a_goal_without_a_path_from_the_start(
        self, seat: Collector
    ) -> None:
        """The one edge leads from 0 to 1."""
        check.is_none(
            seat,
            path(1, 0, graph((0, 1)), {0, 1}),
            "a path from 1 to 0 does not exist",
        )

    def test_returns_the_start_alone_for_a_start_that_is_the_goal(
        self, seat: Collector
    ) -> None:
        """The graph is empty."""
        check.equal(seat, path(2, 2, graph(), {2}), [2], "the path is the start")


class TestAlternates:
    """alternates reports whether a closed walk does not have two adjacent rw edges."""

    tests: ClassVar[list[tuple[str, Walk, bool]]] = [
        (
            "a walk whose rw edges are apart",
            [(0, "rw"), (1, "wr"), (2, "rw"), (3, "ww")],
            True,
        ),
        ("a walk with two adjacent rw edges", [(0, "rw"), (1, "rw"), (2, "wr")], False),
        (
            "a walk whose last rw edge is adjacent to its first",
            [(0, "rw"), (1, "wr"), (2, "rw")],
            False,
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_reports_whether_the_walk_alternates_for(
        self, seat: Collector, give: Walk, want: bool
    ) -> None:
        """The verdict is True for a walk without two adjacent rw edges."""
        check.equal(
            seat, alternates(give), want, "alternates returns the expected verdict"
        )


class TestSimple:
    """simple returns the simple cycle of a closed walk."""

    def test_starts_a_cycle_at_its_first_rw_edge(self, seat: Collector) -> None:
        """The rw edge leaves transaction 1."""
        check.equal(
            seat,
            simple([(0, "wr"), (1, "rw"), (2, "ww")]),
            [(1, "rw"), (2, "ww"), (0, "wr")],
            "the cycle starts at 1",
        )

    def test_keeps_a_cycle_without_an_rw_edge_as_it_starts(
        self, seat: Collector
    ) -> None:
        """The walk has a ww edge and a wr edge."""
        check.equal(
            seat,
            simple([(0, "ww"), (1, "wr")]),
            [(0, "ww"), (1, "wr")],
            "the cycle starts at 0",
        )

    def test_keeps_the_part_between_two_visits_of_a_transaction_that_alternates(
        self, seat: Collector
    ) -> None:
        """The walk visits 4 twice. The loop between the two visits alternates."""
        check.equal(
            seat,
            simple([(0, "rw"), (2, "ww"), (4, "rw"), (6, "wr"), (4, "wr")]),
            [(4, "rw"), (6, "wr")],
            "the cycle is the loop through 4 and 6",
        )

    def test_keeps_the_rest_of_a_walk_whose_loop_has_two_adjacent_rw_edges(
        self, seat: Collector
    ) -> None:
        """The loop through 4 and 6 has two adjacent rw edges."""
        check.equal(
            seat,
            simple([(0, "rw"), (2, "ww"), (4, "rw"), (6, "rw"), (4, "wr")]),
            [(0, "rw"), (2, "ww"), (4, "wr")],
            "the cycle visits 0, 2 and 4",
        )
