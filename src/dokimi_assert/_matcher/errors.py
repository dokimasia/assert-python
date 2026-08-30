"""Assertions about failures.

The standard models two failure shapes: a value returned and an
exception raised. Python raises, so an exc argument here is the
exception a caller already caught, or None when nothing was raised.
"""

from __future__ import annotations

from typing import TypeVar

from dokimi_assert._matcher.seat import Mode, Seat, report

_E = TypeVar("_E", bound=BaseException)


def _chain(exc: BaseException | None) -> list[BaseException]:
    """Return exc and every cause beneath it, outermost first.

    Both ``__cause__`` and ``__context__`` are walked: the first is an
    explicit ``raise ... from``, the second is what Python records when
    one exception is raised while handling another. A cycle stops the
    walk rather than looping.
    """
    out: list[BaseException] = []
    seen: set[int] = set()

    current = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        out.append(current)
        current = current.__cause__ or current.__context__
    return out


def no_error(seat: Seat, mode: Mode, exc: BaseException | None, msg: str) -> None:
    """Report when an exception was raised.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        exc: The error to inspect, or None when there was none.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if exc is not None:
        report(seat, mode, f"{msg}: unexpected error: {exc!r}")


def has_error(seat: Seat, mode: Mode, exc: BaseException | None, msg: str) -> None:
    """Report when nothing was raised.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        exc: The error to inspect, or None when there was none.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if exc is None:
        report(seat, mode, f"{msg}: expected an error, got none")


def error_is(
    seat: Seat, mode: Mode, exc: BaseException | None, target: BaseException, msg: str
) -> None:
    """Report when target is not exc or one of its causes.

    Identity, not equality: a sentinel matches however deeply it was
    wrapped on the way up.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        exc: The error to inspect, or None when there was none.
        target: The sentinel exception or class to match against.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if not any(item is target for item in _chain(exc)):
        report(seat, mode, f"{msg}: got error {exc!r}, want one matching {target!r}")


def error_is_not(
    seat: Seat, mode: Mode, exc: BaseException | None, target: BaseException, msg: str
) -> None:
    """Report when target is exc or one of its causes.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        exc: The error to inspect, or None when there was none.
        target: The sentinel exception or class to match against.
        msg: The contract under test. It is the first line of the failure.
    """
    __tracebackhide__ = True
    seat.helper()
    if any(item is target for item in _chain(exc)):
        report(
            seat, mode, f"{msg}: error {exc!r} matches {target!r}, want them distinct"
        )


def error_as(
    seat: Seat, mode: Mode, exc: BaseException | None, want: type[_E], msg: str
) -> _E | None:
    """Return the first exception of type want in the chain.

    Reports and returns None when the chain holds none, so a recording
    seat carries on with a value a caller can test rather than an
    attribute error.

    Args:
        seat: Where the failure is reported.
        mode: Whether a failure stops the test or is recorded.
        exc: The error to inspect, or None when there was none.
        want: The value it is supposed to produce.
        msg: The contract under test. It is the first line of the failure.

    Returns:
        The matching exception, or None when nothing matched.
    """
    __tracebackhide__ = True
    seat.helper()
    for item in _chain(exc):
        if type(item) is want:
            return item
    report(seat, mode, f"{msg}: got error {exc!r}, want one of type {want.__name__}")
    return None
