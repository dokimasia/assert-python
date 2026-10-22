"""The decoding of the values that a shape file describes.

A shape is a JSON object that describes the values of a type in the same way
for every language. Its key shape has the id of the shape, such as int or
record. The root of a shape file can also have two other keys:

- definitions maps names to shapes. A ref refers to one of these shapes by
  its name.
- source has the language and the type that the shape describes. read checks
  that source has both, and ignores it otherwise.

read returns the generator of a shape file. Two implementations that read one
shape decode the same value from the same choices.

A structural shape decodes in the same way as a generator of the engine:

- bool decodes as boolean.
- An int up to 64 bits wide decodes as integer.
- float decodes as float.
- char and string decode as string.
- bytes decodes as bytes.
- list, fixed-list and set decode as list.
- map decodes as dict.
- optional decodes as optional.
- literal decodes as sampled-from.

The other structural shapes decode by rules of their own:

- record decodes its fields in order.
- enum decodes an index and then the payload of the chosen variant.
- ref decodes the value of the definition that has its name.

A domain shape decodes to the representation of its values in the
definition:

- uuid and ip-address decode to their bytes in network order.
- decimal decodes to its unscaled integer.
- date decodes to its days since 1970-01-01.
- time-of-day decodes to its units since midnight.
- duration decodes to its units.
- offset decodes to its seconds east of UTC.
- zone decodes to its name.
- instant decodes to a record of its seconds since 1970-01-01T00:00:00Z and
  its units within the second.
- local-date-time decodes to a record of its date and its time of day.
- zoned-date-time decodes to a record of its instant and its zone.
- wall-time decodes to a record of its local-date-time and its zone.

read raises ShapeError for a shape that the definition does not allow. The
text of the error contains the path of the part at fault, such as shape.of.

A value of a recursive shape has a budget of 100 nodes. A node is the value
of a definition that can refer to itself through refs. Once a value has used
its budget, each container that refers back takes its exit:

- An optional is absent.
- A list, a set or a map whose min_size is 0 does not take another element.
- An enum takes its first variant that does not refer back.

read raises ShapeError for a definition that can refer to itself without
passing through such a container. Such a definition does not have a finite
value.

The budget of a value in progress belongs to the thread that decodes it, so
each thread decodes one value of a shape file at a time.
"""

from __future__ import annotations

import json
import math
import re
import sys
import threading
from collections.abc import Callable, Mapping
from fractions import Fraction
from typing import Any, cast

from dokimi_assert._prop.engine import alphabet, draw, literal
from dokimi_assert._prop.engine.case import Case, Request
from dokimi_assert._prop.engine.choice import (
    INT64_MAX,
    INT64_MIN,
    UINT64_MAX,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
)
from dokimi_assert._prop.engine.collection import ELEMENT, ENTRY, Sizes, collect
from dokimi_assert._prop.engine.float import Width
from dokimi_assert._prop.engine.generator import (
    Bool,
    Bytes,
    Float,
    Generator,
    Integer,
    Matching,
    SampledFrom,
    Text,
)
from dokimi_assert._prop.engine.pattern import piece
from dokimi_assert._prop.engine.value import Fields, Pairs, Variant, canonical
from dokimi_assert._prop.engine.zone import ZONES, Zone

__all__ = [
    "EnumShape",
    "InstantShape",
    "Int128Shape",
    "IpShape",
    "ListShape",
    "LocalDateTimeShape",
    "MapShape",
    "OptionalShape",
    "RecordShape",
    "Ref",
    "Root",
    "ShapeError",
    "WallShape",
    "ZonedShape",
    "halves",
    "read",
    "second_part",
]

#: The number of nodes that one value of a recursive shape can use.
_BUDGET = 100

#: The units of a time shape. Each name maps to the number of the unit in one
#: second.
_UNITS = {"s": 1, "ms": 1_000, "us": 1_000_000, "ns": 1_000_000_000}

#: The default bounds of the date and time shapes. They cover the years 1 to
#: 9999 in seconds and in days.
_SECONDS_PER_DAY = 86_400
_FIRST_SECOND = -62_135_596_800
_LAST_SECOND = 253_402_300_799
_FIRST_DAY = _FIRST_SECOND // _SECONDS_PER_DAY
_LAST_DAY = _LAST_SECOND // _SECONDS_PER_DAY

#: The largest duration in nanoseconds and the largest offset from UTC in
#: seconds.
_MAX_DURATION_NS = INT64_MAX
_MAX_OFFSET = 64_800

#: The probability that a zoned value is near a change of its zone, and the
#: probability that a wall time near a change uses the offset after it.
_NEAR_CHANGE = Fraction(1, 4)
_AFTER_CHANGE = Fraction(1, 2)

#: The widths of the int shape and the width of each half of a 128-bit integer.
_INT_WIDTHS = frozenset({8, 16, 32, 64, 128})
_HALF = 64

#: The number of bytes of an address of each IP version and of a UUID.
_ADDRESS_BYTES: dict[float, int] = {4: 4, 6: 16}
_UUID_BYTES = 16

#: The largest finite float of each width.
_FLOAT_MAX = {32: 3.4028234663852886e38, 64: sys.float_info.max}

#: The widths of the float shape as values of the type Width.
_FLOAT_WIDTHS: dict[int, Width] = {32: 32, 64: 64}

#: The keys of each shape besides shape. The first tuple has the required keys,
#: and the second has the optional keys.
_KEYS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "bool": ((), ()),
    "int": (("width", "signed"), ("min", "max")),
    "float": (("width",), ("min", "max", "allow_nan", "allow_infinity")),
    "char": ((), ("alphabet",)),
    "string": ((), ("min_size", "max_size", "alphabet", "pattern")),
    "bytes": ((), ("min_size", "max_size")),
    "list": (("of",), ("min_size", "max_size")),
    "fixed-list": (("of", "size"), ()),
    "set": (("of",), ("min_size", "max_size")),
    "map": (("key", "of"), ("min_size", "max_size")),
    "optional": (("of",), ()),
    "record": (("fields",), ()),
    "enum": (("variants",), ()),
    "literal": (("values",), ()),
    "ref": (("name",), ()),
    "uuid": ((), ()),
    "ip-address": ((), ("version",)),
    "decimal": (("scale",), ("min", "max")),
    "instant": (("unit",), ("min", "max")),
    "date": ((), ("min", "max")),
    "time-of-day": (("unit",), ("min", "max")),
    "local-date-time": (("unit",), ("min", "max")),
    "duration": (("unit",), ("min", "max")),
    "offset": ((), ("min", "max")),
    "zone": ((), ()),
    "zoned-date-time": (("unit",), ()),
    "wall-time": (("unit",), ()),
}

