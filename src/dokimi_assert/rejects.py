# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The assertion that a check fails against a subject that it must reject.

A check whose every statement is no_error passes against a subject whose
methods do nothing and return None. Such a check looks like coverage but
does not establish anything. rejects drives the check against such a
subject and returns the failure records of the check.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, final

from dokimi_assert._matcher.body import Body, Ended, run_on
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.loop import Loop
from dokimi_assert._matcher.verdict import Running
from dokimi_assert._override import override
from dokimi_assert._record.calls import Slot, own
from dokimi_assert.failure import Failure, call_site

if TYPE_CHECKING:
    from collections.abc import Callable

    from dokimi_assert._matcher.seat import Mode, Seat

__all__ = ["rejects"]


@final
class _Check(Body):
    """The seat of the check that rejects drives.

    It keeps each failure record of the check in call order, and whether the
    check failed at all. A failure that stops ends the check in the same way
    as it ends a test. A fault that ends its call ends the check, and the
    seat keeps the fault.
    """

    def __init__(self, slot: Slot | None, parent: Seat) -> None:
        """Return the seat of the check of the call that slot started on parent."""
        super().__init__(slot, parent)
        self.records: list[Failure] = []
        self.fault: BaseException | None = None

    def report(self, failure: Failure, aborting: bool) -> None:
        """Keep failure, and end the check when it came from the aborting surface.

        Args:
            failure: The record of the failure.
            aborting: When True, the record came from the aborting surface.

        Raises:
            Ended: The record came from the aborting surface.
        """
        self.failed = True
        self.records.append(failure)
        if aborting:
            raise Ended

    @override
    def report_fault(self, fault: BaseException, ending: bool) -> None:
        """Keep a fault that ends its call, and end the check.

        A noted fault passes to the seat of rejects, and the check continues.

        Args:
            fault: The fault.
            ending: When True, the fault ends its call.

        Raises:
            Ended: The fault ends its call.
        """
        if not ending:
            super().report_fault(fault, ending)
            return
        if self.fault is None:
            self.fault = fault
        raise Ended


def rejects(
    seat: Seat, mode: Mode, msg: str, body: Callable[[Any], object]
) -> list[Failure]:
    """Report when the check does not fail, and return its failure records.

    The body receives a seat of its own. That seat keeps every failure record
    of the check, and it ends the check at its first failure that stops in
    the same way as a failure ends a test. A message that the check passes to
    the fail or the record of that seat directly fails the check without a
    record. An exception of the body propagates out of the call, because it
    is a defect of the check or of the subject and not a rejection. The calls
    of the check are recorded under the call of rejects.

    A fault that ends a call of the check ends the call of rejects with the
    same fault, because a check that ends with a fault rejects nothing. The
    record of rejects states the verdict error, the seat receives the fault
    as seat.fault passes it, and rejects returns an empty list. A fault that
    the check notes passes to the seat as a noted fault.

    Args:
        seat: The seat that receives the failure.
        mode: Mode.FATAL stops the test at a failure, and Mode.SOFT records
            the failure.
        msg: The contract under test.
        body: The check that must fail. A coroutine function runs on an
            event loop of the call.

    Returns:
        The failure records of the check in call order. The list is empty
        when the check passed, and then the assertion failed.
    """
    __tracebackhide__ = True
    seat.helper()
    call = Running.begin(seat, call_site())
    with Loop("rejects") as loop:
        try:
            check = run_on(_Check(call.slot, seat), body, loop)
        except FaultError as error:
            call.faulted(mode, "rejects", msg, error)
            return []
    if call.slot is not None:
        call.slot.take(own(check))
    if check.fault is not None:
        call.faulted(mode, "rejects", msg, check.fault)
        return []
    if not check.failed:
        call.failed(mode, "rejects", msg, {})
        return []
    call.passed(mode, "rejects", msg)
    return list(check.records)
