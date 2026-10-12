"""The spec of _matcher/order.py tests the assertion about neighbouring items."""

from __future__ import annotations

from dokimi_assert._matcher import order
from dokimi_assert._matcher.seat import Mode
from dokimi_assert.seat import Recorder


class TestPairwise:
    """pairwise checks a predicate on every two adjacent items."""

    def test_passes_items_when_every_pair_satisfies_the_predicate(self) -> None:
        """Items in ascending order pass the predicate a <= b."""
        seat = Recorder()
        order.pairwise(seat, Mode.FATAL, [1, 2, 2, 3], lambda a, b: a <= b, "c")
        assert not seat.failed

    def test_passes_a_sequence_without_a_pair(self) -> None:
        """An empty sequence and a sequence of one item do not have a pair."""
        seat = Recorder()
        order.pairwise(seat, Mode.FATAL, [], lambda a, b: False, "none")
        order.pairwise(seat, Mode.FATAL, [1], lambda a, b: False, "one")
        assert not seat.failed

    def test_fails_at_the_first_pair_that_does_not_satisfy_the_predicate(self) -> None:
        """The failure has the index of the pair and its two items."""
        seat = Recorder()
        order.pairwise(seat, Mode.FATAL, [1, 3, 2, 0], lambda a, b: a <= b, "c")
        assert dict(seat.failures[0].detail) == {"index": 1, "first": 3, "second": 2}