#: The keys that only the root of a shape file can have.
_ROOT_KEYS = frozenset({"definitions", "source"})

#: The patterns of a date, a time of day, a date and time, and a decimal bound.
#: The reader matches each pattern against a whole text.
_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
_TIME = re.compile(r"([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.([0-9]{1,9}))?")
_DATE_TIME = re.compile(
    r"([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]{1,9}))?(Z?)"
)
_DECIMAL = re.compile(r"-?[0-9]+(\.[0-9]+)?")

#: A shape as a parsed JSON object.
Node = Mapping[str, Any]

#: A bound of a shape of two choices. It has a first part and a second part.
Pair = tuple[int, int]


class ShapeError(ValueError):
    """The error that read raises for an invalid shape file."""


def _shown(value: object) -> str:
    """Return the compact JSON text of a value for the text of an error."""
    return json.dumps(value, separators=(",", ":"))


def _name_of(value: object) -> str:
    """Return the name of a ref, or the JSON text of a name that is not a string."""
    return value if isinstance(value, str) else _shown(value)


class _Used(threading.local):
    """The node counts of the values that one thread decodes. The innermost is last."""

    def __init__(self) -> None:
        self.counts: list[int] = []


class _Budget:
    """The node counts of the values of one shape file that each thread decodes."""

    def __init__(self) -> None:
        self._used: _Used = _Used()

    def value(self, fn: Callable[[], object]) -> object:
        """Call fn with a node count of zero for its value, and return its result."""
        counts = self._used.counts
        counts.append(0)
        try:
            return fn()
        finally:
            counts.pop()

    def spend(self) -> None:
        """Count one node of the value in progress."""
        self._used.counts[-1] += 1

    @property
    def exhausted(self) -> bool:
        """True when the value in progress has used its budget."""
        counts = self._used.counts
        return bool(counts) and counts[-1] >= _BUDGET


class Root(Generator[Any]):
    """The root of a recursive shape. It counts the budget of each value from zero.

    Attributes:
        node: The generator of the root shape.
    """

    def __init__(self, node: Generator[Any], budget: _Budget) -> None:
        """Return the root of a generator and the budget of its values.

        Args:
            node: The generator of the root shape.
            budget: The budget of the values of the shape file.
        """
        self.node: Generator[Any] = node
        self._budget: _Budget = budget

    def decode(self, c: Case) -> Any:
        """Return one value of the root shape.

        Args:
            c: The case.

        Returns:
            The value.
        """
        return self._budget.value(lambda: self.node.decode(c))


class Ref(Generator[Any]):
    """The value of the definition with a name.

    A ref to a definition that can refer to itself counts one node of the
    budget.

    Attributes:
        name: The name of the definition.
        definitions: The generators of the definitions.
    """

    def __init__(
        self,
        name: str,
        definitions: Mapping[str, Generator[Any]],
        cyclic: bool,
        budget: _Budget,
    ) -> None:
        """Return the ref of a name.

        Args:
            name: The name of the definition.
            definitions: The generators of the definitions, by name.
            cyclic: When True, the definition can refer to itself, and each
                value of the ref counts one node of the budget.
            budget: The budget of the values of the shape file.
        """
        self.name: str = name
        self.definitions: Mapping[str, Generator[Any]] = definitions
        self._cyclic: bool = cyclic
        self._budget: _Budget = budget

    def decode(self, c: Case) -> Any:
        """Return the value of the definition of the ref.

        Args:
            c: The case.

        Returns:
            The value of the definition.
        """
        if self._cyclic:
            self._budget.spend()
        return self.definitions[self.name].decode(c)


class OptionalShape(Generator[Any]):
    """A value or None. An exit forces the presence choice to absent.

    Attributes:
        of: The generator of the value.
    """

    def __init__(self, of: Generator[Any], exits: bool, budget: _Budget) -> None:
        """Return the optional of a generator.

        Args:
            of: The generator of the value.
            exits: When True, the optional is an exit of a definition that
                refers back, so a used budget makes it absent.
            budget: The budget of the values of the shape file.
        """
        self.of: Generator[Any] = of
        self._exits: bool = exits
        self._budget: _Budget = budget

    def decode(self, c: Case) -> Any:
        """Return None when absent, and the decoded value when present.

        Args:
            c: The case.

        Returns:
            The value, or None for a presence choice of 0.
        """
        forced = self._exits and self._budget.exhausted
        bounds = IntegerBounds(0, 0 if forced else 1)
        with c.span("optional"):
            return self.of.decode(c) if c.integer(bounds, 1) == 1 else None


class ListShape(Generator[list[Any]]):
    """A list, a fixed-list or a set. It decodes as a collection and stops at an exit.

    The elements of a set are unique.

    Attributes:
        of: The generator of the elements.
        sizes: The sizes.
        unique: When True, the elements are unique.
    """

    def __init__(
        self,
        of: Generator[Any],
        sizes: Sizes,
        unique: bool,
        exits: bool,
        budget: _Budget,
    ) -> None:
        """Return the list of a generator.

        Args:
            of: The generator of the elements.
            sizes: The sizes.
            unique: When True, the elements are unique.
            exits: When True, the list stops adding elements once the
                budget of its value is used.
            budget: The budget of the values of the shape file.
        """
        self.of: Generator[Any] = of
        self.sizes: Sizes = sizes
        self.unique: bool = unique
        self._exits: bool = exits
        self._budget: _Budget = budget

    def decode(self, c: Case) -> list[Any]:
        """Return the elements that the flags and the choices of the case decode to.

        Args:
            c: The case.

        Returns:
            The elements.

        Raises:
            Rejected: The list stops below its minimum size.
        """
        budget = self._budget
        stop = (lambda: budget.exhausted) if self._exits else None

        def element() -> tuple[Any, str | None]:
            value = self.of.decode(c)
            return value, canonical(value) if self.unique else None

        with c.span("list"):
            return collect(c, self.sizes, ELEMENT, element, stop)


