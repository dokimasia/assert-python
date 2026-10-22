# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The fixture types of the definition, and the runner of the fixtures vectors.

A fixtures vector has a fixture type and the shape of the type. Each class
here is the Python type that the summary of its fixture describes. The
runner reads the type with prop.shape_of, and compares the shape with the
shape of the vector. The comparison leaves out the source of the shape file.
The reader gives a definition the module and the name of its class, so the
comparison renames each definition after the order in which the shape first
refers to it.

The module registers the values of Status and the variants of Payment when
it is imported. A registration applies to the whole test process, so the
import comes before the first run of a property.
"""

from __future__ import annotations

import dataclasses
import ipaddress
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Annotated, Any, cast
from zoneinfo import ZoneInfo

import annotated_types

from dokimi_assert import prop
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.literal import same_json

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["FIXTURES", "fixtures_of"]

#: A signed integer of 32 bits.
Int32 = Annotated[int, prop.Width(32)]


@dataclass(frozen=True)
class Flag:
    """A record of one boolean field, enabled."""

    enabled: bool


@dataclass(frozen=True)
class Counter:
    """A record of one signed 32-bit integer field, count."""

    count: Int32


@dataclass(frozen=True)
class Ratio:
    """A record of one 64-bit float field, value."""

    value: float


@dataclass(frozen=True)
class Initial:
    """A record of one character field, letter."""

    letter: Annotated[str, prop.Char()]


@dataclass(frozen=True)
class Person:
    """A record of one text field, name."""

    name: str


@dataclass(frozen=True)
class Blob:
    """A record of one byte-string field, payload."""

    payload: bytes


@dataclass(frozen=True)
class Readings:
    """A record of one field, values, a list of signed 32-bit integers."""

    values: list[Int32]


@dataclass(frozen=True)
class Colour:
    """A record of one field, rgb, an array of exactly three unsigned bytes."""

    rgb: Annotated[
        list[Annotated[int, prop.Width(8, signed=False)]], annotated_types.Len(3, 3)
    ]


@dataclass(frozen=True)
class Tags:
    """A record of one field, tags, a set of text."""

    tags: frozenset[str]


@dataclass(frozen=True)
class Inventory:
    """A record of one field, counts, a map from text to signed 32-bit integers."""

    counts: dict[str, Int32]


@dataclass(frozen=True)
class Memo:
    """A record of one field, note, an optional text."""

    note: str | None


@dataclass(frozen=True)
class Line:
    """A line of an order with a text field sku and a signed 32-bit field qty."""

    sku: str
    qty: Int32


@dataclass(frozen=True)
class Order:
    """An order with an unsigned 32-bit id, a list of lines and an optional note."""

    id: Annotated[int, prop.Width(32, signed=False)]
    lines: list[Line]
    note: str | None


class Payment:
    """A payment state. Its variants are pending, paid and refunded, in that order."""


#: The variant of Payment without a payload.
pending = dataclasses.make_dataclass("pending", [], frozen=True)

#: The variant of Payment of a signed 64-bit amount.
paid = type("paid", (int,), {"__doc__": "A payment of a signed 64-bit amount."})

#: The variant of Payment of a text reason.
refunded = type("refunded", (str,), {"__doc__": "A refund with a text reason."})


class Status(str):
    """An enumeration of the text values pending, paid and shipped, in that order."""

    __slots__ = ()


@dataclass(frozen=True)
class Tree:
    """A tree with a signed 32-bit field value and a list of trees, children."""

    value: Int32
    children: list[Tree]


@dataclass(frozen=True)
class Account:
    """A record of one UUID field, id."""

    id: uuid.UUID


@dataclass(frozen=True)
class Host:
    """A record of one IP address field of either version, address."""

    address: ipaddress.IPv4Address | ipaddress.IPv6Address


@dataclass(frozen=True)
class Price:
    """A record of one decimal field, amount, with two digits after the point."""

    amount: Annotated[Decimal, prop.Scale(2)]


@dataclass(frozen=True)
class Event:
    """A record of one instant field, at, at microseconds."""

    at: Annotated[datetime, annotated_types.Timezone(UTC)]


@dataclass(frozen=True)
class Due:
    """A record of one date field, day."""

    day: date


@dataclass(frozen=True)
class Opening:
    """A record of one time-of-day field, opens, at microseconds."""

    opens: time


@dataclass(frozen=True)
class Appointment:
    """A record of one date-and-time field without a zone, starts, at microseconds."""

    starts: Annotated[datetime, annotated_types.Timezone(None)]


@dataclass(frozen=True)
class Timeout:
    """A record of one duration field, after, at microseconds."""

    after: timedelta


@dataclass(frozen=True)
class Offset:
    """A record of one UTC-offset field, offset."""

    offset: timezone


@dataclass(frozen=True)
class Locale:
    """A record of one time-zone field, zone."""

    zone: ZoneInfo


@dataclass(frozen=True)
class Meeting:
    """A record of one field, starts, an instant in a time zone, at microseconds."""

    starts: Annotated[datetime, annotated_types.Timezone(...)]


@dataclass(frozen=True)
class Quantity:
    """A record of one signed 32-bit integer field, qty, from 1 to 99."""

    qty: Annotated[int, prop.Width(32), annotated_types.Ge(1), annotated_types.Le(99)]


@dataclass(frozen=True)
class Batch:
    """A record of one field, lines, a list of 1 to 10 texts."""

    lines: Annotated[list[str], annotated_types.Len(1, 10)]


@dataclass(frozen=True)
class Sku:
    """A record of one text field, code.

    A code is three capital letters, a hyphen and four digits.
    """

    code: Annotated[str, prop.Pattern("[A-Z]{3}-[0-9]{4}")]


@dataclass(frozen=True)
class Hex:
    """A record of one text field, digits, over the alphabet 0123456789abcdef."""

    digits: Annotated[str, prop.Alphabet("0123456789abcdef")]


@dataclass(frozen=True)
class Measurement:
    """A record of one 64-bit float field, value, that admits NaN and the infinities."""

    value: Annotated[float, prop.AllowNan(), prop.AllowInfinity()]


@dataclass(frozen=True)
class Stamp:
    """A record of one instant field, at, at milliseconds."""

    at: Annotated[datetime, annotated_types.Timezone(UTC), prop.Unit("ms")]


@dataclass(frozen=True)
class Fee:
    """A record of one decimal field, amount.

    An amount has four digits after the point, and it is at least 0.0001.
    """

    amount: Annotated[Decimal, prop.Scale(4), annotated_types.Ge(Decimal("0.0001"))]


@dataclass(frozen=True)
class Gateway:
    """A record of one IP address field of version 4, address."""

    address: ipaddress.IPv4Address


prop.register_values(Status, Status("pending"), Status("paid"), Status("shipped"))
prop.register_variants(Payment, pending, paid, refunded)

#: The Python type of each fixture type of the definition, by the name of the
#: fixture.
FIXTURES: dict[str, type] = {
    "flag": Flag,
    "counter": Counter,
    "ratio": Ratio,
    "initial": Initial,
    "person": Person,
    "blob": Blob,
    "readings": Readings,
    "colour": Colour,
    "tags": Tags,
    "inventory": Inventory,
    "memo": Memo,
    "order": Order,
    "payment": Payment,
    "status": Status,
    "tree": Tree,
    "account": Account,
    "host": Host,
    "price": Price,
    "event": Event,
    "due": Due,
    "opening": Opening,
    "appointment": Appointment,
    "timeout": Timeout,
    "offset": Offset,
    "locale": Locale,
    "meeting": Meeting,
    "quantity": Quantity,
    "batch": Batch,
    "sku": Sku,
    "hex": Hex,
    "measurement": Measurement,
    "stamp": Stamp,
    "fee": Fee,
    "gateway": Gateway,
}


def _normal(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shape file whose referred definitions have the names #0, #1 and on.

    The numbers follow the order in which a walk of the shape first refers
    to each definition. The walk visits the members of an object in the
    order of their names and the items of a list in order. It visits a
    definition at the first ref to it. A definition outside the walk keeps
    its name.
    """
    definitions = cast("dict[str, Any]", document.get("definitions", {}))
    names: dict[str, str] = {}
    renamed: dict[str, Any] = {}

    def walk(node: object) -> object:
        if isinstance(node, list):
            return [walk(item) for item in cast("list[object]", node)]
        if not isinstance(node, dict):
            return node
        members = cast("dict[str, Any]", node)
        out: dict[str, Any] = {}
        name = members.get("name")
        if members.get("shape") == "ref" and isinstance(name, str):
            if name not in names:
                names[name] = f"#{len(names)}"
                renamed[names[name]] = walk(definitions.get(name))
            out["name"] = names[name]
        for key in sorted(members):
            if key != "definitions" and key not in out:
                out[key] = walk(members[key])
        return out

    shape = cast("dict[str, Any]", walk(document))
    if "definitions" in document:
        kept = {name: d for name, d in definitions.items() if name not in names}
        shape["definitions"] = {**kept, **renamed}
    return shape


def fixtures_of(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Compare the shape of the fixture type of a vector with the shape of the vector.

    Args:
        raw: The JSON object of the vector.

    Returns:
        An empty dict, because the vector does not have outputs to compare
        beside the shape.

    Raises:
        FaultError: The fixture type does not exist, or it has another shape
            than the vector.
    """
    fixture = raw.get("fixture")
    t = FIXTURES.get(fixture) if isinstance(fixture, str) else None
    if t is None:
        at = "fixture"
        raise FaultError(at, f"{json.dumps(fixture)} is not a fixture type")
    read = json.loads(prop.shape_of(t))
    del read["source"]
    got = _normal(read)
    want = _normal(cast("dict[str, Any]", raw.get("shape")))
    if not same_json(got, want):
        at = "shape"
        raise FaultError(
            at,
            f"the fixture type has the shape {json.dumps(got, sort_keys=True)}, "
            f"want {json.dumps(want, sort_keys=True)}",
        )
    return {}
