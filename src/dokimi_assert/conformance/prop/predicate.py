# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The predicates that the bodies and the filters of the property vectors take.

A predicate is a JSON object with a kind and the parameters of the kind. The
member not with the value true negates it. These are the kinds:

- always and never.
- equals value: a value equal to the typed literal value.
- at-least n: a number of at least n.
- divisible-by n: an integer that n divides.
- sum-above n: a list whose numbers have a sum above n.
- length-at-least n: a list, a string, bytes or a dict of at least n
  elements.
- contains value: a list with an element equal to the typed literal value,
  or a string or bytes that contains the value.
- not-sorted: a list that is not in ascending order.
- has-duplicate: a list with two equal elements.
- indexed-above n: a list whose last element is an index from 0 into the
  elements before it, where the element at the index is a number above n.

Two values are equal when they have the same canonical text in the engine.
The values are the values that the engine decodes.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable, Mapping
from typing import Any, cast

from dokimi_assert._prop.engine import literal
from dokimi_assert._prop.engine.value import Pairs, canonical

__all__ = ["Predicate", "predicate"]

#: A condition on a decoded value.
Predicate = Callable[[Any], bool]

#: A predicate as a JSON object.
_Spec = Mapping[str, Any]


def _number_of(value: object) -> int | float:
    """Return the number parameter of a predicate. A float stays a float."""
    if isinstance(value, float):
        return value
    return literal.integer(value)


def _is_number(value: object) -> bool:
    """Report whether a decoded value is an int or a float."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _always(_: _Spec) -> Predicate:
    """Return the predicate that every value meets."""
    return lambda _value: True


def _never(_: _Spec) -> Predicate:
    """Return the predicate that is false for every value."""
    return lambda _value: False


def _equals(spec: _Spec) -> Predicate:
    """Return the predicate of a value equal to a typed literal."""
    key = canonical(literal.decode(spec.get("value")))
    return lambda value: canonical(value) == key


def _at_least(spec: _Spec) -> Predicate:
    """Return the predicate of a number of at least n."""
    n = _number_of(spec.get("n"))
    return lambda value: _is_number(value) and value >= n


def _divisible_by(spec: _Spec) -> Predicate:
    """Return the predicate of an integer that n divides."""
    n = literal.integer(spec.get("n"))
    return lambda value: type(value) is int and value % n == 0


def _sum_above(spec: _Spec) -> Predicate:
    """Return the predicate of a list whose numbers have a sum above n."""
    n = _number_of(spec.get("n"))

    def test(value: Any) -> bool:
        if not isinstance(value, list):
            return False
        return bool(sum(item for item in value if _is_number(item)) > n)

    return test


def _length_at_least(spec: _Spec) -> Predicate:
    """Return the predicate of a collection of at least n elements.

    A collection is a list, a string, bytes or a dict.
    """
    n = literal.integer(spec.get("n"))

    def test(value: Any) -> bool:
        if isinstance(value, Pairs):
            return len(value.items) >= n
        return isinstance(value, (list, str, bytes)) and len(value) >= n

    return test


def _contains(spec: _Spec) -> Predicate:
    """Return the predicate of a list, a string or bytes that contains a value."""
    wanted = literal.decode(spec.get("value"))
    key = canonical(wanted)

    def test(value: Any) -> bool:
        if isinstance(value, list):
            return any(canonical(item) == key for item in value)
        if isinstance(value, str) and isinstance(wanted, str):
            return wanted in value
        if isinstance(value, bytes) and isinstance(wanted, bytes):
            return wanted in value
        return False

    return test


def _not_sorted(_: _Spec) -> Predicate:
    """Return the predicate of a list whose elements are not in ascending order.

    Numbers compare by value and strings by code point.
    """

    def test(value: Any) -> bool:
        if not isinstance(value, list):
            return False
        return any(later < earlier for earlier, later in itertools.pairwise(value))

    return test


def _has_duplicate(_: _Spec) -> Predicate:
    """Return the predicate of a list with two equal elements."""

    def test(value: Any) -> bool:
        if not isinstance(value, list):
            return False
        return len({canonical(item) for item in value}) < len(value)

    return test


def _indexed_above(spec: _Spec) -> Predicate:
    """Return the predicate of a list whose last element indexes a number above n."""
    n = _number_of(spec.get("n"))

    def test(value: Any) -> bool:
        if not isinstance(value, list) or not value:
            return False
        *earlier, index = value
        if type(index) is not int or not 0 <= index < len(earlier):
            return False
        element = earlier[index]
        return _is_number(element) and element > n

    return test


#: The factory of the predicate of each kind, by the kind.
_KINDS: dict[str, Callable[[_Spec], Predicate]] = {
    "always": _always,
    "never": _never,
    "equals": _equals,
    "at-least": _at_least,
    "divisible-by": _divisible_by,
    "sum-above": _sum_above,
    "length-at-least": _length_at_least,
    "contains": _contains,
    "not-sorted": _not_sorted,
    "has-duplicate": _has_duplicate,
    "indexed-above": _indexed_above,
}


def predicate(spec: object) -> Predicate:
    """Return the predicate that a JSON object states.

    Args:
        spec: The JSON object of the predicate.

    Returns:
        The predicate.

    Raises:
        ValueError: The value is not an object, its kind does not exist, or a
            parameter is not a value of the kind.
    """
    if not isinstance(spec, dict):
        msg = f"prop: {json.dumps(spec)} is not a predicate"
        raise ValueError(msg)
    stated = cast("dict[str, Any]", spec)
    kind = stated.get("kind")
    factory = _KINDS.get(kind) if isinstance(kind, str) else None
    if factory is None:
        msg = f"prop: {json.dumps(kind)} is not a kind of predicate"
        raise ValueError(msg)
    test = factory(stated)
    if stated.get("not") is True:
        return lambda value: not test(value)
    return test