class MapShape(Generator[Pairs]):
    """A map of entries with distinct keys. It decodes as a dict and stops at an exit.

    Attributes:
        key: The generator of the keys.
        of: The generator of the values.
        sizes: The sizes.
    """

    def __init__(
        self,
        key: Generator[Any],
        of: Generator[Any],
        sizes: Sizes,
        exits: bool,
        budget: _Budget,
    ) -> None:
        """Return the map of a generator of keys and a generator of values.

        Args:
            key: The generator of the keys.
            of: The generator of the values.
            sizes: The sizes.
            exits: When True, the map stops adding entries once the budget of
                its value is used.
            budget: The budget of the values of the shape file.
        """
        self.key: Generator[Any] = key
        self.of: Generator[Any] = of
        self.sizes: Sizes = sizes
        self._exits: bool = exits
        self._budget: _Budget = budget

    def decode(self, c: Case) -> Pairs:
        """Return the entries that the flags, keys and values of the case decode to.

        Args:
            c: The case.

        Returns:
            The entries.

        Raises:
            Rejected: The map stops below its minimum size.
        """
        budget = self._budget
        stop = (lambda: budget.exhausted) if self._exits else None

        def entry() -> tuple[tuple[Any, Any], str]:
            key = self.key.decode(c)
            return (key, self.of.decode(c)), canonical(key)

        with c.span("dict"):
            return Pairs(tuple(collect(c, self.sizes, ENTRY, entry, stop)))


class RecordShape(Generator[Fields]):
    """A record of named fields. The fields decode in order inside one span.

    Attributes:
        fields: The fields. Each field is a name and a generator.
    """

    def __init__(self, fields: list[tuple[str, Generator[Any]]]) -> None:
        """Return the record of fields.

        Args:
            fields: The fields. Each field is a name and a generator.
        """
        self.fields: tuple[tuple[str, Generator[Any]], ...] = tuple(fields)

    def decode(self, c: Case) -> Fields:
        """Return the record of the value of each field.

        Args:
            c: The case.

        Returns:
            The record.
        """
        values: list[tuple[str, Any]] = []
        with c.span("record"):
            for name, of in self.fields:
                values.append((name, of.decode(c)))
        return Fields(tuple(values))


class EnumShape(Generator[Variant]):
    """The variant that an index chooses, and its payload.

    The index decides structure. When the chosen variant has a payload, the
    enum decodes it after the index. For an enum that refers back, the exit
    is the index of the first variant that does not refer back. Once the
    budget is used, the index takes the exit.

    Attributes:
        variants: The variants. Each variant is a name and the generator of
            its payload, or a name and None.
    """

    def __init__(
        self,
        variants: list[tuple[str, Generator[Any] | None]],
        exit: int | None,
        budget: _Budget,
    ) -> None:
        """Return the enum of variants.

        Args:
            variants: The variants. Each variant is a name and the generator
                of its payload, or a name and None.
            exit: The index of the first variant that does not refer back,
                or None for an enum that does not refer back.
            budget: The budget of the values of the shape file.
        """
        self.variants: tuple[tuple[str, Generator[Any] | None], ...] = tuple(variants)
        self._exit: int | None = exit
        self._budget: _Budget = budget

    def decode(self, c: Case) -> Variant:
        """Return the variant that the case chooses.

        Args:
            c: The case.

        Returns:
            The variant, with its payload when it has one.
        """
        bounds = IntegerBounds(0, len(self.variants) - 1)
        if self._exit is not None and self._budget.exhausted:
            bounds = IntegerBounds(self._exit, self._exit)
        with c.span("enum"):
            name, payload = self.variants[c.integer(bounds, 0)]
            if payload is None:
                return Variant(name)
            return Variant(name, payload.decode(c))


def second_part(first: int, lo: Pair, hi: Pair, top: int) -> IntegerBounds:
    """Return the bounds of the second choice of a shape of two choices.

    The second choice ranges over [0, top]. Where the first choice equals the
    first part of a bound, the second choice stops at the second part of that
    bound.

    Args:
        first: The first choice.
        lo: The lower bound.
        hi: The upper bound.
        top: The largest second part.

    Returns:
        The bounds.
    """
    return IntegerBounds(
        lo[1] if first == lo[0] else 0, hi[1] if first == hi[0] else top
    )


def halves(value: int) -> Pair:
    """Return the high and the low 64 bits of a 128-bit integer.

    Args:
        value: The integer.

    Returns:
        The signed high half and the unsigned low half.
    """
    return value >> _HALF, value & UINT64_MAX


class Int128Shape(Generator[int]):
    """A 128-bit integer. Its high 64 bits and then its low 64 bits decode in one span.

    The high half is signed when the shape is signed. The low half ranges
    over the unsigned 64-bit range. Where the high half equals the high half
    of a bound, the low half stops at the low half of that bound.

    Attributes:
        lo: The smallest value.
        hi: The largest value.
    """

    def __init__(self, lo: int, hi: int) -> None:
        """Return the 128-bit integers from lo to hi.

        Args:
            lo: The smallest value.
            hi: The largest value.
        """
        self.lo: int = lo
        self.hi: int = hi

    def decode(self, c: Case) -> int:
        """Return the integer of the two halves.

        Args:
            c: The case.

        Returns:
            The integer.
        """
        lo = halves(self.lo)
        hi = halves(self.hi)
        with c.span("int"):
            high = c.integer(IntegerBounds(lo[0], hi[0]), None, True)
            low = c.integer(second_part(high, lo, hi, UINT64_MAX), None, True)
        return (high << _HALF) | low


def _instant_value(seconds: int, units: int) -> Fields:
    """Return an instant as a record of its seconds and its units within the second."""
    return Fields((("seconds", seconds), ("units", units)))


def _local_value(day: int, time: int) -> Fields:
    """Return a local-date-time as a record of its date and its time of day."""
    return Fields((("date", day), ("time-of-day", time)))


class InstantShape(Generator[Fields]):
    """An instant. Its seconds and then its units within the second decode in one span.

    At a unit of one second, the shape does not make the second choice.

    Attributes:
        per: The units in a second.
        lo: The seconds and the units of the lower bound.
        hi: The seconds and the units of the upper bound.
    """

    def __init__(self, per: int, lo: Pair, hi: Pair) -> None:
        """Return the instants from lo to hi at a unit.

        Args:
            per: The units in a second.
            lo: The seconds and the units of the lower bound.
            hi: The seconds and the units of the upper bound.
        """
        self.per: int = per
        self.lo: Pair = lo
        self.hi: Pair = hi

    def decode(self, c: Case) -> Fields:
        """Return the record of the seconds and the units.

        Args:
            c: The case.

        Returns:
            The record of the seconds and the units within the second.
        """
        units = 0
        with c.span("instant"):
            seconds = c.integer(IntegerBounds(self.lo[0], self.hi[0]), None, True)
            if self.per != 1:
                bounds = second_part(seconds, self.lo, self.hi, self.per - 1)
                units = c.integer(bounds, None, True)
        return _instant_value(seconds, units)


