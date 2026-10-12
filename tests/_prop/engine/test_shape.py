"""The spec of _prop/engine/shape.py tests what each shape decodes and how read fails.

The expected values are the values that the reference implementation of the
definition decodes from the same choices.
"""

from __future__ import annotations

import calendar
import math
import threading
from typing import Any, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.case import (
    Case,
    Generating,
    Provider,
    Replaying,
    Request,
)
from dokimi_assert._prop.engine.choice import (
    INT64_MAX,
    UINT64_MAX,
    Choice,
    IntegerBounds,
    Value,
)
from dokimi_assert._prop.engine.generator import Generator, Integer, Just
from dokimi_assert._prop.engine.shape import (
    Root,
    ShapeError,
    halves,
    read,
    second_part,
)
from dokimi_assert._prop.engine.source import case_source
from dokimi_assert._prop.engine.value import Fields, Pairs, Variant, canonical
from dokimi_assert._prop.engine.zone import ZONES
from dokimi_assert.seat import Collector
from helpers import integers, refusal

#: The number of nodes that one value of a recursive shape can use.
BUDGET = 100

#: The seconds that a thread of a case waits on a signal of the other.
WAIT = 10.0

INF = math.inf

INT8 = {"shape": "int", "width": 8, "signed": True}
UINT8 = {"shape": "int", "width": 8, "signed": False}

#: A tree shape. A tree is a record of a value and a list of child trees.
TREE = {
    "shape": "ref",
    "name": "tree",
    "definitions": {
        "tree": {
            "shape": "record",
            "fields": [
                ["value", UINT8],
                ["children", {"shape": "list", "of": {"shape": "ref", "name": "tree"}}],
            ],
        }
    },
}

#: The first offset change of Europe/Amsterdam.
CHANGE = ZONES[1].changes[0]

#: The text of a definition without a finite value, after its name.
ENDLESS = (
    "does not have a finite value, because it refers to itself without passing "
    "through an optional, a list, a set, a map or an enum that can exit"
)


def choice_of(value: Value) -> Choice:
    """Return a recorded choice of the kind of a value."""
    if isinstance(value, tuple):
        return Choice("sequence", value)
    if isinstance(value, float):
        return Choice("float", value)
    return Choice("integer", value)


def decoded_from(shape: object, *values: Value) -> tuple[Any, Case]:
    """Return the value that a shape decodes from recorded values, and the case."""
    c = Case(Replaying([choice_of(value) for value in values]))
    return read(shape).decode(c), c


def canonical_of(shape: object, *values: Value) -> str:
    """Return the canonical value that a shape decodes from recorded values."""
    return canonical(decoded_from(shape, *values)[0])


def seconds(year: int, month: int, day: int) -> int:
    """Return the seconds since 1970-01-01T00:00:00Z of a UTC midnight."""
    return calendar.timegm((year, month, day, 0, 0, 0))


def instant(at: int, units: int) -> Fields:
    """Return the record of an instant."""
    return Fields((("seconds", at), ("units", units)))


def local(day: int, time: int) -> Fields:
    """Return the record of a local date and time."""
    return Fields((("date", day), ("time-of-day", time)))


def nodes(value: Any) -> int:
    """Return the number of nodes of a tree value."""
    children = cast("list[Any]", cast("Fields", value).fields[1][1])
    return 1 + sum(nodes(child) for child in children)


class TestShapeError:
    """ShapeError is the error that read raises for an invalid shape file."""

    def test_is_a_value_error(self, seat: Collector) -> None:
        """A caller that catches ValueError catches the error."""
        error = ShapeError("prop: [] is not a shape")
        check.error_as(seat, error, ValueError, "the error is a ValueError")


class TestHalves:
    """halves returns the high and the low 64 bits of a 128-bit integer."""

    def test_returns_the_high_and_the_low_64_bits_of_a_128_bit_integer(
        self, seat: Collector
    ) -> None:
        """2**64 + 3 and -1 split into their halves."""
        check.equal(
            seat,
            [halves(2**64 + 3), halves(-1)],
            [(1, 3), (-1, UINT64_MAX)],
            "each integer splits into its halves",
        )


