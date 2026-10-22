# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The typed literals of decoded values.

The vectors of the definition give each value as a typed literal. decode
returns the value of a literal, and encode returns the one canonical literal
of a decoded value. Besides `type`, the literal of each type has these
fields.

- A null has no other field.
- A bool, a string and a float have `value`. A float that is not finite has
  the value NaN, Inf or -Inf.
- An int has `value`. The value is a JSON integer up to 2^53 - 1 in
  magnitude, and a decimal string above that.
- Bytes have `value` in lowercase hexadecimal.
- A list of one scalar type with at least one element has `of` and
  `value`. Any other list has `items`.
- A map has `entries`. The entries are pairs of a key literal and a value
  literal in the order of the map. The map decodes as Pairs. A map with
  string keys can instead have `key`, `of` and a JSON object as its
  `value`.
- A list or a map of a scalar type with the value null is absent. It
  decodes to None.
- A record has `fields`, a list of pairs of a name and a value literal. The
  record decodes as Fields.
- A variant has `name`, and `payload` when the variant has a payload. It
  decodes as a Variant.
- A reference has `id` and `value`. It decodes to its value.
"""

from __future__ import annotations

import json
import math
import re
from typing import TYPE_CHECKING, Any, TypeGuard

from dokimi_assert._prop.engine.value import Fields, Pairs, Variant, canonical

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = ["LiteralError", "decode", "encode", "integer", "number", "plain"]

#: The largest integer magnitude that every language decodes exactly from a
#: JSON number.
_SAFE_INTEGER = 2**53 - 1

#: The names of the floats that JSON does not have, with their values.
_NON_FINITE = {"NaN": math.nan, "Inf": math.inf, "-Inf": -math.inf}

#: The scalar types that the fields `of` and `key` can have.
_SCALARS = frozenset({"bool", "int", "float", "string"})

#: The decimal text of an integer and the lowercase hexadecimal text of bytes.
_DECIMAL = re.compile(r"-?[0-9]+")
_HEX = re.compile(r"(?:[0-9a-f]{2})*")


class LiteralError(ValueError):
    """The error of a literal that the encoding does not define."""


def _shown(value: object) -> str:
    """Return the compact JSON text of a value for an error message."""
    return json.dumps(value, separators=(",", ":"))


def _is_int(value: object) -> TypeGuard[int]:
    """Report whether a value is an int that is not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


#: The values of a pair.
_PAIR = 2


def _is_pair(entry: object) -> TypeGuard[list[Any]]:
    """Report whether an entry is a JSON array of two values."""
    if not isinstance(entry, list):
        return False
    stated: list[object] = entry
    return len(stated) == _PAIR


def integer(value: object) -> int:
    """Return the int of a JSON integer or of a decimal string.

    A JSON integer has a magnitude of at most 2^53 - 1. A larger integer is a
    canonical decimal string.

    Args:
        value: The JSON value.

    Returns:
        The integer.

    Raises:
        LiteralError: The value is not an integer in either form.
    """
    if _is_int(value):
        if abs(value) > _SAFE_INTEGER:
            msg = f"prop: {value} is not a safe integer, so it must be a string"
            raise LiteralError(msg)
        return value
    if isinstance(value, str) and _DECIMAL.fullmatch(value):
        parsed = int(value)
        if abs(parsed) <= _SAFE_INTEGER or str(parsed) != value:
            msg = f"prop: {_shown(value)} is not a canonical large integer"
            raise LiteralError(msg)
        return parsed
    msg = f"prop: {_shown(value)} is not an integer"
    raise LiteralError(msg)


def number(value: object) -> float:
    """Return the float of a JSON number or of the name NaN, Inf or -Inf.

    An integer outside the range of a float becomes the infinity of its sign.
    IEEE 754 rounds it the same way.

    Args:
        value: The JSON value.

    Returns:
        The float.

    Raises:
        LiteralError: The value is not a number or one of the names.
    """
    if isinstance(value, float):
        return value
    if _is_int(value):
        try:
            return float(value)
        except OverflowError:
            return math.inf if value > 0 else -math.inf
    if isinstance(value, str) and value in _NON_FINITE:
        return _NON_FINITE[value]
    msg = f"prop: {_shown(value)} is not a float"
    raise LiteralError(msg)


