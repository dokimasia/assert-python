"""The decoder of the typed literals of a corpus case, and their comparison.

A case has its arguments in a language-neutral encoding, because every
implementation runs the same case. This module decodes the encoding into
Python values, and it compares a reported value with a value of a case.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import math
import re
from collections.abc import Callable, Mapping
from typing import Any

from dokimi_assert._files.literal import decode as decode_tree

__all__ = [
    "LiteralError",
    "Objects",
    "RefFloat",
    "RefInt",
    "RefStr",
    "canonical",
    "decode",
    "same_json",
]

#: The floats without a JSON syntax, by their names in the encoding.
_NAMED_FLOATS = {"NaN": math.nan, "Inf": math.inf, "-Inf": -math.inf}

#: The scalar types that a list or a map can have as its element type.
_SCALARS = frozenset({"bool", "int", "float", "string"})

#: The lowercase hexadecimal text of bytes.
_HEX = re.compile(r"(?:[0-9a-f]{2})*")

#: The decimal text of an integer.
_DIGITS = re.compile(r"-?[0-9]+")


class LiteralError(ValueError):
    """A typed literal that the decoder cannot decode.

    A case that cannot be decoded stops the run, so it does not become an
    empty case that passes.
    """


class RefInt(int):
    """An int that is a reference. A reference literal decodes to it."""


class RefFloat(float):
    """A float that is a reference. A reference literal decodes to it."""


class RefStr(str):
    """A str that is a reference. A reference literal decodes to it."""


#: The class of the object of a reference literal by the type of its value.
#: An instance of a subclass of a value type is a reference, so each decode
#: returns an object of its own. The encoder writes such an object as the
#: literal of its value.
_REFERENCES: dict[type, Callable[[Any], Any]] = {
    int: RefInt,
    float: RefFloat,
    str: RefStr,
}

#: The classes of the records that the decoder builds, by their field names.
_RECORDS: dict[tuple[str, ...], type] = {}


def _record_class(names: tuple[str, ...]) -> type:
    """Return the dataclass of a record with the field names.

    Each set of names has one class.
    """
    cls = _RECORDS.get(names)
    if cls is None:
        if not all(name.isidentifier() for name in names):
            raise LiteralError(
                f"a field name of a record is not an identifier: {names!r}"
            )
        cls = dataclasses.make_dataclass("Record", list(names), frozen=True)
        _RECORDS[names] = cls
    return cls


def _integer(value: object) -> int:
    """Return the int of a JSON number or of the decimal text of a larger number."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and _DIGITS.fullmatch(value):
        return int(value)
    raise LiteralError(f"the value {json.dumps(value)} is not an int")


def _float(value: object) -> float:
    """Return the float of a JSON number or of a named float.

    The names are those of the floats without a JSON syntax.
    """
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value in _NAMED_FLOATS:
        return _NAMED_FLOATS[value]
    raise LiteralError(f"the value {json.dumps(value)} is not a float")


def _scalar(of: str, value: object) -> Any:
    """Return one element of the type of in a scalar list or map."""
    if of == "int":
        return _integer(value)
    if of == "float":
        return _float(value)
    if of == "bool":
        if not isinstance(value, bool):
            raise LiteralError(f"the value {json.dumps(value)} is not a bool")
        return value
    if not isinstance(value, str):
        raise LiteralError(f"the value {json.dumps(value)} is not a string")
    return value


def _element_type(literal: Mapping[str, Any], which: str) -> str:
    """Return the element type of a list or a map, or raise LiteralError.

    An empty collection decodes without the type, so the decoder checks the
    type first.
    """
    element = literal.get(which)
    if element is None:
        raise LiteralError(
            f"a {literal.get('type')} does not have the member {json.dumps(which)}"
        )
    if element not in _SCALARS:
        raise LiteralError(
            f"the member {json.dumps(which)} of a {literal.get('type')} is not a "
            f"scalar: {json.dumps(element)}"
        )
    return str(element)