class LocalDateTimeShape(Generator[Fields]):
    """A date and a time of day without a zone. Both decode in one span.

    Attributes:
        per: The units in a second.
        lo: The day and the time of day of the lower bound.
        hi: The day and the time of day of the upper bound.
    """

    def __init__(self, per: int, lo: Pair, hi: Pair) -> None:
        """Return the local dates and times from lo to hi at a unit.

        Args:
            per: The units in a second.
            lo: The day and the time of day of the lower bound.
            hi: The day and the time of day of the upper bound.
        """
        self.per: int = per
        self.lo: Pair = lo
        self.hi: Pair = hi

    def decode(self, c: Case) -> Fields:
        """Return the record of the date and the time of day.

        Args:
            c: The case.

        Returns:
            The record of the date and the time of day.
        """
        top = _SECONDS_PER_DAY * self.per - 1
        with c.span("local-date-time"):
            day = c.integer(IntegerBounds(self.lo[0], self.hi[0]), None, True)
            bounds = second_part(day, self.lo, self.hi, top)
            time = c.integer(bounds, None, True)
        return _local_value(day, time)


#: The bounds of a choice of 0 or 1, and of a step from -1 to 1.
_BIT = IntegerBounds(0, 1)
_STEP = IntegerBounds(-1, 1)


#: The requests of the choice whether a zoned value is near a change of its
#: zone, and of the choice whether a wall time near a change uses the offset
#: after it.
_NEAR = Request(_BIT, lambda source: draw.boolean(source, _NEAR_CHANGE))
_AFTER = Request(_BIT, lambda source: draw.boolean(source, _AFTER_CHANGE))


def _near(c: Case, zone: Zone) -> bool:
    """Report whether a value of a zone is near one of its changes.

    The case does not make a choice for a zone without a change.
    """
    if not zone.changes:
        return False
    return c.choose(_NEAR) == 1


def _change_and_step(c: Case, zone: Zone) -> tuple[int, int]:
    """Return the index of one of the changes of a zone, and a step from -1 to 1."""
    index = c.integer(IntegerBounds(0, len(zone.changes) - 1), 0)
    return index, c.integer(_STEP, None, True)


#: The bounds of the index of a zone of the list.
_ZONE_INDEX = IntegerBounds(0, len(ZONES) - 1)


def _zone_of(c: Case) -> Zone:
    """Return the zone of the list at the index that the case chooses."""
    return ZONES[c.integer(_ZONE_INDEX, 0)]


class ZonedShape(Generator[Fields]):
    """An instant in a zone of the list.

    The zone decodes first. For a zone with changes, a choice then decides
    whether the instant is within one unit of a change. Otherwise the
    instant decodes over its whole range.

    Attributes:
        instant: The shape of the instant.
    """

    def __init__(self, instant: InstantShape) -> None:
        """Return the zoned instants of an instant shape.

        Args:
            instant: The shape of the instant.
        """
        self.instant: InstantShape = instant

    def decode(self, c: Case) -> Fields:
        """Return the record of the instant and the name of the zone.

        Args:
            c: The case.

        Returns:
            The record of the instant and the name of the zone.
        """
        per = self.instant.per
        with c.span("zoned-date-time"):
            zone = _zone_of(c)
            if _near(c, zone):
                index, step = _change_and_step(c, zone)
                change = zone.changes[index]
                value = _instant_value(*divmod(change.at * per + step, per))
            else:
                value = self.instant.decode(c)
        return Fields((("instant", value), ("zone", zone.name)))


class WallShape(Generator[Fields]):
    """A wall time in a zone of the list.

    The code under test resolves the wall time to an instant. The zone
    decodes first. A wall time near a change is the instant of the change in
    the offset before or after it, plus a step of up to one unit either way.
    These wall times include the ones that a gap skips and the ones that a
    fold repeats.

    Attributes:
        local: The shape of the local date and time.
    """

    def __init__(self, local: LocalDateTimeShape) -> None:
        """Return the wall times of a local date and time shape.

        Args:
            local: The shape of the local date and time.
        """
        self.local: LocalDateTimeShape = local

    def decode(self, c: Case) -> Fields:
        """Return the record of the local date and time and the name of the zone.

        Args:
            c: The case.

        Returns:
            The record of the local date and time and the name of the zone.
        """
        per = self.local.per
        with c.span("wall-time"):
            zone = _zone_of(c)
            if _near(c, zone):
                index, step = _change_and_step(c, zone)
                change = zone.changes[index]
                offset = change.after if c.choose(_AFTER) == 1 else change.before
                total = (change.at + offset) * per + step
                value = _local_value(*divmod(total, _SECONDS_PER_DAY * per))
            else:
                value = self.local.decode(c)
        return Fields((("local-date-time", value), ("zone", zone.name)))


class IpShape(Generator[bytes]):
    """An IP address of either version.

    An index chooses the version. The 4 or 16 bytes of the address follow
    the index.

    Attributes:
        versions: The generators of the bytes of the two versions.
    """

    def __init__(self, versions: tuple[Bytes, Bytes]) -> None:
        """Return the addresses of both versions.

        Args:
            versions: The generators of the bytes of a version 4 address and
                of a version 6 address.
        """
        self.versions: tuple[Bytes, Bytes] = versions

    def decode(self, c: Case) -> bytes:
        """Return the bytes of the address in network order.

        Args:
            c: The case.

        Returns:
            The 4 or 16 bytes of the address.
        """
        with c.span("ip-address"):
            return self.versions[c.integer(_BIT, 0)].decode(c)


def _fixed_bytes(count: int) -> Bytes:
    """Return the generator of exactly count bytes."""
    return Bytes(SequenceBounds(256, count, count))


def _int_parameter(node: Node, key: str, where: str) -> int:
    """Return an integer parameter in the form of the value of an int literal."""
    try:
        return literal.integer(node.get(key))
    except literal.LiteralError:
        raise ShapeError(
            f"prop: {where}.{key} is {_shown(node.get(key))}, not an integer"
        ) from None


