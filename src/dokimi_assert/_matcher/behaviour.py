# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The assertions about the behaviour of a subject, not about its result.

Python does not have a cancellation handle in every signature, as Go has
context.Context. asyncio cancels a coroutine through its task, so the
cancellation assertions drive a coroutine function and do not hand it a
handle.
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from typing import TYPE_CHECKING, Any

from dokimi_assert._matcher.compare import equal as _equal
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.loop import Loop
from dokimi_assert._matcher.option import Option, settings
from dokimi_assert._matcher.seat import Mode, Seat, clock_of
from dokimi_assert._matcher.verdict import Running
from dokimi_assert.failure import call_site

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

__all__ = [
    "NOTICE_TIMEOUT",
    "completes_within",
    "honours_cancellation",
    "honours_deadline",
    "is_pure",
    "none_handle_safe",
]

#: The seconds that a cancellation assertion waits for a cancelled subject to
#: stop.
NOTICE_TIMEOUT = 1.0


def honours_cancellation(
    seat: Seat, mode: Mode, fn: Callable[[], Awaitable[Any]], msg: str
) -> None:
    """Report when a cancelled subject does not raise CancelledError.

    The assertion starts the subject and cancels it at its first await. The
    field got of a failure describes what the subject did instead.

    - got is None when the subject returns before it awaits.
    - got is the error when the subject raises another error.
    - got is a text when the subject returns after the cancellation, or when
      it does not stop within NOTICE_TIMEOUT.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        fn: The coroutine function under test.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    call = Running.of(seat, call_site())

    async def drive() -> tuple[bool, object]:
        task = asyncio.ensure_future(fn())
        await asyncio.sleep(0)
        if task.done():
            error = None if task.cancelled() else task.exception()
            return False, error
        task.cancel()
        try:
            await asyncio.wait_for(task, NOTICE_TIMEOUT)
        except asyncio.CancelledError:
            return True, None
        except TimeoutError:
            return False, f"the subject did not stop within {NOTICE_TIMEOUT}s"
        except Exception as error:
            return False, error
        return False, "the cancelled subject returned"

    _honours(call, mode, "honours-cancellation", msg, drive)


def honours_deadline(
    seat: Seat, mode: Mode, fn: Callable[[], Awaitable[Any]], msg: str
) -> None:
    """Report when a subject with an expired deadline does not time out.

    The deadline has passed when the subject starts, so the timeout cancels
    the subject at its first await. The field got of a failure describes
    what the subject did instead.

    - got is None when the subject returns before it awaits.
    - got is the error when the subject raises another error.

    The assertion uses asyncio.timeout and not asyncio.wait_for. wait_for
    with a timeout of 0 does not start the coroutine, so every subject would
    time out.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        fn: The coroutine function under test.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    call = Running.of(seat, call_site())

    async def drive() -> tuple[bool, object]:
        try:
            async with asyncio.timeout(0):
                await fn()
        except TimeoutError:
            return True, None
        except Exception as error:
            return False, error
        return False, None

    _honours(call, mode, "honours-deadline", msg, drive)


def _honours(
    call: Running,
    mode: Mode,
    assertion: str,
    msg: str,
    drive: Callable[[], Awaitable[tuple[bool, object]]],
) -> None:
    """Run drive on the loop of the call, and report its verdict."""
    __tracebackhide__ = True
    with Loop(assertion) as loop:
        try:
            honoured, got = loop.resolve(drive())
        except FaultError as error:
            call.faulted(mode, assertion, msg, error)
            return
    if not honoured:
        call.failed(mode, assertion, msg, {"got": got})
        return
    call.passed(mode, assertion, msg)


def completes_within(
    seat: Seat, mode: Mode, within: float, fn: Callable[[], Any], msg: str
) -> None:
    """Report when fn takes longer than within seconds.

    The assertion calls fn on a daemon thread and waits for it on the
    platform clock. When fn has not returned at the end of the duration, the
    call fails at once, and got is the number of seconds that it waited. The
    thread of fn continues after the test.

    When fn returns in time, the assertion also measures fn on the clock of
    the seat. A test can control that clock. The assertion treats an
    exception of fn as a return, so a subject that raises in time passes.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        within: The most seconds that fn can take.
        fn: The callable under test. A coroutine function runs on an event
            loop of the thread.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    call = Running.of(seat, call_site())
    clock = clock_of(seat)
    started = clock.now()
    # perf_counter has the highest resolution of the platform. Before Python
    # 3.13, monotonic on Windows had a resolution of 15.6 milliseconds.
    waited = time.perf_counter()
    done = threading.Event()

    def subject() -> None:
        # The assertion measures the time of fn and not its outcome.
        try:
            with contextlib.suppress(Exception), Loop("completes-within") as loop:
                loop.resolve(fn())
        finally:
            done.set()

    threading.Thread(target=subject, name="completes-within", daemon=True).start()
    if not done.wait(max(within, 0.0)):
        got = round(time.perf_counter() - waited, 3)
        call.failed(mode, "completes-within", msg, {"want": within, "got": got})
        return
    elapsed = clock.now() - started
    if elapsed > within:
        got = round(elapsed, 3)
        call.failed(mode, "completes-within", msg, {"want": within, "got": got})
        return
    call.passed(mode, "completes-within", msg)


def is_pure(
    seat: Seat,
    mode: Mode,
    observe: Callable[[], Any],
    fn: Callable[[], Any],
    msg: str,
    *options: Option,
) -> None:
    """Report when fn changes what observe returns.

    fn can change any state that observe does not return. observe must
    return a copy. When observe returns state that the subject shares, the
    assertion compares one object with itself.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        observe: Returns a copy of the state. It runs before and after fn.
        fn: The call that must not change what observe returns.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    call = Running.of(seat, call_site())
    with Loop("pure") as loop:
        try:
            before = loop.resolve(observe())
            loop.resolve(fn())
            after = loop.resolve(observe())
        except FaultError as error:
            call.faulted(mode, "pure", msg, error)
            return
    if not _equal(after, before, settings(options)):
        call.failed(mode, "pure", msg, {"want": before, "got": after})
        return
    call.passed(mode, "pure", msg)


def none_handle_safe(
    seat: Seat, mode: Mode, fn: Callable[[Any], Any], msg: str
) -> None:
    """Report when a subject with None in place of a handle crashes.

    The assertion fails a subject that raises AttributeError or TypeError. A
    subject raises one of the two when it uses None without a check. The
    assertion passes a subject that raises any other exception, because a
    refusal of the call is a decision.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        fn: The callable under test. It receives None.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    call = Running.of(seat, call_site())
    with Loop("nil-context-safe") as loop:
        try:
            loop.resolve(fn(None))
        except FaultError as error:
            call.faulted(mode, "nil-context-safe", msg, error)
            return
        except (AttributeError, TypeError) as error:
            call.failed(mode, "nil-context-safe", msg, {"got": error})
            return
        # Any other exception is a refusal of the call, and the subject passes.
        except Exception:  # noqa: S110
            pass
    call.passed(mode, "nil-context-safe", msg)
