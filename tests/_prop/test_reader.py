"""The spec of _prop/reader.py tests the read of Python types into shapes."""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field, make_dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from ipaddress import IPv4Address, IPv6Address
from typing import (
    Annotated,
    Any,
    ClassVar,
    Literal,
    NamedTuple,
    NewType,
    TypedDict,
    cast,
)
from uuid import UUID
from zoneinfo import ZoneInfo

import annotated_types as at
import pytest

from dokimi_assert import check
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._prop.convert import Converter
from dokimi_assert._prop.engine.choice import IntegerBounds
from dokimi_assert._prop.engine.float import next_down
from dokimi_assert._prop.engine.generator import Integer
from dokimi_assert._prop.engine.value import Fields, Pairs, canonical
from dokimi_assert._prop.engine.value import Variant as Neutral
from dokimi_assert._prop.markers import (
    AllowInfinity,
    AllowNan,
    Alphabet,
    Char,
    Pattern,
    Scale,
    Unit,
    Version,
    Width,
)
from dokimi_assert._prop.reader import (
    Derived,
    Literals,
    Node,
    Registrations,
    derive,
    literal_converter,
    qualified,
)
from dokimi_assert.seat import Collector
from helpers import refusal

#: The shapes of the scalars that the cases refer to.
INT: Node = {"shape": "int", "width": 64, "signed": True}
STRING: Node = {"shape": "string"}
BOOL: Node = {"shape": "bool"}

#: A generator of one digit.
DIGITS = Integer(IntegerBounds(0, 9))


@dataclass(frozen=True)
class Point:
    """A record of two ints."""

    x: int
    y: int


@dataclass
class Line:
    """A line of an order."""

    sku: str
    qty: Annotated[int, Width(32)]


@dataclass
class Order:
    """An order has lines and a note."""

    id: Annotated[int, Width(32, signed=False)]
    lines: list[Line]
    note: str | None


@dataclass
class Tree:
    """A tree of values."""

    value: Annotated[int, Width(32)]
    children: list[Tree]


@dataclass
class Forest:
    """Two trees."""

    first: Tree
    second: Tree


@dataclass
class Chain:
    """A chain whose link has a constraint. A ref does not take a constraint."""

    value: int
    link: Annotated[Chain, at.Ge(1)] | None


@dataclass
class Counted:
    """A record with a field that the reader does not read."""

    count: int
    seen: int = field(default=0, init=False)


@dataclass
class Pending:
    """A variant without a payload."""


class Paid(int):
    """A variant of an amount."""


class Refunded(str):
    """A variant of a reason."""


class Colour(enum.Enum):
    """An Enum of two members."""

    RED = 1
    GREEN = 2


class Empty(enum.Enum):
    """An Enum without members."""


class Pair(NamedTuple):
    """A NamedTuple of two fields."""

    a: int
    b: str


class Movie(TypedDict):
    """A TypedDict of two keys."""

    title: str
    year: int


class Draft(TypedDict, total=False):
    """A TypedDict of a key that is not required."""

    title: str


class Status(str):
    """A text type whose values come from a registration."""


class Shape:
    """A base class of variants."""


@dataclass(frozen=True)
class Circle(Shape):
    """A variant of a radius."""

    radius: int


@dataclass(frozen=True)
class Square(Shape):
    """A variant of a side."""

    side: int


@dataclass
class Unhashable:
    """A record whose values are not hashable."""

    a: int


#: A record whose annotation refers to a type that its module does not have.
UNRESOLVED = make_dataclass("Unresolved", [("missing", "Nowhere")])

#: Two variant classes of one name.
TWINS = (
    make_dataclass("Twin", [("a", int)], frozen=True),
    make_dataclass("Twin", [("b", int)], frozen=True),
)

#: A NewType of an int.
UserId = NewType("UserId", int)


def read(t: object, **kwargs: Any) -> Derived:
    """Return the read of a type under a registry without registrations."""
    return derive(t, Registrations(), **kwargs)


def root(t: object) -> Node:
    """Return the root shape of a type."""
    return read(t).root


def converted(t: object) -> Converter:
    """Return the converter of a type."""
    return read(t).converter


def same(seat: Collector, got: object, want: object, msg: str) -> None:
    """Check that two neutral values have one canonical text."""
    check.equal(seat, canonical(got), canonical(want), msg)


def unchanged(seat: Collector, converter: Converter, value: object) -> None:
    """Check that back returns a value of another type unchanged."""
    check.is_true(
        seat, converter.back(value) is value, "back returns the value unchanged"
    )


class TestQualified:
    """qualified returns the name of a type with its module."""

    def test_returns_the_module_and_the_name_of_a_class(self, seat: Collector) -> None:
        """The class is in the standard library."""
        check.equal(
            seat,
            qualified(UUID),
            "uuid.UUID",
            "qualified returns the module and the name",
        )

    def test_returns_the_repr_of_an_annotation_that_is_not_a_class(
        self, seat: Collector
    ) -> None:
        """The annotation is a generic."""
        check.equal(
            seat, qualified(list[int]), "list[int]", "qualified returns the repr"
        )


