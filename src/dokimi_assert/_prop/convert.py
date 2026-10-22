# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The Python values of shapes, and their conversion back to neutral values.

The engine decodes a shape to a neutral value. The function to of a converter
turns the neutral value into the value that a body receives. The function
back converts a Python value to a neutral value, and it returns a neutral
value unchanged. A typed literal of a store entry or of the draws option
decodes to a neutral value, so the inverse of the shape accepts it. back
also returns a value of any other type unchanged, and the inverse of the
shape then refuses the value.

of_shape decodes each shape of a shape file to these values:

==================================  =========================================
Shape                               Python value
==================================  =========================================
bool, int, float                    bool, int, float
char, string, bytes                 str, str, bytes
list, fixed-list, set               list
map                                 dict
record                              dict of the fields in their order
enum                                Variant
optional                            None, or the value
literal                             the value of its typed literal
uuid, ip-address, decimal           UUID, IPv4Address or IPv6Address, Decimal
instant                             datetime in UTC, or an int at ns
date, time-of-day                   date, time
local-date-time                     datetime without a zone
duration                            timedelta, or an int at ns
offset, zone                        timezone, ZoneInfo
zoned-date-time                     datetime in its ZoneInfo
wall-time                           WallTime
==================================  =========================================

datetime, time and timedelta have a resolution of one microsecond, so a
time-of-day, a local-date-time, a zoned-date-time and a wall-time at
nanoseconds do not have a Python value.
"""

from __future__ import annotations

import ipaddress
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._prop.engine import literal
from dokimi_assert._prop.engine.inverse import CannotInvertError
from dokimi_assert._prop.engine.value import Fields, Pairs, canonical
from dokimi_assert._prop.engine.value import Variant as Neutral
from dokimi_assert._prop.engine.zone import ZONES

__all__ = [
    "IDENTITY",
    "Converter",
    "Variant",
    "WallTime",
    "converter_of",
    "date_converter",
    "decimal_converter",
    "duration_converter",
    "instant_converter",
    "ip_converter",
    "local_converter",
    "offset_converter",
    "plain_of",
    "time_converter",
    "uuid_converter",
    "zone_converter",
    "zone_of",
    "zoned_converter",
]


@dataclass(frozen=True, slots=True)
class Converter:
    """The two conversions of the values of one shape.

    Attributes:
        to: The function that returns the Python value of a neutral value of
            the shape.
        back: The function that returns the neutral value of a Python value
            of the shape. It returns a neutral value and a value of any other
            type unchanged. It raises CannotInvertError for a Python value of
            the shape without a neutral value. A time finer than the unit is
            such a value.
    """

    to: Callable[[Any], Any]
    back: Callable[[Any], Any]


def _same(value: Any) -> Any:
    """Return value. Its Python value and its neutral value are the same."""
    return value


#: The converter of a shape whose Python values are its neutral values. A
#: generator without a shape uses it too, because its values are Python
#: values.
IDENTITY = Converter(_same, _same)


def deferred_converter(cell: list[Converter]) -> Converter:
    """Return a converter that delegates to the converter in a cell.

    The read of a recursive definition fills the cell after it returns this
    converter, so each conversion reads the cell when it runs.

    Args:
        cell: The cell that the read fills with the converter of the
            definition.

    Returns:
        The converter.
    """

    def to(value: Any) -> Any:
        return cell[0].to(value)

    def back(value: Any) -> Any:
        return cell[0].back(value)

    return Converter(to, back)


@dataclass(frozen=True, slots=True)
class Variant:
    """A variant of an enum and its payload.

    of_shape decodes an enum to this value.

    Attributes:
        name: The name of the variant.
        payload: The value of the payload, or None for a variant without one.
    """

    name: str
    payload: Any = None


@dataclass(frozen=True, slots=True)
class WallTime:
    """A wall time in a zone.

    of_shape decodes a wall-time to this value. The code under test resolves
    the wall time to an instant. A wall time in a gap of the zone does not
    have an instant, and one in a fold has two.

    Attributes:
        local: The wall time as a datetime without a zone.
        zone: The zone.
    """

    local: datetime
    zone: ZoneInfo


#: The epoch of the date and time shapes. The shapes count their instants and
#: their days from it, and the time-of-day shapes count their units from its
#: midnight without a zone.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_EPOCH_DAY = date(1970, 1, 1)
_MIDNIGHT = datetime.combine(_EPOCH_DAY, time())

#: The microseconds of one unit of a time shape at each unit above ns.
_MICROSECONDS = {"s": 1_000_000, "ms": 1_000, "us": 1}

#: The nanoseconds of a second, and the duration of a microsecond.
_SECOND_NS = 1_000_000_000
_MICROSECOND = timedelta(microseconds=1)

#: The names of the zones of the definition.
_ZONE_NAMES = frozenset(zone.name for zone in ZONES)


def _parts(value: Fields) -> tuple[Any, Any]:
    """Return the two parts of the neutral value of a time shape of two parts."""
    return value.fields[0][1], value.fields[1][1]


def _two(first: str, a: object, second: str, b: object) -> Fields:
    """Return the neutral value of a time shape of two named parts."""
    return Fields(((first, a), (second, b)))


def _whole(micros: int, unit: str, value: object) -> int:
    """Return the number of units in micros microseconds.

    Raises:
        CannotInvertError: micros is not a whole number of units.
    """
    units, rest = divmod(micros, _MICROSECONDS[unit])
    if rest:
        msg = f"prop: {value!r} is finer than the unit {unit}"
        raise CannotInvertError(msg)
    return units


def _micros_of(delta: timedelta) -> int:
    """Return the microseconds of a timedelta."""
    return delta // _MICROSECOND


def date_converter() -> Converter:
    """Return the converter of a date.

    The neutral value of a date is its number of days since 1970-01-01.

    Returns:
        The converter.
    """

    def to(value: int) -> date:
        return _EPOCH_DAY + timedelta(days=value)

    def back(value: Any) -> Any:
        if isinstance(value, date) and not isinstance(value, datetime):
            return (value - _EPOCH_DAY).days
        return value

    return Converter(to, back)


def instant_converter(unit: str) -> Converter:
    """Return the converter of an instant at a unit.

    The Python value is a datetime in UTC. At the unit ns, it is an int of
    nanoseconds since 1970-01-01T00:00:00Z.

    Args:
        unit: s, ms, us or ns.

    Returns:
        The converter.
    """
    if unit == "ns":

        def nanoseconds(value: Fields) -> int:
            seconds, units = _parts(value)
            return cast("int", seconds) * _SECOND_NS + cast("int", units)

        def from_nanoseconds(value: Any) -> Any:
            if type(value) is not int:
                return value
            seconds, units = divmod(value, _SECOND_NS)
            return _two("seconds", seconds, "units", units)

        return Converter(nanoseconds, from_nanoseconds)
    per = _MICROSECONDS[unit]

    def to(value: Fields) -> datetime:
        seconds, units = _parts(value)
        return _EPOCH + timedelta(seconds=seconds, microseconds=units * per)

    def back(value: Any) -> Any:
        if not isinstance(value, datetime) or value.tzinfo is None:
            return value
        seconds, micros = divmod(_micros_of(value - _EPOCH), 1_000_000)
        return _two("seconds", seconds, "units", _whole(micros, unit, value))

    return Converter(to, back)


def time_converter(unit: str) -> Converter:
    """Return the converter of a time of day at a unit above ns.

    Args:
        unit: s, ms or us.

    Returns:
        The converter.
    """
    per = _MICROSECONDS[unit]

    def to(value: int) -> time:
        return (_MIDNIGHT + timedelta(microseconds=value * per)).time()

    def back(value: Any) -> Any:
        if not isinstance(value, time) or value.tzinfo is not None:
            return value
        since = datetime.combine(_MIDNIGHT.date(), value) - _MIDNIGHT
        return _whole(_micros_of(since), unit, value)

    return Converter(to, back)


def local_converter(unit: str) -> Converter:
    """Return the converter of a local date and time at a unit above ns.

    The Python value is a datetime without a zone.

    Args:
        unit: s, ms or us.

    Returns:
        The converter.
    """
    days = date_converter()
    times = time_converter(unit)

    def to(value: Fields) -> datetime:
        day, units = _parts(value)
        return datetime.combine(days.to(day), times.to(units))

    def back(value: Any) -> Any:
        if not isinstance(value, datetime) or value.tzinfo is not None:
            return value
        return _two(
            "date", days.back(value.date()), "time-of-day", times.back(value.time())
        )

    return Converter(to, back)


def duration_converter(unit: str) -> Converter:
    """Return the converter of a duration at a unit.

    The Python value is a timedelta. At the unit ns, the Python value and the
    neutral value are both the int of nanoseconds.

    Args:
        unit: s, ms, us or ns.

    Returns:
        The converter.
    """
    if unit == "ns":
        return IDENTITY
    per = _MICROSECONDS[unit]

    def to(value: int) -> timedelta:
        return timedelta(microseconds=value * per)

    def back(value: Any) -> Any:
        if not isinstance(value, timedelta):
            return value
        return _whole(_micros_of(value), unit, value)

    return Converter(to, back)


def offset_converter() -> Converter:
    """Return the converter of an offset.

    The Python value of an offset is a timezone.

    Returns:
        The converter.
    """

    def to(value: int) -> timezone:
        return timezone(timedelta(seconds=value))

    def back(value: Any) -> Any:
        if not isinstance(value, timezone):
            return value
        return _whole(_micros_of(value.utcoffset(None)), "s", value)

    return Converter(to, back)


def zone_of(name: str, at: str) -> ZoneInfo:
    """Return the ZoneInfo of a zone name.

    Args:
        name: The name of the zone.
        at: The location of the zone in the shape. A fault is at this
            location.

    Returns:
        The zone.

    Raises:
        FaultError: zoneinfo finds the zone neither in the time-zone database
            of the system nor in the package tzdata.
    """
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise FaultError(
            at,
            f"zoneinfo does not find the zone {name} in the time-zone database of "
            "the system or in the package tzdata",
            error,
        ) from error


def _zone_name(value: Any) -> Any:
    """Return the name of a ZoneInfo, and any other value unchanged."""
    return value.key if isinstance(value, ZoneInfo) else value


def zone_converter(at: str) -> Converter:
    """Return the converter of a zone.

    The Python value of a zone is a ZoneInfo.

    Args:
        at: The location of the zone in the shape. The fault of a zone that
            zoneinfo does not find is at this location.

    Returns:
        The converter.

    Raises:
        FaultError: zoneinfo does not find a zone of the definition.
    """
    for name in sorted(_ZONE_NAMES):
        zone_of(name, at)
    return Converter(ZoneInfo, _zone_name)


def zoned_converter(unit: str, at: str) -> Converter:
    """Return the converter of an instant in a zone at a unit above ns.

    The Python value is a datetime in its ZoneInfo.

    Args:
        unit: s, ms or us.
        at: The location of the zone in the shape. The fault of a zone that
            zoneinfo does not find is at this location.

    Returns:
        The converter.

    Raises:
        FaultError: zoneinfo does not find a zone of the definition.
    """
    instant = instant_converter(unit)
    zones = zone_converter(at)

    def to(value: Fields) -> datetime:
        at_instant, zone = _parts(value)
        return cast("datetime", instant.to(at_instant)).astimezone(zones.to(zone))

    def back(value: Any) -> Any:
        if not isinstance(value, datetime) or not isinstance(value.tzinfo, ZoneInfo):
            return value
        return _two("instant", instant.back(value), "zone", _zone_name(value.tzinfo))

    return Converter(to, back)


def _wall_converter(unit: str, at: str) -> Converter:
    """Return the converter of a wall time in a zone at a unit above ns.

    Raises:
        FaultError: zoneinfo does not find a zone of the definition.
    """
    local = local_converter(unit)
    zones = zone_converter(at)

    def to(value: Fields) -> WallTime:
        wall, zone = _parts(value)
        return WallTime(local.to(wall), zones.to(zone))

    def back(value: Any) -> Any:
        if not isinstance(value, WallTime):
            return value
        return _two("local-date-time", local.back(value.local), "zone", value.zone.key)

    return Converter(to, back)


def uuid_converter() -> Converter:
    """Return the converter of a UUID.

    The neutral value of a UUID is its 16 bytes.

    Returns:
        The converter.
    """

    def back(value: Any) -> Any:
        return value.bytes if isinstance(value, uuid.UUID) else value

    return Converter(lambda value: uuid.UUID(bytes=value), back)


def ip_converter() -> Converter:
    """Return the converter of an IP address.

    The neutral value of an address is its bytes. The Python value is an
    IPv4Address or an IPv6Address.

    Returns:
        The converter.
    """

    def back(value: Any) -> Any:
        if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            return value.packed
        return value

    return Converter(ipaddress.ip_address, back)


def decimal_converter(scale: int) -> Converter:
    """Return the converter of a decimal of scale digits after the point.

    The neutral value is the unscaled integer, and the Python value is a
    Decimal with scale digits after the point.

    Args:
        scale: The number of digits after the point.

    Returns:
        The converter.
    """

    def to(value: int) -> Decimal:
        digits = tuple(int(d) for d in str(abs(value)))
        return Decimal((int(value < 0), digits, -scale))

    def back(value: Any) -> Any:
        if not isinstance(value, Decimal) or not value.is_finite():
            return value
        sign, digits, exponent = value.as_tuple()
        shift = cast("int", exponent) + scale
        magnitude = int("".join(map(str, digits)))
        if magnitude == 0:
            return 0
        if shift > len(str(2**63)):
            msg = f"prop: {value!r} is outside the 64-bit range"
            raise CannotInvertError(msg)
        if shift < 0:
            magnitude, rest = divmod(magnitude, 10**-shift)
            if rest:
                msg = f"prop: {value!r} has more digits than the scale of {scale}"
                raise CannotInvertError(msg)
        else:
            magnitude *= 10**shift
        return -magnitude if sign else magnitude

    return Converter(to, back)


def plain_of(value: Any) -> Any:
    """Return the Python value of a decoded typed literal.

    A record becomes a dict of its fields, and a map becomes a dict. A
    variant becomes a Variant, and a list becomes a list of the Python values
    of its elements.

    Args:
        value: The decoded value.

    Returns:
        The Python value.
    """
    if isinstance(value, list):
        return [plain_of(item) for item in value]
    if isinstance(value, Fields):
        return {name: plain_of(item) for name, item in value.fields}
    if isinstance(value, Pairs):
        return {plain_of(k): plain_of(v) for k, v in value.items}
    if isinstance(value, Neutral):
        payload = plain_of(value.payload) if value.has_payload else None
        return Variant(value.name, payload)
    return value


def _joined(at: str, part: str) -> str:
    """Return the path of a part of the shape at a path."""
    return f"{at}.{part}" if at else part


#: The shapes whose Python values cannot be the keys of a dict.
_UNHASHABLE = frozenset({"list", "fixed-list", "set", "map", "record"})

#: The date and time shapes that do not have a Python value at nanoseconds.
_MICROSECOND_ONLY = frozenset(
    {"time-of-day", "local-date-time", "zoned-date-time", "wall-time"}
)


class _Walker:
    """The shapes of a shape file and the converters that the walk has built."""

    def __init__(self, definitions: Mapping[str, Any]) -> None:
        """Return the walker of a shape file with definitions."""
        self._definitions: Mapping[str, Any] = definitions
        self._built: dict[str, Converter] = {}

    def ref(self, name: str, at: str) -> Converter:
        """Return the converter of the definition of a ref.

        The walker builds the converter of a definition once.
        """
        built = self._built.get(name)
        if built is not None:
            return built
        cell: list[Converter] = []
        lazy = deferred_converter(cell)
        self._built[name] = lazy
        cell.append(self.convert(self._definitions[name], _joined(at, name)))
        return lazy

    def hashable(self, node: Mapping[str, Any], seen: frozenset[str]) -> bool:
        """Report whether every Python value of a shape can be a key of a dict."""
        kind = node["shape"]
        if kind in _UNHASHABLE:
            return False
        if kind == "optional":
            return self.hashable(node["of"], seen)
        if kind == "enum":
            return all(
                payload is None or self.hashable(payload, seen)
                for _, payload in node["variants"]
            )
        if kind == "literal":
            return all(
                not isinstance(plain_of(literal.decode(v)), (list, dict))
                for v in node["values"]
            )
        if kind == "ref":
            name = node["name"]
            return name in seen or self.hashable(self._definitions[name], seen | {name})
        return True

    def convert(self, node: Mapping[str, Any], at: str) -> Converter:
        """Return the converter of a shape that the shape reader of the engine accepted.

        Raises:
            FaultError: The shape does not have a Python value. A date or a
                time at nanoseconds, a map whose keys cannot be the keys of a
                dict, and a zone that zoneinfo does not find are such shapes.
        """
        kind = node["shape"]
        unit = node.get("unit")
        if unit == "ns" and kind in _MICROSECOND_ONLY:
            raise FaultError(
                at,
                f"a {kind} at nanoseconds does not have a Python value, because "
                "datetime has a resolution of one microsecond",
            )
        if kind in ("list", "fixed-list", "set"):
            return _list_converter(self.convert(node["of"], f"{at}[]"))
        if kind == "map":
            key = _joined(at, "key")
            if not self.hashable(node["key"], frozenset()):
                raise FaultError(
                    key,
                    "the keys of the map decode to values that a dict does not "
                    "take as keys",
                )
            return _map_converter(
                self.convert(node["key"], key), self.convert(node["of"], f"{at}[]")
            )
        if kind == "optional":
            return _optional_converter(self.convert(node["of"], at))
        return self._named(kind, node, at)

    def _named(self, kind: str, node: Mapping[str, Any], at: str) -> Converter:
        """Return the converter of a record, an enum, a literal, a ref or a scalar.

        A domain shape is a scalar.

        Raises:
            FaultError: The shape does not have a Python value.
        """
        if kind == "record":
            return _fields_converter(
                [
                    (name, self.convert(field, _joined(at, name)))
                    for name, field in node["fields"]
                ]
            )
        if kind == "enum":
            return _variant_converter(
                {
                    name: None if payload is None else self.convert(payload, at)
                    for name, payload in node["variants"]
                }
            )
        if kind == "literal":
            return _literal_converter([literal.decode(v) for v in node["values"]])
        if kind == "ref":
            return self.ref(node["name"], at)
        return _domain_converter(kind, node, at)


#: The converter of each domain shape, from the shape and its path.
_DOMAINS: dict[str, Callable[[Mapping[str, Any], str], Converter]] = {
    "uuid": lambda *_: uuid_converter(),
    "ip-address": lambda *_: ip_converter(),
    "decimal": lambda node, _: decimal_converter(cast("int", node["scale"])),
    "instant": lambda node, _: instant_converter(cast("str", node.get("unit"))),
    "date": lambda *_: date_converter(),
    "time-of-day": lambda node, _: time_converter(cast("str", node.get("unit"))),
    "local-date-time": lambda node, _: local_converter(cast("str", node.get("unit"))),
    "duration": lambda node, _: duration_converter(cast("str", node.get("unit"))),
    "offset": lambda *_: offset_converter(),
    "zone": lambda _, at: zone_converter(at),
    "zoned-date-time": lambda node, at: zoned_converter(
        cast("str", node.get("unit")), at
    ),
    "wall-time": lambda node, at: _wall_converter(cast("str", node.get("unit")), at),
}


def _domain_converter(kind: str, node: Mapping[str, Any], at: str) -> Converter:
    """Return the converter of a scalar or a domain shape."""
    build = _DOMAINS.get(kind)
    return IDENTITY if build is None else build(node, at)


def _list_converter(of: Converter) -> Converter:
    """Return the converter of a list, a fixed-list or a set.

    The Python value is a list.
    """

    def back(value: Any) -> Any:
        if not isinstance(value, (list, tuple)):
            return value
        return [of.back(item) for item in cast("Sequence[Any]", value)]

    return Converter(lambda value: [of.to(item) for item in value], back)


def _map_converter(key: Converter, of: Converter) -> Converter:
    """Return the converter of a map. The Python value is a dict."""

    def back(value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        entries = value.items()
        return Pairs(tuple((key.back(k), of.back(v)) for k, v in entries))

    def to(value: Pairs) -> dict[Any, Any]:
        return {key.to(k): of.to(v) for k, v in value.items}

    return Converter(to, back)


def _optional_converter(of: Converter) -> Converter:
    """Return the converter of an optional. The Python value is None or the value."""

    def to(value: Any) -> Any:
        return None if value is None else of.to(value)

    def back(value: Any) -> Any:
        return None if value is None else of.back(value)

    return Converter(to, back)


def _fields_converter(fields: list[tuple[str, Converter]]) -> Converter:
    """Return the converter of a record. The Python value is a dict of its fields."""

    def to(value: Fields) -> dict[str, Any]:
        return {
            name: conv.to(item)
            for (name, conv), (_, item) in zip(fields, value.fields, strict=True)
        }

    def back(value: Any) -> Any:
        if not isinstance(value, Mapping):
            return value
        mapping = cast("Mapping[str, Any]", value)
        if set(mapping) != {name for name, _ in fields}:
            return value
        return Fields(tuple((name, conv.back(mapping[name])) for name, conv in fields))

    return Converter(to, back)


def _variant_converter(payloads: Mapping[str, Converter | None]) -> Converter:
    """Return the converter of an enum. The Python value is a Variant."""

    def to(value: Neutral) -> Variant:
        payload = payloads[value.name]
        return Variant(
            value.name, None if payload is None else payload.to(value.payload)
        )

    def back(value: Any) -> Any:
        if not isinstance(value, Variant) or value.name not in payloads:
            return value
        payload = payloads[value.name]
        if payload is None:
            return Neutral(value.name)
        return Neutral(value.name, payload.back(value.payload))

    return Converter(to, back)


def _literal_converter(decoded: list[object]) -> Converter:
    """Return the converter of a literal over decoded values.

    Each value converts to its Python value. back finds the decoded value of
    a Python value by its canonical text.
    """
    keys: dict[str, object] = {}
    for value in decoded:
        keys[canonical(value)] = value
        keys[canonical(plain_of(value))] = value

    def back(value: Any) -> Any:
        return keys.get(canonical(value), value)

    return Converter(plain_of, back)


def converter_of(document: Mapping[str, Any]) -> Converter:
    """Return the converter of the root of a shape file that the engine read.

    Args:
        document: The parsed JSON of the shape file.

    Returns:
        The converter.

    Raises:
        FaultError: A shape of the file does not have a Python value. A date
            or a time at nanoseconds, a map whose keys cannot be the keys of
            a dict, and a zone that zoneinfo does not find are such shapes.
    """
    definitions = cast("Mapping[str, Any]", document.get("definitions") or {})
    return _Walker(definitions).convert(document, "")
