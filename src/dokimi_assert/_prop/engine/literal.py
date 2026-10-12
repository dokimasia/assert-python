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
from collections.abc import Mapping
from typing import Any, TypeGuard

from dokimi_assert._prop.engine.value import Fields, Pairs, Variant, canonical

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


def _is_pair(entry: object) -> TypeGuard[list[Any]]:
    """Report whether an entry is a JSON array of two values."""
    if not isinstance(entry, list):
        return False
    stated: list[object] = entry
    return len(stated) == 2


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
            raise LiteralError(
                f"prop: {value} is not a safe integer, so it must be a string"
            )
        return value
    if isinstance(value, str) and _DECIMAL.fullmatch(value):
        parsed = int(value)
        if abs(parsed) <= _SAFE_INTEGER or str(parsed) != value:
            raise LiteralError(
                f"prop: {_shown(value)} is not a canonical large integer"
            )
        return parsed
    raise LiteralError(f"prop: {_shown(value)} is not an integer")


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
    raise LiteralError(f"prop: {_shown(value)} is not a float")


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
    raise LiteralError(f"prop: {_shown(value)} is not a literal of type {_shown(kind)}")


def _bytes_of(value: object) -> bytes:
    """Return the bytes of lowercase hexadecimal text."""
    if not isinstance(value, str) or not _HEX.fullmatch(value):
        raise LiteralError(f"prop: {_shown(value)} is not lowercase hexadecimal")
    return bytes.fromhex(value)


def _absent(literal: Mapping[str, Any]) -> bool:
    """Report whether a literal is an absent container of a scalar type."""
    if "value" not in literal or literal["value"] is not None:
        return False
    if literal.get("of") not in _SCALARS:
        raise LiteralError(
            f"prop: the absent value of {_shown(literal)} does not have a scalar type"
        )
    return True


def _list_of(literal: Mapping[str, Any]) -> list[object] | None:
    """Return the list of a literal, or None for an absent list.

    The literal has `of` and `value`, or it has `items`.
    """
    if "items" in literal:
        items = literal["items"]
        if not isinstance(items, list):
            raise LiteralError(f"prop: items is {_shown(items)}, not a list")
        return [decode(item) for item in items]
    if _absent(literal):
        return None
    values = literal.get("value")
    if not isinstance(values, list):
        raise LiteralError(f"prop: {_shown(literal)} does not have a list as its value")
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
            raise LiteralError(
                f"prop: entries is {_shown(entries)}, not key and value pairs"
            )
        return Pairs(tuple((decode(k), decode(v)) for k, v in entries))
    if literal.get("key") != "string":
        raise LiteralError(f"prop: {_shown(literal)} is not a map with string keys")
    if _absent(literal):
        return None
    values = literal.get("value")
    if not isinstance(values, dict):
        raise LiteralError(f"prop: {_shown(literal)} is not a map with string keys")
    of = literal.get("of")
    return Pairs(tuple((k, _scalar(of, v)) for k, v in values.items()))


def _named(field: object) -> TypeGuard[list[Any]]:
    """Report whether a field is a pair of a name that is not empty and a value."""
    return _is_pair(field) and isinstance(field[0], str) and field[0] != ""


def _record_of(literal: Mapping[str, Any]) -> Fields:
    """Return the record of a literal with pairs of a name and a value."""
    fields = literal.get("fields")
    if not isinstance(fields, list) or not all(map(_named, fields)):
        raise LiteralError(
            f"prop: fields is {_shown(fields)}, not name and value pairs"
        )
    names = [name for name, _ in fields]
    if len(set(names)) != len(names):
        raise LiteralError(f"prop: the field names {_shown(names)} repeat a name")
    return Fields(tuple((name, decode(value)) for name, value in fields))


def _variant_of(literal: Mapping[str, Any]) -> Variant:
    """Return the variant of a literal.

    The literal has `name`, and `payload` when the variant has a payload.
    """
    name = literal.get("name")
    if not isinstance(name, str) or name == "":
        raise LiteralError(
            f"prop: {_shown(literal)} does not have the name of a variant"
        )
    if "payload" in literal:
        return Variant(name, decode(literal["payload"]))
    return Variant(name)


def _reference_of(literal: Mapping[str, Any]) -> object:
    """Return the value that a reference refers to."""
    ident = literal.get("id")
    if not isinstance(ident, str) or ident == "":
        raise LiteralError(f"prop: {_shown(literal)} does not have an id")
    value: object = literal.get("value")
    if isinstance(value, dict):
        stated: dict[str, object] = value
        if stated.get("type") == "null":
            raise LiteralError(
                f"prop: the reference {_shown(ident)} refers to null, not to an object"
            )
    return decode(value)


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
        raise LiteralError(f"prop: {_shown(literal)} is not a typed literal")
    form: dict[str, Any] = literal
    kind = form.get("type")
    if kind == "null":
        return None
    if kind == "bytes":
        return _bytes_of(form.get("value"))
    if kind == "list":
        return _list_of(form)
    if kind == "map":
        return _map_of(form)
    if kind == "record":
        return _record_of(form)
    if kind == "variant":
        return _variant_of(form)
    if kind == "reference":
        return _reference_of(form)
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


def encode(value: object) -> dict[str, Any]:
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
        raise TypeError(f"prop: {canonical(value)} is not a decoded value")
    return {"type": scalar, "value": plain(value)}