class TestLiterals:
    """Literals has the values that register_values gives a type."""

    def test_keeps_the_literals_and_the_converter(self, seat: Collector) -> None:
        """Literals keeps both fields."""
        written = [{"type": "string", "value": "a"}]
        kept = Literals(written, literal_converter(["a"], written))
        check.equal(
            seat,
            [kept.literals, kept.converter.to("a")],
            [written, "a"],
            "Literals keeps the literals and the converter",
        )


class TestRegistrations:
    """Registrations has the registrations that a read consults."""

    def test_starts_open_and_empty(self, seat: Collector) -> None:
        """The process has not registered a type."""
        registrations = Registrations()
        check.equal(
            seat,
            [
                registrations.generators,
                registrations.values,
                registrations.variants,
                registrations.consulted,
                registrations.closed,
            ],
            [{}, {}, {}, set(), False],
            "the registrations are open and empty",
        )


class TestDerived:
    """Derived is a type that the reader has read into a shape file."""

    def test_keeps_the_root_without_definitions_of_a_flat_type(
        self, seat: Collector
    ) -> None:
        """An int does not refer to itself."""
        derived = read(int)
        check.equal(
            seat,
            [derived.root, derived.externals, derived.external_paths],
            [INT, {}, []],
            "the read does not have definitions or externals",
        )


class TestLiteralConverter:
    """literal_converter returns the converter between decoded literals and values."""

    def test_converts_a_registered_value_both_ways(self, seat: Collector) -> None:
        """The status has the text paid."""
        converter = literal_converter(
            [Status("paid")], [{"type": "string", "value": "paid"}]
        )
        got = converter.to("paid")
        check.equal(
            seat,
            [type(got), got, converter.back(Status("paid"))],
            [Status, Status("paid"), "paid"],
            "the converter converts both ways",
        )

    def test_returns_a_value_without_a_literal_unchanged(self, seat: Collector) -> None:
        """The inverse refuses the value."""
        converter = literal_converter(["a"], [{"type": "string", "value": "a"}])
        unchanged(seat, converter, "b")