def _count_parameter(node: Node, key: str, where: str) -> int | None:
    """Return a count of at least 0, or None for an absent or null parameter."""
    if node.get(key) is None:
        return None
    value = _int_parameter(node, key, where)
    if value < 0:
        raise ShapeError(f"prop: {where}.{key} is {value}, below 0")
    return value


def _sizes_of(node: Node, where: str) -> Sizes:
    """Return the sizes of min_size and max_size.

    min_size is 0 by default. Without max_size, the sizes do not have an upper
    bound.
    """
    lo = _count_parameter(node, "min_size", where)
    hi = _count_parameter(node, "max_size", where)
    low = 0 if lo is None else lo
    if hi is not None and hi < low:
        raise ShapeError(f"prop: {where}: sizes [{low}, {hi}] are empty")
    return Sizes(low, hi)


def _unit_of(node: Node, where: str) -> int:
    """Return the number of units in one second for the unit of a time shape."""
    unit = node.get("unit")
    per = _UNITS.get(unit) if isinstance(unit, str) else None
    if per is None:
        raise ShapeError(
            f"prop: {where}.unit is {_shown(unit)}, not one of ms, ns, s, us"
        )
    return per


def _fraction_units(digits: str | None, per: int, where: str) -> int:
    """Return the number of units in the fraction of a second with the given digits."""
    if not digits:
        return 0
    scale: int = 10 ** len(digits)
    scaled = int(digits) * per
    if scaled % scale != 0:
        raise ShapeError(
            f"prop: {where} has a bound with a fraction finer than its unit"
        )
    return scaled // scale


def _leap(year: int) -> bool:
    """Report whether a year is a leap year of the proleptic Gregorian calendar."""
    return (year % 4 == 0 and year % 100 != 0) or year % 400 == 0


#: The days of each month of a year that is not a leap year.
_MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


def _day_of(year: str, month: str, day: str, where: str) -> int:
    """Return the days since 1970-01-01 of a proleptic Gregorian date."""
    y, m, d = int(year), int(month), int(day)
    length = 0
    if 1 <= m <= 12:
        length = 29 if m == 2 and _leap(y) else _MONTH_DAYS[m - 1]
    if y < 1 or y > 9999 or d < 1 or d > length:
        raise ShapeError(f"prop: {where} bound {year}-{month}-{day} is not a date")
    # The days from 1970-01-01 of a civil date, by counting eras of 400 years.
    shifted = y - 1 if m <= 2 else y
    era = shifted // 400
    year_of_era = shifted - era * 400
    day_of_year = (153 * (m - 3 if m > 2 else m + 9) + 2) // 5 + d - 1
    day_of_era = year_of_era * 365 + year_of_era // 4 - year_of_era // 100 + day_of_year
    return era * 146_097 + day_of_era - 719_468


def _time_of(hour: str, minute: str, second: str, where: str) -> int:
    """Return the seconds since midnight of a time of day."""
    h, m, s = int(hour), int(minute), int(second)
    if h > 23 or m > 59 or s > 59:
        raise ShapeError(
            f"prop: {where} bound {hour}:{minute}:{second} is not a time of day"
        )
    return h * 3600 + m * 60 + s


def _range_of(
    node: Node,
    where: str,
    fallback: tuple[int, int],
    parse: Callable[[object], int],
) -> tuple[int, int]:
    """Return the bounds of the min and the max of a shape.

    fallback has the default bounds. Raise ShapeError for bounds that are
    empty or outside fallback.
    """
    lo = fallback[0] if node.get("min") is None else parse(node.get("min"))
    hi = fallback[1] if node.get("max") is None else parse(node.get("max"))
    if not fallback[0] <= lo <= hi <= fallback[1]:
        raise ShapeError(
            f"prop: {where} bounds [{lo}, {hi}] are empty or outside "
            f"[{fallback[0]}, {fallback[1]}]"
        )
    return lo, hi


def _bounded(
    node: Node,
    where: str,
    fallback: tuple[int, int],
    parse: Callable[[object], int],
) -> IntegerBounds:
    """Return the integer bounds of the min and the max of a shape."""
    lo, hi = _range_of(node, where, fallback, parse)
    return IntegerBounds(lo, hi)


def _pair_bounds(
    node: Node,
    where: str,
    fallback: tuple[Pair, Pair],
    parse: Callable[[object], Pair],
) -> tuple[Pair, Pair]:
    """Return the bounds of a shape of two choices. Each bound is a Pair."""
    lo = fallback[0] if node.get("min") is None else parse(node.get("min"))
    hi = fallback[1] if node.get("max") is None else parse(node.get("max"))
    if not fallback[0] <= lo <= hi <= fallback[1]:
        raise ShapeError(
            f"prop: {where} bounds {lo[0]},{lo[1]} to {hi[0]},{hi[1]} are empty or "
            "out of range"
        )
    return lo, hi


def _closure(graph: Mapping[str, set[str]]) -> dict[str, set[str]]:
    """Return the transitive closure of a graph of names.

    A name is in its own set only when it is on a cycle.
    """
    paths = {name: set(named) for name, named in graph.items()}
    changed = True
    while changed:
        changed = False
        for name, named in paths.items():
            wider = set(named)
            for target in named:
                wider |= paths.get(target, set())
            if len(wider) != len(named):
                paths[name] = wider
                changed = True
    return paths


def _alphabet_of(node: Node, where: str) -> tuple[list[str] | None, int]:
    """Return the characters and the size of the alphabet of a shape.

    The characters are None for the default alphabet.
    """
    characters = node.get("alphabet")
    if characters is None:
        return None, alphabet.SIZE
    if not isinstance(characters, str) or characters == "":
        raise ShapeError(
            f"prop: {where}.alphabet is {_shown(characters)}, not a string of at "
            "least one character"
        )
    chars = list(characters)
    if len(set(chars)) != len(chars):
        raise ShapeError(f"prop: {where}.alphabet repeats a character")
    if any(alphabet.index_of(char) is None for char in chars):
        raise ShapeError(
            f"prop: {where}.alphabet has a lone surrogate instead of a character"
        )
    return chars, len(chars)


