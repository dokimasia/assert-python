"""The spec of _prop/engine/alphabet.py tests the default alphabet of a string."""

from __future__ import annotations

from typing import ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.alphabet import (
    SIZE,
    character,
    index_of,
    indices,
    merge,
)
from dokimi_assert.seat import Collector

#: The index of DEL. DEL is the first code point after the printable
#: characters and the controls below space.
DEL = 95 + 32

#: The index of U+E000. It is the first code point after the surrogates.
AFTER_SURROGATES = DEL + (0xD7FF - 0x7F + 1)


class TestSize:
    """SIZE is the number of characters of the default alphabet."""

    def test_counts_every_unicode_scalar_value(self, seat: Collector) -> None:
        """The alphabet has every code point but the surrogates."""
        check.equal(seat, SIZE, 0x110000 - 0x800, "SIZE counts the scalar values")


class TestCharacter:
    """character returns the character at an index of the default alphabet."""

    tests: ClassVar[list[tuple[str, int, str]]] = [
        ("returns the digit 0 at index 0", 0, "0"),
        ("returns the first lowercase letter after the digits", 10, "a"),
        ("returns space after the letters", 62, " "),
        ("returns the first control after the printable characters", 95, chr(0)),
        ("returns del after the controls", DEL, chr(0x7F)),
        ("returns the code point after the surrogates", AFTER_SURROGATES, chr(0xE000)),
        ("returns the last scalar value at the last index", SIZE - 1, chr(0x10FFFF)),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_character_of_an_index(
        self, seat: Collector, give: int, want: str
    ) -> None:
        """The printable characters come first."""
        check.equal(
            seat, character(give), want, "character returns the character of the index"
        )

    refusals: ClassVar[list[tuple[str, int]]] = [
        ("raises value error for an index below 0", -1),
        ("raises value error for an index of size", SIZE),
    ]

    @pytest.mark.parametrize(
        "give", [t[1] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_value_error_for_an_index_outside_the_alphabet(
        self, seat: Collector, give: int
    ) -> None:
        """An index is in [0, SIZE)."""
        error = check.raises(seat, lambda: character(give), "character raises")
        check.error_as(seat, error, ValueError, "the error is a ValueError")
        want = f"prop: index {give} is outside the default alphabet"
        check.equal(seat, str(error), want, "the error has the index")


class TestIndexOf:
    """index_of returns the index of a character in the default alphabet."""

    def test_returns_the_index_of_every_character_that_character_returns(
        self, seat: Collector
    ) -> None:
        """The function index_of inverts character."""
        sample = [0, 9, 61, 94, 95, 126, DEL, 55_000, AFTER_SURROGATES, SIZE - 1]
        check.equal(
            seat,
            [index_of(character(i)) for i in sample],
            sample,
            "index_of returns the index of each character",
        )

    def test_returns_none_for_a_lone_surrogate(self, seat: Collector) -> None:
        """A surrogate is not a scalar value."""
        check.is_none(seat, index_of(chr(0xD800)), "a surrogate does not have an index")


class TestIndices:
    """indices returns the indices of a range of code points."""

    def test_returns_one_interval_for_the_digits(self, seat: Collector) -> None:
        """The digits are the first ten characters."""
        check.equal(seat, indices(0x30, 0x39), [(0, 9)], "the digits are one interval")

    def test_returns_the_indices_of_a_range_across_the_controls(
        self, seat: Collector
    ) -> None:
        """The range has two controls, space and the exclamation mark."""
        check.equal(
            seat,
            indices(0x1E, 0x21),
            [(62, 63), (95 + 30, 95 + 31)],
            "the range has two intervals",
        )

    def test_leaves_the_surrogates_out(self, seat: Collector) -> None:
        """The code points around the surrogates are neighbours in the alphabet."""
        check.equal(
            seat,
            indices(0xD7FF, 0xE000),
            [(AFTER_SURROGATES - 1, AFTER_SURROGATES)],
            "the range is one interval",
        )

    def test_returns_an_empty_list_for_a_range_of_surrogates_alone(
        self, seat: Collector
    ) -> None:
        """A surrogate does not have an index."""
        check.is_empty(
            seat, indices(0xD800, 0xDFFF), "the range does not have an index"
        )


class TestMerge:
    """merge returns the union of inclusive intervals."""

    def test_returns_the_sorted_union_of_overlapping_and_touching_intervals(
        self, seat: Collector
    ) -> None:
        """Touching intervals join."""
        check.equal(
            seat,
            merge([(10, 12), (1, 3), (1, 2), (4, 5), (11, 20)]),
            [(1, 5), (10, 20)],
            "the union has two intervals",
        )

    def test_keeps_intervals_apart_that_neither_overlap_nor_touch(
        self, seat: Collector
    ) -> None:
        """A gap of one keeps two intervals apart."""
        check.equal(
            seat,
            merge([(5, 6), (1, 3)]),
            [(1, 3), (5, 6)],
            "the union has two intervals",
        )
