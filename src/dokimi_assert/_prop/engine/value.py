# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""Decoded values and the equality that decides uniqueness.

The generators of the engine decode to Python values: None, a bool, an int,
a float, a str, bytes, a list, Pairs for a dict, and Fields and Variant for
the record and enum shapes. canonical gives every value a text. Two values
share their text exactly when they are equal, and floats compare by their
bits.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
import enum
import fractions
import ipaddress
import json
import math
import uuid
import zoneinfo
from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from typing import Any

from dokimi_assert._prop.engine.float import NAN_BITS, bits_of

__all__ = ["Fields", "Pairs", "Variant", "canonical"]

#: The types whose repr contains their whole value. Two equal values of one
#: such type share their text.
_BY_REPR: tuple[type, ...] = (
    dt.date,
    dt.time,
    dt.timedelta,
    dt.tzinfo,
    decimal.Decimal,
    fractions.Fraction,
    uuid.UUID,
    ipaddress.IPv4Address,
    ipaddress.IPv6Address,
    zoneinfo.ZoneInfo,
    complex,
)


@dataclass(frozen=True, slots=True)
class Pairs:
    """A decoded dict with its entries in the order of their generation.

    The keys are distinct under canonical.

    Attributes:
        items: The entries. Each entry is a key and a value.
    """

    items: tuple[tuple[Any, Any], ...]


@dataclass(frozen=True, slots=True)
class Fields:
    """A decoded record of the names and values of its fields in declaration order.

    The names of the fields are distinct.

    Attributes:
        fields: The fields. Each field is a name and a value.
    """

    fields: tuple[tuple[str, Any], ...]


class Variant:
    """A decoded variant of an enum. It has a name and an optional payload.

    A variant whose optional payload is absent has the payload None and
    has_payload set.

    Attributes:
        name: The name of the variant.
        payload: The payload when has_payload is set, and None otherwise.
        has_payload: When True, the variant has a payload.
    """

    def __init__(self, name: str, *payload: Any) -> None:
        """Return the variant of a name and an optional payload.

        Args:
            name: The name of the variant.
            *payload: The payload. A variant has at most one, and the call of
                a variant without a payload does not pass one.
        """
        self.name: str = name
        self.has_payload: bool = len(payload) == 1
        self.payload: Any = payload[0] if payload else None


def _sorted(texts: Any) -> str:
    """Return the sorted texts joined by commas."""
    return ",".join(sorted(texts))


def _field(name: str, value: Any) -> str:
    """Return the canonical text of one field of a record."""
    return f"{json.dumps(name)}={canonical(value)}"


# canonical takes one call of this function for each level of a value, and a
# value of a recursive shape has up to 100 levels. A split of this function
# adds a frame to each level, and such a value then passes the recursion limit.
def _canonical_object(value: object) -> str:  # noqa: C901, PLR0911
    """Return the canonical text of a value that is not a scalar."""
    if isinstance(value, Pairs):
        entries = [f"{canonical(k)}={canonical(v)}" for k, v in value.items]
        return f"map:{{{_sorted(entries)}}}"
    if isinstance(value, Fields):
        return f"record:[{','.join(_field(n, v) for n, v in value.fields)}]"
    if isinstance(value, Variant):
        payload = f"={canonical(value.payload)}" if value.has_payload else ""
        return f"variant:{json.dumps(value.name)}{payload}"
    if isinstance(value, enum.Enum):
        return f"enum:{type(value).__qualname__}.{value.name}"
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = [
            _field(f.name, getattr(value, f.name)) for f in dataclasses.fields(value)
        ]
        return f"record:{type(value).__qualname__}[{','.join(fields)}]"
    if isinstance(value, tuple) and hasattr(value, "_fields"):
        named: Any = value
        fields = [_field(n, getattr(named, n)) for n in named._fields]
        return f"record:{type(value).__qualname__}[{','.join(fields)}]"
    if isinstance(value, (list, tuple)):
        items: Any = value
        return f"list:[{','.join(canonical(item) for item in items)}]"
    if isinstance(value, Mapping):
        mapping: Mapping[Any, Any] = value
        entries = [f"{canonical(k)}={canonical(v)}" for k, v in mapping.items()]
        return f"map:{{{_sorted(entries)}}}"
    if isinstance(value, AbstractSet):
        elements: AbstractSet[Any] = value
        return f"set:{{{_sorted(canonical(e) for e in elements)}}}"
    if isinstance(value, _BY_REPR):
        return f"{type(value).__qualname__}:{value!r}"
    return f"identity:{id(value)}"


def canonical(value: object) -> str:
    """Return the canonical text of a value.

    Two values have one text exactly when they are equal. A float compares
    by its bits, so -0.0 differs from 0.0 and every NaN is one value. A
    bool, an int and a float are of different types. A list and a tuple
    compare by their items in order. A dict compares by its entries in any
    order, and a set by its elements in any order. A dataclass and a named
    tuple compare by their type and their fields in order. A date or time
    value, a Decimal, a Fraction, a UUID and an address compare by their
    type and their repr. A member of an enum compares by its type and its
    name. Any other object compares by identity.

    Args:
        value: The value.

    Returns:
        The text.
    """
    if value is None:
        return "null"
    if isinstance(value, (bool, int, float)):
        return _canonical_number(value)
    if isinstance(value, (str, bytes, bytearray)):
        return _canonical_text(value)
    return _canonical_object(value)


def _canonical_number(value: float) -> str:
    """Return the canonical text of a bool, an int or a float.

    An int that is a member of an enum has the text of its type and its name.
    """
    if isinstance(value, bool):
        return f"bool:{'true' if value else 'false'}"
    if isinstance(value, int) and not isinstance(value, enum.Enum):
        return f"int:{value}"
    if isinstance(value, float):
        return f"float:{NAN_BITS if math.isnan(value) else bits_of(value)}"
    return _canonical_object(value)


def _canonical_text(value: str | bytes | bytearray) -> str:
    """Return the canonical text of a str, bytes or a bytearray.

    A str that is a member of an enum has the text of its type and its name.
    """
    if isinstance(value, str) and not isinstance(value, enum.Enum):
        return f"string:{json.dumps(value)}"
    if isinstance(value, (bytes, bytearray)):
        return f"bytes:{bytes(value).hex()}"
    return _canonical_object(value)
