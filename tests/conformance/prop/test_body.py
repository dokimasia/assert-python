"""The spec of conformance/prop/body.py tests the bodies of the property vectors."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.case import Case, Rejected
from dokimi_assert._prop.engine.choice import IntegerBounds
from dokimi_assert.conformance.prop.body import DRAWN, body_of
from dokimi_assert.seat import Collector
from helpers import body_case, refusal, replaying

#: The generator of the digits.
DIGIT: dict[str, Any] = {"gen": "integer", "min": 0, "max": 9}

#: The predicate of an even number.
EVEN: dict[str, Any] = {"kind": "divisible-by", "n": 2}


def ending(spec: object, *choices: int) -> tuple[str, list[str | None], list[str]]:
    """Run the body of spec on a case that replays integer choices.

    Returns:
        How the body ended, ran or rejected, the identities that its ending
        received, and the labels of the case.
    """
    ends: list[str | None] = []
    body = body_of(spec, lambda _, failure: ends.append(failure))
    c, engine = body_case(replaying(*choices))
    try:
        body(c)
    except Rejected:
        return "rejected", ends, sorted(engine.labels)
    return "ran", ends, sorted(engine.labels)


def drawn_case(body: Any, *choices: int) -> Case:
    """Return the engine case of one call of body on a case that replays choices."""
    c, engine = body_case(replaying(*choices))
    body(c)
    return engine


class TestBodyOf:
    """body_of returns a new body of a JSON object."""

    tests: ClassVar[list[tuple[str, dict[str, Any], list[int], Any]]] = [
        (
            "classifies the case under each label whose predicate is true",
            {
                "draw": DIGIT,
                "classify": {"even": EVEN, "big": {"kind": "at-least", "n": 5}},
            },
            [4],
            ("ran", [None], ["even"]),
        ),
        (
            "rejects the case when the predicate rejects-when is true",
            {
                "draw": DIGIT,
                "rejects-when": {"kind": "always"},
                "fails": [{"identity": "every", "when": {"kind": "always"}}],
            },
            [4],
            ("rejected", [], []),
        ),
        (
            "ends the case with the identity of the first true entry of fails",
            {
                "draw": DIGIT,
                "fails": [
                    {"identity": "odd", "when": {**EVEN, "not": True}},
                    {"identity": "big", "when": {"kind": "at-least", "n": 5}},
                ],
            },
            [7],
            ("ran", ["odd"], []),
        ),
        (
            "ends the case without an identity when no predicate of fails is true",
            {
                "draw": DIGIT,
                "fails": [{"identity": "big", "when": {"kind": "at-least", "n": 5}}],
            },
            [2],
            ("ran", [None], []),
        ),
        (
            "ends the case of draws-nothing without an identity",
            {"kind": "draws-nothing"},
            [],
            ("ran", [None], []),
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "give_choices", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_returns_the_body(
        self, seat: Collector, give: dict[str, Any], give_choices: list[int], want: Any
    ) -> None:
        """The body classifies, rejects and ends its case in that order."""
        check.equal(
            seat,
            ending(give, *give_choices),
            want,
            "the body ends its case as its object describes",
        )

    def test_returns_a_body_that_draws_under_the_label_value(
        self, seat: Collector
    ) -> None:
        """The counterexample of a vector has the label value."""
        engine = drawn_case(body_of({"draw": DIGIT}, lambda _, __: None), 3)
        check.equal(
            seat,
            [(d.label, d.value) for d in engine.draws],
            [(DRAWN, 3)],
            "the body draws one value under the label value",
        )

    def test_returns_a_body_of_diverges_that_requests_other_bounds_after_its_first_call(
        self, seat: Collector
    ) -> None:
        """The first call draws a digit, and every later call draws a bool."""
        body = body_of({"kind": "diverges"}, lambda _, __: None)
        highs = [
            cast("IntegerBounds", drawn_case(body, 0).requests[0].bounds).hi
            for _ in range(3)
        ]
        check.equal(seat, highs, [9, 1, 1], "the requests change after the first call")

    def test_returns_a_body_of_fails_once_that_fails_once_above_1000(
        self, seat: Collector
    ) -> None:
        """The second value above 1,000 passes."""
        ends: list[str | None] = []
        body = body_of({"kind": "fails-once"}, lambda _, failure: ends.append(failure))
        for value in (1000, 1001, 2000):
            drawn_case(body, value)
        check.equal(seat, ends, [None, "once", None], "the body fails once")

    refused: ClassVar[list[tuple[str, Any, str]]] = [
        ("raises for a value that is not an object", 5, "prop: 5 is not a body"),
        (
            "raises for a named body that does not exist",
            {"kind": "widget"},
            'prop: "widget" is not a named body',
        ),
        (
            "raises for a classify that is not an object",
            {"draw": DIGIT, "classify": []},
            "prop: classify is [], not an object",
        ),
        (
            "raises for fails that are not a list",
            {"draw": DIGIT, "fails": {}},
            "prop: fails is {}, not a list",
        ),
        (
            "raises for an identity that is not a string",
            {"draw": DIGIT, "fails": [{"identity": 1, "when": {"kind": "always"}}]},
            "prop: 1 is not an identity",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refused], ids=[t[0] for t in refused]
    )
    def test_raises_for_an_object_that_is_not_a_body(
        self, seat: Collector, give: Any, want: str
    ) -> None:
        """The error has the part at fault."""
        check.equal(
            seat,
            refusal(seat, lambda: body_of(give, lambda _, __: None)),
            want,
            "body_of refuses the object",
        )
