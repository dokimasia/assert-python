# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _matcher/errors.py tests the assertions about an error value."""

from __future__ import annotations

from dokimi_assert._matcher import errors
from dokimi_assert._matcher.seat import Mode
from dokimi_assert.seat import Recorder


class ClosedError(Exception):
    """A class of errors that the cases use as a target."""


def wrapped() -> BaseException:
    """Return a RuntimeError whose __cause__ is a ClosedError."""
    error = RuntimeError("the store failed")
    error.__cause__ = ClosedError("closed")
    return error


def contextual() -> BaseException:
    """Return a RuntimeError whose __context__ is a ClosedError."""
    error = RuntimeError("the cleanup failed")
    error.__context__ = ClosedError("closed")
    return error


class TestChain:
    """chain lists an error and the errors that it wraps."""

    def test_follows_the_cause(self) -> None:
        """The chain follows __cause__."""
        assert [type(e) for e in errors.chain(wrapped())] == [RuntimeError, ClosedError]

    def test_follows_the_context(self) -> None:
        """The chain follows __context__."""
        assert [type(e) for e in errors.chain(contextual())] == [
            RuntimeError,
            ClosedError,
        ]

    def test_stops_at_a_cycle(self) -> None:
        """The walk stops before the first repeated error."""
        first, second = ValueError("a"), ValueError("b")
        first.__cause__, second.__cause__ = second, first
        assert errors.chain(first) == [first, second]

    def test_returns_an_empty_list_for_none(self) -> None:
        """None has an empty chain."""
        assert errors.chain(None) == []


class TestMatchesTarget:
    """matches_target finds a target in the chain of an error."""

    def test_matches_the_same_object(self) -> None:
        """A sentinel object matches itself."""
        sentinel = ClosedError("closed")
        assert errors.matches_target(sentinel, sentinel)

    def test_matches_the_class_of_an_error_in_the_chain(self) -> None:
        """A class matches an instance anywhere in the chain."""
        assert errors.matches_target(wrapped(), ClosedError)

    def test_does_not_match_an_equal_error_that_is_another_object(self) -> None:
        """An exception matches by identity and not by its text."""
        assert not errors.matches_target(ClosedError("closed"), ClosedError("closed"))


class TestNoError:
    """no_error checks that a value is not an error."""

    def test_passes_none(self) -> None:
        """None is not an error."""
        seat = Recorder()
        errors.no_error(seat, Mode.SOFT, None, "none")
        assert not seat.failed

    def test_fails_an_error_with_the_record_of_err_absent(self) -> None:
        """The record has the id err-absent and the contract of the call."""
        seat = Recorder()
        errors.no_error(seat, Mode.SOFT, ValueError("x"), "some")
        assert [(f.assertion, f.contract) for f in seat.failures] == [
            ("err-absent", "some")
        ]


class TestHasError:
    """has_error checks that a value is an error."""

    def test_passes_an_error(self) -> None:
        """An exception is an error."""
        seat = Recorder()
        errors.has_error(seat, Mode.SOFT, ValueError("x"), "some")
        assert not seat.failed

    def test_fails_none_with_the_record_of_err_present(self) -> None:
        """The record has the id err-present and the contract of the call."""
        seat = Recorder()
        errors.has_error(seat, Mode.SOFT, None, "none")
        assert [(f.assertion, f.contract) for f in seat.failures] == [
            ("err-present", "none")
        ]


class TestErrorIs:
    """error_is checks that the chain of an error has the target."""

    def test_passes_an_error_whose_chain_has_the_target(self) -> None:
        """The cause of the error is an instance of the class."""
        seat = Recorder()
        errors.error_is(seat, Mode.SOFT, wrapped(), ClosedError, "is")
        assert not seat.failed

    def test_fails_an_error_without_the_target(self) -> None:
        """The failure has the target as want and the error as got."""
        seat = Recorder()
        error = wrapped()
        errors.error_is(seat, Mode.SOFT, error, KeyError, "is not")
        assert [(f.assertion, dict(f.detail)) for f in seat.failures] == [
            ("err-is", {"want": KeyError, "got": error})
        ]


class TestErrorIsNot:
    """error_is_not checks that the chain of an error does not have the target."""

    def test_passes_an_error_without_the_target(self) -> None:
        """The chain does not have an instance of the class."""
        seat = Recorder()
        errors.error_is_not(seat, Mode.SOFT, wrapped(), KeyError, "is not")
        assert not seat.failed

    def test_fails_an_error_whose_chain_has_the_target(self) -> None:
        """The record has the id err-is-not and the contract of the call."""
        seat = Recorder()
        errors.error_is_not(seat, Mode.SOFT, wrapped(), ClosedError, "is")
        assert [(f.assertion, f.contract) for f in seat.failures] == [
            ("err-is-not", "is")
        ]


class TestErrorAs:
    """error_as returns the first error of a class in the chain of an error."""

    def test_returns_the_error_of_the_class(self) -> None:
        """An instance of a subclass is an instance of the class."""
        seat = Recorder()
        found = errors.error_as(seat, Mode.FATAL, wrapped(), Exception, "c")
        assert isinstance(found, RuntimeError)
        assert not seat.failed

    def test_fails_without_an_error_of_the_class(self) -> None:
        """The call returns None.

        The failure has the class as want and the error as got.
        """
        seat = Recorder()
        assert errors.error_as(seat, Mode.FATAL, None, KeyError, "c") is None
        assert dict(seat.failures[0].detail) == {"want": KeyError, "got": None}
