# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of conformance/literal.py tests the typed literals of a corpus case.

A literal that the decoder cannot read stops the run, because an empty case
would pass without a check.
"""

from __future__ import annotations

import dataclasses
import enum
import math
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check, files
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.literal import (
    LiteralError,
    Objects,
    RefFloat,
    RefInt,
    RefStr,
    canonical,
    decode,
    same_json,
)
from dokimi_assert.option import by_identity, equate_nans

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


class Colour(enum.Enum):
    """An enum with one member."""

    RED = 1


@dataclasses.dataclass
class Point:
    """A dataclass with two fields."""

    b: int
    a: str


class TestDecode:
    """decode returns the value of one typed literal."""

    tests: ClassVar[list[tuple[str, dict[str, Any], Any]]] = [
        ("returns none for null", {"type": "null"}, None),
        ("returns the bool of a bool", {"type": "bool", "value": True}, True),
        ("returns the int of an int", {"type": "int", "value": 42}, 42),
        ("returns the float of a float", {"type": "float", "value": 1.5}, 1.5),
        ("returns the str of a string", {"type": "string", "value": "hi"}, "hi"),
        ("returns nan for the float NaN", {"type": "float", "value": "NaN"}, math.nan),
        (
            "returns infinity for the float Inf",
            {"type": "float", "value": "Inf"},
            math.inf,
        ),
        (
            "returns minus infinity for the float -Inf",
            {"type": "float", "value": "-Inf"},
            -math.inf,
        ),
        (
            "returns the float of a float with a JSON integer",
            {"type": "float", "value": 2},
            2.0,
        ),
        (
            "returns a list for a list of scalars",
            {"type": "list", "of": "int", "value": [1, 2]},
            [1, 2],
        ),
        (
            "returns none for a list whose value is null",
            {"type": "list", "of": "int", "value": None},
            None,
        ),
        (
            "returns a dict for a map of scalars",
            {"type": "map", "key": "string", "of": "int", "value": {"a": 1}},
            {"a": 1},
        ),
        (
            "returns none for a map whose value is null",
            {"type": "map", "key": "string", "of": "int", "value": None},
            None,
        ),
        (
            "returns the int of a decimal string",
            {"type": "int", "value": "-42"},
            -42,
        ),
        (
            "returns an int beyond 64 bits of a decimal string",
            {"type": "int", "value": "18446744073709551616"},
            2**64,
        ),
        (
            "returns the bytes of lowercase hexadecimal text",
            {"type": "bytes", "value": "00ff10"},
            b"\x00\xff\x10",
        ),
        ("returns empty bytes for the empty text", {"type": "bytes", "value": ""}, b""),
        (
            "returns the values of a list of bools",
            {"type": "list", "of": "bool", "value": [True]},
            [True],
        ),
        (
            "returns the values of a list of strings",
            {"type": "list", "of": "string", "value": ["a"]},
            ["a"],
        ),
        (
            "returns the values of a list of floats",
            {"type": "list", "of": "float", "value": [1.5, "Inf"]},
            [1.5, math.inf],
        ),
        (
            "returns the decoded items of a list of items",
            {
                "type": "list",
                "items": [
                    {"type": "int", "value": 1},
                    {"type": "string", "value": "a"},
                ],
            },
            [1, "a"],
        ),
        (
            "returns the decoded entries of a map of entries",
            {
                "type": "map",
                "entries": [
                    [{"type": "int", "value": 1}, {"type": "string", "value": "a"}]
                ],
            },
            {1: "a"},
        ),
        (
            "returns the tree of a tree literal",
            {"type": "tree", "entries": [{"path": "a.txt", "text": "a"}]},
            {"a.txt": files.text("a")},
        ),
    ]

    @pytest.mark.parametrize(("name", "give", "want"), tests, ids=[t[0] for t in tests])
    def test_returns_the_value_of_a_literal(
        self, seat: Collector, name: str, give: dict[str, Any], want: Any
    ) -> None:
        """Each literal decodes to its Python value."""
        check.equal(seat, decode(give), want, f"decode {name}", equate_nans())

    def test_returns_a_dataclass_of_the_fields_of_a_record(
        self, seat: Collector
    ) -> None:
        """A record decodes to a frozen dataclass with its fields in order."""
        value = decode(
            {
                "type": "record",
                "fields": [["b", {"type": "int", "value": 1}], ["a", {"type": "null"}]],
            }
        )
        check.equal(
            seat,
            [(f.name, getattr(value, f.name)) for f in dataclasses.fields(value)],
            [("b", 1), ("a", None)],
            "the record has its fields in order",
        )

    def test_returns_one_class_for_two_records_of_the_same_names(
        self, seat: Collector
    ) -> None:
        """Two records with the same names have one class, so they can be equal."""
        literal = {"type": "record", "fields": [["a", {"type": "int", "value": 1}]]}
        check.is_true(
            seat,
            type(decode(literal)) is type(decode(literal)),
            "the records have one class",
        )

    refusals: ClassVar[list[tuple[str, dict[str, Any], str]]] = [
        (
            "refuses a float name that the encoding does not define",
            {"type": "float", "value": "huge"},
            'the value "huge" is not a float',
        ),
        (
            "refuses a type that the encoding does not define",
            {"type": "decimal", "value": 1},
            "unknown literal type: decimal",
        ),
        (
            "refuses a list without an element type",
            {"type": "list", "value": []},
            'a list does not have the member "of"',
        ),
        (
            "refuses a list whose element type is not a scalar",
            {"type": "list", "of": "list", "value": []},
            'the member "of" of a list is not a scalar: "list"',
        ),
        (
            "refuses a list whose value is not an array",
            {"type": "list", "of": "int", "value": 1},
            "the value of a list is not an array",
        ),
        (
            "refuses a map without a key type",
            {"type": "map", "of": "int", "value": {}},
            'a map does not have the member "key"',
        ),
        (
            "refuses a map whose value is not an object",
            {"type": "map", "key": "string", "of": "int", "value": [1]},
            "the value of a map is not an object",
        ),
        (
            "refuses a map whose key type is not a scalar",
            {"type": "map", "key": "list", "of": "int", "value": {}},
            'the member "key" of a map is not a scalar: "list"',
        ),
        (
            "refuses an int with a bool value",
            {"type": "int", "value": True},
            "the value true is not an int",
        ),
        (
            "refuses an int whose text has a letter",
            {"type": "int", "value": "4x"},
            'the value "4x" is not an int',
        ),
        (
            "refuses a float with a bool value",
            {"type": "float", "value": True},
            "the value true is not a float",
        ),
        (
            "refuses a bool with the value 1",
            {"type": "bool", "value": 1},
            "the value 1 is not a bool",
        ),
        (
            "refuses a string with the value 1",
            {"type": "string", "value": 1},
            "the value 1 is not a string",
        ),
        (
            "refuses bytes in uppercase hexadecimal",
            {"type": "bytes", "value": "0A"},
            'the bytes value "0A" is not lowercase hexadecimal',
        ),
        (
            "refuses bytes without text",
            {"type": "bytes", "value": 1},
            "the bytes value 1 is not lowercase hexadecimal",
        ),
        (
            "refuses a list whose items are not an array",
            {"type": "list", "items": 1},
            "the items of a list are not an array",
        ),
        (
            "refuses a map whose entries are not an array",
            {"type": "map", "entries": 1},
            "the entries of a map are not an array",
        ),
        (
            "refuses a record whose fields are not an array",
            {"type": "record", "fields": 1},
            "the fields of a record are not an array",
        ),
        (
            "refuses a record whose field name is not an identifier",
            {"type": "record", "fields": [["a b", {"type": "null"}]]},
            "a field name of a record is not an identifier: ('a b',)",
        ),
        (
            "refuses a reference without an id",
            {"type": "reference", "value": {"type": "int", "value": 1}},
            "a reference does not have an id",
        ),
        (
            "refuses a reference of null",
            {"type": "reference", "id": "a", "value": {"type": "null"}},
            'a reference of {"type": "null"} does not have an object',
        ),
        (
            "refuses a reference of a bool",
            {"type": "reference", "id": "a", "value": {"type": "bool", "value": True}},
            'a reference of {"type": "bool", "value": true} does not have an object',
        ),
    ]

    @pytest.mark.parametrize(
        ("name", "give", "want"), refusals, ids=[t[0] for t in refusals]
    )
    def test_refuses_a_literal_that_it_cannot_decode(
        self, seat: Collector, name: str, give: dict[str, Any], want: str
    ) -> None:
        """The error has the reason and the value."""
        error = check.raises(seat, lambda: decode(give), f"decode {name}")
        check.is_true(
            seat, isinstance(error, LiteralError), "the error is a LiteralError"
        )
        check.equal(seat, str(error), want, "the error has the reason")

    def test_raises_the_fault_of_a_tree_literal_with_wrong_entries(
        self, seat: Collector
    ) -> None:
        """The fault is at the member of the literal."""
        literal = {"type": "tree", "entries": 1}
        error = check.raises(
            seat, lambda: decode(literal), "decode refuses the tree literal"
        )
        check.is_true(seat, isinstance(error, FaultError), "the error is a FaultError")
        want = "entries: the literal does not have a list of entries"
        check.equal(seat, str(error), want, "the fault has the member and the reason")


class TestObjectsDecode:
    """Objects.decode returns the value of a literal among the objects of one case."""

    def test_returns_one_object_for_each_reference_of_one_id(
        self, seat: Collector
    ) -> None:
        """The second reference of an id is the first object."""
        objects = Objects()
        literal = {
            "type": "reference",
            "id": "a",
            "value": {"type": "list", "of": "int", "value": [1]},
        }
        first = objects.decode(literal)
        check.equal(
            seat,
            objects.decode(literal),
            first,
            "the references are one object",
            by_identity(),
        )

    def test_returns_two_objects_for_two_ids(self, seat: Collector) -> None:
        """References of two ids are two objects of one value."""
        objects = Objects()
        value = {"type": "list", "of": "int", "value": [1]}
        a = objects.decode({"type": "reference", "id": "a", "value": value})
        b = objects.decode({"type": "reference", "id": "b", "value": value})
        check.not_equal(seat, a, b, "the references are two objects", by_identity())
        check.equal(seat, a, b, "the objects are equal")

    tests: ClassVar[list[tuple[str, dict[str, Any], type]]] = [
        (
            "returns a RefInt for a reference of an int",
            {"type": "int", "value": 1},
            RefInt,
        ),
        (
            "returns a RefFloat for a reference of a float",
            {"type": "float", "value": 1.5},
            RefFloat,
        ),
        (
            "returns a RefStr for a reference of a string",
            {"type": "string", "value": "a"},
            RefStr,
        ),
    ]

    @pytest.mark.parametrize(("name", "give", "want"), tests, ids=[t[0] for t in tests])
    def test_returns_an_object_of_a_subclass_for_a_scalar(
        self, seat: Collector, name: str, give: dict[str, Any], want: type
    ) -> None:
        """A scalar reference is an object of its own."""
        obj = Objects().decode({"type": "reference", "id": "a", "value": give})
        check.is_true(seat, type(obj) is want, f"Objects.decode {name}")
        check.equal(
            seat,
            canonical(obj),
            canonical(decode(give)),
            "the object has the text of its value",
        )


class TestCanonical:
    """canonical returns the canonical text of a value."""

    pairs: ClassVar[list[tuple[str, tuple[Any, Any], bool]]] = [
        (
            "returns different texts for an int and a float of its value",
            (1, 1.0),
            False,
        ),
        ("returns different texts for -0.0 and 0.0", (-0.0, 0.0), False),
        ("returns one text for two nans", (math.nan, -math.nan), True),
        (
            "returns one text for maps of equal entries in a different order",
            ({"a": 1, "b": 2}, {"b": 2, "a": 1}),
            True,
        ),
        ("returns the text of its value for a reference", (RefInt(1), 1), True),
        ("returns one text for a tuple and a list", ((1, 2), [1, 2]), True),
        ("returns one text for a bytearray and bytes", (bytearray(b"a"), b"a"), True),
    ]

    @pytest.mark.parametrize(("name", "give", "want"), pairs, ids=[t[0] for t in pairs])
    def test_compares_two_values_by_their_texts(
        self, seat: Collector, name: str, give: tuple[Any, Any], want: bool
    ) -> None:
        """Two values are equal when their texts are equal."""
        check.equal(
            seat, canonical(give[0]) == canonical(give[1]), want, f"canonical {name}"
        )

    texts: ClassVar[list[tuple[str, Any, str]]] = [
        ("returns null for none", None, "null"),
        ("returns the text of a bool", True, "bool:true"),
        ("returns the text of an int", -3, "int:-3"),
        ("returns the repr of a float", 0.1, "float:0.1"),
        (
            "returns the JSON text of a str",
            '\N{LATIN SMALL LETTER E WITH ACUTE}"',
            'string:"\N{LATIN SMALL LETTER E WITH ACUTE}\\""',
        ),
        ("returns the hexadecimal text of bytes", b"\x00\xff", "bytes:00ff"),
        ("returns the variant of a member of an enum", Colour.RED, "variant:RED"),
        (
            "returns the text of each field of a dataclass in order",
            Point(1, "x"),
            'record:["b"=int:1,"a"=string:"x"]',
        ),
        ("returns the empty text for the class of a dataclass", Point, ""),
        ("returns the empty text for an exception", ValueError("e"), ""),
        ("returns the empty text for a function", len, ""),
        ("returns the empty text for a set", {1}, ""),
    ]

    @pytest.mark.parametrize(("name", "give", "want"), texts, ids=[t[0] for t in texts])
    def test_returns_the_text_of_a_value(
        self, seat: Collector, name: str, give: Any, want: str
    ) -> None:
        """Each kind of value has its text."""
        check.equal(seat, canonical(give), want, f"canonical {name}")


class TestSameJson:
    """same_json reports whether two JSON values are the same value."""

    tests: ClassVar[list[tuple[str, tuple[Any, Any], bool]]] = [
        (
            "returns true for objects of the same members in a different order",
            ({"a": 1, "b": [True, None]}, {"b": [True, None], "a": 1}),
            True,
        ),
        ("returns false for arrays of different orders", ([1, 2], [2, 1]), False),
        (
            "returns false for objects with different members",
            ({"a": 1}, {"a": 2}),
            False,
        ),
        ("returns false for a string and a number of one text", ("1", 1), False),
    ]

    @pytest.mark.parametrize(("name", "give", "want"), tests, ids=[t[0] for t in tests])
    def test_compares_two_json_values(
        self, seat: Collector, name: str, give: tuple[Any, Any], want: bool
    ) -> None:
        """Two values are the same when their sorted texts are equal."""
        check.equal(seat, same_json(give[0], give[1]), want, f"same_json {name}")
