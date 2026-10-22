# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of conformance/prop/function.py tests the functions of the subject kinds."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert.conformance.prop.function import FUNCTIONS

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


class TestFunctions:
    """FUNCTIONS has the function of each subject kind of one input."""

    def test_contains_the_subject_kinds_of_one_input(self, seat: Collector) -> None:
        """The kinds are those of the table of subjects of the definition."""
        check.equal(
            seat,
            sorted(FUNCTIONS),
            [
                "drops-the-first",
                "identity",
                "is-non-negative",
                "prepends-zero",
                "returns-null",
                "sorts",
                "wraps-in-a-and-b",
            ],
            "the table has the subject kinds of one input",
        )

    tests: ClassVar[list[tuple[str, str, Any, Any]]] = [
        ("returns the input of identity", "identity", [1, 2], [1, 2]),
        ("returns True for 0 under is-non-negative", "is-non-negative", 0, True),
        ("returns False for -1 under is-non-negative", "is-non-negative", -1, False),
        ("returns None under returns-null", "returns-null", 5, None),
        ("drops the first element of a list", "drops-the-first", [3, 4], [4]),
        ("keeps an empty list empty", "drops-the-first", [], []),
        ("drops the first character of a string", "drops-the-first", "ab", "b"),
        ("puts 0 before the elements of a list", "prepends-zero", [5], [0, 5]),
        ("sorts a list of integers", "sorts", [3, -1, 2], [-1, 2, 3]),
        ("wraps a text in a and b", "wraps-in-a-and-b", "x", "axb"),
    ]

    @pytest.mark.parametrize(
        ("give_kind", "give", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_behaves_as_the_table_of_subjects_describes(
        self, seat: Collector, give_kind: str, give: Any, want: Any
    ) -> None:
        """Each function returns the value that its kind describes."""
        check.equal(
            seat,
            FUNCTIONS[give_kind](give),
            want,
            "the function returns the value that its kind describes",
        )
