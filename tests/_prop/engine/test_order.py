"""The spec of _prop/engine/order.py tests the shortlex order of choice sequences."""

from __future__ import annotations

from typing import ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.choice import FloatBounds, IntegerBounds, SequenceBounds
from dokimi_assert._prop.engine.float import Key
from dokimi_assert._prop.engine.order import choice_key, shortlex
from dokimi_assert.seat import Collector


class TestChoiceKey:
    """choice_key returns the key of a choice under its bounds."""

    def test_returns_the_rank_of_integers_before_the_key_of_an_integer(
        self, seat: Collector
    ) -> None:
        """The choice is 2 below the target."""
        check.equal(
            seat,
            choice_key(IntegerBounds(-5, 5), -2),
            (0, 2, 1),
            "the key starts with the rank 0",
        )

    def test_returns_the_rank_of_floats_before_the_key_of_a_float(
        self, seat: Collector
    ) -> None:
        """The value 0.5 has one fractional bit and the numerator 1."""
        key = choice_key(FloatBounds(0.0, 1.0), 0.5)
        check.equal(seat, key, (1, 1, 1, 1, 0), "the key starts with the rank 1")

    def test_returns_the_key_of_a_sequence_with_the_rank_of_sequences_first(
        self, seat: Collector
    ) -> None:
        """The sequence has two elements."""
        key = choice_key(SequenceBounds(4), (3, 1))
        check.equal(seat, key, (2, 2, 3, 1), "the key starts with the rank 2")


class TestShortlex:
    """shortlex returns the key of a choice sequence in shortlex order."""

    tests: ClassVar[list[tuple[str, list[Key], list[Key], bool]]] = [
        ("orders a shorter sequence first", [(0,)], [(0,), (0,)], True),
        ("orders a longer sequence last", [(0,), (0,)], [(5,)], False),
        (
            "orders the sequence of the smaller first difference first",
            [(0, 1), (0, 9)],
            [(0, 2), (0, 0)],
            True,
        ),
        (
            "orders the sequence of the larger first difference last",
            [(0, 1), (0, 9)],
            [(0, 1), (0, 0)],
            False,
        ),
        (
            "does not order a sequence before an equal one",
            [(0, 1)],
            [(0, 1)],
            False,
        ),
    ]

    @pytest.mark.parametrize(
        ("a", "b", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_keys_in_shortlex_order(
        self, seat: Collector, a: list[Key], b: list[Key], want: bool
    ) -> None:
        """The shorter sequence is smaller."""
        check.equal(
            seat, shortlex(a) < shortlex(b), want, "the keys compare in shortlex order"
        )