class TestSecondPart:
    """second_part returns the bounds of the second choice of a shape of two choices."""

    tests: ClassVar[list[tuple[str, int, IntegerBounds]]] = [
        (
            "returns the whole range between the bounds",
            5,
            IntegerBounds(0, UINT64_MAX),
        ),
        (
            "returns the second part of the lower bound at its first part",
            1,
            IntegerBounds(10, UINT64_MAX),
        ),
        (
            "returns the second part of the upper bound at its first part",
            9,
            IntegerBounds(0, 20),
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_bounds_of_the_second_choice(
        self, seat: Collector, give: int, want: IntegerBounds
    ) -> None:
        """The lower bound is 1,10, and the upper bound is 9,20."""
        got = second_part(give, (1, 10), (9, 20), UINT64_MAX)
        check.equal(seat, got, want, "the second choice has the bounds")


class TestRead:
    """read returns the generator of a shape file."""

    def test_reads_a_shape_without_recursion_as_the_generator_that_it_maps_to(
        self, seat: Collector
    ) -> None:
        """An int shape reads as Integer, and a recursive shape reads as Root."""
        check.equal(
            seat,
            [isinstance(read(INT8), Integer), isinstance(read(TREE), Root)],
            [True, True],
            "each shape reads as its generator",
        )

    def test_reads_a_bool_as_a_boolean(self, seat: Collector) -> None:
        """The choice 1 decodes to True, and the target decodes to False."""
        shape = {"shape": "bool"}
        check.equal(
            seat,
            [decoded_from(shape, 1)[0], decoded_from(shape)[0]],
            [True, False],
            "1 decodes to True and the target to False",
        )

    def test_reads_an_int_over_its_width(self, seat: Collector) -> None:
        """The ends of a byte decode, and a value outside decodes to the target."""
        check.equal(
            seat,
            [
                decoded_from(INT8, -128)[0],
                decoded_from(INT8, 128)[0],
                decoded_from(UINT8, 255)[0],
                decoded_from(UINT8, -1)[0],
            ],
            [-128, 0, 255, 0],
            "each byte decodes inside its width",
        )

    def test_reads_the_bounds_of_an_int_from_its_min_and_max(
        self, seat: Collector
    ) -> None:
        """99 decodes, and 100 replays as the target 1."""
        bounded = {**INT8, "min": 1, "max": 99}
        check.equal(
            seat,
            [decoded_from(bounded, 99)[0], decoded_from(bounded, 100)[0]],
            [99, 1],
            "99 decodes to itself and 100 to the target",
        )

    def test_reads_a_float_without_the_infinities_unless_they_are_allowed(
        self, seat: Collector
    ) -> None:
        """Infinity decodes to itself only with allow_infinity."""
        finite = {"shape": "float", "width": 64}
        check.equal(
            seat,
            [
                decoded_from(finite, INF)[0],
                decoded_from({**finite, "allow_infinity": True}, INF)[0],
            ],
            [0.0, INF],
            "infinity decodes only where the shape allows it",
        )

    def test_reads_a_float_of_width_32_as_a_binary32_value(
        self, seat: Collector
    ) -> None:
        """0.1 is not a binary32 value."""
        narrow = {"shape": "float", "width": 32}
        check.equal(
            seat,
            [decoded_from(narrow, 0.1)[0], decoded_from(narrow, 0.5)[0]],
            [0.0, 0.5],
            "0.1 decodes to the target and 0.5 to itself",
        )

    def test_reads_a_float_between_its_min_and_max(self, seat: Collector) -> None:
        """NaN decodes when allow_nan is true."""
        bounded = {
            "shape": "float",
            "width": 64,
            "min": -2,
            "max": "Inf",
            "allow_infinity": True,
            "allow_nan": True,
        }
        got = decoded_from(bounded, math.nan)[0]
        check.is_true(seat, math.isnan(got), "NaN decodes")

    def test_reads_a_char_as_one_character_of_its_alphabet(
        self, seat: Collector
    ) -> None:
        """Index 10 of the default alphabet is a, and index 2 of xyz is z."""
        check.equal(
            seat,
            [
                decoded_from({"shape": "char"}, (10,))[0],
                decoded_from({"shape": "char", "alphabet": "xyz"}, (2,))[0],
            ],
            ["a", "z"],
            "the indices decode to a and z",
        )

    def test_reads_a_string_as_a_sequence_of_indices(self, seat: Collector) -> None:
        """The replay pads the sequence with zeros, and a|b decodes b from 1."""
        sized = {"shape": "string", "min_size": 2, "max_size": 3}
        check.equal(
            seat,
            [
                decoded_from(sized, (1,))[0],
                decoded_from({"shape": "string", "pattern": "a|b"}, 1)[0],
            ],
            ["10", "b"],
            "the strings are 10 and b",
        )

    def test_reads_bytes_as_a_sequence_of_byte_values(self, seat: Collector) -> None:
        """The sequence of 0 and 255 decodes to two bytes."""
        got = decoded_from({"shape": "bytes"}, (0, 255))[0]
        check.equal(seat, got, b"\x00\xff", "the bytes are 0 and 255")

    def test_reads_a_list_or_a_fixed_list_as_a_collection(
        self, seat: Collector
    ) -> None:
        """Both lists decode their flags and their elements."""
        check.equal(
            seat,
            [
                decoded_from({"shape": "list", "of": UINT8}, 1, 7, 1, 8, 0)[0],
                decoded_from(
                    {"shape": "fixed-list", "of": UINT8, "size": 2}, 1, 7, 1, 8, 0
                )[0],
            ],
            [[7, 8], [7, 8]],
            "both lists are [7, 8]",
        )

    def test_reads_a_set_that_discards_a_repeated_element(
        self, seat: Collector
    ) -> None:
        """The set discards the second 7."""
        got = decoded_from({"shape": "set", "of": UINT8}, 1, 7, 1, 7, 0)[0]
        check.equal(seat, got, [7], "the set is [7]")

    def test_reads_a_map_as_a_dict(self, seat: Collector) -> None:
        """The map has one entry."""
        shape = {"shape": "map", "key": UINT8, "of": {"shape": "bool"}}
        check.equal(
            seat,
            canonical_of(shape, 1, 3, 1, 0),
            canonical(Pairs(((3, True),))),
            "the map maps 3 to True",
        )

    def test_reads_a_literal_as_one_of_its_values(self, seat: Collector) -> None:
        """Index 1 chooses the second value."""
        values = [{"type": "string", "value": v} for v in ("paid", "shipped")]
        got = decoded_from({"shape": "literal", "values": values}, 1)[0]
        check.equal(seat, got, "shipped", "the value is shipped")

    def test_reads_a_uuid_as_16_bytes(self, seat: Collector) -> None:
        """The sequence of 0 to 15 decodes to 16 bytes."""
        sixteen = tuple(range(16))
        got = decoded_from({"shape": "uuid"}, sixteen)[0]
        check.equal(seat, got, bytes(sixteen), "the uuid has the 16 bytes")

    def test_reads_an_address_of_one_version_as_its_bytes(
        self, seat: Collector
    ) -> None:
        """Version 4 decodes 4 bytes, and version 6 decodes 16."""
        check.equal(
            seat,
            [
                decoded_from({"shape": "ip-address", "version": 4}, (127, 0, 0, 1))[0],
                decoded_from({"shape": "ip-address", "version": 6})[0],
            ],
            [b"\x7f\x00\x00\x01", bytes(16)],
            "each address has the bytes of its version",
        )

    def test_reads_a_decimal_as_its_unscaled_value_with_bounds_rounded_inward(
        self, seat: Collector
    ) -> None:
        """The bounds 0.005 and 1.999 round inward to 1 and 199."""
        money = {"shape": "decimal", "scale": 2, "min": "0.005", "max": "1.999"}
        check.equal(
            seat,
            [
                decoded_from(money, 0)[0],
                decoded_from(money, 199)[0],
                decoded_from(money, 200)[0],
                decoded_from({"shape": "decimal", "scale": 0}, INT64_MAX)[0],
            ],
            [1, 199, 1, INT64_MAX],
            "the values are inside the rounded bounds",
        )

    def test_reads_a_decimal_with_a_negative_bound(self, seat: Collector) -> None:
        """The bounds -0.25 and -0.05 round inward to -2 and -1."""
        shape = {"shape": "decimal", "scale": 1, "min": "-0.25", "max": "-0.05"}
        check.equal(seat, decoded_from(shape, 0)[0], -1, "the value is the target -1")

    def test_reads_a_date_as_its_days_since_1970_01_01(self, seat: Collector) -> None:
        """The bounds are the days 1 and 30."""
        bounded = {"shape": "date", "min": "1970-01-02", "max": "1970-01-31"}
        check.equal(
            seat,
            [decoded_from(bounded, 0)[0], decoded_from(bounded, 30)[0]],
            [1, 30],
            "0 decodes to the target 1 and 30 to itself",
        )

    def test_reads_a_date_between_the_years_1_and_9999_by_default(
        self, seat: Collector
    ) -> None:
        """The first and the last day decode, and a day outside decodes to 0."""
        date = {"shape": "date"}
        check.equal(
            seat,
            [
                decoded_from(date, -719_162)[0],
                decoded_from(date, -719_163)[0],
                decoded_from(date, 2_932_896)[0],
                decoded_from(date, 2_932_897)[0],
            ],
            [-719_162, 0, 2_932_896, 0],
            "each day is in the years 1 to 9999",
        )

    def test_reads_a_date_of_a_leap_day(self, seat: Collector) -> None:
        """The bound 2024-02-29 is the day 19782."""
        shape = {"shape": "date", "min": "2024-02-29", "max": "2024-02-29"}
        check.equal(seat, decoded_from(shape)[0], 19_782, "the date is the day 19782")

    def test_reads_a_date_after_february_as_its_days_since_1970(
        self, seat: Collector
    ) -> None:
        """The bound 2024-03-01 is the day 19783."""
        shape = {"shape": "date", "min": "2024-03-01", "max": "2024-03-01"}
        check.equal(seat, decoded_from(shape)[0], 19_783, "the date is the day 19783")

    def test_reads_a_time_of_day_as_its_units_since_midnight(
        self, seat: Collector
    ) -> None:
        """The last millisecond decodes, and a minimum of 23:00 is the target."""
        check.equal(
            seat,
            [
                decoded_from({"shape": "time-of-day", "unit": "ms"}, 86_399_999)[0],
                decoded_from(
                    {"shape": "time-of-day", "unit": "s", "min": "23:00:00"}, 0
                )[0],
            ],
            [86_399_999, 82_800],
            "each time is in units since midnight",
        )

    def test_reads_the_fraction_of_a_time_of_day_at_its_unit(
        self, seat: Collector
    ) -> None:
        """The bound 00:00:01.25 is 1250 milliseconds."""
        shape = {"shape": "time-of-day", "unit": "ms", "min": "00:00:01.25"}
        check.equal(seat, decoded_from(shape, 0)[0], 1250, "the time is 1250 ms")

    def test_reads_a_duration_over_a_go_duration_in_its_unit(
        self, seat: Collector
    ) -> None:
        """A Go duration has at most 2^63 - 1 nanoseconds, or 9223372036 seconds."""
        check.equal(
            seat,
            [
                decoded_from({"shape": "duration", "unit": "ns"}, INT64_MAX)[0],
                decoded_from({"shape": "duration", "unit": "s"}, -9_223_372_036)[0],
                decoded_from({"shape": "duration", "unit": "s"}, 9_223_372_037)[0],
            ],
            [INT64_MAX, -9_223_372_036, 0],
            "each duration is inside the range of a Go duration",
        )

    def test_reads_an_offset_of_at_most_18_hours_either_way(
        self, seat: Collector
    ) -> None:
        """18 hours are 64800 seconds."""
        check.equal(
            seat,
            [
                decoded_from({"shape": "offset"}, -64_800)[0],
                decoded_from({"shape": "offset"}, 64_801)[0],
            ],
            [-64_800, 0],
            "-64800 decodes to itself and 64801 to the target",
        )

    def test_reads_a_zone_as_a_name_of_the_list_with_utc_first(
        self, seat: Collector
    ) -> None:
        """The target is UTC, and index 1 is Europe/Amsterdam."""
        check.equal(
            seat,
            [decoded_from({"shape": "zone"})[0], decoded_from({"shape": "zone"}, 1)[0]],
            ["UTC", "Europe/Amsterdam"],
            "the zones are UTC and Europe/Amsterdam",
        )

    def test_reads_a_root_with_a_source(self, seat: Collector) -> None:
        """The source has a Go type."""
        shape = {**UINT8, "source": {"language": "go", "type": "example.com/x.Qty"}}
        check.equal(seat, decoded_from(shape, 7)[0], 7, "the value is 7")

    def test_reads_a_ref_to_a_definition_without_recursion_as_the_definition(
        self, seat: Collector
    ) -> None:
        """The list has two ids."""
        shape = {
            "shape": "list",
            "of": {"shape": "ref", "name": "id"},
            "definitions": {"id": UINT8},
        }
        got = decoded_from(shape, 1, 4, 1, 5, 0)[0]
        check.equal(seat, got, [4, 5], "the list is [4, 5]")

    def test_reads_a_ref_to_a_name_that_the_file_does_not_define_as_its_external(
        self, seat: Collector
    ) -> None:
        """The list has one value of the external generator."""
        externals: dict[str, Generator[Any]] = {"Ext": Just("x")}
        shape = read(
            {"shape": "list", "of": {"shape": "ref", "name": "Ext"}}, externals
        )
        got = shape.decode(Case(Replaying(integers(1))))
        check.equal(seat, got, ["x"], "the list has the external value")

    def test_reads_a_ref_to_a_name_that_the_file_defines_as_its_definition(
        self, seat: Collector
    ) -> None:
        """The definition takes precedence over an external generator."""
        externals: dict[str, Generator[Any]] = {"id": Just("external")}
        shape = read(
            {"shape": "ref", "name": "id", "definitions": {"id": UINT8}}, externals
        )
        got = shape.decode(Case(Replaying(integers(7))))
        check.equal(seat, got, 7, "the value comes from the definition")

    def test_reads_a_ref_inside_a_definition_to_a_name_that_the_file_does_not_define(
        self, seat: Collector
    ) -> None:
        """The definition decodes the value of the external generator."""
        externals: dict[str, Generator[Any]] = {"Ext": Just("x")}
        shape = read(
            {
                "shape": "ref",
                "name": "ids",
                "definitions": {
                    "ids": {"shape": "list", "of": {"shape": "ref", "name": "Ext"}}
                },
            },
            externals,
        )
        got = shape.decode(Case(Replaying(integers(1))))
        check.equal(seat, got, ["x"], "the list has the external value")

    def test_reads_an_instant_whose_bounds_are_one_second(
        self, seat: Collector
    ) -> None:
        """Both bounds are 2020-01-01T00:00:00Z."""
        one = {
            "shape": "instant",
            "unit": "s",
            "min": "2020-01-01T00:00:00Z",
            "max": "2020-01-01T00:00:00Z",
        }
        want = canonical(instant(seconds(2020, 1, 1), 0))
        check.equal(seat, canonical_of(one), want, "the instant is the bound")

    def test_reads_an_instant_whose_bounds_are_two_fractions_of_one_second(
        self, seat: Collector
    ) -> None:
        """The target is the lower bound at 100 milliseconds."""
        inside = {
            "shape": "instant",
            "unit": "ms",
            "min": "2020-01-01T00:00:00.1Z",
            "max": "2020-01-01T00:00:00.5Z",
        }
        want = canonical(instant(seconds(2020, 1, 1), 100))
        check.equal(seat, canonical_of(inside), want, "the instant is the lower bound")

    refusals: ClassVar[list[tuple[str, object, str]]] = [
        (
            "raises shape error for a value that is not an object",
            [],
            "prop: [] is not a shape",
        ),
        ("raises shape error for none", None, "prop: null is not a shape"),
        (
            "raises shape error for a shape id that is not a string",
            {"shape": 5},
            "prop: shape.shape is 5, not the id of a shape",
        ),
        (
            "raises shape error for an instant bound that is not a string",
            {"shape": "instant", "unit": "s", "min": 5},
            "prop: shape bound 5 is not an instant in UTC",
        ),
        (
            "raises shape error for a date bound that is not a string",
            {"shape": "date", "min": 5},
            "prop: shape bound 5 is not a date",
        ),
        (
            "raises shape error for a time bound that is not a string",
            {"shape": "time-of-day", "unit": "s", "min": 5},
            "prop: shape bound 5 is not a time of day",
        ),
        (
            "raises shape error for a local date and time bound that is not a string",
            {"shape": "local-date-time", "unit": "s", "min": 5},
            "prop: shape bound 5 is not a local date and time",
        ),
        (
            "raises shape error for a definition of an enum whose variants are not a "
            "list",
            {
                "shape": "ref",
                "name": "e",
                "definitions": {"e": {"shape": "enum", "variants": 5}},
            },
            "prop: definitions.e.variants is 5, not a list of pairs",
        ),
        (
            "raises shape error for a definition of an enum whose variant is not a "
            "pair",
            {
                "shape": "ref",
                "name": "e",
                "definitions": {"e": {"shape": "enum", "variants": [["x"]]}},
            },
            'prop: definitions.e.variants has ["x"], not a name and a shape',
        ),
        (
            "raises shape error for an unknown shape",
            {"shape": "widget"},
            'prop: shape.shape is "widget", not the id of a shape',
        ),
        (
            "raises shape error for a missing key",
            {"shape": "int", "width": 8},
            "prop: shape.signed is missing from the int shape",
        ),
        (
            "raises shape error for a width outside the int widths",
            {"shape": "int", "width": 12, "signed": True},
            "prop: shape.width is 12, not 8, 16, 32, 64 or 128",
        ),
        (
            "raises shape error for a key that the shape does not take",
            {**INT8, "mx": 1},
            "prop: shape.mx does not apply to the int shape",
        ),
        (
            "raises shape error for a bound outside the width",
            {**INT8, "min": 200},
            "prop: shape bounds [200, 127] are empty or outside [-128, 127]",
        ),
        (
            "raises shape error for a bound that is not an integer",
            {"shape": "record", "fields": [["id", {**UINT8, "max": "x"}]]},
            'prop: shape.id: prop: "x" is not an integer',
        ),
        (
            "raises shape error for a record that repeats a field name",
            {"shape": "record", "fields": [["id", UINT8], ["id", UINT8]]},
            'prop: shape.fields has an empty or repeated name "id"',
        ),
        (
            "raises shape error for a record without fields",
            {"shape": "record", "fields": []},
            "prop: shape.fields is [], not a list of pairs",
        ),
        (
            "raises shape error for a variant without a shape",
            {"shape": "enum", "variants": [["x"]]},
            'prop: shape.variants has ["x"], not a name and a shape',
        ),
        (
            "raises shape error for a decimal with a null scale",
            {"shape": "decimal", "scale": None},
            "prop: shape.scale is null, not an integer",
        ),
        (
            "raises shape error for a decimal bound with an exponent",
            {"shape": "decimal", "scale": 2, "min": "1e3"},
            'prop: shape.min is "1e3", not a decimal',
        ),
        (
            "raises shape error for a fixed list with a null size",
            {"shape": "fixed-list", "of": UINT8, "size": None},
            "prop: shape.size is null, not an integer",
        ),
        (
            "raises shape error for a pattern with a size",
            {"shape": "string", "pattern": "a", "max_size": 3},
            "prop: shape has a pattern, so it cannot have an alphabet or a size",
        ),
        (
            "raises shape error for a pattern that is not a string",
            {"shape": "string", "pattern": 3},
            "prop: shape.pattern is 3, not a string",
        ),
        (
            "raises shape error for a pattern outside the subset",
            {"shape": "string", "pattern": "a**"},
            'prop: shape: pattern "a**" at 3: "*" must be escaped here',
        ),
        (
            "raises shape error for an alphabet that repeats a character",
            {"shape": "string", "alphabet": "aa"},
            "prop: shape.alphabet repeats a character",
        ),
        (
            "raises shape error for an alphabet that is not a string",
            {"shape": "char", "alphabet": 3},
            "prop: shape.alphabet is 3, not a string of at least one character",
        ),
        (
            "raises shape error for an alphabet with a lone surrogate",
            {"shape": "char", "alphabet": "a\ud800"},
            "prop: shape.alphabet has a lone surrogate instead of a character",
        ),
        (
            "raises shape error for a float width of 16",
            {"shape": "float", "width": 16},
            "prop: shape.width is 16, not 32 or 64",
        ),
        (
            "raises shape error for an allow_nan that is not a bool",
            {"shape": "float", "width": 64, "allow_nan": "yes"},
            'prop: shape.allow_nan is "yes", not true or false',
        ),
        (
            "raises shape error for the infinities with two finite bounds",
            {"shape": "float", "width": 64, "allow_infinity": True, "min": 0, "max": 1},
            "prop: shape allows the infinities, but both of its bounds are finite",
        ),
        (
            "raises shape error for float bounds that run backwards",
            {"shape": "float", "width": 64, "min": 1, "max": 0},
            "prop: shape: prop: float bounds [1.0, 0.0] are empty",
        ),
        (
            "raises shape error for an address version of 5",
            {"shape": "ip-address", "version": 5},
            "prop: shape.version is 5, not 4 or 6",
        ),
        (
            "raises shape error for an address version that is not a number",
            {"shape": "ip-address", "version": [4]},
            "prop: shape.version is [4], not 4 or 6",
        ),
        (
            "raises shape error for a unit of minutes",
            {"shape": "instant", "unit": "min"},
            'prop: shape.unit is "min", not one of ms, ns, s, us',
        ),
        (
            "raises shape error for a unit that is not a string",
            {"shape": "instant", "unit": ["s"]},
            'prop: shape.unit is ["s"], not one of ms, ns, s, us',
        ),
        (
            "raises shape error for an instant bound without a zone",
            {"shape": "instant", "unit": "s", "min": "2020-01-01T00:00:00"},
            'prop: shape bound "2020-01-01T00:00:00" is not an instant in UTC',
        ),
        (
            "raises shape error for an instant bound finer than its unit",
            {"shape": "instant", "unit": "s", "min": "2020-01-01T00:00:00.5Z"},
            "prop: shape has a bound with a fraction finer than its unit",
        ),
        (
            "raises shape error for an instant whose bounds run backwards",
            {
                "shape": "instant",
                "unit": "s",
                "min": "2020-01-02T00:00:00Z",
                "max": "2020-01-01T00:00:00Z",
            },
            "prop: shape bounds 1577923200,0 to 1577836800,0 are empty or out of range",
        ),
        (
            "raises shape error for instant bounds that run backwards in one second",
            {
                "shape": "instant",
                "unit": "ms",
                "min": "2020-01-01T00:00:00.5Z",
                "max": "2020-01-01T00:00:00.1Z",
            },
            "prop: shape bounds 1577836800,500 to 1577836800,100 are empty or out of "
            "range",
        ),
        (
            "raises shape error for a date that does not exist",
            {"shape": "date", "min": "2021-02-29"},
            "prop: shape bound 2021-02-29 is not a date",
        ),
        (
            "raises shape error for a date in another form",
            {"shape": "date", "min": "2020/01/01"},
            'prop: shape bound "2020/01/01" is not a date',
        ),
        (
            "raises shape error for a date of month 13",
            {"shape": "date", "max": "2020-13-01"},
            "prop: shape bound 2020-13-01 is not a date",
        ),
        (
            "raises shape error for a date of month 0",
            {"shape": "date", "max": "2020-00-01"},
            "prop: shape bound 2020-00-01 is not a date",
        ),
        (
            "raises shape error for a date of the year 0",
            {"shape": "date", "min": "0000-01-01"},
            "prop: shape bound 0000-01-01 is not a date",
        ),
        (
            "raises shape error for a date with digits of another script",
            {"shape": "date", "min": "\U00000662020-01-01"},
            'prop: shape bound "\\u0662020-01-01" is not a date',
        ),
        (
            "raises shape error for a time of 24 hours",
            {"shape": "time-of-day", "unit": "s", "max": "24:00:00"},
            "prop: shape bound 24:00:00 is not a time of day",
        ),
        (
            "raises shape error for a time in words",
            {"shape": "time-of-day", "unit": "s", "min": "noon"},
            'prop: shape bound "noon" is not a time of day',
        ),
        (
            "raises shape error for a time with a final newline",
            {"shape": "time-of-day", "unit": "s", "min": "12:00:00\n"},
            'prop: shape bound "12:00:00\\n" is not a time of day',
        ),
        (
            "raises shape error for a local date and time bound with a zone",
            {"shape": "local-date-time", "unit": "s", "min": "2020-01-01T00:00:00Z"},
            'prop: shape bound "2020-01-01T00:00:00Z" is not a local date and time',
        ),
        (
            "raises shape error for sizes that run backwards",
            {"shape": "list", "of": UINT8, "min_size": 3, "max_size": 2},
            "prop: shape: sizes [3, 2] are empty",
        ),
        (
            "raises shape error for a negative size",
            {"shape": "list", "of": UINT8, "min_size": -1},
            "prop: shape.min_size is -1, below 0",
        ),
        (
            "raises shape error for a nested value that is not a shape",
            {"shape": "optional", "of": 3},
            "prop: shape.of is 3, not a shape",
        ),
        (
            "raises shape error for a literal without values",
            {"shape": "literal", "values": []},
            "prop: shape.values is [], not a list of literals",
        ),
        (
            "raises shape error for a literal value that is not a typed literal",
            {"shape": "literal", "values": [1]},
            "prop: shape: prop: 1 is not a typed literal",
        ),
        (
            "raises shape error for definitions that are not a map",
            {**UINT8, "definitions": []},
            "prop: definitions is not a map of names to shapes",
        ),
        (
            "raises shape error for a definition that is not a shape",
            {**UINT8, "definitions": {"id": 3}},
            "prop: definitions.id is 3, not a shape",
        ),
        (
            "raises shape error for a source without a type",
            {**UINT8, "source": {"language": "go"}},
            'prop: source is {"language":"go"}, not a language and a type',
        ),
        (
            "raises shape error for a source that is not an object",
            {**UINT8, "source": "go"},
            'prop: source is "go", not a language and a type',
        ),
        (
            "raises shape error for a source below the root",
            {"shape": "list", "of": {**UINT8, "source": {}}},
            "prop: shape.of.source does not apply to the int shape",
        ),
        (
            "raises shape error for a width that is not an integer",
            {"shape": "int", "width": "x", "signed": True},
            'prop: shape.width is "x", not an integer',
        ),
        (
            "raises shape error for a signed that is not a bool",
            {"shape": "int", "width": 8, "signed": "yes"},
            'prop: shape.signed is "yes", not true or false',
        ),
        (
            "raises shape error for a ref without a definition",
            {"shape": "ref", "name": "missing"},
            'prop: a ref to "missing" does not have a definition',
        ),
        (
            "raises shape error for a ref whose name is not a string",
            {"shape": "ref", "name": 1},
            'prop: a ref to "1" does not have a definition',
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_shape_error_for_a_shape_that_does_not_read(
        self, seat: Collector, give: object, want: str
    ) -> None:
        """The error has the reason."""
        got = refusal(seat, lambda: read(give), ShapeError)
        check.equal(seat, got, want, "the error has the reason")

    endless: ClassVar[list[tuple[str, dict[str, Any], str]]] = [
        (
            "raises shape error for a record that contains itself",
            {
                "shape": "ref",
                "name": "loop",
                "definitions": {
                    "loop": {
                        "shape": "record",
                        "fields": [["next", {"shape": "ref", "name": "loop"}]],
                    }
                },
            },
            "loop",
        ),
        (
            "raises shape error for a list that must contain itself",
            {
                "shape": "ref",
                "name": "t",
                "definitions": {
                    "t": {
                        "shape": "list",
                        "min_size": 1,
                        "of": {"shape": "ref", "name": "t"},
                    }
                },
            },
            "t",
        ),
        (
            "raises shape error for an enum whose every variant refers back",
            {
                "shape": "ref",
                "name": "e",
                "definitions": {
                    "e": {
                        "shape": "enum",
                        "variants": [["only", {"shape": "ref", "name": "e"}]],
                    }
                },
            },
            "e",
        ),
        (
            "raises shape error for two records that contain each other",
            {
                "shape": "ref",
                "name": "a",
                "definitions": {
                    "a": {
                        "shape": "record",
                        "fields": [["b", {"shape": "ref", "name": "b"}]],
                    },
                    "b": {
                        "shape": "record",
                        "fields": [["a", {"shape": "ref", "name": "a"}]],
                    },
                },
            },
            "a",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in endless], ids=[t[0] for t in endless]
    )
    def test_raises_shape_error_for_a_definition_without_a_finite_value(
        self, seat: Collector, give: dict[str, Any], want: str
    ) -> None:
        """The error has the first such definition in the order of the names."""
        got = refusal(seat, lambda: read(give), ShapeError)
        check.equal(
            seat,
            got,
            f"prop: definitions.{want} {ENDLESS}",
            "the error has the definition and the reason",
        )


class TestInt128Shape:
    """Int128Shape decodes a 128-bit integer from two halves."""

    WIDE: ClassVar[dict[str, object]] = {"shape": "int", "width": 128, "signed": True}

    def test_decodes_its_signed_high_half_before_its_low_half(
        self, seat: Collector
    ) -> None:
        """Each pair of halves decodes to its 128-bit integer."""
        check.equal(
            seat,
            [
                decoded_from(self.WIDE, -1, UINT64_MAX)[0],
                decoded_from(self.WIDE, 1, 0)[0],
                decoded_from(self.WIDE, -(2**63), 0)[0],
                decoded_from({**self.WIDE, "signed": False}, UINT64_MAX, UINT64_MAX)[0],
            ],
            [-1, 2**64, -(2**127), 2**128 - 1],
            "each pair of halves decodes to its integer",
        )

    def test_bounds_its_low_half_by_the_bound_whose_high_half_it_shares(
        self, seat: Collector
    ) -> None:
        """A low half outside the range of its high half decodes to the target."""
        bounded = {
            "shape": "int",
            "width": 128,
            "signed": False,
            "min": str(2**64 + 10),
            "max": str(2**65),
        }
        check.equal(
            seat,
            [
                decoded_from(bounded, 1, 3)[0],
                decoded_from(bounded, 2, 9)[0],
                decoded_from(bounded, 1, 11)[0],
            ],
            [2**64 + 10, 2**65, 2**64 + 11],
            "each value is inside the bounds",
        )


class TestInstantShape:
    """InstantShape decodes the seconds and the units of an instant."""

    def test_decodes_its_seconds_and_its_units(self, seat: Collector) -> None:
        """An instant makes two choices at nanoseconds and one at seconds."""
        value, c = decoded_from({"shape": "instant", "unit": "s"}, 253_402_300_799)
        check.equal(
            seat,
            [
                canonical_of({"shape": "instant", "unit": "ns"}, -1, 999_999_999),
                canonical(value),
                len(c.choices),
            ],
            [
                canonical(instant(-1, 999_999_999)),
                canonical(instant(253_402_300_799, 0)),
                1,
            ],
            "each instant has its seconds and its units",
        )

    def test_stops_the_units_of_the_second_of_its_bound(self, seat: Collector) -> None:
        """The units start at 500 in the second of the bound and at 0 after it."""
        start = seconds(2020, 1, 1)
        bounded = {"shape": "instant", "unit": "ms", "min": "2020-01-01T00:00:00.5Z"}
        check.equal(
            seat,
            [canonical_of(bounded, start, 3), canonical_of(bounded, start + 1, 3)],
            [canonical(instant(start, 500)), canonical(instant(start + 1, 3))],
            "3 decodes to 500 in the second of the bound and to 3 after it",
        )

    def test_decodes_from_the_first_second_of_the_year_1_by_default(
        self, seat: Collector
    ) -> None:
        """The first second is 0001-01-01T00:00:00Z."""
        got = canonical_of({"shape": "instant", "unit": "s"}, -62_135_596_800)
        want = canonical(instant(-62_135_596_800, 0))
        check.equal(seat, got, want, "the instant is the first second")


class TestLocalDateTimeShape:
    """LocalDateTimeShape decodes a date and a time of day without a zone."""

    def test_stops_the_time_of_day_of_the_date_of_its_bound(
        self, seat: Collector
    ) -> None:
        """The time of day stops at the bound on the date of the bound alone."""
        bounded = {
            "shape": "local-date-time",
            "unit": "s",
            "max": "1970-01-02T12:00:00",
        }
        check.equal(
            seat,
            [canonical_of(bounded, 1, 86_399), canonical_of(bounded, 0, 86_399)],
            [canonical(local(1, 0)), canonical(local(0, 86_399))],
            "the time of day stops at the bound on its date alone",
        )


class TestIpShape:
    """IpShape decodes an address of either version."""

    def test_decodes_the_bytes_of_the_version_that_an_index_chooses(
        self, seat: Collector
    ) -> None:
        """Index 1 chooses version 6."""
        got = decoded_from({"shape": "ip-address"}, 1, (1,) * 16)[0]
        check.equal(seat, got, b"\x01" * 16, "the address has 16 bytes")


class TestZonedShape:
    """ZonedShape decodes an instant in a zone of the list."""

    def test_decodes_the_instant_of_a_zone_without_a_change_over_the_whole_range(
        self, seat: Collector
    ) -> None:
        """The case does not make a choice of a change for UTC."""
        value, c = decoded_from({"shape": "zoned-date-time", "unit": "s"}, 0, 42)
        want = Fields((("instant", instant(42, 0)), ("zone", "UTC")))
        check.equal(
            seat,
            [canonical(value), len(c.choices)],
            [canonical(want), 2],
            "the value of UTC has two choices",
        )

    def test_decodes_an_instant_one_unit_from_a_change(self, seat: Collector) -> None:
        """The step -1 is one nanosecond before the change."""
        got = canonical_of({"shape": "zoned-date-time", "unit": "ns"}, 1, 1, 0, -1)
        want = Fields(
            (
                ("instant", instant(CHANGE.at - 1, 999_999_999)),
                ("zone", "Europe/Amsterdam"),
            )
        )
        check.equal(
            seat, got, canonical(want), "the instant is one unit before the change"
        )

    def test_decodes_an_instant_away_from_the_changes_over_the_whole_range(
        self, seat: Collector
    ) -> None:
        """The instant decodes from two choices of its own."""
        got = canonical_of({"shape": "zoned-date-time", "unit": "ms"}, 1, 0, 7, 8)
        want = Fields((("instant", instant(7, 8)), ("zone", "Europe/Amsterdam")))
        check.equal(seat, got, canonical(want), "the instant is 7 seconds and 8 ms")

    def test_decodes_about_one_case_in_four_from_the_changes(
        self, seat: Collector
    ) -> None:
        """The share of the values near a change is a quarter to within 0.03."""
        shape = read({"shape": "zoned-date-time", "unit": "s"})
        near = 0
        changed = 0
        for index in range(4000):
            c = Case(Generating(case_source(11, index)))
            shape.decode(c)
            if ZONES[cast("int", c.choices[0].value)].changes:
                changed += 1
                near += c.choices[1].value == 1
        check.is_true(
            seat,
            changed > 3000 and abs(near / changed - 0.25) <= 0.03,
            "a quarter of the values are near a change",
        )


class TestWallShape:
    """WallShape decodes a wall time in a zone of the list."""

    @pytest.mark.parametrize(
        ("side", "offset"),
        [(0, CHANGE.before), (1, CHANGE.after)],
        ids=[
            "decodes the instant of the change in the offset before it",
            "decodes the instant of the change in the offset after it",
        ],
    )
    def test_decodes_the_instant_of_the_change_in_an_offset(
        self, seat: Collector, side: int, offset: int
    ) -> None:
        """The wall time is the instant of the change in the chosen offset."""
        day, time = divmod(CHANGE.at + offset, 86_400)
        got = canonical_of({"shape": "wall-time", "unit": "s"}, 1, 1, 0, 0, side)
        want = Fields(
            (("local-date-time", local(day, time)), ("zone", "Europe/Amsterdam"))
        )
        check.equal(seat, got, canonical(want), "the wall time is in the offset")

    def test_decodes_a_wall_time_away_from_the_changes_over_the_whole_range(
        self, seat: Collector
    ) -> None:
        """The wall time decodes from the two choices of its local date and time."""
        got = canonical_of({"shape": "wall-time", "unit": "s"}, 1, 0, 5, 6)
        want = Fields((("local-date-time", local(5, 6)), ("zone", "Europe/Amsterdam")))
        check.equal(seat, got, canonical(want), "the wall time is day 5 at second 6")

    def test_decodes_about_half_of_the_wall_times_near_a_change_after_it(
        self, seat: Collector
    ) -> None:
        """The share of the wall times after a change is a half to within 0.06."""
        shape = read({"shape": "wall-time", "unit": "s"})
        near = 0
        after = 0
        for index in range(4000):
            c = Case(Generating(case_source(13, index)))
            shape.decode(c)
            changes = ZONES[cast("int", c.choices[0].value)].changes
            if changes and c.choices[1].value == 1:
                near += 1
                after += c.choices[4].value == 1
        check.is_true(
            seat,
            near > 600 and abs(after / near - 0.5) <= 0.06,
            "half of the wall times near a change are after it",
        )


class TestOptionalShape:
    """OptionalShape decodes a value or None."""

    def test_decodes_a_present_value_from_the_flag_1_alone(
        self, seat: Collector
    ) -> None:
        """The target is absent, and the flag 1 decodes the value 5."""
        optional = {"shape": "optional", "of": UINT8}
        check.equal(
            seat,
            [decoded_from(optional)[0], decoded_from(optional, 1, 5)[0]],
            [None, 5],
            "the values are None and 5",
        )

    def test_ends_a_linked_list_at_an_absent_next(self, seat: Collector) -> None:
        """The list has two nodes."""
        linked = {
            "shape": "ref",
            "name": "node",
            "definitions": {
                "node": {
                    "shape": "record",
                    "fields": [
                        ["value", UINT8],
                        [
                            "next",
                            {
                                "shape": "optional",
                                "of": {"shape": "ref", "name": "node"},
                            },
                        ],
                    ],
                }
            },
        }
        want = Fields(
            (
                ("value", 1),
                ("next", Fields((("value", 2), ("next", None)))),
            )
        )
        got = canonical_of(linked, 1, 1, 2)
        check.equal(seat, got, canonical(want), "the list ends at the second node")

    def test_stops_definitions_that_refer_to_each_other_once_the_budget_is_used(
        self, seat: Collector
    ) -> None:
        """Each level of the value counts two nodes."""
        mutual = {
            "shape": "ref",
            "name": "even",
            "definitions": {
                "even": {"shape": "optional", "of": {"shape": "ref", "name": "odd"}},
                "odd": {
                    "shape": "record",
                    "fields": [["next", {"shape": "ref", "name": "even"}]],
                },
            },
        }
        value = decoded_from(mutual, *[1] * 400)[0]
        depth = 0
        while value is not None:
            value = cast("Fields", value).fields[0][1]
            depth += 1
        check.equal(seat, depth, BUDGET // 2, "the depth is half the budget")


class TestRecordShape:
    """RecordShape decodes named fields in their order."""

    def test_decodes_its_fields_in_order(self, seat: Collector) -> None:
        """The record has an id and a flag."""
        record = {
            "shape": "record",
            "fields": [["id", UINT8], ["ok", {"shape": "bool"}]],
        }
        want = Fields((("id", 4), ("ok", True)))
        got = canonical_of(record, 4, 1)
        check.equal(seat, got, canonical(want), "the fields decode in order")


class TestEnumShape:
    """EnumShape decodes a variant and its payload."""

    OPTIONAL: ClassVar[dict[str, object]] = {
        "shape": "enum",
        "variants": [["none", None], ["some", UINT8]],
    }

    def test_decodes_the_payload_of_the_variant_that_an_index_chooses(
        self, seat: Collector
    ) -> None:
        """The variant none does not have a payload, and the variant some has one."""
        bare = cast("Variant", decoded_from(self.OPTIONAL)[0])
        check.equal(
            seat,
            [bare.name, bare.has_payload, canonical_of(self.OPTIONAL, 1, 9)],
            ["none", False, canonical(Variant("some", 9))],
            "each variant has its payload or none",
        )

    def test_takes_its_first_exit_once_the_budget_is_used(
        self, seat: Collector
    ) -> None:
        """The leaves end the value once the budget is used."""
        nested = {
            "shape": "ref",
            "name": "node",
            "definitions": {
                "node": {
                    "shape": "enum",
                    "variants": [
                        [
                            "branch",
                            {
                                "shape": "fixed-list",
                                "size": 2,
                                "of": {"shape": "ref", "name": "node"},
                            },
                        ],
                        ["leaf", None],
                    ],
                }
            },
        }

        def count(node: Any) -> int:
            variant = cast("Variant", node)
            if variant.name == "leaf":
                return 1
            return 1 + sum(count(child) for child in variant.payload)

        value = decoded_from(nested, *[0] * 400)[0]
        check.is_true(seat, count(value) < 3 * BUDGET, "the value is finite")


class TestRef:
    """Ref decodes the value of a definition by its name."""

    def test_decodes_a_tree_through_its_definition(self, seat: Collector) -> None:
        """The tree has one child."""
        want = Fields(
            (
                ("value", 3),
                ("children", [Fields((("value", 4), ("children", [])))]),
            )
        )
        got = canonical_of(TREE, 3, 1, 4, 0, 0)
        check.equal(
            seat, got, canonical(want), "the tree decodes through its definition"
        )


class Pausing(Replaying):
    """A replay that waits at one index until another thread signals."""

    def __init__(
        self,
        choices: list[Choice],
        at: int,
        paused: threading.Event,
        resume: threading.Event,
    ) -> None:
        """Return the replay that pauses at an index."""
        super().__init__(choices)
        self._at: int = at
        self._paused: threading.Event = paused
        self._resume: threading.Event = resume

    def value(self, request: Request, index: int) -> Value:
        """Return the recorded value, after the pause at the index."""
        if index == self._at:
            self._paused.set()
            self._resume.wait(WAIT)
        return super().value(request, index)


class Waiting(Provider):
    """A provider that signals, then waits for the other thread to finish."""

    def __init__(self, started: threading.Event, done: threading.Event) -> None:
        """Return the provider of the signals."""
        self._started: threading.Event = started
        self._done: threading.Event = done

    def value(self, request: Request, index: int) -> Value:
        """Return the target, after the other thread has finished."""
        del index
        self._started.set()
        self._done.wait(WAIT)
        return request.bounds.target


class TestRoot:
    """Root counts the budget of each value of a recursive shape."""

    def test_stops_a_tree_from_growing_once_its_value_has_used_the_budget(
        self, seat: Collector
    ) -> None:
        """The largest tree of 300 cases has as many nodes as the budget."""
        shape = read(TREE)
        largest = max(
            nodes(shape.decode(Case(Generating(case_source(5, index)))))
            for index in range(300)
        )
        check.equal(seat, largest, BUDGET, "the largest tree has 100 nodes")

    def test_counts_the_budget_of_each_thread_apart(self, seat: Collector) -> None:
        """A value in another thread leaves the budget of this one alone."""
        shape = read(TREE)
        paused = threading.Event()
        started = threading.Event()
        done = threading.Event()
        # The value of the hundredth node is choice 198. The tree has used its
        # budget there, and the other thread starts a value of its own.
        c = Case(Pausing(integers(*[1] * 400), 198, paused, started))
        got: list[object] = []

        def first() -> None:
            try:
                got.append(shape.decode(c))
            finally:
                done.set()

        thread = threading.Thread(target=first)
        thread.start()
        paused.wait(WAIT)
        other = shape.decode(Case(Waiting(started, done)))
        thread.join()
        check.equal(
            seat,
            [[nodes(value) for value in got], nodes(other)],
            [[BUDGET], 1],
            "each tree uses a budget of its own",
        )


class TestMapShape:
    """MapShape decodes entries with distinct keys."""

    def test_stops_a_map_that_refers_back_once_the_budget_is_used(
        self, seat: Collector
    ) -> None:
        """The largest map of 200 cases has as many nodes as the budget."""
        keyed = {
            "shape": "ref",
            "name": "node",
            "definitions": {
                "node": {
                    "shape": "map",
                    "key": {"shape": "int", "width": 64, "signed": False},
                    "of": {"shape": "ref", "name": "node"},
                }
            },
        }
        shape = read(keyed)

        def count(value: Any) -> int:
            entries = cast("Pairs", value).items
            return 1 + sum(count(child) for _, child in entries)

        largest = max(
            count(shape.decode(Case(Generating(case_source(3, index)))))
            for index in range(200)
        )
        check.equal(seat, largest, BUDGET, "the largest map has 100 nodes")