def _pairs_of(node: Node, key: str, where: str) -> list[tuple[str, object]]:
    """Return the pairs of a name and a value. Each name is unique and not empty."""
    items = node.get(key)
    if not isinstance(items, list) or not items:
        raise ShapeError(f"prop: {where}.{key} is {_shown(items)}, not a list of pairs")
    pairs: list[tuple[str, object]] = []
    for item in cast("list[object]", items):
        pair = cast("list[object]", item) if isinstance(item, list) else []
        name = pair[0] if len(pair) == 2 else None
        if not isinstance(name, str):
            raise ShapeError(
                f"prop: {where}.{key} has {_shown(item)}, not a name and a shape"
            )
        if name == "" or any(known == name for known, _ in pairs):
            raise ShapeError(
                f"prop: {where}.{key} has an empty or repeated name {_shown(name)}"
            )
        pairs.append((name, pair[1]))
    return pairs


#: A function that builds the generator of one shape from its node.
_Builder = Callable[["_Reader", Node, str], Generator[Any]]


class _Reader:
    """The state of one read of a shape file.

    The reader has the definitions of the file and the budget of its values.
    It also has the generators of the names that the file does not define.
    """

    def __init__(self, document: Node, externals: Mapping[str, Generator[Any]]) -> None:
        self._document: Node = document
        self._externals: Mapping[str, Generator[Any]] = externals
        self.budget: _Budget = _Budget()
        self.built: dict[str, Generator[Any]] = {}
        self._sources: dict[str, Node] = {}
        self.cyclic: frozenset[str] = frozenset()

    def root(self) -> Generator[Any]:
        """Check the definitions, build them, and return the generator of the root."""
        definitions = self._document.get("definitions", {})
        if not isinstance(definitions, dict):
            raise ShapeError("prop: definitions is not a map of names to shapes")
        for name, node in cast("dict[str, object]", definitions).items():
            if not isinstance(node, dict):
                raise ShapeError(
                    f"prop: definitions.{name} is {_shown(node)}, not a shape"
                )
            self._sources[name] = cast("Node", node)
        source = self._document.get("source")
        named: Node = cast("Node", source) if isinstance(source, dict) else {}
        stated = isinstance(named.get("language"), str) and isinstance(
            named.get("type"), str
        )
        if source is not None and not stated:
            raise ShapeError(
                f"prop: source is {_shown(source)}, not a language and a type"
            )
        self.cyclic = self._cyclic_names()
        self._finite()
        for name, generator in self._externals.items():
            if name not in self._sources:
                self.built[name] = generator
        for name, node in self._sources.items():
            self.built[name] = self.build(node, f"definitions.{name}")
        root = self.build(self._document, "shape", True)
        return Root(root, self.budget) if self.cyclic else root

    def refs(self, node: object, stop_at_exits: bool = False) -> list[str]:
        """Return the names of the refs inside node without following a ref.

        When stop_at_exits is True, the search does not enter a container that
        can always exit. The result then has only the refs that every value of
        node expands.
        """
        if isinstance(node, list):
            items = cast("list[object]", node)
            return [name for item in items for name in self.refs(item, stop_at_exits)]
        if not isinstance(node, dict):
            return []
        shape = cast("Node", node)
        if shape.get("shape") == "ref":
            return [_name_of(shape.get("name"))]
        if stop_at_exits and self.exits(shape):
            return []
        return [
            name
            for key, value in shape.items()
            if key not in _ROOT_KEYS and key != "values"
            for name in self.refs(value, stop_at_exits)
        ]

    def _cyclic_names(self) -> frozenset[str]:
        """Return the definitions that can refer to themselves through refs."""
        graph = self._graph(False)
        targets = self.refs(self._document) + [
            target for named in graph.values() for target in named
        ]
        for target in targets:
            if target not in self._sources and target not in self._externals:
                raise ShapeError(
                    f"prop: a ref to {_shown(target)} does not have a definition"
                )
        paths = _closure(graph)
        return frozenset(name for name, named in paths.items() if name in named)

    def _graph(self, stop_at_exits: bool) -> dict[str, set[str]]:
        """Return the refs of each definition.

        When stop_at_exits is True, each set has only the refs that every value
        of the definition expands.
        """
        return {
            name: set(self.refs(node, stop_at_exits))
            for name, node in self._sources.items()
        }

    def refers_back(self, node: object) -> bool:
        """Report whether node refers to a definition that can refer to itself."""
        return any(name in self.cyclic for name in self.refs(node))

    def exits(self, node: Node) -> bool:
        """Report whether a container can always take an exit.

        An optional can be absent. A list, a set or a map whose min_size is 0
        can be empty. An enum can take a variant that does not refer back.
        """
        kind = node.get("shape")
        if kind == "optional":
            return True
        if kind in ("list", "set", "map"):
            least = node.get("min_size")
            return least is None or (
                isinstance(least, (int, float))
                and not isinstance(least, bool)
                and least == 0
            )
        return kind == "enum" and self.exit_variant(node) is not None

    def exit_variant(self, node: Node) -> int | None:
        """Return the index of the first variant of an enum that does not refer back."""
        variants = node.get("variants")
        listed = cast("list[object]", variants) if isinstance(variants, list) else []
        for index, variant in enumerate(listed):
            pair = cast("list[object]", variant) if isinstance(variant, list) else []
            payload = pair[1] if len(pair) == 2 else None
            if not self.refers_back(payload):
                return index
        return None

    def _finite(self) -> None:
        """Raise ShapeError for a definition without a finite value.

        Every value of such a definition contains a value of the definition.
        """
        must = _closure(self._graph(True))
        for name in sorted(self.cyclic):
            if name in must.get(name, set()):
                raise ShapeError(
                    f"prop: definitions.{name} does not have a finite value, "
                    "because it refers to itself without passing through an "
                    "optional, a list, a set, a map or an enum that can exit"
                )

    def build(self, node: Node, where: str, root: bool = False) -> Generator[Any]:
        """Return the generator of one shape."""
        kind = node.get("shape")
        keys = _KEYS.get(kind) if isinstance(kind, str) else None
        if keys is None:
            raise ShapeError(
                f"prop: {where}.shape is {_shown(kind)}, not the id of a shape"
            )
        required, optional = keys
        stated = [
            key for key in node if key != "shape" and not (root and key in _ROOT_KEYS)
        ]
        missing = sorted(key for key in required if key not in stated)
        if missing:
            raise ShapeError(
                f"prop: {where}.{missing[0]} is missing from the {kind} shape"
            )
        extra = sorted(
            key for key in stated if key not in required and key not in optional
        )
        if extra:
            raise ShapeError(
                f"prop: {where}.{extra[0]} does not apply to the {kind} shape"
            )
        try:
            return _BUILDERS[cast("str", kind)](self, node, where)
        except ShapeError:
            raise
        except ValueError as error:
            raise ShapeError(f"prop: {where}: {error}") from error

    def child(self, node: object, where: str) -> Generator[Any]:
        """Return the generator of a shape nested in another."""
        if not isinstance(node, dict):
            raise ShapeError(f"prop: {where} is {_shown(node)}, not a shape")
        return self.build(cast("Node", node), where)


