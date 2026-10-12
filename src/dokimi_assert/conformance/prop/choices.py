"""The form of a choice and of a seed in the property vectors.

The definition writes an integer choice as a JSON integer, or as a decimal
string above 2^53 - 1 in magnitude. It writes a float choice as an object
with the member float, whose value is a number or the name NaN, Inf or -Inf.
It writes a sequence choice as an object with the member sequence, whose
value is the list of the elements. A seed is a decimal string.
"""

from __future__ import annotations

import json
import re
from typing import Any, cast

from dokimi_assert._prop.engine import literal
from dokimi_assert._prop.engine.choice import Choice

__all__ = ["choice_literal", "parse_choice", "parse_choices", "seed_of"]

#: The text of a seed.
_DECIMAL = re.compile(r"[0-9]+")


def choice_literal(choice: Choice) -> object:
    """Return the form of a choice in a vector.

    Args:
        choice: The choice.

    Returns:
        The JSON value.
    """
    if choice.kind == "integer":
        return literal.plain(choice.value)
    if choice.kind == "float":
        return {"float": literal.plain(choice.value)}
    return {"sequence": list(cast("tuple[int, ...]", choice.value))}


def parse_choice(written: object) -> Choice:
    """Return the choice of its form in a vector.

    Args:
        written: The JSON value.

    Returns:
        The choice.

    Raises:
        ValueError: The value is not the form of a choice.
    """
    if not isinstance(written, dict):
        return Choice("integer", literal.integer(written))
    form = cast("dict[str, Any]", written)
    if list(form) == ["float"]:
        return Choice("float", literal.number(form["float"]))
    elements = form.get("sequence")
    if list(form) == ["sequence"] and isinstance(elements, list):
        items = cast("list[object]", elements)
        return Choice("sequence", tuple(literal.integer(item) for item in items))
    raise ValueError(f"prop: {json.dumps(written)} is not a choice")


def parse_choices(written: object) -> list[Choice]:
    """Return the choices of a list of their forms in a vector.

    Args:
        written: The JSON value.

    Returns:
        The choices in order.

    Raises:
        ValueError: The value is not a list, or an element is not the form of
            a choice.
    """
    if not isinstance(written, list):
        raise ValueError(f"prop: {json.dumps(written)} is not a list of choices")
    return [parse_choice(item) for item in cast("list[object]", written)]


def seed_of(seed: object) -> int:
    """Return the seed of its text in a vector.

    Args:
        seed: The JSON value.

    Returns:
        The seed.

    Raises:
        ValueError: The value is not a decimal string.
    """
    if not isinstance(seed, str) or not _DECIMAL.fullmatch(seed):
        raise ValueError(f"prop: the seed {json.dumps(seed)} is not a decimal string")
    return int(seed)
