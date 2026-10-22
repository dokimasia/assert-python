# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _matcher/value.py tests the assertions about a value.

The corpus has the cases of each assertion. This spec adds values that the
corpus does not have. It checks its verdicts with the assert statement of
pytest, because the module computes the verdicts.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

import pytest

from dokimi_assert._matcher import value
from dokimi_assert._matcher.option import equate_nans
from dokimi_assert._matcher.seat import Mode
from dokimi_assert.seat import Recorder

#: A call of an assertion on a recorder.
Drive = Callable[[Recorder], None]

#: Haystacks that contain their needles.
CONTAINED: list[tuple[str, Any, Any]] = [
    ("finds a substring of a str", "hello", "ell"),
    ("finds a byte string in bytes", b"abc", b"bc"),
    ("finds a byte in bytes", b"abc", 98),
    ("finds a byte string in a bytearray", bytearray(b"abc"), bytearray(b"a")),
    ("finds a key of a mapping", {"a": 1}, "a"),
    ("finds an element of a sequence", (1, 2), 2),
    ("finds an element of a set", {1, 2}, 1),
]

#: Haystacks that cannot contain their needles.
UNSUPPORTED: list[tuple[str, Any, Any]] = [
    ("refuses a needle of a str that is not a str", "hello", 1),
    ("refuses a bool needle of bytes", b"\x01", True),
    ("refuses a str needle of bytes", b"a", "a"),
    ("refuses a haystack of another type", 42, 4),
]


def failed(drive: Drive) -> Recorder:
    """Return the recorder of one call of drive. The call must fail."""
    seat = Recorder()
    drive(seat)
    assert seat.failed
    return seat


def passed(drive: Drive) -> Recorder:
    """Return the recorder of one call of drive. The call must pass."""
    seat = Recorder()
    drive(seat)
    assert not seat.failed, seat.message
    return seat


class TestLengthOf:
    """length_of returns the number of items of a value."""

    tests: ClassVar[list[tuple[str, Any, int | None]]] = [
        ("counts the scalar values of a str", "e\N{COMBINING ACUTE ACCENT}", 2),
        ("counts a character outside the basic plane once", "\U0001f600", 1),
        ("counts the bytes of bytes", b"\xc3\xa9", 2),
        ("counts the items of a sized value", {1: 2}, 1),
        ("returns none for a str with a surrogate", "\udc80", None),
        ("returns none for none", None, None),
        ("returns none for a value without a length", 3, None),
    ]

    @pytest.mark.parametrize(("name", "give", "want"), tests, ids=[t[0] for t in tests])
    def test_counts_the_items(self, name: str, give: Any, want: int | None) -> None:
        """Each value has its number of items."""
        assert value.length_of(give) == want, name


class TestNumberOf:
    """number_of returns a value as a number."""

    @pytest.mark.parametrize("give", [3, 2.5])
    def test_returns_an_int_or_a_float(self, give: float) -> None:
        """An int and a float are numbers."""
        assert value.number_of(give) == give

    @pytest.mark.parametrize("give", [True, "3", None])
    def test_returns_none_for_another_value(self, give: object) -> None:
        """A bool, a str and None are not numbers."""
        assert value.number_of(give) is None


class TestIsTrue:
    """is_true checks that a condition is true."""

    def test_passes_true(self) -> None:
        """The condition True passes."""
        passed(lambda s: value.is_true(s, Mode.FATAL, True, "c"))

    def test_fails_false(self) -> None:
        """The condition False fails."""
        failed(lambda s: value.is_true(s, Mode.FATAL, False, "c"))


class TestIsFalse:
    """is_false checks that a condition is false."""

    def test_passes_false(self) -> None:
        """The condition False passes."""
        passed(lambda s: value.is_false(s, Mode.FATAL, False, "c"))

    def test_fails_true(self) -> None:
        """The condition True fails."""
        failed(lambda s: value.is_false(s, Mode.FATAL, True, "c"))


class TestIsNone:
    """is_none checks that a value is None."""

    def test_passes_none(self) -> None:
        """None is None."""
        passed(lambda s: value.is_none(s, Mode.FATAL, None, "c"))

    def test_fails_another_value(self) -> None:
        """0 is not None, and the failure has 0 as got."""
        seat = failed(lambda s: value.is_none(s, Mode.FATAL, 0, "c"))
        assert seat.failures[0].got == 0


class TestIsNotNone:
    """is_not_none checks that a value is not None."""

    def test_passes_another_value(self) -> None:
        """0 is not None."""
        passed(lambda s: value.is_not_none(s, Mode.FATAL, 0, "c"))

    def test_fails_none(self) -> None:
        """None is None."""
        failed(lambda s: value.is_not_none(s, Mode.FATAL, None, "c"))


