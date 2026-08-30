"""Assertions about failures.

Python raises rather than returning a failure value, so these take the
exception a caller already caught. Written with the library, as a
consumer would.
"""

from __future__ import annotations

import pytest

from dokimi_assert import check
from dokimi_assert.seat import Recorder, Standard

OUTER = Standard()

SAMPLE = ValueError("sample")
OTHER = KeyError("other")


class TypedError(Exception):
    """A concrete type, for the cases about finding one by type."""

    def __init__(self, field: str) -> None:
        """Carry a field, so a found error differs from a fresh one."""
        super().__init__(field)
        self.field: str = field


def _wrapped(inner: BaseException) -> BaseException:
    """Return an exception whose cause is inner, so finding it walks."""
    try:
        try:
            raise inner
        except BaseException as cause:
            raise RuntimeError("while doing the thing") from cause
    except RuntimeError as outer:
        return outer


def test_no_error_passes_when_nothing_was_raised() -> None:
    """A caller who caught nothing passes."""
    seat = Recorder()
    check.no_error(seat, None, "the call succeeds")
    check.is_false(OUTER, seat.failed, "no exception passes")


def test_no_error_reports_an_exception() -> None:
    """A caught exception is reported, naming it."""
    seat = Recorder()
    check.no_error(seat, SAMPLE, "the call succeeds")

    check.is_true(OUTER, seat.failed, "an exception fails")
    check.contains(OUTER, seat.message, "sample", "the failure names the error")


def test_has_error_passes_when_something_was_raised() -> None:
    """A caught exception passes."""
    seat = Recorder()
    check.has_error(seat, SAMPLE, "the call fails")
    check.is_false(OUTER, seat.failed, "an exception passes")


def test_has_error_reports_nothing_raised() -> None:
    """Catching nothing when something was wanted fails."""
    seat = Recorder()
    check.has_error(seat, None, "the call fails")
    check.is_true(OUTER, seat.failed, "no exception fails")


def test_error_is_matches_the_same_exception() -> None:
    """An exception matches itself."""
    seat = Recorder()
    check.error_is(seat, SAMPLE, SAMPLE, "it is the sentinel")
    check.is_false(OUTER, seat.failed, "the same exception matches")


def test_error_is_walks_the_chain() -> None:
    """A sentinel matches however deeply it was wrapped."""
    seat = Recorder()
    check.error_is(seat, _wrapped(SAMPLE), SAMPLE, "it is the sentinel")
    check.is_false(OUTER, seat.failed, "a wrapped sentinel matches")


def test_error_is_reports_a_different_exception() -> None:
    """A different exception does not match."""
    seat = Recorder()
    check.error_is(seat, OTHER, SAMPLE, "it is the sentinel")
    check.is_true(OUTER, seat.failed, "a different exception fails")


def test_error_is_reports_nothing_raised() -> None:
    """Catching nothing matches no sentinel."""
    seat = Recorder()
    check.error_is(seat, None, SAMPLE, "it is the sentinel")
    check.is_true(OUTER, seat.failed, "no exception matches no sentinel")


def test_error_is_not_passes_for_distinct_exceptions() -> None:
    """Two distinct exceptions are distinct."""
    seat = Recorder()
    check.error_is_not(seat, OTHER, SAMPLE, "they are distinct")
    check.is_false(OUTER, seat.failed, "distinct exceptions pass")


def test_error_is_not_reports_a_match() -> None:
    """An exception that matches is not distinct from it."""
    seat = Recorder()
    check.error_is_not(seat, SAMPLE, SAMPLE, "they are distinct")
    check.is_true(OUTER, seat.failed, "the same exception fails")


def test_error_as_finds_a_typed_error_in_the_chain() -> None:
    """The error of the wanted type is returned from the chain."""
    typed = TypedError("carried")
    seat = Recorder()

    found = check.error_as(
        seat, _wrapped(typed), TypedError, "it carries a typed error"
    )

    check.is_false(OUTER, seat.failed, "a typed error in the chain is found")
    check.is_not_none(OUTER, found, "the error is returned")
    if found is not None:
        check.equal(OUTER, found.field, "carried", "it is the one from the chain")


def test_error_as_reports_when_no_type_matches() -> None:
    """A chain holding no such type is reported."""
    seat = Recorder()
    found = check.error_as(seat, SAMPLE, TypedError, "it carries a typed error")

    check.is_true(OUTER, seat.failed, "a chain without the type fails")
    check.is_none(OUTER, found, "nothing is returned on failure")


@pytest.mark.parametrize("exc", [None, SAMPLE])
def test_error_as_returns_none_rather_than_raising(exc: BaseException | None) -> None:
    """A caller reading the result never dereferences a missing error."""
    check.is_none(
        OUTER,
        check.error_as(Recorder(), exc, TypedError, "it carries a typed error"),
        "nothing is returned when no type matches",
    )
