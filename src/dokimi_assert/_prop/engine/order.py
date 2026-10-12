"""The shortlex order of the choice sequences that the shrinker compares.

A sequence is smaller than another when it is shorter, or equally long and
smaller in the first choice where the two differ. Choices of one kind
compare by their sort keys. Choices of different kinds compare by kind, with
an integer before a float and a float before a sequence.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from dokimi_assert._prop.engine.choice import Bounds, Value
from dokimi_assert._prop.engine.float import Key, float_key

__all__ = ["choice_key", "shortlex"]


def choice_key(bounds: Bounds, value: Value) -> Key:
    """Return the key of a choice.

    The key is the rank of the kind of the choice followed by its sort key.

    Args:
        bounds: The bounds of the request of the choice.
        value: The value of the choice, of the kind of the bounds.

    Returns:
        The key.
    """
    if bounds.kind == "integer":
        return (0, *bounds.key(cast("int", value)))
    if bounds.kind == "float":
        return (1, *float_key(cast("float", value)))
    elements = cast("tuple[int, ...]", value)
    return (2, len(elements), *elements)


def shortlex(keys: Sequence[Key]) -> tuple[int, tuple[Key, ...]]:
    """Return the shortlex key of a choice sequence.

    Of two keys, the one of the shorter sequence is smaller. Of two
    sequences of one length, the one with the smaller key where they first
    differ is smaller.

    Args:
        keys: The keys of the choices of the sequence.

    Returns:
        The key. Python compares two such keys in shortlex order.
    """
    return (len(keys), tuple(keys))
