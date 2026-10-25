# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The verdict of every assertion call. A call passes, fails or ends with a fault.

Each verdict function writes the record of the call when the seat records
calls. A seat that takes records receives the record of a failure. Any other
seat receives the sentence of the record. On both surfaces, a fault ends the
call. A faulted call did not check anything, and a test that continued would
fail on the same fault again. A seat that takes faults receives the fault as
the exception it is, and any other seat ends the call with the exception.

The run of a property can also skip. The call then writes its record with
the verdict skip, and a seat that skips its test skips it.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any, cast

from dokimi_assert._matcher.seat import (
    Mode,
    Seat,
    report,
    takes_faults,
    takes_records,
    takes_skips,
)
from dokimi_assert._record.call import Call
from dokimi_assert._record.calls import Slot, add, calls_of
from dokimi_assert._record.literal import detail as literal_of
from dokimi_assert._record.switch import reading
from dokimi_assert.failure import Failure, Where, call_site, render

if TYPE_CHECKING:
    from collections.abc import Mapping

    from dokimi_assert._record.calls import Calls

__all__ = [
    "Running",
    "as_fault",
    "end",
    "fail",
    "fault",
    "fault_text",
    "note_fault",
    "pass_",
]


def fault_text(error: object) -> str:
    """Return the text of a fault.

    Args:
        error: What ended the call.

    Returns:
        The str of an exception, and the str of any other value.
    """
    return str(error)


def as_fault(error: object) -> BaseException:
    """Return a fault as an exception.

    Args:
        error: The fault.

    Returns:
        error when it is an exception, and an Exception of its text otherwise.
    """
    return error if isinstance(error, BaseException) else Exception(fault_text(error))


def end(seat: Seat, error: object) -> None:
    """End a call with a fault.

    A seat that takes faults receives the fault with ending True. For any
    other seat, end raises the fault. It does not write a call record. It
    might not return.

    Args:
        seat: The seat of the call.
        error: The fault. A value that is not an exception becomes an
            Exception of its text.

    Raises:
        BaseException: The fault, for a seat that does not take faults.
    """
    __tracebackhide__ = True
    seat.helper()
    fault = as_fault(error)
    if takes_faults(seat):
        seat.report_fault(fault, True)
        return
    raise fault


def note_fault(seat: Seat, error: object, stacklevel: int = 2) -> None:
    """Note a fault that does not end the call.

    A seat that takes faults receives the fault with ending False. For any
    other seat, the text of the fault is a warning of the module warnings,
    which pytest shows in the summary of the run.

    Args:
        seat: The seat of the call.
        error: The fault.
        stacklevel: The frame of the warning, counted as warnings.warn counts
            it from the caller of note_fault.
    """
    fault = as_fault(error)
    if takes_faults(seat):
        seat.report_fault(fault, False)
        return
    warnings.warn(fault_text(fault), stacklevel=stacklevel + 1)


def _site(where: Where | None) -> tuple[str, int] | None:
    """Return the file and the line of where for a call record."""
    return None if where is None else (where.file, where.line)


