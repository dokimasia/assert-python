"""The typed-literal encoding a corpus case states its values in."""

from __future__ import annotations

import math
from typing import Any

NULL = "null"
BOOL = "bool"
INT = "int"
FLOAT = "float"
STRING = "string"
LIST = "list"
MAP = "map"

#: The float values JSON has no number for.
_NAMED_FLOATS = {"NaN": math.nan, "Inf": math.inf, "-Inf": -math.inf}

#: Scalar decoders, keyed by the tag a literal carries.
_SCALARS: dict[str, type] = {BOOL: bool, INT: int, STRING: str}


class UnknownLiteralError(ValueError):
    """A typed literal this decoder does not implement."""


def decode(literal: dict[str, Any]) -> Any:
    """Turn one typed literal into a native value.

    An empty list decodes to a list and an empty mapping to a dict,
    never to None. That is what lets a case tell a collection that is
    absent from one that is present and empty, which is the rule the
    encoding exists to pin.

    Args:
        literal: One typed literal from a corpus case.

    Returns:
        The native value the literal states.
    """
    tag = literal.get("type")

    if tag == NULL:
        return None
    if tag in _SCALARS:
        return _SCALARS[tag](literal["value"])
    if tag == FLOAT:
        return _decode_float(literal["value"])
    if tag == LIST:
        _refuse_unknown_element(literal["of"])
        return [_element(literal["of"], v) for v in literal["value"]]
    if tag == MAP:
        return _decode_map(literal)

    raise UnknownLiteralError(f"unknown typed-literal type {tag!r}")


def _decode_float(value: Any) -> float:
    """Accept a JSON number, or a name JSON has no number for."""
    if isinstance(value, str):
        if value not in _NAMED_FLOATS:
            raise UnknownLiteralError(f"unrecognised float literal {value!r}")
        return _NAMED_FLOATS[value]
    return float(value)


def _decode_map(literal: dict[str, Any]) -> dict[str, Any]:
    """Materialise a mapping, which the encoding keys by string."""
    if literal.get("key") != STRING:
        raise UnknownLiteralError(f"map keyed by {literal.get('key')!r}")
    _refuse_unknown_element(literal["of"])
    return {k: _element(literal["of"], v) for k, v in literal["value"].items()}


def _refuse_unknown_element(of: str) -> None:
    """Refuse an element type before the collection is walked.

    An empty collection never reaches the element decoder, so checking
    only per element would let a literal naming a type this does not
    implement decode to an empty value rather than being refused. A gap
    in the encoding has to be visible, not silent.
    """
    if of != FLOAT and of not in _SCALARS:
        raise UnknownLiteralError(f"element type {of!r}")


def _element(of: str, value: Any) -> Any:
    """Materialise one element of a list or mapping."""
    if of == FLOAT:
        return _decode_float(value)
    if of not in _SCALARS:
        raise UnknownLiteralError(f"element type {of!r}")
    return _SCALARS[of](value)