class Objects:
    """The objects of the references of one case.

    Every reference of one id in a case is one object. The first literal of
    an id decodes to a new object of its value, and each later literal decodes
    to that object.
    """

    def __init__(self) -> None:
        """Return the objects of a case before its first reference."""
        self._by_id: dict[str, Any] = {}

    def decode(self, literal: Mapping[str, Any]) -> Any:
        """Return the value of a typed literal.

        Args:
            literal: One typed literal of the case.

        Returns:
            The value for an assertion. A tree literal decodes to a tree of
            files.

        Raises:
            LiteralError: The literal has a type that the encoding does not
                define, or a value that its type does not allow.
            FaultError: The literal is a tree literal that breaks a rule of a
                tree. The error is at the member of the literal that breaks it.
        """
        kind = literal.get("type")
        if kind == "null":
            return None
        if kind in _SCALARS:
            return _scalar(str(kind), literal.get("value"))
        if kind == "bytes":
            value = literal.get("value")
            if not isinstance(value, str) or not _HEX.fullmatch(value):
                raise LiteralError(
                    f"the bytes value {json.dumps(value)} is not lowercase hexadecimal"
                )
            return bytes.fromhex(value)
        if kind == "list":
            return self._list(literal)
        if kind == "map":
            return self._map(literal)
        if kind == "record":
            return self._record(literal)
        if kind == "reference":
            return self._reference(literal)
        if kind == "tree":
            return decode_tree(literal)
        raise LiteralError(f"unknown literal type: {kind}")

    def _list(self, literal: Mapping[str, Any]) -> list[Any] | None:
        """Decode a list of scalar values of one type or of item literals."""
        if "items" in literal:
            items = literal["items"]
            if not isinstance(items, list):
                raise LiteralError("the items of a list are not an array")
            return [self.decode(item) for item in items]
        of = _element_type(literal, "of")
        value = literal.get("value")
        if value is None:
            return None
        if not isinstance(value, list):
            raise LiteralError("the value of a list is not an array")
        return [_scalar(of, element) for element in value]

    def _map(self, literal: Mapping[str, Any]) -> dict[Any, Any] | None:
        """Decode a map of str keys and scalar values or of entry literals."""
        if "entries" in literal:
            entries = literal["entries"]
            if not isinstance(entries, list):
                raise LiteralError("the entries of a map are not an array")
            return {self.decode(key): self.decode(value) for key, value in entries}
        of = _element_type(literal, "of")
        _element_type(literal, "key")
        value = literal.get("value")
        if value is None:
            return None
        if not isinstance(value, dict):
            raise LiteralError("the value of a map is not an object")
        return {key: _scalar(of, element) for key, element in value.items()}

    def _record(self, literal: Mapping[str, Any]) -> Any:
        """Decode a record into a dataclass of its fields, in order."""
        fields = literal.get("fields")
        if not isinstance(fields, list):
            raise LiteralError("the fields of a record are not an array")
        names = tuple(str(name) for name, _ in fields)
        values = [self.decode(value) for _, value in fields]
        return _record_class(names)(*values)

    def _reference(self, literal: Mapping[str, Any]) -> Any:
        """Decode a reference into the object of its id."""
        ident = literal.get("id")
        if not isinstance(ident, str):
            raise LiteralError("a reference does not have an id")
        if ident in self._by_id:
            return self._by_id[ident]
        value = self.decode(literal["value"])
        box = _REFERENCES.get(type(value))
        if value is None or isinstance(value, bool):
            raise LiteralError(
                f"a reference of {json.dumps(literal['value'])} does not have an object"
            )
        obj = box(value) if box is not None else value
        self._by_id[ident] = obj
        return obj


def decode(literal: Mapping[str, Any]) -> Any:
    """Return the value of a typed literal that is the only literal of its case.

    Args:
        literal: One typed literal of a corpus case.

    Returns:
        The value for an assertion.
    """
    return Objects().decode(literal)


def canonical(value: object) -> str:
    """Return the canonical text of value under the equality of the encoding.

    The runner compares a reported value with the value of a case through
    their texts.

    - An int and a float are different kinds. -0.0 differs from 0.0, and
      every NaN is one value.
    - The text of a list or a tuple has the elements in order. bytes and a
      bytearray have one text.
    - The text of a mapping has the entries in the order of their texts, so
      two maps of equal entries have one text.
    - The text of a dataclass has the fields in order with their names. A
      member of an Enum is a variant of its name.
    - Any other value has the empty text. A value of a case never has the
      empty text.

    Args:
        value: A reported or a decoded value.

    Returns:
        The text.
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return f"bool:{str(value).lower()}"
    if isinstance(value, enum.Enum):
        return f"variant:{value.name}"
    if isinstance(value, int):
        return f"int:{int(value)}"
    if isinstance(value, float):
        return "float:nan" if math.isnan(value) else f"float:{float(value)!r}"
    if isinstance(value, str):
        return f"string:{json.dumps(str(value), ensure_ascii=False)}"
    if isinstance(value, (bytes, bytearray)):
        return f"bytes:{bytes(value).hex()}"
    if isinstance(value, (list, tuple)):
        return "list:[" + ",".join(canonical(item) for item in value) + "]"
    if isinstance(value, Mapping):
        entries = sorted(f"{canonical(k)}={canonical(v)}" for k, v in value.items())
        return "map:{" + ",".join(entries) + "}"
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = [
            f"{json.dumps(f.name)}={canonical(getattr(value, f.name))}"
            for f in dataclasses.fields(value)
        ]
        return "record:[" + ",".join(fields) + "]"
    return ""


def _sorted_json(value: Any) -> str:
    """Return the JSON text of value, with the members of each object in name order."""
    if isinstance(value, list):
        return "[" + ",".join(_sorted_json(item) for item in value) + "]"
    if isinstance(value, dict):
        members = [
            f"{json.dumps(name)}:{_sorted_json(value[name])}" for name in sorted(value)
        ]
        return "{" + ",".join(members) + "}"
    return json.dumps(value)


def same_json(a: Any, b: Any) -> bool:
    """Report whether two JSON values are the same value.

    Two objects are the same when they have the same members in any order.
    Two arrays are the same when they have the same elements in order.

    Args:
        a: A JSON value, as json.loads returns it.
        b: Another JSON value.

    Returns:
        True for the same value.
    """
    return _sorted_json(a) == _sorted_json(b)
