"""The value assertions, where the corpus cannot reach.

The corpus drives what each assertion means for values it can state as
data. These are the paths it cannot: a type with no length, a haystack
that cannot be searched, a pattern that does not compile. Each is
reported like any other failure rather than raised, which is what keeps
a wrong argument from ending a run.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from dokimi_assert import check
from dokimi_assert.seat import Recorder, Standard

OUTER = Standard()

Drive = Callable[[Recorder], None]
"""A call under test, driven against a seat that records."""


NO_LENGTH: list[tuple[str, Drive]] = [
    ("length", lambda s: check.length(s, 42, 1, "it has a length")),
    ("is_empty", lambda s: check.is_empty(s, 42, "it is empty")),
    ("is_not_empty", lambda s: check.is_not_empty(s, 42, "it holds something")),
]
"""Length assertions given a value that has no length."""


@pytest.mark.parametrize(("name", "drive"), NO_LENGTH)
def test_a_type_with_no_length_is_reported(name: str, drive: Drive) -> None:
    """Asking a number for its length is the failure, not an exception."""
    seat = Recorder()
    drive(seat)

    check.is_true(OUTER, seat.failed, f"{name} reports a type with no length")
    check.contains(OUTER, seat.message, "not supported", "it says why")


def test_a_type_with_no_containment_is_reported() -> None:
    """Asking a number what it contains is the failure."""
    seat = Recorder()
    check.contains(seat, 42, 4, "it holds four")

    check.is_true(OUTER, seat.failed, "an unsearchable haystack reports")
    check.contains(OUTER, seat.message, "not supported", "it says why")


def test_not_contains_reports_the_same_way() -> None:
    """The negation answers for the same types."""
    seat = Recorder()
    check.not_contains(seat, 42, 4, "it lacks four")
    check.contains(OUTER, seat.message, "not supported", "it says why")


NOT_TEXT: list[tuple[str, Drive]] = [
    ("has_prefix", lambda s: check.has_prefix(s, 42, "4", "it starts with four")),
    ("has_suffix", lambda s: check.has_suffix(s, 42, "2", "it ends with two")),
    ("matches", lambda s: check.matches(s, 42, r"\d", "it is a digit")),
    (
        "contains_in_order",
        lambda s: check.contains_in_order(s, 42, ["4"], "it holds four"),
    ),
]
"""Text assertions given a value that is not text."""


@pytest.mark.parametrize(("name", "drive"), NOT_TEXT)
def test_a_non_text_value_is_reported(name: str, drive: Drive) -> None:
    """A text assertion given a number reports rather than raising."""
    seat = Recorder()
    drive(seat)

    check.is_true(OUTER, seat.failed, f"{name} reports a non-text value")
    check.contains(OUTER, seat.message, "requires text", "it says what it needed")


def test_a_pattern_that_does_not_compile_is_reported() -> None:
    """A broken pattern establishes nothing, and says so on the seat."""
    seat = Recorder()
    check.matches(seat, "anything", "([unclosed", "it matches")

    check.is_true(OUTER, seat.failed, "a broken pattern reports")
    check.contains(OUTER, seat.message, "does not compile", "it says why")


NOT_NUMERIC: list[tuple[str, Drive]] = [
    ("close_to", lambda s: check.close_to(s, "1", 1.0, 0.5, "it is about one")),
    ("in_range", lambda s: check.in_range(s, "5", 0.0, 10.0, "it is in range")),
]
"""Numeric assertions given a value that is not a number."""


@pytest.mark.parametrize(("name", "drive"), NOT_NUMERIC)
def test_a_non_numeric_value_is_reported(name: str, drive: Drive) -> None:
    """A numeric assertion given text reports rather than raising."""
    seat = Recorder()
    drive(seat)

    check.is_true(OUTER, seat.failed, f"{name} reports a non-numeric value")
    check.contains(OUTER, seat.message, "requires a number", "it says what it needed")


def test_a_bool_is_not_a_number() -> None:
    """A bool subclasses int, so a bare check would pass True as 1."""
    seat = Recorder()
    check.in_range(seat, True, 0.0, 10.0, "it is in range")

    check.is_true(OUTER, seat.failed, "a bool is refused where a number is wanted")


def test_bytes_answer_as_text() -> None:
    """A bytes value is text for the assertions that read text."""
    seat = Recorder()
    check.has_prefix(seat, b"store: missing", "store: ", "it carries the package")

    check.is_false(OUTER, seat.failed, "bytes answer as text")


def test_a_map_key_of_the_wrong_type_is_absent() -> None:
    """A key that cannot be in the map is absent, not an error."""
    seat = Recorder()
    check.contains(seat, {"a": 1}, 42, "it holds the key")

    check.is_true(OUTER, seat.failed, "a key of the wrong type is absent")


def test_an_inverted_range_always_fails() -> None:
    """A range nothing can be in says so rather than reporting a value."""
    seat = Recorder()
    check.in_range(seat, 5, 10.0, 1.0, "it is in range")

    check.contains(OUTER, seat.message, "empty range", "it names the inverted range")


def test_a_text_haystack_cannot_answer_for_a_non_text_needle() -> None:
    """Asking a string whether it holds a number is the failure."""
    seat = Recorder()
    check.contains(seat, "hello", 42, "it holds the answer")

    check.is_true(OUTER, seat.failed, "a non-text needle reports")
    check.contains(OUTER, seat.message, "not supported", "it says why")


def test_a_bytes_haystack_takes_a_text_needle() -> None:
    """A str needle is encoded before it is looked for in bytes."""
    seat = Recorder()
    check.contains(seat, b"store: missing", "missing", "it names what is gone")

    check.is_false(OUTER, seat.failed, "a text needle searches bytes")