class TestDerive:
    """derive reads a Python type into a shape file."""

    tests: ClassVar[list[tuple[str, object, Node]]] = [
        ("reads a bool", bool, BOOL),
        ("reads an int as a signed int of 64 bits", int, INT),
        (
            "reads the width and the bounds of an int",
            Annotated[int, Width(8, signed=False), at.Ge(1), at.Le(9)],
            {"shape": "int", "width": 8, "signed": False, "min": 1, "max": 9},
        ),
        (
            "reads an exclusive bound of an int one step inside",
            Annotated[int, at.Gt(0), at.Lt(10)],
            {**INT, "min": 1, "max": 9},
        ),
        (
            "reads an interval of an int",
            Annotated[int, at.Interval(ge=-5, lt=5)],
            {**INT, "min": -5, "max": 4},
        ),
        (
            "reads a bound of an int beyond 2 to the 53 as its digits",
            Annotated[int, Width(128), at.Le(2**60)],
            {"shape": "int", "width": 128, "signed": True, "max": str(2**60)},
        ),
        ("reads a float of 64 bits", float, {"shape": "float", "width": 64}),
        (
            "reads the width, the bounds and the special values of a float",
            Annotated[
                float, Width(32), AllowNan(), AllowInfinity(), at.Ge(0), at.Lt(1.0)
            ],
            {
                "shape": "float",
                "width": 32,
                "allow_nan": True,
                "allow_infinity": True,
                "min": 0.0,
                "max": next_down(1.0, 32),
            },
        ),
        (
            "reads an exclusive lower bound of a float one step inside",
            Annotated[float, at.Gt(0.0)],
            {"shape": "float", "width": 64, "min": 5e-324},
        ),
        ("reads a str as a string", str, STRING),
        (
            "reads the sizes and the alphabet of a string",
            Annotated[str, at.MinLen(1), at.MaxLen(5), Alphabet("ab")],
            {"shape": "string", "min_size": 1, "max_size": 5, "alphabet": "ab"},
        ),
        (
            "reads the pattern of a string",
            Annotated[str, Pattern("[a-z]+")],
            {"shape": "string", "pattern": "[a-z]+"},
        ),
        (
            "reads a str with Char as a char",
            Annotated[str, Char(), Alphabet("xyz")],
            {"shape": "char", "alphabet": "xyz"},
        ),
        ("reads bytes", bytes, {"shape": "bytes"}),
        (
            "reads the sizes of bytes",
            Annotated[bytes, at.Len(2, 4)],
            {"shape": "bytes", "min_size": 2, "max_size": 4},
        ),
        ("reads a list", list[int], {"shape": "list", "of": INT}),
        (
            "reads the sizes of a list",
            Annotated[list[int], at.MaxLen(2)],
            {"shape": "list", "of": INT, "max_size": 2},
        ),
        (
            "reads a list of one size as a fixed-list",
            Annotated[list[int], at.Len(3, 3)],
            {"shape": "fixed-list", "of": INT, "size": 3},
        ),
        (
            "reads a tuple of one type as a list",
            tuple[int, ...],
            {"shape": "list", "of": INT},
        ),
        (
            "reads a tuple of fields as a record",
            tuple[int, str],
            {"shape": "record", "fields": [["0", INT], ["1", STRING]]},
        ),
        ("reads a set", set[str], {"shape": "set", "of": STRING}),
        (
            "reads the sizes of a frozenset",
            Annotated[frozenset[int], at.MinLen(1)],
            {"shape": "set", "of": INT, "min_size": 1},
        ),
        (
            "reads a dict as a map",
            dict[str, int],
            {"shape": "map", "key": STRING, "of": INT},
        ),
        (
            "reads the sizes of a map",
            Annotated[dict[str, bool], at.Len(0, 3)],
            {"shape": "map", "key": STRING, "of": BOOL, "min_size": 0, "max_size": 3},
        ),
        (
            "reads the keys of a map of a hashable tuple",
            dict[tuple[Annotated[str, at.MinLen(1)], int | None, Literal["a"]], int],
            {
                "shape": "map",
                "key": {
                    "shape": "record",
                    "fields": [
                        ["0", {"shape": "string", "min_size": 1}],
                        ["1", {"shape": "optional", "of": INT}],
                        [
                            "2",
                            {
                                "shape": "literal",
                                "values": [{"type": "string", "value": "a"}],
                            },
                        ],
                    ],
                },
                "of": INT,
            },
        ),
        ("reads an optional", int | None, {"shape": "optional", "of": INT}),
        (
            "reads the constraints of an optional as the constraints of its value",
            Annotated[int | None, at.Ge(0)],
            {"shape": "optional", "of": {**INT, "min": 0}},
        ),
        (
            "reads an optional of a union as an optional of an enum",
            int | str | None,
            {
                "shape": "optional",
                "of": {"shape": "enum", "variants": [["int", INT], ["str", STRING]]},
            },
        ),
        (
            "reads a union as an enum of its classes",
            int | str,
            {"shape": "enum", "variants": [["int", INT], ["str", STRING]]},
        ),
        (
            "reads a union of variants with and without payloads",
            Pending | Paid | Refunded,
            {
                "shape": "enum",
                "variants": [["Pending", None], ["Paid", INT], ["Refunded", STRING]],
            },
        ),
        (
            "reads a union of the two address classes as an ip-address",
            IPv4Address | IPv6Address,
            {"shape": "ip-address"},
        ),
        (
            "reads the version of an ip-address of either version",
            Annotated[IPv4Address | IPv6Address, Version(6)],
            {"shape": "ip-address", "version": 6},
        ),
        (
            "reads a Literal as a literal of its values",
            Literal["a", 1],
            {
                "shape": "literal",
                "values": [
                    {"type": "string", "value": "a"},
                    {"type": "int", "value": 1},
                ],
            },
        ),
        (
            "reads an Enum as an enum of its members",
            Colour,
            {"shape": "enum", "variants": [["RED", None], ["GREEN", None]]},
        ),
        (
            "reads a dataclass as a record of its fields",
            Point,
            {"shape": "record", "fields": [["x", INT], ["y", INT]]},
        ),
        (
            "reads the fields of a dataclass that its constructor takes",
            Counted,
            {"shape": "record", "fields": [["count", INT]]},
        ),
        (
            "reads a NamedTuple as a record of its fields",
            Pair,
            {"shape": "record", "fields": [["a", INT], ["b", STRING]]},
        ),
        (
            "reads a TypedDict as a record of its keys",
            Movie,
            {"shape": "record", "fields": [["title", STRING], ["year", INT]]},
        ),
        (
            "reads a nested record",
            Order,
            {
                "shape": "record",
                "fields": [
                    ["id", {"shape": "int", "width": 32, "signed": False}],
                    [
                        "lines",
                        {
                            "shape": "list",
                            "of": {
                                "shape": "record",
                                "fields": [
                                    ["sku", STRING],
                                    [
                                        "qty",
                                        {"shape": "int", "width": 32, "signed": True},
                                    ],
                                ],
                            },
                        },
                    ],
                    ["note", {"shape": "optional", "of": STRING}],
                ],
            },
        ),
        ("reads a subclass of int as an int", Paid, INT),
        ("reads a NewType as its supertype", UserId, INT),
        ("reads a date", date, {"shape": "date"}),
        (
            "reads the bounds of a date",
            Annotated[date, at.Ge(date(2000, 1, 1)), at.Lt(date(2001, 1, 1))],
            {"shape": "date", "min": "2000-01-01", "max": "2000-12-31"},
        ),
        (
            "reads a time as a time-of-day at us",
            time,
            {"shape": "time-of-day", "unit": "us"},
        ),
        (
            "reads the unit and an exclusive bound of a time",
            Annotated[time, Unit("s"), at.Gt(time(9))],
            {"shape": "time-of-day", "unit": "s", "min": "09:00:01.000000"},
        ),
        (
            "reads a timedelta as a duration at us",
            timedelta,
            {"shape": "duration", "unit": "us"},
        ),
        (
            "reads the bounds of a duration in its units",
            Annotated[
                timedelta, Unit("ms"), at.Ge(timedelta(0)), at.Le(timedelta(seconds=1))
            ],
            {"shape": "duration", "unit": "ms", "min": 0, "max": 1000},
        ),
        ("reads a timezone as an offset", timezone, {"shape": "offset"}),
        (
            "reads the bounds of an offset in seconds",
            Annotated[timezone, at.Ge(timedelta(hours=-1)), at.Lt(timedelta(0))],
            {"shape": "offset", "min": -3600, "max": -1},
        ),
        (
            "reads a bound of an offset given as a timezone",
            Annotated[timezone, at.Le(cast("Any", timezone(timedelta(hours=2))))],
            {"shape": "offset", "max": 7200},
        ),
        (
            "reads a datetime without a zone as a local-date-time",
            Annotated[datetime, at.Timezone(None), at.Ge(datetime(2000, 1, 1))],
            {
                "shape": "local-date-time",
                "unit": "us",
                "min": "2000-01-01T00:00:00.000000",
            },
        ),
        (
            "reads a datetime in UTC as an instant",
            Annotated[
                datetime, at.Timezone(UTC), at.Gt(datetime(2000, 1, 1, tzinfo=UTC))
            ],
            {"shape": "instant", "unit": "us", "min": "2000-01-01T00:00:00.000001Z"},
        ),
        (
            "reads a datetime in any zone as a zoned-date-time",
            Annotated[datetime, at.Timezone(...), Unit("ms")],
            {"shape": "zoned-date-time", "unit": "ms"},
        ),
        ("reads a ZoneInfo as a zone", ZoneInfo, {"shape": "zone"}),
        ("reads a UUID", UUID, {"shape": "uuid"}),
        (
            "reads an IPv4Address as an ip-address of version 4",
            IPv4Address,
            {"shape": "ip-address", "version": 4},
        ),
        (
            "reads an IPv6Address with its version",
            Annotated[IPv6Address, Version(6)],
            {"shape": "ip-address", "version": 6},
        ),
        (
            "reads a Decimal of a scale with its bounds",
            Annotated[Decimal, Scale(2), at.Ge(Decimal("0.01")), at.Lt(10)],
            {"shape": "decimal", "scale": 2, "min": "0.01", "max": "9.99"},
        ),
        (
            "reads a bound of a Decimal given as text",
            Annotated[Decimal, Scale(1), at.Le("2.5")],
            {"shape": "decimal", "scale": 1, "max": "2.5"},
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_reads_the_shape_of_a_type(
        self, seat: Collector, give: object, want: Node
    ) -> None:
        """The root shape is the shape of the type."""
        check.equal(seat, root(give), want, "derive returns the shape")

    def test_reads_a_class_that_refers_to_itself_as_a_definition(
        self, seat: Collector
    ) -> None:
        """A tree has trees."""
        name = qualified(Tree)
        definition: Node = {
            "shape": "record",
            "fields": [
                ["value", {"shape": "int", "width": 32, "signed": True}],
                ["children", {"shape": "list", "of": {"shape": "ref", "name": name}}],
            ],
        }
        check.equal(
            seat,
            root(Tree),
            {"shape": "ref", "name": name, "definitions": {name: definition}},
            "the root is a ref to the definition",
        )

    def test_reads_a_second_occurrence_of_a_definition_as_a_ref(
        self, seat: Collector
    ) -> None:
        """A forest has two trees."""
        ref = {"shape": "ref", "name": qualified(Tree)}
        check.equal(
            seat,
            root(Forest)["fields"],
            [["first", ref], ["second", ref]],
            "both fields are refs",
        )

    def test_reads_a_type_that_using_gives_a_generator_as_a_ref(
        self, seat: Collector
    ) -> None:
        """The fields of a point are ints."""
        derived = read(Point, using={int: DIGITS})
        ref = {"shape": "ref", "name": "builtins.int"}
        check.equal(
            seat,
            [derived.root, derived.externals, derived.external_paths],
            [
                {"shape": "record", "fields": [["x", ref], ["y", ref]]},
                {"builtins.int": DIGITS},
                ["Point.x", "Point.y"],
            ],
            "the read has the refs and their paths",
        )

    def test_reads_a_type_that_register_gives_a_generator_as_a_ref(
        self, seat: Collector
    ) -> None:
        """The type is a list of points."""
        registrations = Registrations(generators={Point: DIGITS})
        derived = derive(list[Point], registrations)
        check.equal(
            seat,
            [derived.root, derived.external_paths],
            [
                {"shape": "list", "of": {"shape": "ref", "name": qualified(Point)}},
                [f"{list[Point]!r}[]"],
            ],
            "the element is a ref",
        )

    def test_records_each_type_that_it_looks_up_while_the_registry_is_open(
        self, seat: Collector
    ) -> None:
        """The read looks up the point and its ints."""
        registrations = Registrations()
        derive(Point, registrations)
        check.equal(
            seat,
            registrations.consulted,
            {Point, int},
            "the registrations record the lookups",
        )

    def test_does_not_record_a_lookup_of_a_closed_registry(
        self, seat: Collector
    ) -> None:
        """The registry is closed."""
        registrations = Registrations(closed=True)
        derive(Point, registrations)
        check.is_empty(
            seat,
            registrations.consulted,
            "the registrations do not record a lookup",
        )

    def test_reads_registered_values_as_a_literal(self, seat: Collector) -> None:
        """A registration gives the status its values."""
        written = [{"type": "string", "value": "paid"}]
        converter = literal_converter([Status("paid")], written)
        registrations = Registrations(values={Status: Literals(written, converter)})
        check.equal(
            seat,
            derive(Status, registrations).root,
            {"shape": "literal", "values": written},
            "the root is the literal",
        )

    def test_reads_the_type_whose_registration_it_skips_without_the_registration(
        self, seat: Collector
    ) -> None:
        """The read returns the base of a status."""
        written = [{"type": "string", "value": "paid"}]
        converter = literal_converter([Status("paid")], written)
        registrations = Registrations(
            generators={Status: DIGITS}, values={Status: Literals(written, converter)}
        )
        check.equal(
            seat,
            derive(Status, registrations, skip=Status).root,
            STRING,
            "the root is the shape of the base",
        )

    def test_reads_registered_variants_as_an_enum(self, seat: Collector) -> None:
        """The variants are a circle and a square."""
        registrations = Registrations(variants={Shape: (Circle, Square)})
        check.equal(
            seat,
            derive(Shape, registrations).root,
            {
                "shape": "enum",
                "variants": [
                    ["Circle", {"shape": "record", "fields": [["radius", INT]]}],
                    ["Square", {"shape": "record", "fields": [["side", INT]]}],
                ],
            },
            "the root is the enum",
        )

    faults: ClassVar[list[tuple[str, object, str]]] = [
        ("refuses Any", Any, "Any: Any is not a type that the reader reads"),
        (
            "refuses a class that is not a record",
            object,
            "object: object is not a type that the reader reads",
        ),
        (
            "refuses a generic that the reader does not read",
            type[int],
            "type[int]: type[int] is not a type that the reader reads",
        ),
        (
            "refuses a datetime without Timezone",
            datetime,
            "datetime: a datetime needs the constraint Timezone, because a value of "
            "the type datetime can have a zone or not",
        ),
        (
            "refuses a Timezone of one zone",
            Annotated[datetime, at.Timezone("Europe/Amsterdam")],
            "datetime: the reader maps Timezone of None, timezone.utc and ..., not "
            "'Europe/Amsterdam'",
        ),
        (
            "refuses a time at nanoseconds",
            Annotated[time, Unit("ns")],
            "time: a datetime, a time and a timedelta do not have values at ns, "
            "because their resolution is one microsecond",
        ),
        (
            "refuses a unit that the definition does not have",
            Annotated[timedelta, Unit(cast("Any", "min"))],
            "timedelta: the unit 'min' is not one of s, ms, us and ns",
        ),
        (
            "refuses a Decimal without Scale",
            Decimal,
            "Decimal: a Decimal needs the constraint Scale, because a default scale "
            "does not suit most domains",
        ),
        (
            "refuses an int of a width without a shape",
            Annotated[int, Width(12)],
            "int: an int of 12 bits does not have a shape",
        ),
        (
            "refuses a float of a width without a shape",
            Annotated[float, Width(16)],
            "float: a float of 16 bits does not have a shape",
        ),
        (
            "refuses two constraints of one bound",
            Annotated[int, at.Ge(1), at.Gt(0)],
            "int: the constraints Ge(ge=1) and Gt(gt=0) conflict",
        ),
        (
            "refuses a constraint of annotated-types that the reader does not map",
            Annotated[int, at.MultipleOf(2)],
            "int: MultipleOf(multiple_of=2) is not a constraint of prop or of "
            "annotated-types that the reader maps",
        ),
        (
            "refuses an argument of Annotated that is not a constraint",
            Annotated[int, "the count"],
            "int: 'the count' is not a constraint of prop or of annotated-types that "
            "the reader maps",
        ),
        (
            "refuses a bound of an int that is not an int",
            Annotated[int, at.Ge("1")],
            "int: the bound '1' is not an int",
        ),
        (
            "refuses a bound of a float that is NaN",
            Annotated[float, at.Le(math.nan)],
            "float: the bound nan is not a number",
        ),
        (
            "refuses a bound of a Decimal of a float",
            Annotated[Decimal, Scale(2), at.Ge(1.5)],
            "Decimal: the bound 1.5 is not a Decimal",
        ),
        (
            "refuses a bound of a Decimal of text that is not a number",
            Annotated[Decimal, Scale(2), at.Ge("x")],
            "Decimal: the bound 'x' is not a Decimal",
        ),
        (
            "refuses a bound of a Decimal that is not finite",
            Annotated[Decimal, Scale(2), at.Le(Decimal("Infinity"))],
            "Decimal: the bound Decimal('Infinity') is not a finite Decimal",
        ),
        (
            "refuses a bound of a date that is a datetime",
            Annotated[date, at.Ge(datetime(2000, 1, 1))],
            "date: the bound datetime.datetime(2000, 1, 1, 0, 0) is not a date",
        ),
        (
            "refuses an exclusive bound of a date at the last day",
            Annotated[date, at.Gt(date.max)],
            "date: the bound datetime.date(9999, 12, 31) does not have a neighbour in "
            "the years 1 to 9999",
        ),
        (
            "refuses a bound of a time with a zone",
            Annotated[time, at.Ge(time(1, tzinfo=UTC))],
            "time: the bound datetime.time(1, 0, tzinfo=datetime.timezone.utc) is not "
            "a time without a zone",
        ),
        (
            "refuses an exclusive bound of a time at the last microsecond",
            Annotated[time, at.Gt(time(23, 59, 59, 999_999))],
            "time: the bound datetime.time(23, 59, 59, 999999) does not have a "
            "neighbour in the same day",
        ),
        (
            "refuses a bound of a local-date-time with a zone",
            Annotated[
                datetime, at.Timezone(None), at.Ge(datetime(2000, 1, 1, tzinfo=UTC))
            ],
            "datetime: the bound datetime.datetime(2000, 1, 1, 0, 0, "
            "tzinfo=datetime.timezone.utc) is not a datetime without a zone",
        ),
        (
            "refuses an exclusive bound of a local-date-time at the last instant",
            Annotated[datetime, at.Timezone(None), at.Gt(datetime.max)],
            "datetime: the bound datetime.datetime(9999, 12, 31, 23, 59, 59, 999999) "
            "does not have a neighbour in the years 1 to 9999",
        ),
        (
            "refuses a bound of an instant without a zone",
            Annotated[datetime, at.Timezone(UTC), at.Le(datetime(2000, 1, 1))],
            "datetime: the bound datetime.datetime(2000, 1, 1, 0, 0) is not a "
            "datetime with a zone",
        ),
        (
            "refuses an exclusive bound of an instant at the last instant",
            Annotated[
                datetime, at.Timezone(UTC), at.Gt(datetime.max.replace(tzinfo=UTC))
            ],
            "datetime: the bound datetime.datetime(9999, 12, 31, 23, 59, 59, 999999, "
            "tzinfo=datetime.timezone.utc) does not have a neighbour in the years 1 "
            "to 9999",
        ),
        (
            "refuses a bound of a duration that is not a timedelta",
            Annotated[timedelta, at.Ge(5)],
            "timedelta: the bound 5 is not a timedelta",
        ),
        (
            "refuses a bound of a duration finer than its unit",
            Annotated[timedelta, Unit("ms"), at.Ge(timedelta(microseconds=1))],
            "timedelta: the bound datetime.timedelta(microseconds=1) is not a whole "
            "number of the unit ms",
        ),
        (
            "refuses a bound of an offset that is not a timedelta",
            Annotated[timezone, at.Ge(5)],
            "timezone: the bound 5 is not a timedelta or a timezone",
        ),
        (
            "refuses a bound of an offset finer than a second",
            Annotated[timezone, at.Ge(timedelta(microseconds=1))],
            "timezone: the bound datetime.timedelta(microseconds=1) is not a whole "
            "number of seconds",
        ),
        (
            "refuses a Literal of a value without a typed literal",
            cast("Any", Literal)[chr(0xD800)],
            f"{cast('Any', Literal)[chr(0xD800)]!r}: the value '\\ud800' does not "
            "have a typed literal",
        ),
        (
            "refuses an IPv4Address of version 6",
            Annotated[IPv4Address, Version(6)],
            "IPv4Address: an IPv4Address is not an address of version 6",
        ),
        (
            "refuses a TypedDict with a key that is not required",
            Draft,
            "Draft: the keys title of the TypedDict are not required",
        ),
        (
            "refuses a record without fields",
            Pending,
            "Pending: a record without fields does not have a shape",
        ),
        (
            "refuses a tuple without fields",
            tuple[()],
            "tuple[()]: a record without fields does not have a shape",
        ),
        (
            "refuses an Enum without members",
            Empty,
            "Empty: Empty does not have a member",
        ),
        (
            "refuses a union with a member that is not a class",
            int | list[int],
            "int | list[int]: the variant list[int] is not a class, so it does not "
            "have a name",
        ),
        (
            "refuses a set of values that are not hashable",
            set[list[int]],
            "set[list[int]][]: the values of list[int] are not hashable",
        ),
        (
            "refuses a dict with keys of a tuple of a list",
            dict[tuple[int, list[int]], int],
            "dict[tuple[int, list[int]], int].key: the values of tuple[int, "
            "list[int]] are not hashable",
        ),
        (
            "refuses a dict with keys of a union of a list",
            dict[int | list[int], int],
            "dict[int | list[int], int].key: the values of int | list[int] are not "
            "hashable",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in faults], ids=[t[0] for t in faults]
    )
    def test_raises_a_fault_at_the_part_that_the_reader_does_not_read(
        self, seat: Collector, give: object, want: str
    ) -> None:
        """The fault has the part and the reason."""
        check.equal(
            seat,
            refusal(seat, lambda: read(give), FaultError),
            want,
            "the fault has the part and the reason",
        )

    untaken: ClassVar[list[tuple[str, object, str]]] = [
        ("refuses a size of an int", Annotated[int, at.MinLen(1)], "int"),
        ("refuses a bound of a bool", Annotated[bool, at.Ge(0)], "a bool"),
        ("refuses a bound of an Enum", Annotated[Colour, at.Ge(0)], "an Enum"),
        (
            "refuses a bound of a Literal",
            Annotated[Literal["a"], at.Ge(0)],
            "a Literal",
        ),
        ("refuses a bound of a list", Annotated[list[int], at.Ge(0)], "a list"),
        ("refuses a bound of a set", Annotated[set[int], at.Ge(0)], "a set"),
        ("refuses a bound of a dict", Annotated[dict[int, int], at.Ge(0)], "a dict"),
        ("refuses a bound of a union", Annotated[int | str, at.Ge(0)], "a union"),
        (
            "refuses a size of an ip-address",
            Annotated[IPv4Address | IPv6Address, at.MinLen(1)],
            "an IP address",
        ),
        (
            "refuses a bound of a tuple of fields",
            Annotated[tuple[int, str], at.Ge(0)],
            "a tuple of fields",
        ),
        ("refuses a bound of a record", Annotated[Point, at.Ge(0)], "Point"),
    ]

    @pytest.mark.parametrize(
        ("give", "what"), [t[1:] for t in untaken], ids=[t[0] for t in untaken]
    )
    def test_raises_a_fault_for_a_constraint_that_the_part_does_not_take(
        self, seat: Collector, give: object, what: str
    ) -> None:
        """The fault has the part and the constraint."""
        text = refusal(seat, lambda: read(give), FaultError)
        check.has_suffix(
            seat, text, f"does not apply to {what}", "the fault ends with the part"
        )

    def test_raises_a_fault_for_a_constraint_of_a_ref_to_a_class_that_refers_to_itself(
        self, seat: Collector
    ) -> None:
        """The link of the chain has a bound."""
        text = refusal(seat, lambda: read(Chain), FaultError)
        check.equal(
            seat,
            text,
            "Chain.link: the constraint Ge(ge=1) does not apply to a type that "
            "refers to itself",
            "the fault is at the link",
        )

    def test_raises_a_fault_for_a_constraint_of_a_type_of_a_generator(
        self, seat: Collector
    ) -> None:
        """The int has a bound, and using generates the int."""
        text = refusal(
            seat,
            lambda: read(Annotated[int, at.Ge(0)], using={int: DIGITS}),
            FaultError,
        )
        check.has_suffix(
            seat,
            text,
            "does not apply to a type that a generator generates",
            "the fault has the reason",
        )

    def test_raises_a_fault_for_a_constraint_of_a_type_of_registered_values(
        self, seat: Collector
    ) -> None:
        """The status has a size."""
        written = [{"type": "string", "value": "paid"}]
        converter = literal_converter([Status("paid")], written)
        registrations = Registrations(values={Status: Literals(written, converter)})
        text = refusal(
            seat,
            lambda: derive(Annotated[Status, at.MinLen(1)], registrations),
            FaultError,
        )
        check.has_suffix(
            seat,
            text,
            "does not apply to a type of registered values",
            "the fault has the reason",
        )

    def test_raises_a_fault_for_a_constraint_of_a_type_of_registered_variants(
        self, seat: Collector
    ) -> None:
        """The shape has a bound."""
        registrations = Registrations(variants={Shape: (Circle, Square)})
        text = refusal(
            seat, lambda: derive(Annotated[Shape, at.Ge(0)], registrations), FaultError
        )
        check.has_suffix(
            seat,
            text,
            "does not apply to a type of registered variants",
            "the fault has the reason",
        )

    def test_raises_a_fault_for_annotations_that_do_not_resolve(
        self, seat: Collector
    ) -> None:
        """The fault has the class whose annotations do not resolve."""
        check.has_prefix(
            seat,
            refusal(seat, lambda: read(UNRESOLVED), FaultError),
            "Unresolved: the annotations of Unresolved do not resolve:",
            "the fault has the class",
        )

    def test_raises_a_fault_for_two_variant_classes_of_one_name(
        self, seat: Collector
    ) -> None:
        """Two classes have the name Twin."""
        registrations = Registrations(variants={Shape: TWINS})
        check.equal(
            seat,
            refusal(seat, lambda: derive(Shape, registrations), FaultError),
            "Shape: two variants are named Twin",
            "the fault has the name",
        )

    def test_raises_a_fault_for_a_dict_with_keys_of_an_unhashable_record(
        self, seat: Collector
    ) -> None:
        """The dataclass is not frozen."""
        t = dict[Unhashable, int]
        check.equal(
            seat,
            refusal(seat, lambda: read(t), FaultError),
            f"{t!r}.key: the values of {Unhashable!r} are not hashable",
            "the fault is at the key",
        )

    def test_converts_a_dataclass_both_ways(self, seat: Collector) -> None:
        """The value is a point."""
        converter = converted(Point)
        neutral = Fields((("x", 1), ("y", 2)))
        check.equal(seat, converter.to(neutral), Point(1, 2), "to returns the point")
        same(
            seat, converter.back(Point(1, 2)), neutral, "back returns the neutral value"
        )
        unchanged(seat, converter, (1, 2))

    def test_converts_a_named_tuple_both_ways(self, seat: Collector) -> None:
        """The value is a pair."""
        converter = converted(Pair)
        neutral = Fields((("a", 1), ("b", "x")))
        check.equal(seat, converter.to(neutral), Pair(1, "x"), "to returns the pair")
        same(
            seat,
            converter.back(Pair(1, "x")),
            neutral,
            "back returns the neutral value",
        )
        unchanged(seat, converter, (1, "x"))

    def test_converts_a_typed_dict_both_ways(self, seat: Collector) -> None:
        """The value is a movie."""
        converter = converted(Movie)
        neutral = Fields((("title", "x"), ("year", 1)))
        movie = {"title": "x", "year": 1}
        check.equal(seat, converter.to(neutral), movie, "to returns the dict")
        same(seat, converter.back(movie), neutral, "back returns the neutral value")
        unchanged(seat, converter, {"title": "x"})
        unchanged(seat, converter, ["x", 1])

    def test_converts_a_tuple_of_fields_both_ways(self, seat: Collector) -> None:
        """The value is a tuple of an int and a str."""
        converter = converted(tuple[int, str])
        neutral = Fields((("0", 1), ("1", "x")))
        check.equal(seat, converter.to(neutral), (1, "x"), "to returns the tuple")
        same(seat, converter.back((1, "x")), neutral, "back returns the neutral value")
        unchanged(seat, converter, (1,))
        unchanged(seat, converter, [1, "x"])

    def test_converts_a_list_and_a_tuple_of_one_type_both_ways(
        self, seat: Collector
    ) -> None:
        """Each function back takes its own type."""
        as_list = converted(list[int])
        as_tuple = converted(tuple[int, ...])
        check.equal(
            seat,
            [
                as_list.to([1, 2]),
                as_tuple.to([1, 2]),
                as_list.back([1, 2]),
                as_tuple.back((1, 2)),
            ],
            [[1, 2], (1, 2), [1, 2], [1, 2]],
            "the converters convert both ways",
        )
        unchanged(seat, as_list, (1, 2))

    def test_converts_a_set_back_in_the_order_of_the_canonical_texts(
        self, seat: Collector
    ) -> None:
        """The set has two strings."""
        converter = converted(set[str])
        check.equal(
            seat,
            [converter.to(["b", "a"]), converter.back({"b", "a"})],
            [{"a", "b"}, ["a", "b"]],
            "the converter converts both ways",
        )
        unchanged(seat, converter, ["a"])

    def test_converts_a_frozenset_to_a_frozenset(self, seat: Collector) -> None:
        """The value is a frozenset."""
        check.equal(
            seat,
            converted(frozenset[int]).to([1]),
            frozenset({1}),
            "to returns a frozenset",
        )

    def test_converts_a_dict_both_ways(self, seat: Collector) -> None:
        """The dict has one entry."""
        converter = converted(dict[str, int])
        neutral = Pairs((("a", 1),))
        check.equal(seat, converter.to(neutral), {"a": 1}, "to returns the dict")
        same(seat, converter.back({"a": 1}), neutral, "back returns the neutral value")
        unchanged(seat, converter, [("a", 1)])

    def test_converts_an_optional_both_ways(self, seat: Collector) -> None:
        """The values are None and 5."""
        converter = converted(int | None)
        check.equal(
            seat,
            [
                converter.to(None),
                converter.to(5),
                converter.back(None),
                converter.back(5),
            ],
            [None, 5, None, 5],
            "the converter converts both ways",
        )

    def test_converts_a_union_of_variants_both_ways(self, seat: Collector) -> None:
        """One variant does not have a payload, and another variant has one."""
        converter = converted(Pending | Paid | Refunded)
        paid = converter.to(Neutral("Paid", 5))
        check.equal(
            seat,
            [converter.to(Neutral("Pending")), type(paid), paid],
            [Pending(), Paid, Paid(5)],
            "to returns the variants",
        )
        same(
            seat,
            converter.back(Pending()),
            Neutral("Pending"),
            "back returns the variant without a payload",
        )
        same(
            seat,
            converter.back(Paid(5)),
            Neutral("Paid", 5),
            "back returns the variant with a payload",
        )
        unchanged(seat, converter, 5)

    def test_converts_an_enum_both_ways(self, seat: Collector) -> None:
        """The value is a colour."""
        converter = converted(Colour)
        check.equal(
            seat, converter.to(Neutral("RED")), Colour.RED, "to returns the member"
        )
        same(
            seat,
            converter.back(Colour.GREEN),
            Neutral("GREEN"),
            "back returns the neutral value",
        )
        unchanged(seat, converter, 1)

    def test_converts_a_literal_both_ways(self, seat: Collector) -> None:
        """The literal has a text and an int."""
        converter = converted(Literal["a", 1])
        check.equal(
            seat,
            [converter.to("a"), converter.to(1), converter.back("a")],
            ["a", 1, "a"],
            "the converter converts both ways",
        )
        unchanged(seat, converter, "b")

    def test_converts_a_subclass_of_int_to_the_subclass(self, seat: Collector) -> None:
        """The value is an amount."""
        converter = converted(Paid)
        got = converter.to(5)
        check.equal(seat, [type(got), got], [Paid, Paid(5)], "to returns the amount")
        unchanged(seat, converter, Paid(5))

    def test_converts_a_class_that_refers_to_itself_both_ways(
        self, seat: Collector
    ) -> None:
        """The tree does not have children."""
        converter = converted(Tree)
        neutral = Fields((("value", 1), ("children", [])))
        check.equal(seat, converter.to(neutral), Tree(1, []), "to returns the tree")
        same(
            seat, converter.back(Tree(1, [])), neutral, "back returns the neutral value"
        )
