"""Assertions about the order of a sequence."""

from __future__ import annotations

from dokimi_assert import check
from dokimi_assert.seat import Recorder, Standard

OUTER = Standard()


def _ascending(earlier: int, later: int) -> bool:
    """Report whether the pair is in ascending order."""
    return earlier < later


def test_an_ordered_sequence_passes() -> None:
    """Every adjacent pair satisfying the predicate passes."""
    seat = Recorder()
    check.pairwise(seat, [1, 2, 3], _ascending, "it ascends")
    check.is_false(OUTER, seat.failed, "an ordered sequence passes")


def test_an_empty_sequence_passes() -> None:
    """Nothing has no pair to break."""
    seat = Recorder()
    check.pairwise(seat, [], _ascending, "it ascends")
    check.is_false(OUTER, seat.failed, "nothing has no pair to break")


def test_one_item_passes() -> None:
    """One item has no pair to break."""
    seat = Recorder()
    check.pairwise(seat, [7], _ascending, "it ascends")
    check.is_false(OUTER, seat.failed, "one item has no pair to break")


def test_a_break_names_its_index_and_both_values() -> None:
    """The first break is reported with enough to find it."""
    seat = Recorder()
    check.pairwise(seat, [1, 5, 3], _ascending, "it ascends")

    check.is_true(OUTER, seat.failed, "an unordered sequence fails")
    check.contains_in_order(
        OUTER, seat.message, ["1", "5", "3"], "the failure names index then values"
    )


def test_equal_neighbours_break_a_strict_order() -> None:
    """A strict predicate refuses equal neighbours."""
    seat = Recorder()
    check.pairwise(seat, [1, 1], _ascending, "it strictly ascends")
    check.is_true(OUTER, seat.failed, "equal neighbours break a strict order")


def test_only_the_first_break_is_reported() -> None:
    """One failure, however many pairs are out of order."""
    seat = Recorder()
    check.pairwise(seat, [9, 1, 9, 1], _ascending, "it ascends")
    check.is_true(OUTER, seat.failed, "an unordered sequence fails once")
