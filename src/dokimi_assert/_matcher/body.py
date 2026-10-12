"""The seat that an assertion makes for a body.

eventually makes one for each attempt, and rejects makes one for its check.
The calls of a body are a run of the call that ran the body, so the record
of that call contains them. A failure that stops ends the body, as it ends a
test.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from typing import TypeVar

from dokimi_assert._matcher.loop import Loop
from dokimi_assert._matcher.seat import Seat
from dokimi_assert._record.calls import Slot, own, run

__all__ = ["Body", "Ended", "run_on"]


class Ended(BaseException):
    """The signal with which the seat of a body ends the body.

    Its class derives from BaseException, so an except Exception in a body
    does not catch it.
    """


class Body:
    """The seat of one run of a body. It records whether the run failed.

    Attributes:
        failed: When True, the run reported a failure.
        message: The text of the first failure of the run, or the empty
            string.
    """

    def __init__(self, slot: Slot | None) -> None:
        """Return the seat of one run of a body.

        Args:
            slot: The slot of the call that runs the body, or None when the
                call is not recorded.
        """
        self.failed: bool = False
        self.message: str = ""
        run(own(self), slot)

    def helper(self) -> None:
        """Do nothing, because the frames of a body are the frames of the test."""

    def fail(self, message: str) -> None:
        """Keep a failure that stops the body, and end the body.

        Args:
            message: The text of the failure.

        Raises:
            Ended: Always.
        """
        self.record(message)
        raise Ended

    def record(self, message: str) -> None:
        """Keep a failure and let the body continue.

        The seat keeps the text of the first failure.

        Args:
            message: The text of the failure.
        """
        if not self.failed:
            self.message = message
        self.failed = True


_B = TypeVar("_B", bound=Body)


def run_on(seat: _B, body: Callable[[Seat], object], loop: Loop) -> _B:
    """Run body on seat, and end the run when body returns or stops.

    A body that returns an awaitable runs on loop to its end. A failure that
    stops ends the run. Any other exception is not a failure of the body,
    and run_on raises it.

    Args:
        seat: The seat of the run.
        body: The body.
        loop: The event loop of the assertion call.

    Returns:
        seat, once the run has ended.
    """
    with contextlib.suppress(Ended):
        loop.resolve(body(seat))
    return seat
