"""The spec of _prop/engine/literal.py tests the decoding and encoding of literals."""

from __future__ import annotations

import math
from typing import Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.literal import (
    LiteralError,
    decode,
    encode,
    integer,
    number,
    plain,
)
from dokimi_assert._prop.engine.value import Fields, Pairs, Variant, canonical
from dokimi_assert.seat import Collector
from helpers import refusal

#: The largest integer that every language decodes exactly from a JSON number.
SAFE = 2**53 - 1

INF = math.inf


class TestLiteralError:
    """LiteralError is the error of a literal that the encoding does not define."""

    def test_is_a_value_error(self, seat: Collector) -> None:
        """A caller that catches ValueError catches the error."""
        error = LiteralError("prop: 1 is not a typed literal")
        check.error_as(seat, error, ValueError, "the error is a ValueError")


class TestInteger:
    """integer returns the int of a JSON integer or of a decimal string."""

    def test_returns_a_safe_json_integer(self, seat: Collector) -> None:
        """A negative safe integer comes back unchanged."""
        check.equal(seat, integer(-3), -3, "the integer is -3")

    def test_returns_an_integer_above_2_to_the_53_less_1_from_a_decimal_string(
        self, seat: Collector
    ) -> None:
        """The decimal strings of both signs decode."""
        check.equal(
            seat,
            [integer(str(SAFE + 1)), integer(f"-{SAFE + 1}")],
            [SAFE + 1, -SAFE - 1],
            "both signs decode",
        )

    refusals: ClassVar[list[tuple[str, object, str]]] = [
        (
            "raises literal error for an unsafe json integer",
            SAFE + 1,
            f"prop: {SAFE + 1} is not a safe integer, so it must be a string",
        ),
        (
            "raises literal error for a safe integer in a string",
            "3",
            'prop: "3" is not a canonical large integer',
        ),
        (
            "raises literal error for a large integer with a leading zero",
            "09007199254740993",
            'prop: "09007199254740993" is not a canonical large integer',
        ),
        ("raises literal error for a bool", True, "prop: true is not an integer"),
        ("raises literal error for a float", 1.0, "prop: 1.0 is not an integer"),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_literal_error_for_a_value_that_is_not_an_integer(
        self, seat: Collector, give: object, want: str
    ) -> None:
        """The error has the value."""
        got = refusal(seat, lambda: integer(give), LiteralError)
        check.equal(seat, got, want, "the error has the reason")


class TestNumber:
    """number returns the float of a JSON number or of a name."""

    def test_returns_the_float_of_a_json_number_or_a_named_float(
        self, seat: Collector
    ) -> None:
        """1.5, an integer and the three names decode to floats."""
        got = [number(1.5), number(2), number("Inf"), number("-Inf")]
        check.equal(seat, got, [1.5, 2.0, INF, -INF], "the values decode to floats")
        check.equal(seat, type(got[1]), float, "an integer decodes to a float")
        check.is_true(seat, math.isnan(number("NaN")), "the name NaN decodes to NaN")

    def test_returns_the_infinity_of_its_sign_for_an_integer_outside_the_floats(
        self, seat: Collector
    ) -> None:
        """An integer of 401 digits decodes to an infinity."""
        check.equal(
            seat,
            [number(10**400), number(-(10**400))],
            [INF, -INF],
            "both signs decode to their infinity",
        )

    refusals: ClassVar[list[tuple[str, object, str]]] = [
        (
            "raises literal error for a name that the encoding does not define",
            "Infinity",
            'prop: "Infinity" is not a float',
        ),
        (
            "raises literal error for a value that is neither a number nor a name",
            True,
            "prop: true is not a float",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_literal_error_for_a_value_that_is_not_a_float(
        self, seat: Collector, give: object, want: str
    ) -> None:
        """The error has the value."""
        got = refusal(seat, lambda: number(give), LiteralError)
        check.equal(seat, got, want, "the error has the reason")


class TestPlain:
    """plain returns the JSON form of a scalar."""

    tests: ClassVar[list[tuple[str, object, object]]] = [
        ("returns a finite float unchanged", 1.5, 1.5),
        ("returns the name of nan", math.nan, "NaN"),
        ("returns the name of positive infinity", INF, "Inf"),
        ("returns the name of negative infinity", -INF, "-Inf"),
        ("returns a safe int unchanged", 7, 7),
        ("returns an unsafe int as a decimal string", -(2**60), str(-(2**60))),
        ("returns a bool unchanged", True, True),
        ("returns a string unchanged", "x", "x"),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_json_form(
        self, seat: Collector, give: object, want: object
    ) -> None:
        """The form is a value that JSON can represent."""
        check.equal(seat, plain(give), want, "the scalar has its JSON form")


class TestDecode:
    """decode returns the value of a typed literal."""

    tests: ClassVar[list[tuple[str, dict[str, Any], object]]] = [
        ("decodes null to none", {"type": "null"}, None),
        ("decodes a bool", {"type": "bool", "value": True}, True),
        ("decodes an int", {"type": "int", "value": -3}, -3),
        ("decodes a float", {"type": "float", "value": 1}, 1.0),
        ("decodes a named float", {"type": "float", "value": "-Inf"}, -INF),
        ("decodes a string", {"type": "string", "value": "x"}, "x"),
        (
            "decodes bytes from lowercase hexadecimal",
            {"type": "bytes", "value": "00ff"},
            b"\x00\xff",
        ),
        ("decodes empty bytes", {"type": "bytes", "value": ""}, b""),
        (
            "decodes a list of one scalar type",
            {"type": "list", "of": "int", "value": [1, 2]},
            [1, 2],
        ),
        (
            "decodes a list of items",
            {"type": "list", "items": [{"type": "int", "value": 1}, {"type": "null"}]},
            [1, None],
        ),
        (
            "decodes a map of entries",
            {
                "type": "map",
                "entries": [
                    [{"type": "int", "value": 2}, {"type": "bool", "value": True}]
                ],
            },
            Pairs(((2, True),)),
        ),
        (
            "decodes a map of string keys",
            {"type": "map", "key": "string", "of": "int", "value": {"a": 1}},
            Pairs((("a", 1),)),
        ),
        (
            "decodes a record with its fields in order",
            {
                "type": "record",
                "fields": [
                    ["id", {"type": "int", "value": 7}],
                    ["note", {"type": "null"}],
                ],
            },
            Fields((("id", 7), ("note", None))),
        ),
        (
            "decodes an absent list of a scalar type to none",
            {"type": "list", "of": "int", "value": None},
            None,
        ),
        (
            "decodes an absent map of a scalar type to none",
            {"type": "map", "key": "string", "of": "int", "value": None},
            None,
        ),
        (
            "decodes a reference to its value",
            {"type": "reference", "id": "a", "value": {"type": "int", "value": 1}},
            1,
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_decodes_the_value_of_a_literal(
        self, seat: Collector, give: dict[str, Any], want: object
    ) -> None:
        """An int and a float are distinct values."""
        check.equal(
            seat,
            canonical(decode(give)),
            canonical(want),
            "the literal decodes to the value",
        )

    def test_decodes_the_name_nan(self, seat: Collector) -> None:
        """The name NaN decodes to a float NaN."""
        got = decode({"type": "float", "value": "NaN"})
        check.is_true(
            seat, isinstance(got, float) and math.isnan(got), "the value is NaN"
        )

    def test_decodes_a_variant_without_a_payload_apart_from_one_with_a_null_payload(
        self, seat: Collector
    ) -> None:
        """A variant without a payload differs from one with a null payload."""
        bare = decode({"type": "variant", "name": "pending"})
        absent = decode(
            {"type": "variant", "name": "note", "payload": {"type": "null"}}
        )
        check.equal(
            seat,
            [canonical(bare), canonical(absent)],
            [canonical(Variant("pending")), canonical(Variant("note", None))],
            "the variants differ",
        )

    refusals: ClassVar[list[tuple[str, object]]] = [
        (
            "raises literal error for an absent list of an unknown type",
            {"type": "list", "of": "widget", "value": None},
        ),
        (
            "raises literal error for an absent list without a type",
            {"type": "list", "value": None},
        ),
        (
            "raises literal error for an absent map with integer keys",
            {"type": "map", "key": "int", "of": "int", "value": None},
        ),
        (
            "raises literal error for an absent map of an unknown type",
            {"type": "map", "key": "string", "of": "widget", "value": None},
        ),
        ("raises literal error for a json array", [1]),
        ("raises literal error for null", None),
        (
            "raises literal error for a safe int in a string",
            {"type": "int", "value": "3"},
        ),
        (
            "raises literal error for a bool as an int",
            {"type": "int", "value": True},
        ),
        (
            "raises literal error for an unsafe int as a json number",
            {"type": "int", "value": SAFE + 1},
        ),
        (
            "raises literal error for a large int with a leading zero",
            {"type": "int", "value": "09007199254740993"},
        ),
        (
            "raises literal error for a float named infinity",
            {"type": "float", "value": "Infinity"},
        ),
        (
            "raises literal error for a number as a bool",
            {"type": "bool", "value": 1},
        ),
        (
            "raises literal error for a number as a string",
            {"type": "string", "value": 1},
        ),
        (
            "raises literal error for bytes with a character outside hexadecimal",
            {"type": "bytes", "value": "0G"},
        ),
        (
            "raises literal error for bytes in uppercase",
            {"type": "bytes", "value": "FF"},
        ),
        (
            "raises literal error for a list with a value of another type",
            {"type": "list", "of": "int", "value": [1, "2"]},
        ),
        (
            "raises literal error for a list whose value is not a list",
            {"type": "list", "of": "int", "value": 1},
        ),
        (
            "raises literal error for a list whose items are not a list",
            {"type": "list", "items": 1},
        ),
        (
            "raises literal error for a map of integer keys as an object",
            {"type": "map", "key": "int", "of": "int", "value": {}},
        ),
        (
            "raises literal error for a map of string keys whose value is a list",
            {"type": "map", "key": "string", "of": "int", "value": []},
        ),
        (
            "raises literal error for a map whose entry is not a pair",
            {"type": "map", "entries": [[{"type": "null"}]]},
        ),
        (
            "raises literal error for a map whose entry is not a list",
            {"type": "map", "entries": [1]},
        ),
        (
            "raises literal error for a map whose entries are not a list",
            {"type": "map", "entries": 1},
        ),
        (
            "raises literal error for a set that the encoding does not define",
            {"type": "set", "value": []},
        ),
        (
            "raises literal error for a record whose fields are an object",
            {"type": "record", "fields": {"id": {"type": "int", "value": 1}}},
        ),
        (
            "raises literal error for a record field without a value",
            {"type": "record", "fields": [["id"]]},
        ),
        (
            "raises literal error for a record field without a name",
            {"type": "record", "fields": [["", {"type": "null"}]]},
        ),
        (
            "raises literal error for a record field whose name is not a string",
            {"type": "record", "fields": [[1, {"type": "null"}]]},
        ),
        (
            "raises literal error for a record that repeats a field name",
            {
                "type": "record",
                "fields": [["id", {"type": "null"}], ["id", {"type": "null"}]],
            },
        ),
        (
            "raises literal error for a record field of an int without a value",
            {"type": "record", "fields": [["id", {"type": "int"}]]},
        ),
        ("raises literal error for a variant without a name", {"type": "variant"}),
        (
            "raises literal error for a variant with an empty name",
            {"type": "variant", "name": ""},
        ),
        (
            "raises literal error for a variant whose payload is not a literal",
            {"type": "variant", "name": "x", "payload": 1},
        ),
        (
            "raises literal error for a reference without an id",
            {"type": "reference", "value": {"type": "int", "value": 1}},
        ),
        (
            "raises literal error for a reference with an empty id",
            {"type": "reference", "id": "", "value": {"type": "int", "value": 1}},
        ),
        (
            "raises literal error for a reference whose id is not a string",
            {"type": "reference", "id": 1, "value": {"type": "int", "value": 1}},
        ),
        (
            "raises literal error for a reference to null",
            {"type": "reference", "id": "a", "value": {"type": "null"}},
        ),
        (
            "raises literal error for a reference whose value is not a literal",
            {"type": "reference", "id": "a", "value": 1},
        ),
    ]

    @pytest.mark.parametrize(
        "give", [t[1] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_literal_error_for_a_literal_that_the_encoding_does_not_define(
        self, seat: Collector, give: object
    ) -> None:
        """Decoding the literal raises LiteralError."""
        refusal(seat, lambda: decode(give), LiteralError)


class TestEncode:
    """encode returns the canonical typed literal of a decoded value."""

    tests: ClassVar[list[tuple[str, object, dict[str, Any]]]] = [
        (
            "encodes the of form for a list of one scalar type",
            [7, 3],
            {"type": "list", "of": "int", "value": [7, 3]},
        ),
        ("encodes items for an empty list", [], {"type": "list", "items": []}),
        (
            "encodes items for a list of mixed types",
            [1, [2]],
            {
                "type": "list",
                "items": [
                    {"type": "int", "value": 1},
                    {"type": "list", "of": "int", "value": [2]},
                ],
            },
        ),
        (
            "encodes items for a list of bools and ints",
            [True, 1],
            {
                "type": "list",
                "items": [{"type": "bool", "value": True}, {"type": "int", "value": 1}],
            },
        ),
        ("encodes the name of nan", math.nan, {"type": "float", "value": "NaN"}),
        (
            "encodes the name of negative infinity",
            -INF,
            {"type": "float", "value": "-Inf"},
        ),
        (
            "encodes an unsafe int as a decimal string",
            SAFE + 1,
            {"type": "int", "value": str(SAFE + 1)},
        ),
        (
            "encodes a list of unsafe ints as decimal strings",
            [SAFE + 1],
            {"type": "list", "of": "int", "value": [str(SAFE + 1)]},
        ),
        (
            "encodes lowercase hexadecimal for bytes",
            b"\x01\xab",
            {"type": "bytes", "value": "01ab"},
        ),
        (
            "encodes entries in order for a map",
            Pairs(((1, "a"),)),
            {
                "type": "map",
                "entries": [
                    [{"type": "int", "value": 1}, {"type": "string", "value": "a"}]
                ],
            },
        ),
        (
            "encodes fields in order for a record",
            Fields((("id", 1),)),
            {"type": "record", "fields": [["id", {"type": "int", "value": 1}]]},
        ),
        (
            "omits the payload of a variant without one",
            Variant("pending"),
            {"type": "variant", "name": "pending"},
        ),
        (
            "encodes a null payload for a variant with an absent one",
            Variant("note", None),
            {"type": "variant", "name": "note", "payload": {"type": "null"}},
        ),
        ("encodes null for none", None, {"type": "null"}),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_encodes_the_canonical_literal_of_a_value(
        self, seat: Collector, give: object, want: dict[str, Any]
    ) -> None:
        """Each value has one literal."""
        check.equal(seat, encode(give), want, "the value has its canonical literal")

    def test_encodes_every_value_to_a_literal_that_decodes_to_the_same_value(
        self, seat: Collector
    ) -> None:
        """Decoding the literal of each value returns the value."""
        values: list[object] = [
            None,
            False,
            -0.0,
            math.nan,
            2**64 - 1,
            "",
            b"",
            [],
            [[], [1.5]],
            Pairs(((None, [b"x"]),)),
            Fields((("a", [Fields(())]), ("b", Variant("v", Variant("w"))))),
            [Variant("x"), Variant("x", None)],
        ]
        check.equal(
            seat,
            [canonical(decode(encode(value))) for value in values],
            [canonical(value) for value in values],
            "each literal decodes to its value",
        )

    refusals: ClassVar[list[tuple[str, object]]] = [
        ("raises type error for an object", object()),
        ("raises type error for a tuple", (1, 2)),
    ]

    @pytest.mark.parametrize(
        "give", [t[1] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_type_error_for_a_value_that_no_generator_decodes(
        self, seat: Collector, give: object
    ) -> None:
        """The encoding does not have a literal for the value."""
        got = refusal(seat, lambda: encode(give), TypeError)
        check.equal(
            seat,
            got,
            f"prop: {canonical(give)} is not a decoded value",
            "the error has the reason",
        )
