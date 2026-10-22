# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The typed literal of a value in a call record.

A call record contains each value of the detail of a failure as a typed
literal of the encoding of the definition. A reader in any language can then
decode it. A value without a typed literal has an opaque literal, and the
opaque literal contains the repr of the value.
"""

from __future__ import annotations

import dataclasses
import enum
import json as _json
import math
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["VALUE_DEPTH", "detail", "encode", "json", "opaque", "quoted"]

#: The most levels of objects and arrays that a literal nests. The root
#: object of a store entry, its counterexample and the draw take three of the
#: 64 levels of a file.
VALUE_DEPTH = 61

#: The most parts that the walk of one value visits. Each value is one part,
#: and each UTF-8 byte of a string, a byte string or the name of a field is
#: one more. The bound ends the walk of a value that contains itself.
_MAX_PARTS = 65_536

#: The largest integer that a JSON reader in JavaScript keeps exact.
_SAFE = 2**53 - 1


@dataclasses.dataclass(frozen=True, slots=True)
class _Written:
    """The literal of one value while the walk builds it.

    Attributes:
        form: The literal.
        scalar: The scalar type of a bool, an int, a float or a str, and
            None for any other value.
        plain: The JSON value of a scalar.
        depth: The levels of objects and arrays that the literal nests.
    """

    form: dict[str, Any]
    scalar: str | None = None
    plain: Any = None
    depth: int = 1


def _scalar(kind: str, plain: Any) -> _Written:
    """Return the literal of a scalar of the type kind with the JSON value plain."""
    return _Written(form={"type": kind, "value": plain}, scalar=kind, plain=plain)


def _float_of(value: float) -> _Written:
    """Return the literal of a float. NaN and the infinities have their names."""
    if math.isnan(value):
        return _scalar("float", "NaN")
    if math.isinf(value):
        return _scalar("float", "Inf" if value > 0 else "-Inf")
    return _scalar("float", value)


def _plain_of(value: bool | enum.Enum | float | None) -> _Written:
    """Return the literal of None, a bool, a member of an Enum, an int or a float."""
    if value is None:
        return _Written(form={"type": "null"})
    if isinstance(value, bool):
        return _scalar("bool", value)
    if isinstance(value, enum.Enum):
        return _Written(form={"type": "variant", "name": value.name})
    if isinstance(value, int):
        return _scalar("int", value if -_SAFE <= value <= _SAFE else str(value))
    return _float_of(value)


def _common_scalar(items: Sequence[_Written]) -> str | None:
    """Return the scalar type of every one of items, or None."""
    if not items:
        return None
    first = items[0].scalar
    if first is None or any(item.scalar != first for item in items):
        return None
    return first


def _is_named_tuple(value: object) -> bool:
    """Report whether value is an instance of a NamedTuple."""
    return isinstance(value, tuple) and isinstance(
        getattr(value, "_fields", None), tuple
    )


class _Walk:
    """The walk of the parts of one value."""

    def __init__(self) -> None:
        """Return a walk that has not visited a part."""
        self._parts: int = 0
        self._level: int = 0

    def _spend(self, n: int) -> bool:
        """Count n more parts, and report whether the walk is within its bound."""
        self._parts += n
        return self._parts <= _MAX_PARTS

    def _fits(self, n: int) -> bool:
        """Report whether n more parts can be within the bound of the walk."""
        return self._parts + n <= _MAX_PARTS

    def _nested(self, value: Any, levels: int) -> _Written | None:
        """Return the literal of value at levels below the current level."""
        self._level += levels
        written = self.literal_of(value)
        self._level -= levels
        return written

    def literal_of(self, value: Any) -> _Written | None:
        """Return the literal of value.

        Args:
            value: The value.

        Returns:
            The literal, or None when value has none, when the walk passes
            its bound, or when value is below more levels than a literal
            nests.
        """
        if not self._spend(1) or self._level > VALUE_DEPTH:
            return None
        if value is None or isinstance(value, (bool, enum.Enum, int, float)):
            return _plain_of(value)
        if isinstance(value, str):
            return self._text(value)
        if isinstance(value, (bytes, bytearray)):
            return self._bytes_of(value)
        return self._composite_of(value)

    def _composite_of(self, value: Any) -> _Written | None:
        """Return the literal of a dataclass, a NamedTuple, a collection or a Mapping.

        A collection is a list, a tuple, a set or a frozenset. Any other value
        does not have a literal.
        """
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            names = [f.name for f in dataclasses.fields(value)]
            return self._record_of([(name, getattr(value, name)) for name in names])
        if _is_named_tuple(value):
            named: Any = value
            fields: tuple[str, ...] = named._fields
            return self._record_of(list(zip(fields, named, strict=True)))
        if isinstance(value, (list, tuple)):
            return self._list_of(list(value))
        if isinstance(value, (set, frozenset)):
            return self._set_of(value)
        if isinstance(value, Mapping):
            return self._map_of(list(value.items()))
        return None

    def _text(self, value: str) -> _Written | None:
        """Return the literal of a str, and None for one that is not UTF-8 text."""
        try:
            encoded = value.encode("utf-8")
        except UnicodeEncodeError:
            return None
        if not self._spend(len(encoded)):
            return None
        return _scalar("string", value)

    def _bytes_of(self, value: bytes | bytearray) -> _Written | None:
        """Return the literal of bytes or a bytearray, and None past the bound."""
        if not self._spend(len(value)):
            return None
        return _Written(form={"type": "bytes", "value": bytes(value).hex()})

    def _items(self, elements: Sequence[Any]) -> list[_Written] | None:
        """Return the literal of each element two levels deeper."""
        if not self._fits(len(elements)):
            return None
        items: list[_Written] = []
        for element in elements:
            item = self._nested(element, 2)
            if item is None:
                return None
            items.append(item)
        return items

    def _list_from(self, items: list[_Written]) -> _Written:
        """Return the literal of a list of items."""
        of = _common_scalar(items)
        if of is not None:
            return _Written(
                form={"type": "list", "of": of, "value": [i.plain for i in items]},
                depth=2,
            )
        deepest = max((i.depth for i in items), default=0)
        return _Written(
            form={"type": "list", "items": [i.form for i in items]}, depth=2 + deepest
        )

    def _list_of(self, elements: Sequence[Any]) -> _Written | None:
        """Return the literal of a list or a tuple with its items in order."""
        items = self._items(elements)
        return None if items is None else self._list_from(items)

    def _set_of(self, elements: set[Any] | frozenset[Any]) -> _Written | None:
        """Return the literal of a set with its items in the order of their JSON text.

        The iteration order of a set of strings changes with PYTHONHASHSEED.
        The sorted order keeps the record of a set the same in every run.
        """
        items = self._items(list(elements))
        if items is None:
            return None
        items.sort(key=lambda i: json(i.form))
        return self._list_from(items)

    def _map_of(self, entries: Sequence[tuple[Any, Any]]) -> _Written | None:
        """Return the literal of a map with its entries in the order of the map."""
        if not self._fits(2 * len(entries)):
            return None
        pairs: list[list[dict[str, Any]]] = []
        depth = 2
        for key, value in entries:
            k = self._nested(key, 3)
            if k is None:
                return None
            v = self._nested(value, 3)
            if v is None:
                return None
            pairs.append([k.form, v.form])
            depth = max(depth, 3 + k.depth, 3 + v.depth)
        return _Written(form={"type": "map", "entries": pairs}, depth=depth)

    def _record_of(self, fields: Sequence[tuple[str, Any]]) -> _Written | None:
        """Return the literal of a record with its fields in declaration order."""
        if not self._fits(len(fields)):
            return None
        stated: list[list[Any]] = []
        depth = 2
        for name, value in fields:
            if not self._spend(len(name.encode())):
                return None
            written = self._nested(value, 3)
            if written is None:
                return None
            stated.append([name, written.form])
            depth = max(depth, 3 + written.depth)
        return _Written(form={"type": "record", "fields": stated}, depth=depth)


def encode(value: Any) -> dict[str, Any] | None:
    """Return the typed literal of value, or None when value does not have one.

    - None is null, a bool is a bool and a str that is UTF-8 text is a
      string.
    - An int is an int. Beyond 2^53 - 1 and below -(2^53 - 1), the literal
      has the digits of the int as a string.
    - A float is a float. NaN, Inf and -Inf have their names.
    - bytes and a bytearray are bytes.
    - A list and a tuple are a list. The list has scalar values when every
      element is a scalar of one type, and item literals otherwise. A set and
      a frozenset are a list of their items in the order of the JSON text of
      the literals of the items.
    - A Mapping is a map of its entries in the order of the Mapping.
    - A dataclass and a NamedTuple are a record of their fields in
      declaration order.
    - A member of an Enum is a variant without a payload.

    Any other value does not have a typed literal, and neither does a value
    that contains one. A value whose literal nests more than 61 levels does
    not have one either, and neither does a value of more than 65,536 parts.

    Args:
        value: The value.

    Returns:
        The literal, or None.
    """
    written = _Walk().literal_of(value)
    if written is None or written.depth > VALUE_DEPTH:
        return None
    return written.form


def opaque(text: str) -> dict[str, Any]:
    """Return the opaque literal of a value without a typed literal.

    Args:
        text: The repr of the value. The sentence of a failure prints the
            same text.

    Returns:
        The literal {"type": "opaque", "text": text}.
    """
    return {"type": "opaque", "text": text}


def detail(value: Any) -> dict[str, Any]:
    """Return the literal of value in the detail of a call record.

    Args:
        value: A value of the detail of a failure.

    Returns:
        The typed literal of value, or the opaque literal of its repr.
    """
    encoded = encode(value)
    return encoded if encoded is not None else opaque(repr(value))


def json(value: Any) -> str:
    """Return the JSON text of a JSON value on one line.

    The keys of each object keep their order.

    Args:
        value: A JSON value. It is None, a bool, an int, a finite float, a
            str, or a list or a dict with str keys of JSON values.

    Returns:
        The text, without spaces between its tokens.

    Raises:
        ValueError: value contains a float that is not finite.
    """
    return _json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )


#: The first and the last code point of the surrogates of UTF-16.
_FIRST_SURROGATE = 0xD800
_LAST_SURROGATE = 0xDFFF


def quoted(text: str) -> str:
    """Return the JSON text of a str for a message that quotes it.

    Every character but a lone surrogate keeps its form, so a message stays
    readable. A lone surrogate becomes its escape, so the message is valid
    UTF-8 for any str.

    Args:
        text: The str.

    Returns:
        The JSON string literal of text.
    """
    stated = _json.dumps(text, ensure_ascii=False)
    return "".join(
        f"\\u{ord(c):04x}" if _FIRST_SURROGATE <= ord(c) <= _LAST_SURROGATE else c
        for c in stated
    )
