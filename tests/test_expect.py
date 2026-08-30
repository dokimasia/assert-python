"""The recording surface.

The corpus drives what each assertion means through this surface too.
These are the things that belong to it alone: that it records rather
than raising, and that several failures in a row are all kept.
"""

from __future__ import annotations

from dokimi_assert import check, expect
from dokimi_assert.seat import Recorder, Standard

OUTER = Standard()


def test_a_failure_does_not_stop_the_caller() -> None:
    """The whole point: the test carries on."""
    seat = Recorder()

    expect.equal(seat, 1, 2, "the first")
    expect.equal(seat, 3, 4, "the second")

    check.length(OUTER, seat.messages, 2, "both failures were recorded")


def test_a_failure_reports_through_the_recording_path() -> None:
    """The fatal path is left untouched."""
    seat = Recorder()
    expect.equal(seat, 1, 2, "the values match")

    check.is_true(OUTER, seat.failed, "the assertion failed")
    check.length(OUTER, seat.messages, 1, "it used the recording path")


def test_the_message_leads_the_failure() -> None:
    """The contract under test is the first thing a reader sees."""
    seat = Recorder()
    expect.equal(seat, 1, 2, "the values match")
    check.has_prefix(OUTER, seat.message, "the values match", "the message leads")


def test_an_assertion_marks_its_own_frame() -> None:
    """A failure is attributed to the caller, not to the library."""
    seat = Recorder()
    expect.equal(seat, 1, 1, "the values match")
    check.is_true(OUTER, seat.helper_calls > 0, "the frame was marked")


def test_a_passing_assertion_reports_nothing() -> None:
    """Nothing is recorded when nothing failed."""
    seat = Recorder()
    expect.equal(seat, 1, 1, "the values match")
    check.is_false(OUTER, seat.failed, "a passing assertion is silent")


def test_the_surface_carries_what_all_says_it_does() -> None:
    """A name in __all__ that is not there would break a caller."""
    for name in expect.__all__:
        check.is_true(OUTER, hasattr(expect, name), f"expect carries {name}")


def test_it_carries_the_same_members_as_the_aborting_surface() -> None:
    """Bar the one excused, the two surfaces are the same surface."""
    check.equal(
        OUTER,
        sorted(set(check.__all__) - {"rejects"}),
        sorted(expect.__all__),
        "both surfaces carry the same assertions",
    )
