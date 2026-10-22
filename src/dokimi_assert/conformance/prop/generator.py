# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The generators of the property vectors.

The definition writes a generator as a JSON object whose member gen has the
id of the generator. build returns the generator of the engine for the
object. Its values are the values that the engine decodes, so a dict
decodes to Pairs. A map takes the function of a subject kind, and a filter
takes a predicate. self is one position of the recursive value whose
extension contains it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from fractions import Fraction
from typing import Any, cast

from dokimi_assert import prop
from dokimi_assert._prop.engine import literal
from dokimi_assert._prop.engine.collection import Sizes
from dokimi_assert._prop.engine.generator import Dict, Generator
from dokimi_assert.conformance.prop.function import FUNCTIONS
from dokimi_assert.conformance.prop.predicate import predicate

__all__ = ["build"]

#: A generator as a JSON object.
_Spec = Mapping[str, Any]

#: A function that builds a generator from its JSON object and from the
#: position of each self in it.
_Builder = Callable[[_Spec, Generator[Any] | None], Generator[Any]]

#: The values that one recursive value draws from its base when the object
#: does not have max_leaves.
_MAX_LEAVES = 100


def _int_of(spec: _Spec, key: str) -> int:
    """Return the integer parameter key.

    Raises:
        ValueError: The object does not have the parameter, or the parameter
            is not an integer.
    """
    if key not in spec:
        msg = f"prop: {json.dumps(spec.get('gen'))} needs {key}"
        raise ValueError(msg)
    return literal.integer(spec[key])


def _bool_of(spec: _Spec, key: str) -> bool:
    """Return the bool parameter key. It is False when the object does not have it.

    Raises:
        ValueError: The parameter is not a bool.
    """
    value = spec.get(key)
    if value is None:
        return False
    if not isinstance(value, bool):
        msg = f"prop: {key} is {json.dumps(value)}, not a bool"
        raise ValueError(msg)
    return value


def _sizes_of(spec: _Spec) -> tuple[int, int | None]:
    """Return min_size and max_size. min_size is 0 by default, and max_size None."""
    low = _int_of(spec, "min_size") if "min_size" in spec else 0
    high = None if spec.get("max_size") is None else _int_of(spec, "max_size")
    return low, high


#: The parts of p: a numerator and a denominator.
_FRACTION_PARTS = 2


def _probability_of(spec: _Spec) -> Fraction:
    """Return p, given as a numerator and a denominator, or 1/2 without p.

    Raises:
        ValueError: p is not two integers with 0 <= numerator <= denominator.
    """
    value = spec.get("p")
    if value is None:
        return Fraction(1, 2)
    refusal = ValueError(
        f"prop: p is {json.dumps(value)}, not [numerator, denominator]"
    )
    if (
        not isinstance(value, list)
        or len(cast("list[object]", value)) != _FRACTION_PARTS
    ):
        raise refusal
    num, den = cast("list[object]", value)
    if type(num) is not int or type(den) is not int or not 0 <= num <= den or den < 1:
        raise refusal
    return Fraction(num, den)


def _values_of(spec: _Spec) -> list[object]:
    """Return the decoded typed literals of the parameter values.

    Raises:
        ValueError: values is not a list of typed literals.
    """
    values = spec.get("values")
    if not isinstance(values, list):
        msg = f"prop: values is {json.dumps(values)}, not a list"
        raise ValueError(msg)
    return [literal.decode(value) for value in cast("list[object]", values)]


def _string(spec: _Spec, _: Generator[Any] | None) -> Generator[Any]:
    """Return the generator of strings over the default alphabet or over alphabet.

    Raises:
        ValueError: alphabet is not a string, or the generator refuses it.
    """
    low, high = _sizes_of(spec)
    alphabet = spec.get("alphabet")
    if alphabet is not None and not isinstance(alphabet, str):
        msg = f"prop: alphabet is {json.dumps(alphabet)}, not a string"
        raise ValueError(msg)
    return prop.string(alphabet=alphabet, min_size=low, max_size=high)


def _string_matching(spec: _Spec, _: Generator[Any] | None) -> Generator[Any]:
    """Return the generator of the strings that the parameter pattern matches.

    Raises:
        ValueError: pattern is not a string, or it is outside the portable
            subset.
    """
    pattern = spec.get("pattern")
    if not isinstance(pattern, str):
        msg = f"prop: pattern is {json.dumps(pattern)}, not a string"
        raise ValueError(msg)
    return prop.string_matching(pattern)


def _float(spec: _Spec, _: Generator[Any] | None) -> Generator[Any]:
    """Return the generator of the floats from min to max of a width."""
    width = _int_of(spec, "width") if "width" in spec else 64
    return prop.float(
        literal.number(spec.get("min")),
        literal.number(spec.get("max")),
        allow_nan=_bool_of(spec, "allow_nan"),
        width=cast("Any", width),
    )


