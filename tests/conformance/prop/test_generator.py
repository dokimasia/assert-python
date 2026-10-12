"""The spec of conformance/prop/generator.py tests the generators of the vectors."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.case import Case, Replaying
from dokimi_assert._prop.engine.choice import Choice
from dokimi_assert._prop.engine.value import Pairs
from dokimi_assert.conformance.prop.generator import build
from dokimi_assert.seat import Collector
from helpers import refusal

#: The generator of the digits.
DIGIT: dict[str, Any] = {"gen": "integer", "min": 0, "max": 9}


def decoded(spec: object, *choices: Choice | int) -> Any:
    """Return the value that the generator of spec decodes from choices.

    An int is an integer choice.
    """
    replayed = [c if isinstance(c, Choice) else Choice("integer", c) for c in choices]
    return build(spec).decode(Case(Replaying(replayed)))


class TestBuild:
    """build returns the generator of a JSON object."""

    tests: ClassVar[list[tuple[str, dict[str, Any], list[Choice | int], Any]]] = [
        ("returns an integer generator", DIGIT, [4], 4),
        (
            "returns a duration generator",
            {"gen": "duration", "min": 0, "max": 100},
            [50],
            50,
        ),
        (
            "returns a float generator of 64 bits",
            {"gen": "float", "min": 0, "max": 1},
            [Choice("float", 0.25)],
            0.25,
        ),
        (
            "returns a float generator of a width",
            {"gen": "float", "min": 0, "max": 1, "width": 32, "allow_nan": True},
            [Choice("float", 0.5)],
            0.5,
        ),
        (
            "returns a boolean generator of p",
            {"gen": "boolean", "p": [1, 4]},
            [1],
            True,
        ),
        ("returns a boolean generator without p", {"gen": "boolean"}, [0], False),
        (
            "returns the generator of one value",
            {"gen": "just", "value": {"type": "string", "value": "a"}},
            [],
            "a",
        ),
        (
            "returns the generator of one of the values",
            {
                "gen": "sampled-from",
                "values": [{"type": "int", "value": 1}, {"type": "int", "value": 2}],
            },
            [1],
            2,
        ),
        (
            "returns a string generator over the default alphabet",
            {"gen": "string", "max_size": 3},
            [Choice("sequence", (10, 11))],
            "ab",
        ),
        (
            "returns a string generator over an alphabet",
            {"gen": "string", "alphabet": "xy", "min_size": 1},
            [Choice("sequence", (1, 0))],
            "yx",
        ),
        (
            "returns the generator of the strings of a pattern",
            {"gen": "string-matching", "pattern": "ab"},
            [],
            "ab",
        ),
        (
            "returns a bytes generator",
            {"gen": "bytes", "max_size": 2},
            [Choice("sequence", (0, 255))],
            b"\x00\xff",
        ),
        (
            "returns the generator of the orderings of the values",
            {
                "gen": "permutation",
                "values": [{"type": "int", "value": 1}, {"type": "int", "value": 2}],
            },
            [1],
            [2, 1],
        ),
        (
            "returns a recursive generator whose extension refers to itself",
            {
                "gen": "recursive",
                "base": DIGIT,
                "extend": {"gen": "list", "of": {"gen": "self"}},
                "max_leaves": 2,
            },
            [1, 1, 0, 3, 0],
            [3],
        ),
        (
            "returns a recursive generator of 100 leaves without max_leaves",
            {
                "gen": "recursive",
                "base": DIGIT,
                "extend": {"gen": "optional", "of": DIGIT},
            },
            [0, 6],
            6,
        ),
        (
            "returns the generator of a value of one of the generators",
            {"gen": "one-of", "of": [DIGIT, {"gen": "boolean"}]},
            [1, 1],
            True,
        ),
        ("returns an optional generator", {"gen": "optional", "of": DIGIT}, [0], None),
        (
            "returns a list generator",
            {"gen": "list", "of": DIGIT, "unique": True, "max_size": None},
            [1, 3, 0],
            [3],
        ),
        (
            "returns a dict generator of Pairs",
            {"gen": "dict", "keys": DIGIT, "values": {"gen": "boolean"}},
            [1, 2, 1, 0],
            Pairs(((2, True),)),
        ),
        (
            "returns the generator of the values that a predicate keeps",
            {"gen": "filter", "of": DIGIT, "keep": {"kind": "at-least", "n": 5}},
            [7],
            7,
        ),
        (
            "returns the generator of the function of a subject kind",
            {"gen": "map", "of": {"gen": "list", "of": DIGIT}, "subject": "sorts"},
            [1, 5, 1, 2, 0],
            [2, 5],
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "give_choices", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_returns_the_generator(
        self,
        seat: Collector,
        give: dict[str, Any],
        give_choices: list[Choice | int],
        want: Any,
    ) -> None:
        """The generator decodes the value of its id from the choices."""
        check.equal(
            seat,
            decoded(give, *give_choices),
            want,
            "the generator decodes the value of its id",
        )

    refused: ClassVar[list[tuple[str, Any, str]]] = [
        ("raises for a value that is not an object", 5, "prop: 5 is not a generator"),
        (
            "raises for an id that does not exist",
            {"gen": "widget"},
            'prop: "widget" is not a generator',
        ),
        (
            "raises for an id that is not a string",
            {"gen": 1},
            "prop: 1 is not a generator",
        ),
        (
            "raises for an integer parameter that the object does not have",
            {"gen": "integer", "min": 0},
            'prop: "integer" needs max',
        ),
        (
            "raises for a bool parameter that is not a bool",
            {"gen": "list", "of": DIGIT, "unique": 1},
            "prop: unique is 1, not a bool",
        ),
        (
            "raises for a p that is not two numbers",
            {"gen": "boolean", "p": [1]},
            "prop: p is [1], not [numerator, denominator]",
        ),
        (
            "raises for a p that is not a list",
            {"gen": "boolean", "p": "half"},
            'prop: p is "half", not [numerator, denominator]',
        ),
        (
            "raises for a p above 1",
            {"gen": "boolean", "p": [3, 2]},
            "prop: p is [3, 2], not [numerator, denominator]",
        ),
        (
            "raises for a p of a zero denominator",
            {"gen": "boolean", "p": [0, 0]},
            "prop: p is [0, 0], not [numerator, denominator]",
        ),
        (
            "raises for a p of a numerator that is not an int",
            {"gen": "boolean", "p": [0.5, 1]},
            "prop: p is [0.5, 1], not [numerator, denominator]",
        ),
        (
            "raises for values that are not a list",
            {"gen": "sampled-from", "values": 1},
            "prop: values is 1, not a list",
        ),
        (
            "raises for an alphabet that is not a string",
            {"gen": "string", "alphabet": 1},
            "prop: alphabet is 1, not a string",
        ),
        (
            "raises for a pattern that is not a string",
            {"gen": "string-matching"},
            "prop: pattern is null, not a string",
        ),
        (
            "raises for a one-of without generators",
            {"gen": "one-of", "of": []},
            "prop: one-of needs a list of generators, not []",
        ),
        (
            "raises for a map of a subject without a function",
            {"gen": "map", "of": DIGIT, "subject": "triples"},
            'prop: the subject "triples" does not have a function',
        ),
        (
            "raises for a map of a subject that is not a string",
            {"gen": "map", "of": DIGIT, "subject": 3},
            "prop: the subject 3 does not have a function",
        ),
        (
            "raises for a self outside every extension",
            {"gen": "list", "of": {"gen": "self"}},
            "prop: self is outside the extension of a recursive generator",
        ),
        (
            "raises for a self in the base of a recursive generator",
            {"gen": "recursive", "base": {"gen": "self"}, "extend": DIGIT},
            "prop: self is outside the extension of a recursive generator",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refused], ids=[t[0] for t in refused]
    )
    def test_raises_for_an_object_that_is_not_a_generator(
        self, seat: Collector, give: Any, want: str
    ) -> None:
        """The error has the part at fault."""
        check.equal(
            seat, refusal(seat, lambda: build(give)), want, "build refuses the object"
        )