def _int_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of the ints of a width and a signedness."""
    del reader
    width = _int_parameter(node, "width", where)
    if width not in _INT_WIDTHS:
        raise ShapeError(f"prop: {where}.width is {width}, not 8, 16, 32, 64 or 128")
    signed = node.get("signed")
    if not isinstance(signed, bool):
        raise ShapeError(f"prop: {where}.signed is {_shown(signed)}, not true or false")
    widest = (
        (-(1 << (width - 1)), (1 << (width - 1)) - 1)
        if signed
        else (0, (1 << width) - 1)
    )
    lo, hi = _range_of(node, where, widest, literal.integer)
    if width == 128:
        return Int128Shape(lo, hi)
    return Integer(IntegerBounds(lo, hi))


def _float_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a float of the width of the shape."""
    del reader
    stated = _int_parameter(node, "width", where)
    width = _FLOAT_WIDTHS.get(stated)
    if width is None:
        raise ShapeError(f"prop: {where}.width is {stated}, not 32 or 64")
    allow_nan = node.get("allow_nan", False)
    infinite = node.get("allow_infinity", False)
    for key, flag in (("allow_nan", allow_nan), ("allow_infinity", infinite)):
        if not isinstance(flag, bool):
            raise ShapeError(
                f"prop: {where}.{key} is {_shown(flag)}, not true or false"
            )
    edge = math.inf if infinite else _FLOAT_MAX[width]
    lo = -edge if node.get("min") is None else literal.number(node.get("min"))
    hi = edge if node.get("max") is None else literal.number(node.get("max"))
    if infinite and math.isfinite(lo) and math.isfinite(hi):
        raise ShapeError(
            f"prop: {where} allows the infinities, but both of its bounds are finite"
        )
    return Float(FloatBounds(lo, hi, allow_nan, width))


def _char_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of one character of the alphabet."""
    del reader
    characters, size = _alphabet_of(node, where)
    return Text(characters, SequenceBounds(size, 1, 1))


def _string_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a string.

    The string is over an alphabet, or it matches a pattern.
    """
    del reader
    if "pattern" in node:
        if any(key in node for key in ("alphabet", "min_size", "max_size")):
            raise ShapeError(
                f"prop: {where} has a pattern, so it cannot have an alphabet or a size"
            )
        text = node["pattern"]
        if not isinstance(text, str):
            raise ShapeError(f"prop: {where}.pattern is {_shown(text)}, not a string")
        return Matching(piece(text))
    characters, size = _alphabet_of(node, where)
    sizes = _sizes_of(node, where)
    return Text(characters, SequenceBounds(size, sizes.min_size, sizes.max_size))


def _bytes_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a byte string."""
    del reader
    sizes = _sizes_of(node, where)
    return Bytes(SequenceBounds(256, sizes.min_size, sizes.max_size))


def _list_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a list, a fixed-list or a set."""
    kind = node.get("shape")
    of = reader.child(node.get("of"), f"{where}.of")
    if kind == "fixed-list":
        size = _count_parameter(node, "size", where)
        if size is None:
            raise ShapeError(f"prop: {where}.size is null, not an integer")
        sizes = Sizes(size, size)
    else:
        sizes = _sizes_of(node, where)
    exits = kind != "fixed-list" and reader.exits(node) and reader.refers_back(node)
    return ListShape(of, sizes, kind == "set", exits, reader.budget)


def _map_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a map from keys to values."""
    key = reader.child(node.get("key"), f"{where}.key")
    of = reader.child(node.get("of"), f"{where}.of")
    exits = reader.exits(node) and reader.refers_back(node)
    return MapShape(key, of, _sizes_of(node, where), exits, reader.budget)


def _optional_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of an optional value."""
    of = reader.child(node.get("of"), f"{where}.of")
    return OptionalShape(of, reader.refers_back(node), reader.budget)


def _record_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a record of named fields."""
    return RecordShape(
        [
            (name, reader.child(of, f"{where}.{name}"))
            for name, of in _pairs_of(node, "fields", where)
        ]
    )


def _enum_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of an enum of named variants with optional payloads."""
    variants = [
        (name, None if of is None else reader.child(of, f"{where}.{name}"))
        for name, of in _pairs_of(node, "variants", where)
    ]
    exit = reader.exit_variant(node) if reader.refers_back(node) else None
    return EnumShape(variants, exit, reader.budget)


def _literal_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of one of the values of a literal shape."""
    del reader
    values = node.get("values")
    if not isinstance(values, list) or not values:
        raise ShapeError(
            f"prop: {where}.values is {_shown(values)}, not a list of literals"
        )
    return SampledFrom(
        [literal.decode(value) for value in cast("list[object]", values)]
    )


def _ref_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a named definition.

    Before it builds a shape, the reader checks that every ref has a
    definition.
    """
    del where
    name = _name_of(node.get("name"))
    return Ref(name, reader.built, name in reader.cyclic, reader.budget)


def _ip_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of an IP address of one version or either."""
    del reader
    version = node.get("version")
    if version is None:
        return IpShape((_fixed_bytes(4), _fixed_bytes(16)))
    count = None
    if isinstance(version, (int, float)) and not isinstance(version, bool):
        count = _ADDRESS_BYTES.get(version)
    if count is None:
        raise ShapeError(f"prop: {where}.version is {_shown(version)}, not 4 or 6")
    return _fixed_bytes(count)


def _decimal_bound(
    node: Node, key: str, where: str, factor: int, up: bool
) -> int | None:
    """Return the unscaled value of a decimal bound of node, or None without one.

    The bound is multiplied by factor and rounded inward. A lower bound
    rounds up, and an upper bound rounds down.
    """
    text = node.get(key)
    if text is None:
        return None
    if not isinstance(text, str) or not _DECIMAL.fullmatch(text):
        raise ShapeError(f"prop: {where}.{key} is {_shown(text)}, not a decimal")
    whole, _, fraction = text.partition(".")
    scale: int = 10 ** len(fraction)
    numerator = int(whole + fraction) * factor
    quotient = numerator // scale
    return quotient + 1 if up and quotient * scale != numerator else quotient


def _decimal_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of the unscaled values of a decimal shape.

    A bound with more digits than the scale rounds inward.
    """
    del reader
    scale = _count_parameter(node, "scale", where)
    if scale is None:
        raise ShapeError(f"prop: {where}.scale is null, not an integer")
    factor: int = 10**scale
    unscaled = {
        "min": _decimal_bound(node, "min", where, factor, True),
        "max": _decimal_bound(node, "max", where, factor, False),
    }
    return Integer(
        _bounded(unscaled, where, (INT64_MIN, INT64_MAX), lambda v: cast("int", v))
    )