class Running:
    """A call of an assertion. It reports its verdict once.

    A call that runs a body takes its number through Running.begin before
    the calls of its body. eventually is such a call. The seat of each run of
    the body hands its calls to the slot.
    """

    def __init__(
        self, seat: Seat, slot: Slot | None, body: bool, where: Where | None
    ) -> None:
        """Return a call. Call Running.of or Running.begin instead.

        Args:
            seat: The seat of the call.
            slot: The slot of the record of the call. Only a recorded call
                that runs a body has one.
            body: When True, the call runs a body.
            where: The call site that the call read when it started, or None
                to read it at the verdict.
        """
        self._seat: Seat = seat
        self._slot: Slot | None = slot
        self._body: bool = body
        self._where: Where | None = where

    @staticmethod
    def of(seat: Seat, where: Where | None = None) -> Running:
        """Return a call on seat that does not run a body.

        Args:
            seat: The seat of the call.
            where: The call site that the call read when it started, or None.

        Returns:
            The call.
        """
        return Running(seat, None, False, where)

    @staticmethod
    def begin(seat: Seat, where: Where | None = None) -> Running:
        """Start a call on seat that runs a body.

        The record of the call takes its number before the calls of its body.

        Args:
            seat: The seat of the call.
            where: The call site that the call reads when it starts.

        Returns:
            The call.
        """
        return Running(seat, Slot.begin(seat), True, where)

    @property
    def slot(self) -> Slot | None:
        """The slot to which the seats of the runs of the body hand their calls.

        It is None for a call that is not recorded.

        Returns:
            The slot, or None.
        """
        return self._slot

    def passed(self, mode: Mode, assertion: str, contract: str) -> None:
        """Report that the call passed.

        Args:
            mode: The surface of the call.
            assertion: The canonical id.
            contract: The message of the caller.
        """
        __tracebackhide__ = True
        if not self._switched():
            return
        self._write(Call(assertion, contract, "pass", mode is Mode.FATAL))

    def failed(
        self, mode: Mode, assertion: str, contract: str, detail: Mapping[str, Any]
    ) -> None:
        """Report that the call failed with detail.

        Under Mode.FATAL it might not return.

        Args:
            mode: The surface of the call.
            assertion: The canonical id.
            contract: The message of the caller.
            detail: The fields that the assertion declares, and no others.
        """
        __tracebackhide__ = True
        self._seat.helper()
        if not self._switched():
            return
        where = self._where if self._where is not None else call_site()
        self._write(
            Call(assertion, contract, "fail", mode is Mode.FATAL, _site(where)),
            detail=detail,
        )
        self._report(mode, Failure(assertion, contract, dict(detail), where))

    def faulted(self, mode: Mode, assertion: str, contract: str, error: object) -> None:
        """Report that error ended the call without a verdict.

        The error is a refusal of an argument or of the environment. The call
        ends with the fault on both surfaces, as end ends it, and it might not
        return.

        Args:
            mode: The surface of the call.
            assertion: The canonical id.
            contract: The message of the caller.
            error: The fault.
        """
        __tracebackhide__ = True
        self._seat.helper()
        if not self._switched():
            return
        self._write(
            Call(
                assertion,
                contract,
                "error",
                mode is Mode.FATAL,
                error=fault_text(error),
            )
        )
        end(self._seat, error)

    def passed_run(
        self,
        mode: Mode,
        assertion: str,
        contract: str,
        where: Where | None,
        run: Mapping[str, Any],
    ) -> None:
        """Report that a property at where passed.

        The record of the call has run as its detail. run is the detail of
        the run of the property.

        Args:
            mode: The surface of the call.
            assertion: The canonical id.
            contract: The message of the caller.
            where: The call site of the property.
            run: The detail of the run as JSON values.
        """
        __tracebackhide__ = True
        if not self._switched():
            return
        self._write(
            Call(assertion, contract, "pass", mode is Mode.FATAL, _site(where)), run=run
        )

    def skipped_run(
        self,
        mode: Mode,
        assertion: str,
        contract: str,
        where: Where | None,
        run: Mapping[str, Any],
        reason: str,
    ) -> None:
        """Report that the run of a property at where skipped with reason.

        The record of the call has the verdict skip, and run as its detail.
        run is the detail of the run of the property. The call then skips
        the test of a seat that skips its test, which might not return. Any
        other seat receives nothing.

        Args:
            mode: The surface of the call.
            assertion: The canonical id.
            contract: The message of the caller.
            where: The call site of the property.
            run: The detail of the run as JSON values.
            reason: The reason of the skip.
        """
        __tracebackhide__ = True
        if not self._switched():
            return
        self._write(
            Call(assertion, contract, "skip", mode is Mode.FATAL, _site(where)), run=run
        )
        seat = self._seat
        if takes_skips(seat):
            seat.skip(reason)

    def failed_run(self, mode: Mode, failure: Failure, run: Mapping[str, Any]) -> None:
        """Report that a call failed with the record failure.

        The call record has run in place of the typed literals of the detail
        of the record. run is the detail of the run of a property, or the
        tree literals of a comparison of trees. A typed literal of a value
        does not have those. Under Mode.FATAL it might not return.

        Args:
            mode: The surface of the call.
            failure: The record of the failure.
            run: The detail of the call record as JSON values.
        """
        __tracebackhide__ = True
        self._seat.helper()
        if not self._switched():
            return
        self._write(
            Call(
                failure.assertion,
                failure.contract,
                "fail",
                mode is Mode.FATAL,
                _site(failure.where),
            ),
            run=run,
        )
        self._report(mode, failure)

    def _report(self, mode: Mode, failure: Failure) -> None:
        """Send failure to the seat.

        A seat that takes records receives the record. Any other seat receives
        the sentence of the record.
        """
        __tracebackhide__ = True
        seat = self._seat
        seat.helper()
        if takes_records(seat):
            seat.report(failure, mode is Mode.FATAL)
            return
        report(seat, mode, render(failure))

    def _switched(self) -> bool:
        """Report whether the switch of recording has a defined value.

        When it does not, the call ends with the fault of the switch.
        """
        __tracebackhide__ = True
        state = reading()
        if state.fault is not None:
            end(self._seat, state.fault)
            return False
        return True

    def _write(
        self,
        call: Call,
        detail: Mapping[str, Any] | None = None,
        run: Mapping[str, Any] | None = None,
    ) -> None:
        """Write the record of the call when the call is recorded.

        The record goes into the slot of a call that runs a body, and into
        the calls of the seat for any other call. The record of a failure has
        the typed literal of each field of detail. The record of a property
        has run. A call that is not recorded does not build a record.
        """
        calls = None if self._body else calls_of(self._seat)
        if (self._slot is None) if self._body else (calls is None):
            return
        where = call.where
        if where is None:
            where = _site(self._where if self._where is not None else call_site())
        stated: Mapping[str, Any] | None = run
        if stated is None and detail is not None:
            stated = {name: literal_of(value) for name, value in detail.items()}
        record = Call(
            call.assertion,
            call.contract,
            call.verdict,
            call.aborting,
            where,
            stated,
            call.error,
        )
        if self._slot is not None:
            self._slot.write(record)
            return
        add(cast("Calls", calls), record)