def _scalar(kind: object, value: object) -> object:
    """Return a value as a scalar of the type kind."""
    if kind == "bool" and isinstance(value, bool):
        return value
    if kind == "int":
        return integer(value)
    if kind == "float":
        return number(value)
    if kind == "string" and isinstance(value, str):
        return value
    msg = f"prop: {_shown(value)} is not a literal of type {_shown(kind)}"
    raise LiteralError(msg)


def _bytes_of(value: object) -> bytes:
    """Return the bytes of lowercase hexadecimal text."""
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        msg = f"prop: {_shown(value)} is not lowercase hexadecimal"
        raise LiteralError(msg)
    return bytes.fromhex(value)


def _absent(literal: Mapping[str, Any]) -> bool:
    """Report whether a literal is an absent container of a scalar type."""
    if "value" not in literal or literal["value"] is not None:
        return False
    if literal.get("of") not in _SCALARS:
        msg = f"prop: the absent value of {_shown(literal)} does not have a scalar type"
        raise LiteralError(msg)
    return True


def _list_of(literal: Mapping[str, Any]) -> list[object] | None:
    """Return the list of a literal, or None for an absent list.

    The literal has `of` and `value`, or it has `items`.
    """
    if "items" in literal:
        items = literal["items"]
        if not isinstance(items, list):
            msg = f"prop: items is {_shown(items)}, not a list"
            raise LiteralError(msg)
        return [decode(item) for item in items]
    if _absent(literal):
        return None
    values = literal.get("value")
    if not isinstance(values, list):
        msg = f"prop: {_shown(literal)} does not have a list as its value"
        raise LiteralError(msg)
    of = literal.get("of")
    return [_scalar(of, element) for element in values]


def _map_of(literal: Mapping[str, Any]) -> Pairs | None:
    """Return the map of a literal, or None for an absent map.

    The literal has `entries`. A map with string keys can instead have `key`,
    `of` and a JSON object as its `value`.
    """
    if "entries" in literal:
        entries = literal["entries"]
        if not isinstance(entries, list) or not all(map(_is_pair, entries)):
            msg = f"prop: entries is {_shown(entries)}, not key and value pairs"
            raise LiteralError(msg)
        return Pairs(tuple((decode(k), decode(v)) for k, v in entries))
    if literal.get("key") != "string":
        msg = f"prop: {_shown(literal)} is not a map with string keys"
        raise LiteralError(msg)
    if _absent(literal):
        return None
    values = literal.get("value")
    if not isinstance(values, dict):
        msg = f"prop: {_shown(literal)} is not a map with string keys"
        raise LiteralError(msg)
    of = literal.get("of")
    return Pairs(tuple((k, _scalar(of, v)) for k, v in values.items()))


def _named(field: object) -> TypeGuard[list[Any]]:
    """Report whether a field is a pair of a name that is not empty and a value."""
    return _is_pair(field) and isinstance(field[0], str) and field[0] != ""


def _record_of(literal: Mapping[str, Any]) -> Fields:
    """Return the record of a literal with pairs of a name and a value."""
    fields = literal.get("fields")
    if not isinstance(fields, list) or not all(map(_named, fields)):
        msg = f"prop: fields is {_shown(fields)}, not name and value pairs"
        raise LiteralError(msg)
    names = [name for name, _ in fields]
    if len(set(names)) != len(names):
        msg = f"prop: the field names {_shown(names)} repeat a name"
        raise LiteralError(msg)
    return Fields(tuple((name, decode(value)) for name, value in fields))


def _variant_of(literal: Mapping[str, Any]) -> Variant:
    """Return the variant of a literal.

    The literal has `name`, and `payload` when the variant has a payload.
    """
    name = literal.get("name")
    if not isinstance(name, str) or name == "":
        msg = f"prop: {_shown(literal)} does not have the name of a variant"
        raise LiteralError(msg)
    if "payload" in literal:
        return Variant(name, decode(literal["payload"]))
    return Variant(name)