def _instant_of(node: Node, where: str) -> InstantShape:
    """Return the generator of an instant at the unit of the shape."""
    per = _unit_of(node, where)

    def parse(text: object) -> Pair:
        found = _DATE_TIME.fullmatch(text) if isinstance(text, str) else None
        if found is None or found[8] != "Z":
            raise ShapeError(
                f"prop: {where} bound {_shown(text)} is not an instant in UTC"
            )
        days = _day_of(found[1], found[2], found[3], where)
        seconds = days * _SECONDS_PER_DAY + _time_of(
            found[4], found[5], found[6], where
        )
        return seconds, _fraction_units(found[7], per, where)

    fallback = ((_FIRST_SECOND, 0), (_LAST_SECOND, per - 1))
    lo, hi = _pair_bounds(node, where, fallback, parse)
    return InstantShape(per, lo, hi)


def _date_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a date as its days since 1970-01-01."""
    del reader

    def parse(text: object) -> int:
        found = _DATE.fullmatch(text) if isinstance(text, str) else None
        if found is None:
            raise ShapeError(f"prop: {where} bound {_shown(text)} is not a date")
        return _day_of(found[1], found[2], found[3], where)

    return Integer(_bounded(node, where, (_FIRST_DAY, _LAST_DAY), parse))


def _time_of_day_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a time of day as its units since midnight."""
    del reader
    per = _unit_of(node, where)

    def parse(text: object) -> int:
        found = _TIME.fullmatch(text) if isinstance(text, str) else None
        if found is None:
            raise ShapeError(f"prop: {where} bound {_shown(text)} is not a time of day")
        seconds = _time_of(found[1], found[2], found[3], where)
        return seconds * per + _fraction_units(found[4], per, where)

    last = _SECONDS_PER_DAY * per - 1
    return Integer(_bounded(node, where, (0, last), parse))


def _local_of(node: Node, where: str) -> LocalDateTimeShape:
    """Return the generator of a date and a time of day without a zone."""
    per = _unit_of(node, where)

    def parse(text: object) -> Pair:
        found = _DATE_TIME.fullmatch(text) if isinstance(text, str) else None
        if found is None or found[8] != "":
            raise ShapeError(
                f"prop: {where} bound {_shown(text)} is not a local date and time"
            )
        days = _day_of(found[1], found[2], found[3], where)
        seconds = _time_of(found[4], found[5], found[6], where)
        return days, seconds * per + _fraction_units(found[7], per, where)

    fallback = ((_FIRST_DAY, 0), (_LAST_DAY, _SECONDS_PER_DAY * per - 1))
    lo, hi = _pair_bounds(node, where, fallback, parse)
    return LocalDateTimeShape(per, lo, hi)


def _duration_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a duration as its number of units."""
    del reader
    largest = _MAX_DURATION_NS // (1_000_000_000 // _unit_of(node, where))
    return Integer(_bounded(node, where, (-largest, largest), literal.integer))


def _offset_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of an offset from UTC as its seconds east of UTC."""
    del reader
    fallback = (-_MAX_OFFSET, _MAX_OFFSET)
    return Integer(_bounded(node, where, fallback, literal.integer))


def _bool_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a bool of even odds."""
    del reader, node, where
    return Bool(Fraction(1, 2))


def _uuid_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of the 16 bytes of a UUID."""
    del reader, node, where
    return _fixed_bytes(_UUID_BYTES)


def _zone_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of the name of a zone of the list."""
    del reader, node, where
    return SampledFrom([zone.name for zone in ZONES])


def _instant_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of an instant."""
    del reader
    return _instant_of(node, where)


def _local_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a local date and time."""
    del reader
    return _local_of(node, where)


def _zoned_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of an instant in a zone of the list."""
    del reader
    return ZonedShape(_instant_of({"unit": node.get("unit")}, where))


def _wall_shape(reader: _Reader, node: Node, where: str) -> Generator[Any]:
    """Return the generator of a wall time in a zone of the list."""
    del reader
    return WallShape(_local_of({"unit": node.get("unit")}, where))


#: The builder of each shape id.
_BUILDERS: dict[str, _Builder] = {
    "bool": _bool_shape,
    "int": _int_shape,
    "float": _float_shape,
    "char": _char_shape,
    "string": _string_shape,
    "bytes": _bytes_shape,
    "list": _list_shape,
    "fixed-list": _list_shape,
    "set": _list_shape,
    "map": _map_shape,
    "optional": _optional_shape,
    "record": _record_shape,
    "enum": _enum_shape,
    "literal": _literal_shape,
    "ref": _ref_shape,
    "uuid": _uuid_shape,
    "ip-address": _ip_shape,
    "decimal": _decimal_shape,
    "instant": _instant_shape,
    "date": _date_shape,
    "time-of-day": _time_of_day_shape,
    "local-date-time": _local_shape,
    "duration": _duration_shape,
    "offset": _offset_shape,
    "zone": _zone_shape,
    "zoned-date-time": _zoned_shape,
    "wall-time": _wall_shape,
}


def read(
    document: object, externals: Mapping[str, Generator[Any]] | None = None
) -> Generator[Any]:
    """Return the generator of a shape file.

    A ref to a name that the file does not define decodes the value of the
    generator that externals has for the name. The budget does not count the
    nodes of such a generator. read does not look for refs inside it.

    Args:
        document: The parsed JSON of the shape file.
        externals: The generators of the names that the file does not
            define.

    Returns:
        The generator.

    Raises:
        ShapeError: The file is not a JSON object, or it has an unknown shape
            id, a key that a shape does not take, a parameter that a shape
            does not allow, a ref without a definition, or a definition
            without a finite value.
    """
    if not isinstance(document, dict):
        raise ShapeError(f"prop: {_shown(document)} is not a shape")
    return _Reader(cast("Node", document), externals or {}).root()
