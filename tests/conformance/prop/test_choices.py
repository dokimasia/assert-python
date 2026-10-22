# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of conformance/prop/choices.py tests the form of choices and seeds."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check, option
from dokimi_assert._prop.engine.choice import Choice
from dokimi_assert.conformance.prop.choices import (
    choice_literal,
    parse_choice,
    parse_choices,
    seed_of,
)
from helpers import refusal

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


class TestChoiceLiteral:
    """choice_literal returns the form of a choice in a vector."""

    tests: ClassVar[list[tuple[str, Choice, object]]] = [
        ("returns a JSON integer for a small integer", Choice("integer", -7), -7),
        (
            "returns a decimal string for an integer beyond 2^53 - 1",
            Choice("integer", 2**64 - 1),
            "18446744073709551615",
        ),
        ("returns the float form of a float", Choice("float", 1.5), {"float": 1.5}),
        (
            "returns the name of a float without a JSON number",
            Choice("float", math.inf),
            {"float": "Inf"},
        ),
        (
            "returns the sequence form of a sequence",
            Choice("sequence", (1, 0, 2)),
            {"sequence": [1, 0, 2]},
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_form(
        self, seat: Collector, give: Choice, want: object
    ) -> None:
        """Each kind of choice has a form of its own."""
        check.equal(seat, choice_literal(give), want, "a choice has its form")


class TestParseChoice:
    """parse_choice returns the choice of its form in a vector."""

    tests: ClassVar[list[tuple[str, object, Choice]]] = [
        ("returns an integer choice of a JSON integer", 3, Choice("integer", 3)),
        (
            "returns an integer choice of a large decimal string",
            "-9223372036854775808",
            Choice("integer", -(2**63)),
        ),
        ("returns a float choice", {"float": 0.5}, Choice("float", 0.5)),
        ("returns a float choice of NaN", {"float": "NaN"}, Choice("float", math.nan)),
        (
            "returns a sequence choice",
            {"sequence": [2, 4]},
            Choice("sequence", (2, 4)),
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_choice(
        self, seat: Collector, give: object, want: Choice
    ) -> None:
        """Each form decodes to one kind of choice."""
        check.equal(
            seat,
            parse_choice(give),
            want,
            "a form decodes to its choice",
            option.equate_nans(),
        )

    refused: ClassVar[list[tuple[str, Any, str]]] = [
        (
            "raises for an object with another member",
            {"bytes": "00"},
            'prop: {"bytes": "00"} is not a choice',
        ),
        (
            "raises for a sequence that is not a list",
            {"sequence": 1},
            'prop: {"sequence": 1} is not a choice',
        ),
        (
            "raises for an object with two members",
            {"float": 1.0, "sequence": []},
            'prop: {"float": 1.0, "sequence": []} is not a choice',
        ),
        (
            "raises for a value that is not an integer",
            True,
            "prop: true is not an integer",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refused], ids=[t[0] for t in refused]
    )
    def test_raises_for_a_form_that_is_not_a_choice(
        self, seat: Collector, give: Any, want: str
    ) -> None:
        """The error contains the form."""
        check.equal(
            seat,
            refusal(seat, lambda: parse_choice(give)),
            want,
            "parse_choice refuses the form",
        )


class TestParseChoices:
    """parse_choices returns the choices of a list of their forms."""

    def test_returns_the_choices_in_order(self, seat: Collector) -> None:
        """Each element is one choice."""
        check.equal(
            seat,
            parse_choices([1, {"float": 2.0}]),
            [Choice("integer", 1), Choice("float", 2.0)],
            "the choices keep the order of the list",
        )

    def test_raises_for_a_value_that_is_not_a_list(self, seat: Collector) -> None:
        """A single choice is not a list of choices."""
        check.equal(
            seat,
            refusal(seat, lambda: parse_choices(1)),
            "prop: 1 is not a list of choices",
            "parse_choices refuses a value that is not a list",
        )


class TestSeedOf:
    """seed_of returns the seed of its text in a vector."""

    def test_returns_the_seed_of_a_decimal_string(self, seat: Collector) -> None:
        """The seed can exceed 2^53."""
        check.equal(
            seat,
            seed_of("18446744073709551615"),
            2**64 - 1,
            "the seed is the value of its decimal digits",
        )

    @pytest.mark.parametrize(
        ("give", "want"),
        [
            (7, "prop: the seed 7 is not a decimal string"),
            ("-1", 'prop: the seed "-1" is not a decimal string'),
            ("0x7", 'prop: the seed "0x7" is not a decimal string'),
        ],
        ids=["a JSON number", "a negative number", "a hexadecimal number"],
    )
    def test_raises_for_a_seed_that_is_not_a_decimal_string(
        self, seat: Collector, give: object, want: str
    ) -> None:
        """A seed is a string of decimal digits."""
        check.equal(
            seat, refusal(seat, lambda: seed_of(give)), want, "seed_of refuses the seed"
        )
