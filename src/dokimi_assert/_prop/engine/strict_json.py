"""The strict JSON of a store file.

A strict text is one JSON text with these properties.

- It does not repeat a name within an object.
- It does not contain NaN or an infinity.
- It nests at most a given number of levels.

The parser reads an integer as an int and any other number as a float, in
the same way as json.loads. An integer is a number without a fraction and
without an exponent.
"""

from __future__ import annotations

import json
import sys
from typing import Any

__all__ = ["JsonError", "parse"]


class JsonError(ValueError):
    """The refusal of a text that is not strict JSON."""


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Return the object of the pairs of a text. The pairs must not repeat a name."""
    found: dict[str, Any] = {}
    for name, value in pairs:
        if name in found:
            raise JsonError(f"prop: an object repeats the name {json.dumps(name)}")
        found[name] = value
    return found


def _constant(name: str) -> Any:
    """Refuse the name of a float that is not a JSON number."""
    raise JsonError(f"prop: {name} is not a JSON number")


def _integer(text: str) -> int:
    """Return the int of an integer of the text, within the digit limit of int."""
    try:
        return int(text)
    except ValueError as error:
        digits = len(text.lstrip("-"))
        limit = sys.get_int_max_str_digits()
        raise JsonError(
            f"prop: an integer of the JSON has {digits} digits, and int allows {limit}"
        ) from error


def _nests_past(value: object, levels: int) -> bool:
    """Report whether value nests more than levels levels of objects and arrays."""
    if not isinstance(value, (dict, list)):
        return False
    if levels == 0:
        return True
    children: Any = value.values() if isinstance(value, dict) else value
    return any(_nests_past(child, levels - 1) for child in children)


def parse(text: str, max_depth: int) -> Any:
    """Return the value of a strict JSON text.

    Args:
        text: The text.
        max_depth: The largest number of levels of objects and arrays. The
            outermost level is the first.

    Returns:
        The value. It consists of dicts, lists, strs, ints, floats, bools and
        None.

    Raises:
        JsonError: The text is not JSON, repeats a name within an object,
            contains NaN or an infinity, has an integer of more digits than
            int allows, or nests past max_depth levels.
    """
    try:
        value = json.loads(
            text,
            object_pairs_hook=_object,
            parse_constant=_constant,
            parse_int=_integer,
        )
    except json.JSONDecodeError as error:
        raise JsonError(f"prop: the JSON at {error.pos}: {error.msg}") from error
    except RecursionError as error:
        raise JsonError(f"prop: the JSON nests past {max_depth} levels") from error
    if _nests_past(value, max_depth):
        raise JsonError(f"prop: the JSON nests past {max_depth} levels")
    return value
