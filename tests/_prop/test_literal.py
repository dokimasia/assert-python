# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/literal.py tests the typed literal of a drawn value."""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.choice import FloatBounds, IntegerBounds, SequenceBounds
from dokimi_assert._prop.engine.collection import Sizes
from dokimi_assert._prop.engine.generator import (
    Bool,
    Bytes,
    Dict,
    Filter,
    Float,
    Integer,
    List,
    Mapped,
    Optional,
    Text,
)
from dokimi_assert._prop.engine.shape import read
from dokimi_assert._prop.engine.value import Fields, Pairs, Variant
from dokimi_assert._prop.literal import drawn_literal
from helpers import Picked

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

#: The generator of the integers 0 to 9.
DIGIT = Integer(IntegerBounds(0, 9))

#: The generator of a fair boolean.
BOOLEAN = Bool(Fraction(1, 2))

#: The shape of a signed 64-bit integer.
INT64 = {"shape": "int", "width": 64, "signed": True}


def refused(value: int) -> int:
    """Raise TypeError, as an inverse does for a value that the map does not return."""
    msg = f"{value} is not a value of the map"
    raise TypeError(msg)


class TestDrawnLiteral:
    """drawn_literal returns the literal of a value in the type of its generator."""

    tests: ClassVar[list[tuple[str, object, object, dict[str, Any] | None]]] = [
        (
            "returns the int of a number that integer drew",
            DIGIT,
            3,
            {"type": "int", "value": 3},
        ),
        (
            "returns the float of an integral number that float drew",
            Float(FloatBounds(0.0, 9.0)),
            3.0,
            {"type": "float", "value": 3.0},
        ),
        (
            "returns the literal of its own type for a map without an inverse",
            Mapped(DIGIT, lambda x: x * 2),
            6,
            {"type": "int", "value": 6},
        ),
        (
            "returns the literal of its own type for a map whose inverse raises",
            Mapped(DIGIT, lambda x: x, refused),
            4,
            {"type": "int", "value": 4},
        ),
        (
            "returns the literal of the value that the inverse of a map returns",
            Mapped(DIGIT, str, int),
            "4",
            {"type": "int", "value": 4},
        ),
        (
            "returns the literal of a filtered value through the filtered generator",
            Filter(DIGIT, lambda x: x % 2 == 0),
            4,
            {"type": "int", "value": 4},
        ),
        (
            "returns the literal of the generator that a deferred generator picks",
            Picked(Mapped(DIGIT, str, int)),
            "4",
            {"type": "int", "value": 4},
        ),
        (
            "returns null for an absent optional value",
            Optional(BOOLEAN),
            None,
            {"type": "null"},
        ),
        (
            "returns the literal of a present optional value",
            Optional(BOOLEAN),
            True,
            {"type": "bool", "value": True},
        ),
        (
            "returns a list of one scalar type",
            List(DIGIT, Sizes()),
            [1, 2],
            {"type": "list", "of": "int", "value": [1, 2]},
        ),
        (
            "returns a list of item literals for elements that are not scalars",
            List(List(BOOLEAN, Sizes()), Sizes()),
            [[True]],
            {
                "type": "list",
                "items": [{"type": "list", "of": "bool", "value": [True]}],
            },
        ),
        (
            "returns an empty list as items",
            List(BOOLEAN, Sizes()),
            [],
            {"type": "list", "items": []},
        ),
        (
            "returns none for a list with an element without a literal",
            List(Mapped(DIGIT, lambda _: object()), Sizes()),
            [object()],
            None,
        ),
        (
            "returns the literal of a string that a list generator receives",
            List(BOOLEAN, Sizes()),
            "x",
            {"type": "string", "value": "x"},
        ),
        (
            "returns the entries of a map through the generators of the dict",
            Dict(DIGIT, BOOLEAN, Sizes()),
            Pairs(((1, True),)),
            {
                "type": "map",
                "entries": [
                    [{"type": "int", "value": 1}, {"type": "bool", "value": True}]
                ],
            },
        ),
        (
            "returns none for a map with a value without a literal",
            Dict(DIGIT, Mapped(DIGIT, lambda _: object()), Sizes()),
            Pairs(((1, object()),)),
            None,
        ),
        (
            "returns the literal of an int that a dict generator receives",
            Dict(DIGIT, DIGIT, Sizes()),
            1,
            {"type": "int", "value": 1},
        ),
        (
            "returns the bytes of a byte string",
            Bytes(SequenceBounds(256)),
            bytes([1, 255]),
            {"type": "bytes", "value": "01ff"},
        ),
        (
            "returns the string of a text generator",
            Text(None, SequenceBounds(10)),
            "ab",
            {"type": "string", "value": "ab"},
        ),
        (
            "returns the literal of a string that an integer generator receives",
            DIGIT,
            "3",
            {"type": "string", "value": "3"},
        ),
        (
            "returns none for a decoded record with a field without a literal",
            DIGIT,
            Fields((("f", object()),)),
            None,
        ),
        (
            "returns the literal of a decoded variant of a different generator",
            DIGIT,
            Variant("v"),
            {"type": "variant", "name": "v"},
        ),
        (
            "returns the entries of a map shape through the shapes of its entries",
            read({"shape": "map", "key": {"shape": "string"}, "of": {"shape": "bool"}}),
            Pairs((("k", True),)),
            {
                "type": "map",
                "entries": [
                    [{"type": "string", "value": "k"}, {"type": "bool", "value": True}]
                ],
            },
        ),
        (
            "returns the record of the fields of a record shape",
            read(
                {
                    "shape": "record",
                    "fields": [["id", INT64], ["ok", {"shape": "bool"}]],
                }
            ),
            Fields((("id", 7), ("ok", False))),
            {
                "type": "record",
                "fields": [
                    ["id", {"type": "int", "value": 7}],
                    ["ok", {"type": "bool", "value": False}],
                ],
            },
        ),
        (
            "returns none for a record shape with a field without a literal",
            read({"shape": "record", "fields": [["id", INT64]]}),
            Fields((("id", object()),)),
            None,
        ),
        (
            "returns the literal of a bool that a record shape receives",
            read({"shape": "record", "fields": [["id", {"shape": "bool"}]]}),
            True,
            {"type": "bool", "value": True},
        ),
        (
            "returns the variant of an enum shape with its payload",
            read({"shape": "enum", "variants": [["none", None], ["some", INT64]]}),
            Variant("some", 3),
            {"type": "variant", "name": "some", "payload": {"type": "int", "value": 3}},
        ),
        (
            "returns the variant of an enum shape without a payload",
            read({"shape": "enum", "variants": [["none", None]]}),
            Variant("none"),
            {"type": "variant", "name": "none"},
        ),
        (
            "returns none for a variant with a payload without a literal",
            read({"shape": "enum", "variants": [["some", {"shape": "bool"}]]}),
            Variant("some", object()),
            None,
        ),
        (
            "returns the literal of a string that an enum shape receives",
            read({"shape": "enum", "variants": [["none", None]]}),
            "none",
            {"type": "string", "value": "none"},
        ),
        (
            "returns the literal of a recursive shape through its definition",
            read(
                {
                    "shape": "ref",
                    "name": "Tree",
                    "definitions": {
                        "Tree": {
                            "shape": "list",
                            "of": {"shape": "ref", "name": "Tree"},
                        }
                    },
                }
            ),
            [[]],
            {"type": "list", "items": [{"type": "list", "items": []}]},
        ),
        (
            "returns the int of a 128-bit integer",
            read({"shape": "int", "width": 128, "signed": True}),
            2**100,
            {"type": "int", "value": str(2**100)},
        ),
        (
            "returns the bytes of an ip address",
            read({"shape": "ip-address"}),
            bytes([127, 0, 0, 1]),
            {"type": "bytes", "value": "7f000001"},
        ),
    ]

    @pytest.mark.parametrize(
        ("generator", "value", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_returns_the_literal(
        self,
        seat: Collector,
        generator: object,
        value: object,
        want: dict[str, Any] | None,
    ) -> None:
        """Each draw has its literal."""
        check.equal(
            seat,
            drawn_literal(generator, value),
            want,
            "drawn_literal returns the literal",
        )
