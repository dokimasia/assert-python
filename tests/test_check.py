"""The aborting surface.

The corpus already drives what each assertion means. These are the
things that belong to the surface rather than to an assertion: that it
reports fatally, marks its frame, and carries what the definition says
it should.
"""

from __future__ import annotations

from dokimi_assert import check
from dokimi_assert.seat import Recorder, Standard

OUTER = Standard()


def test_a_failure_stops_a_standard_seat() -> None:
    """The aborting surface raises rather than returning."""
    caught = check.raises(
        OUTER,
        lambda: check.equal(Standard(), 1, 2, "the values match"),
        "a failing assertion stops the test",
    )
    check.is_true(
        OUTER, isinstance(caught, AssertionError), "it raises an AssertionError"
    )


def test_a_failure_reports_through_the_fatal_path() -> None:
    """A recorder shows which of its two paths was used."""
    seat = Recorder()
    check.equal(seat, 1, 2, "the values match")

    check.is_true(OUTER, seat.failed, "the assertion failed")
    check.is_empty(OUTER, seat.messages, "it did not use the recording path")


def test_the_message_leads_the_failure() -> None:
    """The contract under test is the first thing a reader sees."""
    seat = Recorder()
    check.equal(seat, 1, 2, "the values match")
    check.has_prefix(OUTER, seat.message, "the values match", "the message leads")


def test_an_assertion_marks_its_own_frame() -> None:
    """A failure is attributed to the caller, not to the library."""
    seat = Recorder()
    check.equal(seat, 1, 1, "the values match")
    check.is_true(OUTER, seat.helper_calls > 0, "the frame was marked")


def test_a_passing_assertion_reports_nothing() -> None:
    """Nothing is recorded when nothing failed."""
    seat = Recorder()
    check.equal(seat, 1, 1, "the values match")
    check.is_false(OUTER, seat.failed, "a passing assertion is silent")


def test_the_surface_carries_what_all_says_it_does() -> None:
    """A name in __all__ that is not there would break a caller."""
    for name in check.__all__:
        check.is_true(OUTER, hasattr(check, name), f"check carries {name}")
