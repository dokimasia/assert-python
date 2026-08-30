"""The assertion that an assertion can fail."""

from __future__ import annotations

from collections.abc import Callable

from dokimi_assert._matcher.seat import Seat
from dokimi_assert.seat import Recorder

__all__ = ["rejects"]


def rejects(seat: Seat, msg: str, body: Callable[[Recorder], None]) -> str:
    """Run body against a subject it must reject, and return its failure.

    A check whose every statement is ``no_error`` passes against a
    subject whose methods do nothing and return None. It reads as
    coverage and establishes nothing. This names the wrong subject,
    drives the check against it, and reads the rejection.

        got = rejects(seat, "a store that overwrites fails the check",
                      lambda tb: refuses_a_duplicate(tb, OverwritingStore()))

        check.contains(seat, got, "the key was already present",
                       "and fails for the reason the check is about")

    Assert on the returned message. A subject that raises before
    reaching the assertion satisfies a bare call while the check's own
    assertion never ran, which is the defect this exists to catch, one
    level up.

    An exception from body is not caught. A check that raises is a
    defect in the check or in the stand-in, and reporting it as a
    rejection would hide it.
    """
    __tracebackhide__ = True
    seat.helper()

    recorder = Recorder()
    body(recorder)

    if not recorder.failed:
        seat.fail(f"{msg}: the check passed against a subject it must reject")
    return recorder.message
