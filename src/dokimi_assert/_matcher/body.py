# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The seat that an assertion makes for a body.

eventually makes one for each attempt, and rejects makes one for its check.
The calls of a body are a run of the call that ran the body, so the record
of that call contains them. A failure that stops ends the body, as it ends a
test. A fault that ends its call fails the body with the text of the fault,
and a fault that a call notes passes to the seat of the assertion. The seat
runs the functions that its member cleanup registers when the body ends.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, TypeVar

from dokimi_assert._matcher.cleanup import Cleanups
from dokimi_assert._matcher.loop import Loop
from dokimi_assert._matcher.verdict import fault_text, note_fault
from dokimi_assert._record.calls import Slot, own, run

if TYPE_CHECKING:
    from collections.abc import Callable

    from dokimi_assert._matcher.seat import Seat

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

    def __init__(self, slot: Slot | None, parent: Seat) -> None:
        """Return the seat of one run of a body.

        Args:
            slot: The slot of the call that runs the body, or None when the
                call is not recorded.
            parent: The seat of the assertion that runs the body.
        """
        self.failed: bool = False
        self.message: str = ""
        self.parent: Seat = parent
        self._cleanups: Cleanups = Cleanups()
        run(own(self), slot)

    def cleanup(self, fn: Callable[[], object]) -> None:
        """Register fn to run when the body ends.

        The seat runs the last registered first, on the event loop of the
        assertion call. A function that arrives after the body's cleanups
        ran runs at once, and an awaitable that it returns runs on an event
        loop of its own.

        Args:
            fn: The function.
        """
        if self._cleanups.add(fn):
            return
        with Loop("cleanup") as loop:
            loop.resolve(fn())

    def finish(self, loop: Loop) -> None:
        """End the body: run the functions that cleanup registered.

        The last registered runs first, and an awaitable that one returns
        runs on loop. A failure in a function is a failure of the body. An
        error that a function raises does not stop the later functions.

        Args:
            loop: The event loop of the assertion call.

        Raises:
            Exception: The first error that a function raised, once every
                function ran.
        """
        raised: list[Exception] = []

        def run_one(fn: Callable[[], object]) -> None:
            try:
                with contextlib.suppress(Ended):
                    loop.resolve(fn())
            except Exception as error:
                raised.append(error)

        self._cleanups.close(run_one)
        if raised:
            raise raised[0]

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

    def report_fault(self, fault: BaseException, ending: bool) -> None:
        """Receive a fault of a call of the body.

        A fault that ends its call fails the body with the text of the fault,
        and ends the body. A noted fault passes to the seat of the assertion,
        and the body continues.

        Args:
            fault: The fault.
            ending: When True, the fault ends its call.

        Raises:
            Ended: The fault ends its call.
        """
        if not ending:
            note_fault(self.parent, fault)
            return
        self.fail(fault_text(fault))


_B = TypeVar("_B", bound=Body)


def run_on(seat: _B, body: Callable[[Seat], object], loop: Loop) -> _B:
    """Run body on seat, and end the run when body returns or stops.

    A body that returns an awaitable runs on loop to its end. A failure that
    stops ends the run. Any other exception is not a failure of the body,
    and run_on raises it. The seat runs its cleanups when the body ends,
    however it ended.

    Args:
        seat: The seat of the run.
        body: The body.
        loop: The event loop of the assertion call.

    Returns:
        seat, once the run and its cleanups have ended.
    """
    try:
        with contextlib.suppress(Ended):
            loop.resolve(body(seat))
    finally:
        seat.finish(loop)
    return seat
