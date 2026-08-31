"""Driving a corpus case that names a behaviour rather than a value.

An assertion taking a callable has a shape of its own: one takes a body,
one takes a body and a projection, one takes a timeout and an interval.
This holds the shape for each, so the corpus runner does not.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from dokimi_assert.conformance.subject import drive

__all__ = ["SUBJECT_DRIVERS", "run_subject"]


def _body(invoke: Callable[..., None]) -> Callable[..., None]:
    """An assertion taking a seat, a body and a message."""

    def run(seat: Any, subject: Any, msg: str) -> None:
        invoke(seat, subject, msg)

    return run


def _projected(invoke: Callable[..., None]) -> Callable[..., None]:
    """An assertion taking a seat, a projection, a body and a message."""

    def run(seat: Any, subject: Any, msg: str) -> None:
        invoke(seat, subject.observe, subject, msg)

    return run


def _retried(invoke: Callable[..., None]) -> Callable[..., None]:
    """An assertion taking a seat, a timeout, an interval, a body and a message.

    The seat's clock is what makes this cost nothing: an assertion that
    retries advances it rather than waiting.
    """

    def run(seat: Any, subject: Any, msg: str) -> None:
        invoke(seat, 3600.0, 60.0, subject, msg)

    return run


def _predicate(invoke: Callable[..., None]) -> Callable[..., None]:
    """An assertion taking a seat, a timeout, a predicate and a message."""

    def run(seat: Any, subject: Any, msg: str) -> None:
        from dokimi_assert.seat import Recorder

        attempts = 0

        def flips() -> bool:
            nonlocal attempts
            attempts += 1
            trial = Recorder()
            subject(trial)
            return not trial.failed

        invoke(seat, 3600.0, flips, msg)

    return run


#: How each subject-taking assertion is called, by canonical id.
SUBJECT_DRIVERS: dict[str, Callable[[Callable[..., None]], Callable[..., None]]] = {
    "throws": _body,
    "not-throws": _body,
    "honours-cancellation": _body,
    "honours-deadline": _body,
    "nil-context-safe": _body,
    "pure": _projected,
    "eventually": _retried,
    "eventually-true": _predicate,
}


def run_subject(
    invoke: Callable[..., None], assertion: str, kind: str, seat: Any, msg: str
) -> bool:
    """Drive one subject case, answering whether this language could.

    Args:
        invoke: The assertion under test, on the surface being driven.
        assertion: Its canonical id.
        kind: The subject kind the case names.
        seat: Where the assertion reports.
        msg: The contract under test.

    Returns:
        True when the case ran, False when this language builds no such
        subject and the case was skipped.
    """
    shape = SUBJECT_DRIVERS.get(assertion)
    subject = drive(kind)
    if shape is None or subject is None:
        return False
    shape(invoke)(seat, subject, msg)
    return True
