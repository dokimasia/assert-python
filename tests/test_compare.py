"""The comparison rules, where Python's own answer differs.

Plain asserts rather than the library: equality is what every other
assertion is built on, so testing it with assertions that compare would
let one bug hide another.
"""

from __future__ import annotations

import math

import pytest

from dokimi._matcher.compare import equal
from dokimi._matcher.option import Option, equate_empty, equate_nans

STRICT = Option()


@pytest.mark.parametrize(
    ("got", "want", "python_says"),
    [
        (0, False, True),
        (1, True, True),
        (1, 1.0, True),
        (True, 1, True),
    ],
)
def test_types_that_python_equates_are_kept_apart(
    got: object, want: object, python_says: bool
) -> None:
    """Bool subclasses int and numbers compare across types.

    Python's own == says these are equal. The standard says values of
    different types never compare, so this enforces it rather than
    inheriting it.
    """
    assert (got == want) is python_says, "Python's answer has changed"
    assert not equal(got, want, STRICT)


@pytest.mark.parametrize(
    ("got", "want"),
    [(1, "1"), ([], None), (None, []), ({}, None), ("a", b"a")],
)
def test_values_of_different_types_never_compare(got: object, want: object) -> None:
    """Types must match exactly, whatever Python's == would say."""
    assert not equal(got, want, STRICT)


@pytest.mark.parametrize(
    ("got", "want"),
    [
        (1, 1),
        ("a", "a"),
        ([], []),
        ({}, {}),
        ([1, [2]], [1, [2]]),
        ({"a": 1}, {"a": 1}),
    ],
)
def test_identical_values_compare_equal(got: object, want: object) -> None:
    """Same type, same content, equal."""
    assert equal(got, want, STRICT)


def test_a_nested_type_difference_is_found() -> None:
    """The rule reaches inside a collection, not only its surface."""
    assert not equal([1], [1.0], STRICT)
    assert not equal({"a": 1}, {"a": 1.0}, STRICT)


def test_absent_is_not_empty_by_default() -> None:
    """A value that is absent and one present but empty differ."""
    assert not equal([], None, STRICT)
    assert not equal({}, None, STRICT)


def test_equate_empty_joins_absent_and_empty() -> None:
    """The relaxation is available where the difference does not matter."""
    relaxed = Option(equate_empty=True)
    assert equal([], None, relaxed)
    assert equal(None, {}, relaxed)
    assert equal(None, (), relaxed)


def test_equate_empty_does_not_join_absent_and_populated() -> None:
    """The relaxation covers empty, not anything at all."""
    assert not equal([1], None, Option(equate_empty=True))


def test_nan_does_not_equal_itself() -> None:
    """IEEE 754, which Python's own float comparison already follows."""
    assert not equal(math.nan, math.nan, STRICT)


def test_equate_nans_joins_them() -> None:
    """The relaxation is available where a NaN should match."""
    assert equal(math.nan, math.nan, Option(equate_nans=True))


def test_floats_compare_exactly() -> None:
    """A tolerance belongs to close_to, not here."""
    assert not equal(0.1 + 0.2, 0.3, STRICT)


def test_the_option_builders_produce_the_flags() -> None:
    """The public builders and the dataclass agree."""
    assert equate_empty() == Option(equate_empty=True)
    assert equate_nans() == Option(equate_nans=True)
