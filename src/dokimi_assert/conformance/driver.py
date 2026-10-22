# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The driver of a corpus case with a behaviour in place of values.

The assertions that take a callable differ in their arguments. One takes a
coroutine function, another takes a callable without arguments, and a third
takes a projection and a body. Each entry of DRIVERS calls one assertion with
a built behaviour, so the corpus runner does not need to know the arguments.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any, cast

from dokimi_assert import check, expect
from dokimi_assert._matcher.option import Option
from dokimi_assert.conformance.subject import SUBJECTS, Subject
from dokimi_assert.seat import Recorder

__all__ = ["DRIVERS", "run_subject"]

#: The timeout in seconds of a retrying assertion on the controlled clock of
#: the corpus.
_RETRY_TIMEOUT = 3600.0

#: The seconds between the attempts of a retrying assertion on that clock.
_RETRY_INTERVAL = 60.0

#: The call of one assertion with a built behaviour. It receives the surface,
#: the seat, the behaviour, the contract and the options.
Driver = Callable[[ModuleType, Recorder, Subject, str, list[Option]], Any]


def _flips(subject: Subject) -> Callable[[], bool]:
    """Return a predicate that runs the seated body of subject on a new recorder."""

    def predicate() -> bool:
        trial = Recorder()
        cast("Callable[[Any], None]", subject.seated)(trial)
        return not trial.failed

    return predicate


def _with_input(subject: Subject) -> Callable[[], Any]:
    """Return a call of the operation of subject with its input."""

    def call() -> Any:
        return cast("Callable[[Any], Any]", subject.call)(subject.input)

    return call


def _operands(subject: Subject) -> tuple[Any, Any, Any]:
    """Return the operands of the operation of subject."""
    return cast("tuple[Any, Any, Any]", subject.operands)


#: The driver of each assertion that takes a callable, by canonical id.
DRIVERS: dict[str, Driver] = {
    "throws": lambda s, seat, subject, msg, _: s.raises(seat, subject.bare, msg),
    "not-throws": lambda s, seat, subject, msg, _: s.does_not_raise(
        seat, subject.bare, msg
    ),
    "honours-cancellation": lambda s, seat, subject, msg, _: s.honours_cancellation(
        seat, subject.handled, msg
    ),
    "honours-deadline": lambda s, seat, subject, msg, _: s.honours_deadline(
        seat, subject.handled, msg
    ),
    "nil-context-safe": lambda s, seat, subject, msg, _: s.none_handle_safe(
        seat, subject.handled, msg
    ),
    "pure": lambda s, seat, subject, msg, options: s.is_pure(
        seat, subject.observe, _with_input(subject), msg, *options
    ),
    "not-pure": lambda s, seat, subject, msg, options: s.is_not_pure(
        seat, subject.observe, _with_input(subject), msg, *options
    ),
    "eventually": lambda s, seat, subject, msg, _: s.eventually(
        seat, _RETRY_TIMEOUT, _RETRY_INTERVAL, subject.seated, msg
    ),
    "eventually-true": lambda s, seat, subject, msg, _: s.eventually_true(
        seat, _RETRY_TIMEOUT, _flips(subject), msg
    ),
    "idempotent": lambda s, seat, subject, msg, options: s.is_idempotent(
        seat, subject.call, subject.input, subject.observe, msg, *options
    ),
    "accumulates": lambda s, seat, subject, msg, _: s.accumulates(
        seat, subject.call, subject.input, subject.observe, msg
    ),
    "deterministic": lambda s, seat, subject, msg, options: s.is_deterministic(
        seat, subject.compute, subject.input, msg, *options
    ),
    "commutative": lambda s, seat, subject, msg, options: s.is_commutative(
        seat, subject.combine, *_operands(subject)[:2], msg, *options
    ),
    "associative": lambda s, seat, subject, msg, options: s.is_associative(
        seat, subject.combine, *_operands(subject), msg, *options
    ),
    "round-trip": lambda s, seat, subject, msg, options: s.round_trip(
        seat, subject.render, int, subject.input, msg, *options
    ),
    "stable-order": lambda s, seat, subject, msg, options: s.has_stable_order(
        seat, subject.iterate, msg, *options
    ),
    "no-duplicates": lambda s, seat, subject, msg, options: s.no_duplicates(
        seat, subject.iterate, msg, *options
    ),
    "monotonic": lambda s, seat, subject, msg, _: s.is_monotonic(
        seat, subject.observe, subject.advance, subject.steps, msg
    ),
    "total": lambda s, seat, subject, msg, _: s.is_total(
        seat, subject.call, subject.domain, msg
    ),
    "after-close": lambda s, seat, subject, msg, _: s.fails_after_close(
        seat, subject.close, subject.use, subject.sentinel, msg
    ),
    "poisoned": lambda s, seat, subject, msg, _: s.is_poisoned(
        seat, subject.induce, subject.read, msg
    ),
}

#: The two surfaces that a subject case runs on.
_SURFACES: dict[str, ModuleType] = {"check": check, "expect": expect}


def run_subject(
    surface: str,
    assertion: str,
    kind: str,
    seat: Recorder,
    msg: str,
    options: list[Option] | None = None,
) -> bool:
    """Drive one subject case, and report whether this language can drive it.

    Args:
        surface: The name of the surface: check or expect.
        assertion: The canonical id of the assertion under test.
        kind: The kind of the behaviour of the case.
        seat: The seat that receives the report of the assertion.
        msg: The contract under test.
        options: The relaxations of the case.

    Returns:
        True when the case ran, or False when this language does not know the
        behaviour, the assertion or the surface.
    """
    build = SUBJECTS.get(kind)
    drive = DRIVERS.get(assertion)
    module = _SURFACES.get(surface)
    if build is None or drive is None or module is None:
        return False
    drive(module, seat, build(), msg, list(options or []))
    return True
