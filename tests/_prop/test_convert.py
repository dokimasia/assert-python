"""The spec of _prop/convert.py tests the conversion of the values of shapes."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from ipaddress import IPv4Address, IPv6Address
from typing import Any, ClassVar
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from dokimi_assert import check
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._prop.convert import (
    IDENTITY,
    Converter,
    Variant,
    WallTime,
    converter_of,
    date_converter,
    decimal_converter,
    duration_converter,
    instant_converter,
    ip_converter,
    local_converter,
    offset_converter,
    plain_of,
    time_converter,
    uuid_converter,
    zone_converter,
    zone_of,
    zoned_converter,
)
from dokimi_assert._prop.engine.inverse import CannotInvertError
from dokimi_assert._prop.engine.value import Fields, Pairs, canonical
from dokimi_assert._prop.engine.value import Variant as Neutral
from dokimi_assert.seat import Collector
from helpers import refusal

#: A zone of the definition.
AMSTERDAM = ZoneInfo("Europe/Amsterdam")


def two(first: str, a: object, second: str, b: object) -> Fields:
    """Return the neutral value of a shape of two named parts."""
    return Fields(((first, a), (second, b)))


def instant(seconds: int, units: int) -> Fields:
    """Return the neutral value of an instant."""
    return two("seconds", seconds, "units", units)


def unchanged(seat: Collector, converter: Converter, value: object) -> None:
    """Check that back returns a value of another type unchanged."""
    check.is_true(
        seat, converter.back(value) is value, "back returns the value unchanged"
    )


class TestConverter:
    """Converter has the two conversions of the values of one shape."""

    def test_keeps_both_functions(self, seat: Collector) -> None:
        """The functions are str and int."""
        converter = Converter(str, int)
        check.equal(
            seat,
            [converter.to(1), converter.back("2")],
            ["1", 2],
            "the converter keeps both functions",
        )


class TestIdentity:
    """IDENTITY converts a value to itself in both directions."""

    def test_returns_each_value_itself_both_ways(self, seat: Collector) -> None:
        """Both functions return the same object."""
        value = object()
        check.is_true(
            seat,
            IDENTITY.to(value) is value and IDENTITY.back(value) is value,
            "both functions return the value itself",
        )


class TestVariant:
    """Variant is the value of an enum that of_shape decodes."""

    def test_does_not_have_a_payload_by_default(self, seat: Collector) -> None:
        """The variant has a name alone."""
        check.is_none(
            seat,
            Variant("pending").payload,
            "the variant does not have a payload",
        )


class TestWallTime:
    """WallTime is a wall time in a zone."""

    def test_keeps_its_wall_time_and_its_zone(self, seat: Collector) -> None:
        """The wall time keeps both fields."""
        wall = WallTime(datetime(2026, 3, 29, 2, 30), AMSTERDAM)
        check.equal(
            seat,
            [wall.local, wall.zone],
            [datetime(2026, 3, 29, 2, 30), AMSTERDAM],
            "the wall time keeps its local time and its zone",
        )


class TestDateConverter:
    """date_converter converts a date to its days since 1970-01-01."""

    tests: ClassVar[list[tuple[str, int, date]]] = [
        ("converts the first day", 0, date(1970, 1, 1)),
        ("converts a day before the first", -1, date(1969, 12, 31)),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_converts_both_ways(self, seat: Collector, give: int, want: date) -> None:
        """The converter converts the days and the date."""
        converter = date_converter()
        check.equal(
            seat,
            [converter.to(give), converter.back(want)],
            [want, give],
            "the converter converts both ways",
        )

    def test_returns_a_datetime_unchanged(self, seat: Collector) -> None:
        """A datetime is a date of another shape."""
        unchanged(seat, date_converter(), datetime(1970, 1, 1))


class TestInstantConverter:
    """instant_converter converts an instant at a unit."""

    tests: ClassVar[list[tuple[str, str, Fields, datetime]]] = [
        (
            "converts an instant at microseconds",
            "us",
            instant(1, 5),
            datetime(1970, 1, 1, 0, 0, 1, 5, UTC),
        ),
        (
            "converts an instant at milliseconds",
            "ms",
            instant(1, 5),
            datetime(1970, 1, 1, 0, 0, 1, 5000, UTC),
        ),
        (
            "converts an instant before 1970",
            "us",
            instant(-1, 999_999),
            datetime(1969, 12, 31, 23, 59, 59, 999_999, UTC),
        ),
    ]

    @pytest.mark.parametrize(
        ("unit", "give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_converts_both_ways(
        self, seat: Collector, unit: str, give: Fields, want: datetime
    ) -> None:
        """The converter converts the datetime and its neutral value."""
        converter = instant_converter(unit)
        check.equal(seat, converter.to(give), want, "to returns the datetime")
        check.equal(
            seat,
            canonical(converter.back(want)),
            canonical(give),
            "back returns the neutral value",
        )

    def test_converts_an_instant_at_nanoseconds_to_an_int(
        self, seat: Collector
    ) -> None:
        """The int is the nanoseconds since 1970."""
        converter = instant_converter("ns")
        check.equal(
            seat, converter.to(instant(1, 5)), 1_000_000_005, "to returns the int"
        )
        check.equal(
            seat,
            canonical(converter.back(1_000_000_005)),
            canonical(instant(1, 5)),
            "back returns the neutral value",
        )

    def test_returns_a_value_of_another_type_at_nanoseconds_unchanged(
        self, seat: Collector
    ) -> None:
        """A bool is not an int of nanoseconds."""
        unchanged(seat, instant_converter("ns"), True)

    def test_returns_a_datetime_without_a_zone_unchanged(self, seat: Collector) -> None:
        """A local datetime is not an instant."""
        unchanged(seat, instant_converter("us"), datetime(1970, 1, 1))

    def test_raises_cannot_invert_error_for_a_datetime_finer_than_the_unit(
        self, seat: Collector
    ) -> None:
        """The datetime has one microsecond, and the unit is ms."""
        value = datetime(1970, 1, 1, 0, 0, 0, 1, UTC)
        check.contains(
            seat,
            refusal(
                seat, lambda: instant_converter("ms").back(value), CannotInvertError
            ),
            "is finer than the unit ms",
            "the error has the reason",
        )


class TestTimeConverter:
    """time_converter converts a time of day at a unit."""

    def test_converts_both_ways(self, seat: Collector) -> None:
        """The time is one hour and a microsecond."""
        converter = time_converter("us")
        check.equal(
            seat,
            [converter.to(3_600_000_001), converter.back(time(1, 0, 0, 1))],
            [time(1, 0, 0, 1), 3_600_000_001],
            "the converter converts both ways",
        )

    def test_returns_a_time_with_a_zone_unchanged(self, seat: Collector) -> None:
        """A time of day does not have a zone."""
        unchanged(seat, time_converter("us"), time(1, tzinfo=UTC))

    def test_raises_cannot_invert_error_for_a_time_finer_than_the_unit(
        self, seat: Collector
    ) -> None:
        """The time has a microsecond, and the unit is s."""
        refusal(
            seat, lambda: time_converter("s").back(time(0, 0, 0, 1)), CannotInvertError
        )


class TestLocalConverter:
    """local_converter converts a date and a time of day without a zone."""

    def test_converts_both_ways(self, seat: Collector) -> None:
        """The value is five microseconds into the second day."""
        converter = local_converter("us")
        neutral = two("date", 1, "time-of-day", 5)
        value = datetime(1970, 1, 2, 0, 0, 0, 5)
        check.equal(seat, converter.to(neutral), value, "to returns the datetime")
        check.equal(
            seat,
            canonical(converter.back(value)),
            canonical(neutral),
            "back returns the neutral value",
        )

    def test_returns_a_datetime_with_a_zone_unchanged(self, seat: Collector) -> None:
        """An instant is not a local datetime."""
        unchanged(seat, local_converter("us"), datetime(1970, 1, 2, tzinfo=UTC))


class TestDurationConverter:
    """duration_converter converts a duration at a unit."""

    def test_returns_the_identity_at_nanoseconds(self, seat: Collector) -> None:
        """A duration at ns is an int of nanoseconds."""
        check.is_true(
            seat, duration_converter("ns") is IDENTITY, "the converter is IDENTITY"
        )

    def test_converts_both_ways(self, seat: Collector) -> None:
        """The durations are five microseconds and a second."""
        converter = duration_converter("us")
        check.equal(
            seat,
            [converter.to(5), converter.back(timedelta(seconds=1))],
            [timedelta(microseconds=5), 1_000_000],
            "the converter converts both ways",
        )

    def test_returns_a_value_of_another_type_unchanged(self, seat: Collector) -> None:
        """An int is the neutral value."""
        unchanged(seat, duration_converter("us"), 5)

    def test_raises_cannot_invert_error_for_a_timedelta_finer_than_the_unit(
        self, seat: Collector
    ) -> None:
        """The timedelta has a microsecond, and the unit is ms."""
        refusal(
            seat,
            lambda: duration_converter("ms").back(timedelta(microseconds=1)),
            CannotInvertError,
        )


class TestOffsetConverter:
    """offset_converter converts an offset from UTC to a timezone."""

    def test_converts_both_ways(self, seat: Collector) -> None:
        """The offsets are one hour east and five hours west."""
        converter = offset_converter()
        check.equal(
            seat,
            [converter.to(3600), converter.back(timezone(timedelta(hours=-5)))],
            [timezone(timedelta(hours=1)), -18000],
            "the converter converts both ways",
        )

    def test_returns_a_value_of_another_type_unchanged(self, seat: Collector) -> None:
        """An int is the neutral value."""
        unchanged(seat, offset_converter(), 3600)

    def test_raises_cannot_invert_error_for_an_offset_finer_than_a_second(
        self, seat: Collector
    ) -> None:
        """The offset is a microsecond."""
        offset = timezone(timedelta(microseconds=1))
        refusal(seat, lambda: offset_converter().back(offset), CannotInvertError)


class TestZoneOf:
    """zone_of returns the ZoneInfo of a zone name."""

    def test_returns_the_zone_of_a_name(self, seat: Collector) -> None:
        """The name is UTC."""
        check.equal(
            seat, zone_of("UTC", "zone"), ZoneInfo("UTC"), "zone_of returns the zone"
        )

    def test_raises_a_fault_at_the_part_for_a_zone_that_zoneinfo_does_not_find(
        self, seat: Collector
    ) -> None:
        """The fault has the name of the zone."""
        text = refusal(seat, lambda: zone_of("Nowhere/Land", "zone"), FaultError)
        check.has_prefix(
            seat,
            text,
            "zone: zoneinfo does not find the zone Nowhere/Land in the time-zone "
            "database of the system or in the package tzdata",
            "the fault is at the part",
        )


class TestZoneConverter:
    """zone_converter converts a zone to a ZoneInfo."""

    def test_converts_both_ways(self, seat: Collector) -> None:
        """The zone is Europe/Amsterdam."""
        converter = zone_converter("zone")
        check.equal(
            seat,
            [converter.to("Europe/Amsterdam"), converter.back(AMSTERDAM)],
            [AMSTERDAM, "Europe/Amsterdam"],
            "the converter converts both ways",
        )

    def test_returns_a_value_of_another_type_unchanged(self, seat: Collector) -> None:
        """A name is the neutral value."""
        unchanged(seat, zone_converter("zone"), "UTC")


class TestZonedConverter:
    """zoned_converter converts an instant in a zone."""

    def test_converts_both_ways(self, seat: Collector) -> None:
        """The instant is the first instant of 1970 in Amsterdam."""
        converter = zoned_converter("us", "zone")
        neutral = two("instant", instant(0, 0), "zone", "Europe/Amsterdam")
        value = converter.to(neutral)
        check.equal(
            seat,
            [value, value.tzinfo],
            [datetime(1970, 1, 1, 1, tzinfo=AMSTERDAM), AMSTERDAM],
            "to returns the datetime in its zone",
        )
        check.equal(
            seat,
            canonical(converter.back(value)),
            canonical(neutral),
            "back returns the neutral value",
        )

    def test_returns_a_datetime_without_a_zone_info_unchanged(
        self, seat: Collector
    ) -> None:
        """timezone.utc is not a ZoneInfo."""
        unchanged(seat, zoned_converter("us", "zone"), datetime(1970, 1, 1, tzinfo=UTC))


class TestUuidConverter:
    """uuid_converter converts a UUID to its 16 bytes."""

    def test_converts_both_ways(self, seat: Collector) -> None:
        """The UUIDs are 0 and 1."""
        converter = uuid_converter()
        check.equal(
            seat,
            [converter.to(bytes(16)), converter.back(UUID(int=1))],
            [UUID(int=0), bytes(15) + b"\x01"],
            "the converter converts both ways",
        )

    def test_returns_a_value_of_another_type_unchanged(self, seat: Collector) -> None:
        """Bytes are the neutral value."""
        unchanged(seat, uuid_converter(), bytes(16))


class TestIpConverter:
    """ip_converter converts an IP address to its bytes."""

    def test_converts_both_ways(self, seat: Collector) -> None:
        """The addresses are of both versions."""
        converter = ip_converter()
        check.equal(
            seat,
            [
                converter.to(bytes([127, 0, 0, 1])),
                converter.to(bytes(16)),
                converter.back(IPv4Address("10.0.0.1")),
            ],
            [IPv4Address("127.0.0.1"), IPv6Address("::"), bytes([10, 0, 0, 1])],
            "the converter converts both ways",
        )

    def test_returns_a_value_of_another_type_unchanged(self, seat: Collector) -> None:
        """Bytes are the neutral value."""
        unchanged(seat, ip_converter(), bytes(4))


class TestDecimalConverter:
    """decimal_converter converts a Decimal of a scale to its unscaled integer."""

    tests: ClassVar[list[tuple[str, int, str]]] = [
        ("converts a positive value", 12345, "123.45"),
        ("converts a negative value", -5, "-0.05"),
        ("converts zero with every digit of the scale", 0, "0.00"),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_converts_to_a_decimal_of_the_scale(
        self, seat: Collector, give: int, want: str
    ) -> None:
        """The scale is 2."""
        check.equal(
            seat, str(decimal_converter(2).to(give)), want, "to returns the Decimal"
        )

    backs: ClassVar[list[tuple[str, str, int]]] = [
        ("converts a value of fewer digits back", "1.5", 150),
        ("converts a negative value back", "-0.05", -5),
        ("converts a value with trailing zeros back", "1.230", 123),
        ("converts an integer back", "100", 10000),
        ("converts a zero of any exponent back", "0E+50", 0),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in backs], ids=[t[0] for t in backs]
    )
    def test_converts_back_to_the_unscaled_integer(
        self, seat: Collector, give: str, want: int
    ) -> None:
        """The scale is 2."""
        check.equal(
            seat,
            decimal_converter(2).back(Decimal(give)),
            want,
            "back returns the unscaled integer",
        )

    def test_returns_a_value_that_is_not_finite_unchanged(
        self, seat: Collector
    ) -> None:
        """NaN does not have an unscaled integer."""
        unchanged(seat, decimal_converter(2), Decimal("NaN"))

    refusals: ClassVar[list[tuple[str, str, str]]] = [
        (
            "raises cannot invert error for more digits than the scale",
            "0.001",
            "has more digits than the scale of 2",
        ),
        (
            "raises cannot invert error for a value outside the 64-bit range",
            "1E+30",
            "is outside the 64-bit range",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_refuses_a_decimal_without_an_unscaled_integer(
        self, seat: Collector, give: str, want: str
    ) -> None:
        """The error has the reason."""
        text = refusal(
            seat, lambda: decimal_converter(2).back(Decimal(give)), CannotInvertError
        )
        check.has_suffix(seat, text, want, "the error ends with the reason")


class TestPlainOf:
    """plain_of returns the Python value of a decoded typed literal."""

    tests: ClassVar[list[tuple[str, object, object]]] = [
        ("returns a record as a dict", Fields((("a", 1),)), {"a": 1}),
        ("returns a map as a dict", Pairs(((1, "one"),)), {1: "one"}),
        ("returns a variant without a payload", Neutral("a"), Variant("a")),
        ("returns a variant with its payload", Neutral("a", 5), Variant("a", 5)),
        (
            "returns a list of the values of its elements",
            [Fields((("a", 1),))],
            [{"a": 1}],
        ),
        ("returns a scalar unchanged", 7, 7),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_python_value(
        self, seat: Collector, give: object, want: object
    ) -> None:
        """The value is the Python value of the literal."""
        check.equal(seat, plain_of(give), want, "plain_of returns the Python value")


def converter(node: dict[str, Any], **definitions: Any) -> Converter:
    """Return the converter of a shape file of a root shape and its definitions."""
    document = dict(node)
    if definitions:
        document["definitions"] = definitions
    return converter_of(document)


class TestConverterOf:
    """converter_of returns the converter of the root of a shape file."""

    def test_converts_a_scalar_unchanged(self, seat: Collector) -> None:
        """The shape is an int of 8 bits."""
        check.is_true(
            seat,
            converter({"shape": "int", "width": 8, "signed": True}) is IDENTITY,
            "the converter is IDENTITY",
        )

    def test_converts_a_list_both_ways(self, seat: Collector) -> None:
        """The function back converts a tuple to a list."""
        conv = converter({"shape": "list", "of": {"shape": "bool"}})
        check.equal(
            seat,
            [conv.to([True]), conv.back((False,))],
            [[True], [False]],
            "the converter converts both ways",
        )
        unchanged(seat, conv, "not a list")

    def test_converts_a_map_both_ways(self, seat: Collector) -> None:
        """The dict has one entry."""
        conv = converter(
            {"shape": "map", "key": {"shape": "string"}, "of": {"shape": "bool"}}
        )
        check.equal(
            seat, conv.to(Pairs((("a", True),))), {"a": True}, "to returns the dict"
        )
        check.equal(
            seat,
            canonical(conv.back({"a": True})),
            canonical(Pairs((("a", True),))),
            "back returns the pairs",
        )
        unchanged(seat, conv, ["not", "a", "dict"])

    keys: ClassVar[list[tuple[str, dict[str, Any], dict[str, Any]]]] = [
        ("refuses keys of a list", {"shape": "list", "of": {"shape": "bool"}}, {}),
        (
            "refuses keys of an optional record",
            {
                "shape": "optional",
                "of": {"shape": "record", "fields": [["a", {"shape": "bool"}]]},
            },
            {},
        ),
        (
            "refuses keys of an enum with a payload of a map",
            {
                "shape": "enum",
                "variants": [
                    [
                        "a",
                        {
                            "shape": "map",
                            "key": {"shape": "bool"},
                            "of": {"shape": "bool"},
                        },
                    ]
                ],
            },
            {},
        ),
        (
            "refuses keys of a literal of a list",
            {
                "shape": "literal",
                "values": [{"type": "list", "of": "int", "value": [1]}],
            },
            {},
        ),
        (
            "refuses keys of a ref to a set",
            {"shape": "ref", "name": "s"},
            {"s": {"shape": "set", "of": {"shape": "bool"}}},
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "definitions"), [t[1:] for t in keys], ids=[t[0] for t in keys]
    )
    def test_raises_a_fault_at_the_key_for_keys_that_a_dict_does_not_take(
        self, seat: Collector, give: dict[str, Any], definitions: dict[str, Any]
    ) -> None:
        """The fault is at the key shape."""
        node = {"shape": "map", "key": give, "of": {"shape": "bool"}}
        check.equal(
            seat,
            refusal(seat, lambda: converter(node, **definitions), FaultError),
            "key: the keys of the map decode to values that a dict does not take as "
            "keys",
            "the fault is at the key",
        )

    def test_takes_keys_of_a_recursive_definition_without_containers(
        self, seat: Collector
    ) -> None:
        """The key is an enum of an empty variant and an optional of itself."""
        node = {
            "shape": "map",
            "key": {"shape": "ref", "name": "k"},
            "of": {"shape": "bool"},
        }
        definitions = {
            "k": {
                "shape": "enum",
                "variants": [
                    ["end", None],
                    [
                        "more",
                        {"shape": "optional", "of": {"shape": "ref", "name": "k"}},
                    ],
                ],
            }
        }
        conv = converter(node, **definitions)
        check.equal(
            seat,
            conv.to(Pairs(((Neutral("end"), True),))),
            {Variant("end"): True},
            "to returns the dict",
        )

    def test_takes_keys_of_a_literal_of_scalars(self, seat: Collector) -> None:
        """The keys are a literal of strings."""
        node = {
            "shape": "map",
            "key": {"shape": "literal", "values": [{"type": "string", "value": "a"}]},
            "of": {"shape": "bool"},
        }
        check.equal(
            seat,
            converter(node).to(Pairs((("a", False),))),
            {"a": False},
            "to returns the dict",
        )

    def test_converts_an_optional_both_ways(self, seat: Collector) -> None:
        """The values are None and a UUID."""
        conv = converter({"shape": "optional", "of": {"shape": "uuid"}})
        check.equal(
            seat,
            [
                conv.to(None),
                conv.to(bytes(16)),
                conv.back(None),
                conv.back(UUID(int=0)),
            ],
            [None, UUID(int=0), None, bytes(16)],
            "the converter converts both ways",
        )

    def test_converts_a_record_both_ways(self, seat: Collector) -> None:
        """The Python value is a dict of the fields."""
        conv = converter({"shape": "record", "fields": [["a", {"shape": "bool"}]]})
        check.equal(
            seat, conv.to(Fields((("a", True),))), {"a": True}, "to returns the dict"
        )
        check.equal(
            seat,
            canonical(conv.back({"a": True})),
            canonical(Fields((("a", True),))),
            "back returns the fields",
        )

    pass_through: ClassVar[list[tuple[str, object]]] = [
        ("returns a dict of other fields unchanged", {"b": True}),
        ("returns a value that is not a dict unchanged", 5),
    ]

    @pytest.mark.parametrize(
        "give", [t[1] for t in pass_through], ids=[t[0] for t in pass_through]
    )
    def test_returns_a_value_that_is_not_a_record_unchanged(
        self, seat: Collector, give: object
    ) -> None:
        """The inverse refuses the value."""
        conv = converter({"shape": "record", "fields": [["a", {"shape": "bool"}]]})
        unchanged(seat, conv, give)

    def test_converts_an_enum_both_ways(self, seat: Collector) -> None:
        """A variant without a payload and one with a payload."""
        conv = converter(
            {"shape": "enum", "variants": [["a", None], ["b", {"shape": "uuid"}]]}
        )
        check.equal(
            seat,
            [conv.to(Neutral("a")), conv.to(Neutral("b", bytes(16)))],
            [Variant("a"), Variant("b", UUID(int=0))],
            "to returns the variants",
        )
        check.equal(
            seat,
            [
                canonical(conv.back(Variant("a"))),
                canonical(conv.back(Variant("b", UUID(int=0)))),
            ],
            [canonical(Neutral("a")), canonical(Neutral("b", bytes(16)))],
            "back returns the neutral variants",
        )

    variants: ClassVar[list[tuple[str, object]]] = [
        ("returns a variant of another name unchanged", Variant("z")),
        ("returns a value that is not a variant unchanged", "a"),
    ]

    @pytest.mark.parametrize(
        "give", [t[1] for t in variants], ids=[t[0] for t in variants]
    )
    def test_returns_a_value_that_is_not_a_variant_of_the_enum_unchanged(
        self, seat: Collector, give: object
    ) -> None:
        """The inverse refuses the value."""
        unchanged(seat, converter({"shape": "enum", "variants": [["a", None]]}), give)

    def test_converts_a_literal_both_ways(self, seat: Collector) -> None:
        """The function back finds the record by its canonical text."""
        record = {"type": "record", "fields": [["a", {"type": "int", "value": 1}]]}
        conv = converter(
            {"shape": "literal", "values": [{"type": "string", "value": "x"}, record]}
        )
        check.equal(
            seat,
            [conv.to(Fields((("a", 1),))), conv.back("x")],
            [{"a": 1}, "x"],
            "the converter converts both ways",
        )
        check.equal(
            seat,
            canonical(conv.back({"a": 1})),
            canonical(Fields((("a", 1),))),
            "back returns the decoded record",
        )

    def test_converts_a_ref_through_its_definition(self, seat: Collector) -> None:
        """The definition is a recursive optional."""
        conv = converter(
            {"shape": "ref", "name": "n"},
            n={"shape": "optional", "of": {"shape": "ref", "name": "n"}},
        )
        check.equal(
            seat,
            [conv.to(None), conv.back(None)],
            [None, None],
            "the converter converts both ways",
        )

    domains: ClassVar[list[tuple[str, dict[str, Any], object, object]]] = [
        ("converts a uuid", {"shape": "uuid"}, bytes(16), UUID(int=0)),
        ("converts an ip-address", {"shape": "ip-address"}, bytes(4), IPv4Address(0)),
        ("converts a decimal", {"shape": "decimal", "scale": 0}, 7, Decimal(7)),
        (
            "converts an instant",
            {"shape": "instant", "unit": "s"},
            instant(0, 0),
            datetime(1970, 1, 1, tzinfo=UTC),
        ),
        ("converts a date", {"shape": "date"}, 0, date(1970, 1, 1)),
        (
            "converts a time-of-day",
            {"shape": "time-of-day", "unit": "s"},
            1,
            time(0, 0, 1),
        ),
        (
            "converts a local-date-time",
            {"shape": "local-date-time", "unit": "s"},
            two("date", 0, "time-of-day", 0),
            datetime(1970, 1, 1),
        ),
        (
            "converts a duration",
            {"shape": "duration", "unit": "s"},
            1,
            timedelta(seconds=1),
        ),
        ("converts an offset", {"shape": "offset"}, 0, UTC),
        ("converts a zone", {"shape": "zone"}, "UTC", ZoneInfo("UTC")),
        (
            "converts a zoned-date-time",
            {"shape": "zoned-date-time", "unit": "s"},
            two("instant", instant(0, 0), "zone", "UTC"),
            datetime(1970, 1, 1, tzinfo=ZoneInfo("UTC")),
        ),
        (
            "converts a wall-time",
            {"shape": "wall-time", "unit": "s"},
            two("local-date-time", two("date", 0, "time-of-day", 0), "zone", "UTC"),
            WallTime(datetime(1970, 1, 1), ZoneInfo("UTC")),
        ),
        ("converts a string unchanged", {"shape": "string"}, "a", "a"),
    ]

    @pytest.mark.parametrize(
        ("node", "give", "want"), [t[1:] for t in domains], ids=[t[0] for t in domains]
    )
    def test_converts_a_domain_shape_both_ways(
        self, seat: Collector, node: dict[str, Any], give: object, want: object
    ) -> None:
        """The Python value and the neutral value."""
        conv = converter(node)
        check.equal(seat, conv.to(give), want, "to returns the Python value")
        check.equal(
            seat,
            canonical(conv.back(want)),
            canonical(give),
            "back returns the neutral value",
        )

    def test_returns_a_value_that_is_not_a_wall_time_unchanged(
        self, seat: Collector
    ) -> None:
        """A datetime is not a wall time."""
        unchanged(
            seat, converter({"shape": "wall-time", "unit": "s"}), datetime(1970, 1, 1)
        )

    nanoseconds: ClassVar[list[tuple[str, str]]] = [
        ("refuses a time-of-day at nanoseconds", "time-of-day"),
        ("refuses a local-date-time at nanoseconds", "local-date-time"),
        ("refuses a zoned-date-time at nanoseconds", "zoned-date-time"),
        ("refuses a wall-time at nanoseconds", "wall-time"),
    ]

    @pytest.mark.parametrize(
        "give", [t[1] for t in nanoseconds], ids=[t[0] for t in nanoseconds]
    )
    def test_raises_a_fault_for_a_time_at_nanoseconds(
        self, seat: Collector, give: str
    ) -> None:
        """The resolution of a datetime is one microsecond."""
        node = {"shape": "record", "fields": [["at", {"shape": give, "unit": "ns"}]]}
        check.equal(
            seat,
            refusal(seat, lambda: converter(node), FaultError),
            f"at: a {give} at nanoseconds does not have a Python value, because "
            "datetime has a resolution of one microsecond",
            "the fault has the reason",
        )
