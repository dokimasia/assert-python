"""The structural equality of the definition.

The == of Python has other rules. bool is a subclass of int, so 0 == False
is true. int and float compare across their types, so 1 == 1.0 is true. A
dict finds the key 1.0 under the key 1, and it finds a NaN key only by the
identity of the NaN. Under the definition, values of different types are
never equal, and a NaN does not equal another NaN without equate-nans. This
module compares values by those rules.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable, Mapping, Sized
from typing import Any, TypeGuard

from dokimi_assert._matcher.option import Relaxations

__all__ = ["contains_element", "equal", "is_collection", "is_reference"]

#: The types whose values are not references under by-identity. An instance
#: of a subclass of one of them is a reference. An instance of a subclass of
#: tuple is not.
_VALUES = frozenset({type(None), bool, int, float, str, bytes})

#: The types of the keys and elements that a lookup can match by hash. A
#: value of one of them equals only a value of its own type.
_HASHED = (type(None), bool, int, str, bytes)


def is_reference(value: object) -> bool:
    """Report whether value is a reference under by-identity.

    Args:
        value: The value.

    Returns:
        False for None, a bool, an int, a float, a str, bytes and a tuple,
        and True for every other object. An instance of a subclass of int,
        float, str or bytes is a reference.
    """
    return type(value) not in _VALUES and not isinstance(value, tuple)


def is_collection(value: object) -> TypeGuard[Sized]:
    """Report whether value is a collection under equate-empty.

    Args:
        value: The value.

    Returns:
        True for a list, a tuple, a mapping, a set and a frozenset.
    """
    return isinstance(value, (list, tuple, Mapping, set, frozenset))


def equal(got: Any, want: Any, relax: Relaxations) -> bool:
    """Report whether got and want are equal under the rules of the definition.

    - Values of different types are never equal. A bool is not an int, and
      an int is not a float.
    - Floats are compared by value, so -0.0 equals 0.0. A NaN equals another
      NaN only under equate-nans.
    - The items of two lists or two tuples are compared in order. The
      entries of two mappings, two sets or two frozensets are compared in
      any order. A key or an element is compared by these rules and not by
      its hash.
    - The fields of two dataclasses are compared in declaration order.
    - Any other object is compared with its own ==.
    - The comparison of a value that contains itself stops at the repeated
      pair.

    Args:
        got: The value that the code under test produced.
        want: The value that it is supposed to produce.
        relax: The relaxations in force for the comparison.

    Returns:
        True when the two values are equal.
    """
    return _Walk(relax).equal(got, want)


def _hashed_key(value: object, relax: Relaxations) -> tuple[type, object] | None:
    """Return the key under which a lookup matches value by hash, or None.

    A value of a hashed type equals only a value of its own type. A float
    that is not a NaN equals the floats of its value, and -0.0 and 0.0 have
    one hash. Under equate-empty, None can equal an empty collection, and a
    lookup by hash does not find that collection.
    """
    if value is None and relax.equate_empty:
        return None
    if isinstance(value, _HASHED):
        return (type(value), value)
    if isinstance(value, float) and not math.isnan(value):
        return (float, value)
    return None


class _Walk:
    """The walk of one comparison. It keeps the pairs that it visits."""

    def __init__(self, relax: Relaxations) -> None:
        """Return a walk under relax."""
        self._relax: Relaxations = relax
        self._seen: set[tuple[int, int]] = set()

    def equal(self, a: Any, b: Any) -> bool:
        """Report whether a and b are equal."""
        relax = self._relax
        if relax.equate_empty and self._absent_against_empty(a, b):
            return True
        if relax.by_identity and is_reference(a) and is_reference(b):
            return a is b
        if type(a) is not type(b):
            return False
        if a is None:
            return True
        if isinstance(a, float):
            if math.isnan(a) and math.isnan(b):
                return relax.equate_nans
            return bool(a == b)
        if isinstance(a, (bool, int, str, bytes)):
            return bool(a == b)
        pair = (id(a), id(b))
        if pair in self._seen:
            return True
        self._seen.add(pair)
        try:
            return self._deep(a, b)
        finally:
            self._seen.discard(pair)

    def _absent_against_empty(self, a: object, b: object) -> bool:
        """Report whether one side is None and the other an empty collection."""
        if a is None:
            return is_collection(b) and len(b) == 0
        if b is None:
            return is_collection(a) and len(a) == 0
        return False

    def _deep(self, a: Any, b: Any) -> bool:
        """Compare the inside of two values of one type."""
        if isinstance(a, (list, tuple)):
            return len(a) == len(b) and all(
                self.equal(x, y) for x, y in zip(a, b, strict=True)
            )
        if isinstance(a, Mapping):
            return self._mappings(a, b)
        if isinstance(a, (set, frozenset)):
            return self._matched([(x, None) for x in a], [(y, None) for y in b], False)
        if dataclasses.is_dataclass(a) and not isinstance(a, type):
            return all(
                self.equal(getattr(a, f.name), getattr(b, f.name))
                for f in dataclasses.fields(a)
            )
        return bool(a == b)

    def _mappings(self, a: Mapping[Any, Any], b: Mapping[Any, Any]) -> bool:
        """Report whether a one-to-one matching pairs the entries of a and b.

        Each entry of a takes an unmatched entry of b whose key and value
        equal its own.
        """
        if len(a) != len(b):
            return False
        return self._matched(list(a.items()), list(b.items()), True)

    def _matched(
        self,
        left: list[tuple[Any, Any]],
        right: list[tuple[Any, Any]],
        values: bool,
    ) -> bool:
        """Report whether a one-to-one matching pairs the entries of two lists.

        An entry is a key and a value. When values is True, the values are
        compared too. A key of a hashed type matches through a lookup. Every
        other key is compared with each unmatched key of the other side.
        """
        if len(left) != len(right):
            return False
        relax = self._relax
        index: dict[tuple[type, object], list[tuple[Any, Any]]] = {}
        spare: list[tuple[Any, Any]] = []
        for entry in right:
            key = _hashed_key(entry[0], relax)
            if key is None:
                spare.append(entry)
            else:
                index.setdefault(key, []).append(entry)
        for k, v in left:
            key = _hashed_key(k, relax)
            if key is not None:
                found = self._take(index.get(key, []), k, v, values)
            else:
                found = self._take(spare, k, v, values)
            if not found:
                return False
        return True

    def _take(
        self, candidates: list[tuple[Any, Any]], key: Any, value: Any, values: bool
    ) -> bool:
        """Remove the first candidate whose key and value equal key and value."""
        for at, (k, v) in enumerate(candidates):
            if self.equal(key, k) and (not values or self.equal(value, v)):
                del candidates[at]
                return True
        return False


def contains_element(haystack: Iterable[Any], needle: Any, relax: Relaxations) -> bool:
    """Report whether an element of haystack equals needle.

    Args:
        haystack: The elements.
        needle: The value to find.
        relax: The relaxations in force for the comparison.

    Returns:
        True when an element equals needle under the rules of the definition.
    """
    walk = _Walk(relax)
    return any(walk.equal(item, needle) for item in haystack)