def _bytes(spec: _Spec, _: Generator[Any] | None) -> Generator[Any]:
    """Return the generator of byte strings of the sizes of the object."""
    low, high = _sizes_of(spec)
    return prop.bytes(min_size=low, max_size=high)


def _recursive(spec: _Spec, _: Generator[Any] | None) -> Generator[Any]:
    """Return the generator of recursive values.

    Each self in the extension refers to the position of the extension. A
    self in the base is outside every extension.
    """
    leaves = _int_of(spec, "max_leaves") if "max_leaves" in spec else _MAX_LEAVES
    extension = spec.get("extend")
    return prop.recursive(
        build(spec.get("base")),
        lambda position: build(extension, position),
        max_leaves=leaves,
    )


def _one_of(spec: _Spec, scope: Generator[Any] | None) -> Generator[Any]:
    """Return the generator of a value of one of the generators of the list of.

    Raises:
        ValueError: of is not a list of generators.
    """
    of = spec.get("of")
    if not isinstance(of, list) or not of:
        msg = f"prop: one-of needs a list of generators, not {json.dumps(of)}"
        raise ValueError(msg)
    return prop.one_of(*(build(item, scope) for item in cast("list[object]", of)))


def _list(spec: _Spec, scope: Generator[Any] | None) -> Generator[Any]:
    """Return the generator of lists of the values of of."""
    low, high = _sizes_of(spec)
    of = build(spec.get("of"), scope)
    return prop.list(of, min_size=low, max_size=high, unique=_bool_of(spec, "unique"))


def _dict(spec: _Spec, scope: Generator[Any] | None) -> Generator[Any]:
    """Return the generator of the Pairs of keys and values of the object."""
    low, high = _sizes_of(spec)
    keys = build(spec.get("keys"), scope)
    values = build(spec.get("values"), scope)
    return Dict(keys, values, Sizes(low, high))


def _map(spec: _Spec, scope: Generator[Any] | None) -> Generator[Any]:
    """Return the generator of the function of a subject kind of the values of of.

    Raises:
        ValueError: The subject kind does not have a function.
    """
    subject = spec.get("subject")
    function = FUNCTIONS.get(subject) if isinstance(subject, str) else None
    if function is None:
        msg = f"prop: the subject {json.dumps(subject)} does not have a function"
        raise ValueError(msg)
    return build(spec.get("of"), scope).map(function)


#: The builder of each generator, by its id.
_BUILDERS: dict[str, _Builder] = {
    "integer": lambda s, _: prop.integer(_int_of(s, "min"), _int_of(s, "max")),
    "duration": lambda s, _: prop.duration(_int_of(s, "min"), _int_of(s, "max")),
    "float": _float,
    "boolean": lambda s, _: prop.boolean(_probability_of(s)),
    "just": lambda s, _: prop.just(literal.decode(s.get("value"))),
    "sampled-from": lambda s, _: prop.sampled_from(*_values_of(s)),
    "string": _string,
    "string-matching": _string_matching,
    "bytes": _bytes,
    "permutation": lambda s, _: prop.permutation(*_values_of(s)),
    "recursive": _recursive,
    "one-of": _one_of,
    "optional": lambda s, scope: prop.optional(build(s.get("of"), scope)),
    "list": _list,
    "dict": _dict,
    "filter": lambda s, scope: build(s.get("of"), scope).filter(
        predicate(s.get("keep"))
    ),
    "map": _map,
}


def build(spec: object, scope: Generator[Any] | None = None) -> Generator[Any]:
    """Return the generator of a JSON object.

    Args:
        spec: The JSON object of the generator.
        scope: The position of the recursive value whose extension contains
            spec, or None outside every extension. A self inside spec is
            that position.

    Returns:
        The generator.

    Raises:
        ValueError: The value is not an object, its id does not exist, it
            does not have a parameter, a parameter is not a value of the
            generator, or a self is outside every extension.
    """
    if not isinstance(spec, dict):
        msg = f"prop: {json.dumps(spec)} is not a generator"
        raise ValueError(msg)
    stated = cast("dict[str, Any]", spec)
    gen = stated.get("gen")
    if gen == "self":
        if scope is None:
            msg = "prop: self is outside the extension of a recursive generator"
            raise ValueError(msg)
        return scope
    builder = _BUILDERS.get(gen) if isinstance(gen, str) else None
    if builder is None:
        msg = f"prop: {json.dumps(gen)} is not a generator"
        raise ValueError(msg)
    return builder(stated, scope)
