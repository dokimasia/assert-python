# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/tree.py tests the case tree.

The raises assertion does not catch Repeated and Diverged, because they
derive from BaseException. The spec takes them with pytest.raises.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.case import Request
from dokimi_assert._prop.engine.choice import (
    Bounds,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
    Value,
)
from dokimi_assert._prop.engine.tree import (
    NODE_LIMIT,
    Diverged,
    Ending,
    Repeated,
    Tree,
)
from helpers import no_draw

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

BIT = IntegerBounds(0, 1)
DIGIT = IntegerBounds(0, 9)
ONE_FLOAT = FloatBounds(1.0, 1.0)


def walk(
    tree: Tree, steps: list[tuple[Bounds, Value]], ending: Ending = "passed"
) -> None:
    """Walk one case down a tree, and end it."""
    walker = tree.walker()
    for index, (bounds, value) in enumerate(steps):
        walker.step(index, Request(bounds, no_draw), value)
    walker.end(ending)


class TestNodeLimit:
    """NODE_LIMIT is the largest number of nodes of a tree."""

    def test_limits_a_tree_to_2_to_the_20_nodes(self, seat: Collector) -> None:
        """The limit is about a million nodes."""
        check.equal(seat, NODE_LIMIT, 2**20, "the limit is 2^20")


class TestRepeated:
    """Repeated is the signal of a case that repeats a tested case."""

    def test_returns_the_signal_of_a_repeated_case(self, seat: Collector) -> None:
        """A body that catches Exception lets the signal pass."""
        signal = Repeated()
        check.equal(
            seat,
            str(signal),
            "prop: the case repeats a tested case",
            "the signal has its text",
        )
        check.is_false(
            seat, isinstance(signal, Exception), "the signal is not an Exception"
        )


class TestDiverged:
    """Diverged is the signal of a body that requested other choices."""

    def test_returns_the_divergence_at_a_position_with_both_bounds(
        self, seat: Collector
    ) -> None:
        """A body that catches Exception lets the signal pass."""
        signal = Diverged(2, DIGIT, None)
        check.equal(
            seat,
            [str(signal), signal.index, signal.recorded, signal.requested],
            ["prop: choice 2 diverges", 2, DIGIT, None],
            "the signal has its text and its fields",
        )
        check.is_false(
            seat, isinstance(signal, Exception), "the signal is not an Exception"
        )


class TestTree:
    """Tree has the cases that the simplest, edge and random phases generated."""

    def test_returns_a_tree_of_the_root_alone(self, seat: Collector) -> None:
        """The default limit is NODE_LIMIT."""
        tree = Tree()
        check.equal(
            seat,
            [tree.nodes, tree.limit, tree.full, len(tree.root.children)],
            [1, NODE_LIMIT, False, 0],
            "the tree has the root alone",
        )


class TestTreeExhausted:
    """Tree.exhausted reports whether the run has tested every input of its domain."""

    def test_reports_true_once_every_value_of_two_booleans_has_a_leaf(
        self, seat: Collector
    ) -> None:
        """The tree is exhausted after the fourth case."""
        tree = Tree()
        seen: list[bool] = []
        for first, second in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            walk(tree, [(BIT, first), (BIT, second)])
            seen.append(tree.exhausted)
        check.equal(
            seat,
            seen,
            [False, False, False, True],
            "the tree is exhausted after the fourth case",
        )

    def test_reports_true_for_a_short_branch_once_its_neighbour_is_exhausted(
        self, seat: Collector
    ) -> None:
        """A 1 needs both of its children."""
        tree = Tree()
        walk(tree, [(BIT, 0)])
        walk(tree, [(BIT, 1), (BIT, 0)])
        before = tree.exhausted
        walk(tree, [(BIT, 1), (BIT, 1)])
        check.equal(
            seat,
            [before, tree.exhausted],
            [False, True],
            "the tree is exhausted after the last child",
        )

    def test_reports_true_for_a_case_without_choices(self, seat: Collector) -> None:
        """The root is the leaf."""
        tree = Tree()
        walk(tree, [])
        check.is_true(seat, tree.exhausted, "the domain of one case is exhausted")

    def test_reports_false_for_a_float_of_one_value(self, seat: Collector) -> None:
        """A float never exhausts."""
        tree = Tree()
        walk(tree, [(ONE_FLOAT, 1.0)])
        check.is_false(seat, tree.exhausted, "a float of one value does not exhaust")

    def test_reports_false_for_a_sequence_without_a_maximum(
        self, seat: Collector
    ) -> None:
        """The sequence is unbounded."""
        tree = Tree()
        walk(tree, [(SequenceBounds(1), ())])
        check.is_false(seat, tree.exhausted, "an unbounded sequence does not exhaust")

    def test_reports_true_once_every_sequence_of_the_bounds_has_a_leaf(
        self, seat: Collector
    ) -> None:
        """The bounds allow 1 + 2 + 4 sequences."""
        tree = Tree()
        bounds = SequenceBounds(2, 0, 2)
        every = [(), (0,), (1,), (0, 0), (0, 1), (1, 0), (1, 1)]
        seen: list[bool] = []
        for elements in every:
            walk(tree, [(bounds, elements)])
            seen.append(tree.exhausted)
        check.equal(
            seat,
            seen,
            [False] * 6 + [True],
            "the tree is exhausted after the seventh case",
        )

    def test_reports_true_once_every_sequence_of_a_minimum_length_has_a_leaf(
        self, seat: Collector
    ) -> None:
        """The bounds allow two sequences of one element."""
        tree = Tree()
        bounds = SequenceBounds(2, 1, 1)
        walk(tree, [(bounds, (0,))])
        before = tree.exhausted
        walk(tree, [(bounds, (1,))])
        check.equal(
            seat,
            [before, tree.exhausted],
            [False, True],
            "the tree is exhausted after the second sequence",
        )

    def test_reports_false_for_a_sequence_whose_minimum_length_passes_the_children(
        self, seat: Collector
    ) -> None:
        """The bounds allow a hundred sequences of two digits."""
        tree = Tree()
        walk(tree, [(SequenceBounds(10, 2, 2), (3, 4))])
        check.is_false(
            seat, tree.exhausted, "one sequence of a hundred does not exhaust"
        )

    def test_reports_false_for_a_full_tree(self, seat: Collector) -> None:
        """A full tree does not report an exhausted domain."""
        tree = Tree(2)
        walk(tree, [(BIT, 0)])
        walk(tree, [(BIT, 1)])
        check.equal(
            seat,
            [tree.full, tree.exhausted],
            [True, False],
            "the full tree is not exhausted",
        )