class TestEqual:
    """equal checks that got equals want."""

    def test_passes_an_equal_value(self) -> None:
        """Two lists with the same item are equal."""
        passed(lambda s: value.equal(s, Mode.FATAL, [1], [1], "c"))

    def test_fails_an_int_against_a_float(self) -> None:
        """An int is not a float, and the failure has both values."""
        seat = failed(lambda s: value.equal(s, Mode.FATAL, 1, 1.0, "c"))
        assert dict(seat.failures[0].detail) == {"want": 1.0, "got": 1}


class TestNotEqual:
    """not_equal checks that got differs from want."""

    def test_passes_a_value_that_differs(self) -> None:
        """1 is not 2."""
        passed(lambda s: value.not_equal(s, Mode.FATAL, 1, 2, "c"))

    def test_fails_an_equal_value(self) -> None:
        """The failure has the value as got."""
        seat = failed(lambda s: value.not_equal(s, Mode.SOFT, 1, 1, "c"))
        assert dict(seat.failures[0].detail) == {"got": 1}


class TestLength:
    """length checks the number of items of a value."""

    def test_passes_a_value_with_the_wanted_length(self) -> None:
        """A str of two characters has the length 2."""
        passed(lambda s: value.length(s, Mode.FATAL, "ab", 2, "c"))

    def test_fails_a_value_without_a_length(self) -> None:
        """A number does not have a length, so got is None."""
        seat = failed(lambda s: value.length(s, Mode.FATAL, 42, 1, "c"))
        assert dict(seat.failures[0].detail) == {"want": 1, "got": None}


class TestIsEmpty:
    """is_empty checks that a value does not have an item."""

    def test_passes_an_empty_value(self) -> None:
        """The empty str does not have an item."""
        passed(lambda s: value.is_empty(s, Mode.FATAL, "", "c"))

    def test_fails_a_value_without_a_length(self) -> None:
        """The failure has the value as got and None as length."""
        seat = failed(lambda s: value.is_empty(s, Mode.FATAL, 42, "c"))
        assert dict(seat.failures[0].detail) == {"got": 42, "length": None}


class TestIsNotEmpty:
    """is_not_empty checks that a value has an item."""

    def test_passes_a_value_with_an_item(self) -> None:
        """A list of one item is not empty."""
        passed(lambda s: value.is_not_empty(s, Mode.FATAL, [0], "c"))

    def test_fails_a_value_without_a_length(self) -> None:
        """The failure has the value as got."""
        seat = failed(lambda s: value.is_not_empty(s, Mode.FATAL, 42, "c"))
        assert dict(seat.failures[0].detail) == {"got": 42}


class TestContains:
    """contains checks that a haystack contains a needle."""

    @pytest.mark.parametrize(
        ("haystack", "needle"),
        [t[1:] for t in CONTAINED],
        ids=[t[0] for t in CONTAINED],
    )
    def test_passes_a_haystack_that_contains_the_needle(
        self, haystack: Any, needle: Any
    ) -> None:
        """Containment depends on the kind of haystack."""
        passed(lambda s: value.contains(s, Mode.FATAL, haystack, needle, "c"))

    @pytest.mark.parametrize(
        ("haystack", "needle"),
        [t[1:] for t in UNSUPPORTED],
        ids=[t[0] for t in UNSUPPORTED],
    )
    def test_fails_a_question_that_does_not_apply(
        self, haystack: Any, needle: Any
    ) -> None:
        """The haystack cannot contain the needle, and the failure has both values."""
        seat = failed(lambda s: value.contains(s, Mode.FATAL, haystack, needle, "c"))
        assert dict(seat.failures[0].detail) == {"haystack": haystack, "needle": needle}

    def test_finds_a_nan_under_equate_nans(self) -> None:
        """The options of a call apply to the comparison of its elements."""
        nan = float("nan")
        passed(lambda s: value.contains(s, Mode.FATAL, [nan], nan, "c", equate_nans()))


