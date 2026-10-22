# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The typed literal of a drawn value in the type that its generator decodes.

The type of a draw is the type of its generator, so an integral float is
still a float. A value of a map with an inverse has the literal of the value
that the map received, and a value of a deferred generator the literal of
the generator that it picks. A store entry and the call record of a property
write each draw this way, so the option draws can replay the counterexample
of an entry.
"""

from __future__ import annotations

from typing import Any

from dokimi_assert._prop.engine import literal as engine
from dokimi_assert._prop.engine.generator import (
    Bool,
    Bytes,
    Deferred,
    Dict,
    Filter,
    Float,
    Integer,
    List,
    Mapped,
    Matching,
    Optional,
    Text,
)
from dokimi_assert._prop.engine.shape import (
    EnumShape,
    Int128Shape,
    IpShape,
    ListShape,
    MapShape,
    OptionalShape,
    RecordShape,
    Ref,
    Root,
)
from dokimi_assert._prop.engine.value import Fields, Pairs, Variant
from dokimi_assert._record.literal import encode

__all__ = ["drawn_literal"]

#: The scalar types of a list in the of form.
_SCALARS = frozenset({"bool", "int", "float", "string"})

#: A typed literal as a JSON object.
Literal = dict[str, Any]


def _generic(value: object) -> Literal | None:
    """Return the literal of a value whose generator does not have a type.

    The engine encodes a decoded record, dict or variant, and the library
    encodes any other value.
    """
    if isinstance(value, (Pairs, Fields, Variant)):
        try:
            return engine.encode(value)
        except TypeError:
            return None
    return encode(value)


def _list_of(items: list[Literal | None]) -> Literal | None:
    """Return the literal of a list whose elements have the literals items."""
    literals = [item for item in items if item is not None]
    if len(literals) < len(items):
        return None
    kinds = {literal["type"] for literal in literals}
    if len(kinds) == 1 and kinds <= _SCALARS:
        values = [literal["value"] for literal in literals]
        return {"type": "list", "of": next(iter(kinds)), "value": values}
    return {"type": "list", "items": literals}


def _map_of(keys: object, values: object, value: object) -> Literal | None:
    """Return the literal of a dict. The generators of the dict encode its entries."""
    if not isinstance(value, Pairs):
        return _generic(value)
    entries: list[list[Literal]] = []
    for k, v in value.items:
        key = drawn_literal(keys, k)
        encoded = drawn_literal(values, v)
        if key is None or encoded is None:
            return None
        entries.append([key, encoded])
    return {"type": "map", "entries": entries}


def _record_of(generator: RecordShape, value: object) -> Literal | None:
    """Return the literal of a record. The generator of each field encodes it."""
    if not isinstance(value, Fields):
        return _generic(value)
    fields: list[list[Any]] = []
    for (name, of), (_, field) in zip(generator.fields, value.fields, strict=True):
        literal = drawn_literal(of, field)
        if literal is None:
            return None
        fields.append([name, literal])
    return {"type": "record", "fields": fields}


def _variant_of(generator: EnumShape, value: object) -> Literal | None:
    """Return the literal of a variant. The generator of the payload encodes it."""
    if not isinstance(value, Variant):
        return _generic(value)
    payloads = dict(generator.variants)
    payload = payloads.get(value.name)
    if not value.has_payload or payload is None:
        return _generic(value)
    literal = drawn_literal(payload, value.payload)
    if literal is None:
        return None
    return {"type": "variant", "name": value.name, "payload": literal}


def _mapped_of(generator: Mapped[Any, Any], value: object) -> Literal | None:
    """Return the literal of a mapped value through the inverse of the map."""
    back = generator.back
    if back is None:
        return _generic(value)
    try:
        inner = back(value)
    except Exception:
        return _generic(value)
    return drawn_literal(generator.of, inner)


def _elements_of(of: object, value: object) -> Literal | None:
    """Return the literal of a list. The generator of encodes each element."""
    if not isinstance(value, list):
        return _generic(value)
    items: list[object] = value
    return _list_of([drawn_literal(of, item) for item in items])


def _wrapped(generator: object) -> object | None:
    """Return the generator inside a filter, the root of a shape file or a ref.

    The result is None for any other generator.
    """
    if isinstance(generator, Filter):
        filtered: Filter[Any] = generator
        return filtered.of
    if isinstance(generator, Root):
        return generator.node
    if isinstance(generator, Ref):
        return generator.definitions.get(generator.name)
    return None


def _typed(generator: object, value: object) -> Literal | None:
    """Return the literal of a value of a generator of values of one type.

    The result is None for a generator of a different kind, and for a value
    of a different type than the type of the generator.
    """
    whole = isinstance(value, int) and not isinstance(value, bool)
    if isinstance(generator, (Integer, Int128Shape)) and whole:
        return {"type": "int", "value": engine.plain(value)}
    if isinstance(generator, Float) and isinstance(value, float):
        return {"type": "float", "value": engine.plain(value)}
    if isinstance(generator, Bool) and isinstance(value, bool):
        return {"type": "bool", "value": value}
    if isinstance(generator, (Text, Matching)) and isinstance(value, str):
        return {"type": "string", "value": value}
    if isinstance(generator, (Bytes, IpShape)) and isinstance(value, bytes):
        return engine.encode(value)
    return None


# drawn_literal takes one call for each level of a value, and a value of a
# recursive shape has up to 100 levels. A split of this function adds a frame
# to each level, and such a value then passes the recursion limit.
def drawn_literal(generator: object, value: object) -> Literal | None:  # noqa: PLR0911
    """Return the typed literal of a value that a generator decoded.

    The literal has the type that the generator decodes.

    Args:
        generator: The generator of the draw.
        value: The value.

    Returns:
        The literal, or None for a value without a typed literal.
    """
    if isinstance(generator, Deferred):
        deferred: Deferred[Any] = generator
        with deferred.picked() as picked:
            return drawn_literal(picked, value)
    inner = _wrapped(generator)
    if inner is not None:
        return drawn_literal(inner, value)
    if isinstance(generator, Mapped):
        mapped: Mapped[Any, Any] = generator
        return _mapped_of(mapped, value)
    if isinstance(generator, (Optional, OptionalShape)):
        optional: Optional[Any] | OptionalShape = generator
        return {"type": "null"} if value is None else drawn_literal(optional.of, value)
    if isinstance(generator, RecordShape):
        return _record_of(generator, value)
    if isinstance(generator, EnumShape):
        return _variant_of(generator, value)
    if isinstance(generator, (List, ListShape)):
        listed: List[Any] | ListShape = generator
        return _elements_of(listed.of, value)
    if isinstance(generator, Dict):
        entries: Dict[Any, Any] = generator
        return _map_of(entries.keys, entries.values, value)
    if isinstance(generator, MapShape):
        return _map_of(generator.key, generator.of, value)
    typed = _typed(generator, value)
    return _generic(value) if typed is None else typed
