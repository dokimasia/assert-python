"""The spec of conformance/prop/predicate.py tests the predicates of the vectors."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.value import Pairs
from dokimi_assert.conformance.prop.predicate import predicate
from dokimi_assert.seat import Collector
from helpers import refusal


def literal(kind: str, value: object) -> dict[str, Any]:
    """Return the typed literal of value of the scalar type kind."""
    return {"type": kind, "value": value}


class TestPredicate:
    """predicate returns the predicate of a JSON object."""

    tests: ClassVar[list[tuple[str, dict[str, Any], Any, bool]]] = [
        ("returns True under always", {"kind": "always"}, None, True),
        ("returns False under never", {"kind": "never"}, 1, False),
        (
            "returns True for a value equal to the literal",
            {"kind": "equals", "value": literal("int", 7)},
            7,
            True,
        ),
        (
            "returns False for a float equal in value to an int literal",
            {"kind": "equals", "value": literal("int", 7)},
            7.0,
            False,
        ),
        (
            "returns True at the bound of at-least",
            {"kind": "at-least", "n": 3},
            3,
            True,
        ),
        (
            "returns False below a float bound of at-least",
            {"kind": "at-least", "n": 2.5},
            2,
            False,
        ),
        (
            "returns False for a bool under at-least",
            {"kind": "at-least", "n": 0},
            True,
            False,
        ),
        ("returns True for a multiple", {"kind": "divisible-by", "n": 4}, 8, True),
        (
            "returns False for a float multiple",
            {"kind": "divisible-by", "n": 4},
            8.0,
            False,
        ),
        (
            "returns True for a sum above n",
            {"kind": "sum-above", "n": 2},
            [1, 2, "a"],
            True,
        ),
        ("returns False for a sum at n", {"kind": "sum-above", "n": 3}, [1, 2], False),
        (
            "returns False for a value that is not a list",
            {"kind": "sum-above", "n": 0},
            5,
            False,
        ),
        (
            "counts the entries of a dict",
            {"kind": "length-at-least", "n": 1},
            Pairs(((1, 2),)),
            True,
        ),
        (
            "counts the code points of a string",
            {"kind": "length-at-least", "n": 2},
            "é",
            False,
        ),
        ("counts the bytes of bytes", {"kind": "length-at-least", "n": 2}, b"ab", True),
        ("returns False for an integer", {"kind": "length-at-least", "n": 0}, 5, False),
        (
            "finds an equal element of a list",
            {"kind": "contains", "value": literal("int", 1)},
            [0, 1],
            True,
        ),
        (
            "finds a text inside a string",
            {"kind": "contains", "value": literal("string", "b")},
            "abc",
            True,
        ),
        (
            "finds bytes inside bytes",
            {"kind": "contains", "value": {"type": "bytes", "value": "62"}},
            b"abc",
            True,
        ),
        (
            "returns False for a text inside bytes",
            {"kind": "contains", "value": literal("string", "b")},
            b"abc",
            False,
        ),
        ("returns True for a list out of order", {"kind": "not-sorted"}, [1, 0], True),
        (
            "returns False for a list in order",
            {"kind": "not-sorted"},
            ["a", "b"],
            False,
        ),
        (
            "returns False for a string under not-sorted",
            {"kind": "not-sorted"},
            "ba",
            False,
        ),
        (
            "returns True for two equal elements",
            {"kind": "has-duplicate"},
            [2, 2],
            True,
        ),
        (
            "returns False for distinct elements",
            {"kind": "has-duplicate"},
            [1, 1.0],
            False,
        ),
        (
            "returns False for a string under has-duplicate",
            {"kind": "has-duplicate"},
            "aa",
            False,
        ),
        (
            "returns True for an index of a number above n",
            {"kind": "indexed-above", "n": 4},
            [9, 1, 0],
            True,
        ),
        (
            "returns False for an index of a number at n",
            {"kind": "indexed-above", "n": 9},
            [9, 0],
            False,
        ),
        (
            "returns False for an index past the elements",
            {"kind": "indexed-above", "n": 0},
            [9, 1],
            False,
        ),
        (
            "returns False for an index that is a bool",
            {"kind": "indexed-above", "n": 0},
            [9, True],
            False,
        ),
        (
            "returns False for an element that is not a number",
            {"kind": "indexed-above", "n": 0},
            ["a", 0],
            False,
        ),
        (
            "returns False for an empty list",
            {"kind": "indexed-above", "n": 0},
            [],
            False,
        ),
        (
            "returns False for a value that is not a list",
            {"kind": "indexed-above", "n": 0},
            3,
            False,
        ),
        ("negates a predicate with not", {"kind": "always", "not": True}, None, False),
    ]

    @pytest.mark.parametrize(
        ("give_spec", "give", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_returns_the_predicate(
        self, seat: Collector, give_spec: dict[str, Any], give: Any, want: bool
    ) -> None:
        """The predicate is true exactly for the values of its kind."""
        check.equal(
            seat,
            predicate(give_spec)(give),
            want,
            "the predicate is true exactly for the values of its kind",
        )

    refused: ClassVar[list[tuple[str, Any, str]]] = [
        (
            "raises for a value that is not an object",
            [1],
            "prop: [1] is not a predicate",
        ),
        (
            "raises for a kind that does not exist",
            {"kind": "widget"},
            'prop: "widget" is not a kind of predicate',
        ),
        (
            "raises for a kind that is not a string",
            {"kind": 1},
            "prop: 1 is not a kind of predicate",
        ),
        (
            "raises for a parameter that is not an integer",
            {"kind": "divisible-by", "n": "two"},
            'prop: "two" is not an integer',
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refused], ids=[t[0] for t in refused]
    )
    def test_raises_for_an_object_that_is_not_a_predicate(
        self, seat: Collector, give: Any, want: str
    ) -> None:
        """The error has the part at fault."""
        check.equal(
            seat,
            refusal(seat, lambda: predicate(give)),
            want,
            "predicate refuses the object",
        )