def pass_(seat: Seat, mode: Mode, assertion: str, contract: str) -> None:
    """Report that a call on seat passed.

    Args:
        seat: The seat of the call.
        mode: The surface of the call.
        assertion: The canonical id.
        contract: The message of the caller.
    """
    __tracebackhide__ = True
    Running.of(seat).passed(mode, assertion, contract)


def fail(
    seat: Seat,
    mode: Mode,
    assertion: str,
    contract: str,
    detail: Mapping[str, Any] | None = None,
) -> None:
    """Report that a call on seat failed with detail.

    Under Mode.FATAL it might not return.

    Args:
        seat: The seat of the call.
        mode: The surface of the call.
        assertion: The canonical id.
        contract: The message of the caller.
        detail: The fields that the assertion declares, or None for a failure
            without fields.
    """
    __tracebackhide__ = True
    seat.helper()
    Running.of(seat).failed(mode, assertion, contract, detail or {})


def fault(seat: Seat, mode: Mode, assertion: str, contract: str, error: object) -> None:
    """Report that a call on seat ended with a fault.

    It might not return.

    Args:
        seat: The seat of the call.
        mode: The surface of the call.
        assertion: The canonical id.
        contract: The message of the caller.
        error: The fault.
    """
    __tracebackhide__ = True
    seat.helper()
    Running.of(seat).faulted(mode, assertion, contract, error)