class TestWalkerStep:
    """Walker.step follows the choice at an index of a case."""

    def test_raises_repeated_for_a_choice_that_arrives_at_a_leaf(
        self, seat: Collector
    ) -> None:
        """The second case repeats the choice 7."""
        tree = Tree()
        walk(tree, [(DIGIT, 7)])
        with pytest.raises(Repeated):
            walk(tree, [(DIGIT, 7)])
        check.equal(seat, tree.nodes, 2, "the repeat does not add a node")

    def test_raises_repeated_for_a_repeat_of_a_rejected_case(
        self, seat: Collector
    ) -> None:
        """A rejected case is a leaf."""
        tree = Tree()
        walk(tree, [(DIGIT, 3)], "rejected")
        with pytest.raises(Repeated):
            walk(tree, [(DIGIT, 3)])
        check.equal(seat, tree.nodes, 2, "the repeat does not add a node")

    def test_follows_every_nan_on_one_edge_apart_from_the_two_zeros(
        self, seat: Collector
    ) -> None:
        """A NaN of the other sign repeats."""
        tree = Tree()
        every = FloatBounds(-math.inf, math.inf, True)
        walk(tree, [(every, math.nan)])
        with pytest.raises(Repeated):
            walk(tree, [(every, -math.nan)])
        walk(tree, [(every, 0.0)])
        walk(tree, [(every, -0.0)])
        check.length(seat, tree.root.children, 3, "the root has three edges")

    def test_follows_a_sequence_on_the_edge_of_its_elements(
        self, seat: Collector
    ) -> None:
        """The same elements repeat."""
        tree = Tree()
        data = SequenceBounds(256, 0, 4)
        walk(tree, [(data, (1, 2))])
        with pytest.raises(Repeated):
            walk(tree, [(data, (1, 2))])
        check.length(seat, tree.root.children, 1, "the root has one edge")

    def test_raises_diverged_for_other_bounds_at_a_recorded_position(
        self, seat: Collector
    ) -> None:
        """The second request diverges."""
        tree = Tree()
        walk(tree, [(DIGIT, 1), (DIGIT, 2)])
        with pytest.raises(Diverged) as caught:
            walk(tree, [(DIGIT, 1), (BIT, 0)])
        err = caught.value
        check.equal(
            seat,
            [err.index, err.recorded, err.requested],
            [1, DIGIT, BIT],
            "the divergence has both requests",
        )

    def test_raises_diverged_for_a_request_where_an_earlier_case_ended(
        self, seat: Collector
    ) -> None:
        """The tree recorded an end."""
        tree = Tree()
        walk(tree, [])
        with pytest.raises(Diverged) as caught:
            walk(tree, [(DIGIT, 1)])
        err = caught.value
        check.equal(
            seat,
            [err.index, err.recorded, err.requested],
            [0, None, DIGIT],
            "the divergence has the request",
        )

    def test_stops_checking_a_case_once_the_tree_is_full(self, seat: Collector) -> None:
        """The tree stopped growing."""
        tree = Tree(3)
        walk(tree, [(BIT, 0), (BIT, 0)])
        walk(tree, [(BIT, 0), (BIT, 1)])
        walk(tree, [(BIT, 0), (BIT, 1), (BIT, 1)])
        check.equal(
            seat, [tree.nodes, tree.full], [3, True], "the tree is full at three nodes"
        )


class TestWalkerEnd:
    """Walker.end marks the leaf where a case ended."""

    def test_raises_diverged_for_an_end_where_an_earlier_case_made_a_request(
        self, seat: Collector
    ) -> None:
        """The tree recorded a request."""
        tree = Tree()
        walk(tree, [(DIGIT, 1)])
        with pytest.raises(Diverged) as caught:
            walk(tree, [])
        err = caught.value
        check.equal(
            seat,
            [err.index, err.recorded, err.requested],
            [0, DIGIT, None],
            "the divergence has the end",
        )

    def test_marks_the_leaf_with_how_the_case_ended(self, seat: Collector) -> None:
        """The case was rejected."""
        tree = Tree()
        walk(tree, [(DIGIT, 3)], "rejected")
        check.equal(
            seat, tree.root.children[3].ending, "rejected", "the leaf has the ending"
        )