def _reference_of(literal: Mapping[str, Any]) -> object:
    """Return the value that a reference refers to."""
    ident = literal.get("id")
    if not isinstance(ident, str) or ident == "":
        msg = f"prop: {_shown(literal)} does not have an id"
        raise LiteralError(msg)
    value: object = literal.get("value")
    if isinstance(value, dict):
        stated: dict[str, object] = value
        if stated.get("type") == "null":
            msg = (
                f"prop: the reference {_shown(ident)} refers to null, not to an object"
            )
            raise LiteralError(msg)
    return decode(value)


#: The decoder of each type of a literal that contains values, by its name.
_CONTAINERS: dict[str, Callable[[Mapping[str, Any]], object]] = {
    "list": _list_of,
    "map": _map_of,
    "record": _record_of,
    "variant": _variant_of,
    "reference": _reference_of,
}


def decode(literal: object) -> object:
    """Return the value of a typed literal.

    Args:
        literal: The literal as a JSON value.

    Returns:
        The value.

    Raises:
        LiteralError: The encoding does not define the literal.
    """
    if not isinstance(literal, dict):
        msg = f"prop: {_shown(literal)} is not a typed literal"
        raise LiteralError(msg)
    form: dict[str, Any] = literal
    kind = form.get("type")
    if kind == "null":
        return None
    if kind == "bytes":
        return _bytes_of(form.get("value"))
    container = _CONTAINERS.get(kind) if isinstance(kind, str) else None
    if container is not None:
        return container(form)
    return _scalar(kind, form.get("value"))


def _scalar_kind(value: object) -> str | None:
    """Return the scalar type of a value, or None when the value is not a scalar."""
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    return None


def plain(value: object) -> object:
    """Return the JSON form of a scalar.

    A float that is not finite becomes its name. An integer above 2^53 - 1 in
    magnitude becomes a decimal string.

    Args:
        value: A bool, an int, a float or a str.

    Returns:
        The JSON value.
    """
    if isinstance(value, float):
        if math.isnan(value):
            return "NaN"
        if math.isinf(value):
            return "Inf" if value > 0 else "-Inf"
        return value
    if _is_int(value):
        return str(value) if abs(value) > _SAFE_INTEGER else value
    return value


# encode takes one call for each level of a value, and a value of a recursive
# shape has up to 100 levels. A split of this function adds a frame to each
# level, and such a value then passes the recursion limit.
def encode(value: object) -> dict[str, Any]:  # noqa: PLR0911
    """Return the canonical typed literal of a decoded value.

    Args:
        value: A value that a generator decodes.

    Returns:
        The literal.

    Raises:
        TypeError: No generator decodes the value.
    """
    if value is None:
        return {"type": "null"}
    if isinstance(value, bytes):
        return {"type": "bytes", "value": value.hex()}
    if isinstance(value, list):
        items: list[object] = value
        kinds = {_scalar_kind(item) for item in items}
        kind = next(iter(kinds), None)
        if len(kinds) == 1 and kind is not None:
            return {"type": "list", "of": kind, "value": [plain(i) for i in items]}
        return {"type": "list", "items": [encode(item) for item in items]}
    if isinstance(value, Pairs):
        entries = [[encode(k), encode(v)] for k, v in value.items]
        return {"type": "map", "entries": entries}
    if isinstance(value, Fields):
        fields = [[name, encode(v)] for name, v in value.fields]
        return {"type": "record", "fields": fields}
    if isinstance(value, Variant):
        if value.has_payload:
            payload = encode(value.payload)
            return {"type": "variant", "name": value.name, "payload": payload}
        return {"type": "variant", "name": value.name}
    scalar = _scalar_kind(value)
    if scalar is None:
        msg = f"prop: {canonical(value)} is not a decoded value"
        raise TypeError(msg)
    return {"type": scalar, "value": plain(value)}
