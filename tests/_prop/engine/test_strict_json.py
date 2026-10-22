# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/strict_json.py tests the strict JSON of a store file."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.strict_json import JsonError, parse

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


class TestJsonError:
    """JsonError is the refusal of a text."""

    def test_is_a_value_error(self, seat: Collector) -> None:
        """A caller that catches ValueError catches a refusal."""
        check.error_as(
            seat, JsonError("refused"), ValueError, "a JsonError is a ValueError"
        )


class TestParse:
    """parse returns the value of a strict JSON text."""

    tests: ClassVar[list[tuple[str, str, Any]]] = [
        ("reads an integer as an int", "-12", -12),
        ("reads a number with a fraction as a float", "1.0", 1.0),
        ("reads a number with an exponent as a float", "2e3", 2000.0),
        ("reads the three words", "[true, false, null]", [True, False, None]),
        ("reads an empty array", " [ ] ", []),
        ("reads nested arrays", "[[1], [2, [3]]]", [[1], [2, [3]]]),
        ("reads an object", '{ "a" : 1, "b": {} }', {"a": 1, "b": {}}),
        (
            "reads a string with every escape",
            '"\\"\\\\\\/\\b\\f\\n\\r\\t\\u00e9"',
            '"\\/\b\f\n\r\t' + chr(0xE9),
        ),
        ("reads objects and arrays down to the most levels", "[[[]]]", [[[]]]),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_reads_the_value_of_a_text(
        self, seat: Collector, give: str, want: Any
    ) -> None:
        """An int and a float are distinct values."""
        got = parse(give, 3)
        check.equal(seat, got, want, "parse returns the value")
        check.equal(
            seat, type(got), type(want), "the type of the value is the type of want"
        )

    refusals: ClassVar[list[tuple[str, str, str]]] = [
        (
            "raises json error for a text without a value",
            "",
            "prop: the JSON at 0: Expecting value",
        ),
        (
            "raises json error for a text that continues after its value",
            "1 2",
            "prop: the JSON at 2: Extra data",
        ),
        (
            "raises json error for a value past the most levels",
            "[[[[]]]]",
            "prop: the JSON nests past 3 levels",
        ),
        (
            "raises json error for a repeated name",
            '{"a": 1, "a": 2}',
            'prop: an object repeats the name "a"',
        ),
        (
            "raises json error for a name that is not a string",
            "{1: 2}",
            "prop: the JSON at 1: Expecting property name enclosed in double quotes",
        ),
        (
            "raises json error for a control character in a string",
            '"a\tb"',
            "prop: the JSON at 2: Invalid control character at",
        ),
        (
            "raises json error for a malformed escape",
            '"\\x"',
            "prop: the JSON at 1: Invalid \\escape",
        ),
        (
            "raises json error for a number with a leading zero",
            "01",
            "prop: the JSON at 1: Extra data",
        ),
        (
            "raises json error for nan",
            "NaN",
            "prop: NaN is not a JSON number",
        ),
        (
            "raises json error for an infinity",
            "[-Infinity]",
            "prop: -Infinity is not a JSON number",
        ),
        (
            "raises json error for a text that nests past the recursion limit",
            "[" * 100_000 + "]" * 100_000,
            "prop: the JSON nests past 3 levels",
        ),
        (
            "raises json error for an integer past the digit limit of int",
            "-" + "1" * (sys.get_int_max_str_digits() + 1),
            (
                "prop: an integer of the JSON has "
                f"{sys.get_int_max_str_digits() + 1} digits, and int allows "
                f"{sys.get_int_max_str_digits()}"
            ),
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_json_error_for_a_text_that_is_not_strict(
        self, seat: Collector, give: str, want: str
    ) -> None:
        """The error has the reason."""
        error = check.raises(seat, lambda: parse(give, 3), "parse raises")
        check.error_as(seat, error, JsonError, "the error is a JsonError")
        check.equal(seat, str(error), want, "the error has the reason")