class TestNotContains:
    """not_contains checks that a haystack does not contain a needle."""

    def test_passes_a_haystack_without_the_needle(self) -> None:
        """2 is not an element of the list."""
        passed(lambda s: value.not_contains(s, Mode.FATAL, [1], 2, "c"))

    @pytest.mark.parametrize(
        ("haystack", "needle"),
        [t[1:] for t in CONTAINED],
        ids=[t[0] for t in CONTAINED],
    )
    def test_fails_a_haystack_that_contains_the_needle(
        self, haystack: Any, needle: Any
    ) -> None:
        """Containment depends on the kind of haystack."""
        failed(lambda s: value.not_contains(s, Mode.FATAL, haystack, needle, "c"))

    @pytest.mark.parametrize(
        ("haystack", "needle"),
        [t[1:] for t in UNSUPPORTED],
        ids=[t[0] for t in UNSUPPORTED],
    )
    def test_fails_a_question_that_does_not_apply(
        self, haystack: Any, needle: Any
    ) -> None:
        """The haystack cannot contain the needle."""
        failed(lambda s: value.not_contains(s, Mode.FATAL, haystack, needle, "c"))


class TestContainsInOrder:
    """contains_in_order checks that a text contains the needles in order."""

    def test_passes_a_text_with_the_needles_in_order(self) -> None:
        """The needles follow each other."""
        passed(lambda s: value.contains_in_order(s, Mode.FATAL, "a-b", ["a", "b"], "c"))

    def test_fails_a_value_that_is_not_a_str_at_index_0(self) -> None:
        """The failure has the haystack, an empty needle and the index 0."""
        seat = failed(lambda s: value.contains_in_order(s, Mode.FATAL, 3, ["a"], "c"))
        assert dict(seat.failures[0].detail) == {
            "haystack": 3,
            "needle": "",
            "index": 0,
        }


class TestHasPrefix:
    """has_prefix checks that a text starts with a prefix."""

    def test_passes_a_text_with_the_prefix(self) -> None:
        """The text ab starts with a."""
        passed(lambda s: value.has_prefix(s, Mode.FATAL, "ab", "a", "c"))

    def test_fails_a_value_that_is_not_a_str(self) -> None:
        """Bytes are not a str."""
        failed(lambda s: value.has_prefix(s, Mode.FATAL, b"ab", "a", "c"))


class TestHasSuffix:
    """has_suffix checks that a text ends with a suffix."""

    def test_passes_a_text_with_the_suffix(self) -> None:
        """The text ab ends with b."""
        passed(lambda s: value.has_suffix(s, Mode.FATAL, "ab", "b", "c"))

    def test_fails_a_value_that_is_not_a_str(self) -> None:
        """None is not a str."""
        failed(lambda s: value.has_suffix(s, Mode.FATAL, None, "a", "c"))


class TestMatches:
    """matches checks a text against a pattern of the portable subset."""

    def test_passes_a_text_that_the_pattern_matches(self) -> None:
        """b$ matches ab."""
        passed(lambda s: value.matches(s, Mode.FATAL, "ab", "b$", "c"))

    def test_fails_a_value_that_is_not_a_str(self) -> None:
        """The failure has got, the pattern and None as reason."""
        seat = failed(lambda s: value.matches(s, Mode.FATAL, 3, "a", "c"))
        assert dict(seat.failures[0].detail) == {
            "got": 3,
            "pattern": "a",
            "reason": None,
        }

    def test_fails_a_pattern_outside_the_subset(self) -> None:
        """The reason is the message of the parser."""
        seat = failed(lambda s: value.matches(s, Mode.FATAL, "aa", "(a)\\1", "c"))
        assert seat.failures[0].detail["reason"] == (
            'pattern "(a)\\\\1" at 5: \\1 is not in the portable subset'
        )


class TestCloseTo:
    """close_to checks that a number is within a tolerance of another number."""

    def test_passes_a_number_within_the_tolerance(self) -> None:
        """10 is within 0.5 of 10.2."""
        passed(lambda s: value.close_to(s, Mode.FATAL, 10, 10.2, 0.5, "c"))

    def test_fails_a_value_that_is_not_a_number(self) -> None:
        """A bool is not a number."""
        failed(lambda s: value.close_to(s, Mode.FATAL, True, 1.0, 0.5, "c"))

    def test_fails_an_int_too_large_for_a_float(self) -> None:
        """The difference is infinite for an int beyond the range of float."""
        failed(lambda s: value.close_to(s, Mode.FATAL, 10**400, 1.0, 1e308, "c"))


class TestInRange:
    """in_range checks that a number is between two bounds."""

    def test_passes_a_number_within_its_bounds(self) -> None:
        """An int beyond the range of float is compared exactly."""
        passed(lambda s: value.in_range(s, Mode.FATAL, 10**400, 0, 10**401, "c"))

    def test_fails_a_value_that_is_not_a_number(self) -> None:
        """A bool is not a number."""
        failed(lambda s: value.in_range(s, Mode.FATAL, True, 0, 2, "c"))
