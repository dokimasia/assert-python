# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _record/literal.py tests the typed literal of a value in a call record.

A call record is a verdict of the conformance runner, so this spec checks its
verdicts with the assert statement of pytest.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Any, ClassVar, NamedTuple

import pytest

from dokimi_assert._record.literal import (
    VALUE_DEPTH,
    detail,
    encode,
    json,
    opaque,
    quoted,
)


class Colour(enum.Enum):
    """An enum of the spec."""

    RED = 1


@dataclass
class Point:
    """A dataclass of the spec."""

    x: int
    y: int


@dataclass
class Box:
    """A dataclass of the spec whose field takes any value."""

    value: object


class Pair(NamedTuple):
    """A NamedTuple of the spec."""

    left: str
    right: str


def nested(depth: int) -> Any:
    """Return a list nested depth levels deep around an int."""
    value: Any = 1
    for _ in range(depth):
        value = [value]
    return value


class TestValueDepth:
    """VALUE_DEPTH is the most levels of objects and arrays that a literal nests."""

    def test_contains_61(self) -> None:
        """A store entry takes three of the 64 levels of a file."""
        assert VALUE_DEPTH == 61


class TestEncode:
    """encode returns the typed literal of a value."""

    tests: ClassVar[list[tuple[str, Any, dict[str, Any]]]] = [
        ("encodes None as null", None, {"type": "null"}),
        ("encodes a bool", True, {"type": "bool", "value": True}),
        ("encodes an int", 7, {"type": "int", "value": 7}),
        (
            "encodes an int beyond 2^53 - 1 as its digits",
            2**53,
            {"type": "int", "value": "9007199254740992"},
        ),
        ("encodes a float", 1.5, {"type": "float", "value": 1.5}),
        ("encodes a NaN as its name", math.nan, {"type": "float", "value": "NaN"}),
        ("encodes infinity as its name", math.inf, {"type": "float", "value": "Inf"}),
        (
            "encodes minus infinity as its name",
            -math.inf,
            {"type": "float", "value": "-Inf"},
        ),
        ("encodes a str", "é", {"type": "string", "value": "é"}),
        (
            "encodes bytes in hexadecimal",
            b"\x00\xff",
            {"type": "bytes", "value": "00ff"},
        ),
        (
            "encodes a bytearray as bytes",
            bytearray(b"a"),
            {"type": "bytes", "value": "61"},
        ),
        (
            "encodes a member of an enum as a variant",
            Colour.RED,
            {"type": "variant", "name": "RED"},
        ),
        (
            "encodes a list of scalars of one type with of",
            [1, 2],
            {"type": "list", "of": "int", "value": [1, 2]},
        ),
        (
            "encodes a list of mixed values with items",
            [1, "a"],
            {
                "type": "list",
                "items": [
                    {"type": "int", "value": 1},
                    {"type": "string", "value": "a"},
                ],
            },
        ),
        ("encodes an empty list with items", [], {"type": "list", "items": []}),
        (
            "encodes a tuple as a list",
            (True,),
            {"type": "list", "of": "bool", "value": [True]},
        ),
        (
            "encodes a set in the order of the text of its items",
            {"b", "a"},
            {"type": "list", "of": "string", "value": ["a", "b"]},
        ),
        (
            "encodes a frozenset as a list",
            frozenset({2}),
            {"type": "list", "of": "int", "value": [2]},
        ),
        (
            "encodes a dict as a map of its entries in order",
            {"b": 1, "a": 2},
            {
                "type": "map",
                "entries": [
                    [{"type": "string", "value": "b"}, {"type": "int", "value": 1}],
                    [{"type": "string", "value": "a"}, {"type": "int", "value": 2}],
                ],
            },
        ),
        (
            "encodes a dataclass as a record of its fields in order",
            Point(1, 2),
            {
                "type": "record",
                "fields": [
                    ["x", {"type": "int", "value": 1}],
                    ["y", {"type": "int", "value": 2}],
                ],
            },
        ),
        (
            "encodes a named tuple as a record of its fields",
            Pair("a", "b"),
            {
                "type": "record",
                "fields": [
                    ["left", {"type": "string", "value": "a"}],
                    ["right", {"type": "string", "value": "b"}],
                ],
            },
        ),
    ]

    @pytest.mark.parametrize(("name", "give", "want"), tests, ids=[t[0] for t in tests])
    def test_encodes_a_value(self, name: str, give: Any, want: dict[str, Any]) -> None:
        """Each kind of value has its literal."""
        assert encode(give) == want, name

    unstated: ClassVar[list[tuple[str, Any]]] = [
        ("returns none for a str with a surrogate", "\udc80"),
        ("returns none for a function", len),
        ("returns none for a list that contains a function", [len]),
        ("returns none for a map whose key has no literal", {len: 1}),
        ("returns none for a map whose value has no literal", {1: len}),
        ("returns none for a record whose field has no literal", Box(len)),
        (
            "returns none for a set that contains a value without a literal",
            frozenset({len}),
        ),
        (
            "returns none for a value nested past the depth of a literal",
            nested(VALUE_DEPTH),
        ),
        ("returns none for a str of more parts than a walk visits", "a" * 70_000),
        ("returns none for bytes of more parts than a walk visits", b"a" * 70_000),
        ("returns none for a list of more elements than a walk visits", [0] * 70_000),
        (
            "returns none for a map of more entries than a walk visits",
            dict.fromkeys(range(40_000), 0),
        ),
    ]

    @pytest.mark.parametrize(("name", "give"), unstated, ids=[t[0] for t in unstated])
    def test_returns_none_for_a_value_without_a_literal(
        self, name: str, give: Any
    ) -> None:
        """A value outside the typed literals does not have one."""
        assert encode(give) is None, name

    def test_returns_none_for_a_record_whose_fields_pass_the_parts_of_a_walk(
        self,
    ) -> None:
        """The fields of a record count among the parts of a walk.

        The list, the str and its 65,532 bytes leave room for the record and
        for one part more, and the record has two fields.
        """
        assert encode(["a" * 65_532, Point(1, 2)]) is None

    def test_returns_none_for_a_record_whose_names_pass_the_parts_of_a_walk(
        self,
    ) -> None:
        """Each byte of the name of a field counts as a part of a walk.

        The record, its two fields, the name x and the value 1 fill the room
        that the 65,531 bytes leave, so the name y passes it.
        """
        assert encode(["a" * 65_531, Point(1, 2)]) is None

    def test_returns_none_for_the_class_of_a_dataclass(self) -> None:
        """The class of a dataclass is not a record."""
        assert encode(Point) is None

    def test_returns_the_literal_of_a_value_at_the_depth_of_a_literal(self) -> None:
        """A list nested up to the depth of a literal has its literal."""
        assert encode(nested(VALUE_DEPTH // 2 - 1)) is not None


class TestOpaque:
    """opaque returns the literal of a value without a typed literal."""

    def test_returns_the_text_of_the_value(self) -> None:
        """The literal contains the text that it receives."""
        assert opaque("<function>") == {"type": "opaque", "text": "<function>"}


class TestDetail:
    """detail returns the literal of a value of a detail."""

    def test_returns_the_typed_literal_of_a_value_that_has_one(self) -> None:
        """A value with a typed literal has that literal."""
        assert detail(3) == {"type": "int", "value": 3}

    def test_returns_the_opaque_literal_of_the_repr_otherwise(self) -> None:
        """A value without a typed literal has the opaque literal of its repr."""
        assert detail(len) == {"type": "opaque", "text": repr(len)}


class TestJson:
    """json returns the text of a JSON value on one line."""

    def test_writes_the_members_in_order_without_spaces(self) -> None:
        """The text keeps the order of the keys and does not have spaces."""
        assert json({"b": [1, "é"], "a": None}) == '{"b":[1,"é"],"a":null}'

    def test_writes_minus_zero_with_its_sign(self) -> None:
        """The text keeps the sign of a float."""
        assert json(-0.0) == "-0.0"

    def test_raises_for_a_float_that_is_not_finite(self) -> None:
        """JSON does not have NaN, so json refuses one."""
        with pytest.raises(ValueError, match="JSON"):
            json(math.nan)


class TestQuoted:
    """quoted returns the JSON text of a str for a message."""

    def test_keeps_the_form_of_every_character_but_a_lone_surrogate(self) -> None:
        """A message stays readable."""
        assert quoted('é"') == '"é\\""'

    def test_writes_a_lone_surrogate_as_its_escape(self) -> None:
        """The message is valid UTF-8 for any str."""
        assert quoted("a" + chr(0xD800)) == r'"a\ud800"'
