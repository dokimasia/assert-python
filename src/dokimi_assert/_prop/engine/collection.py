# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The decoding of a collection one element at a time.

Every collection decodes the same way. A list, a dict and a repetition in a
pattern are collections. Before each element, the collection decodes a
continue flag. The flag is an integer choice that decides structure, and the
choices of the element follow it. The bounds of the flag force it while the
count is below the minimum or at the maximum, so every replay of recorded
choices yields a length inside the sizes.

Each element is a span that starts at its flag. The span label is element,
or entry in a dict. A deletion of that span deletes the element whole.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from dokimi_assert._prop.engine import draw
from dokimi_assert._prop.engine.case import Case, Rejected, Request

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["ELEMENT", "ENTRY", "Sizes", "collect", "more"]

#: The span labels of one element of a collection and one entry of a dict.
ELEMENT = "element"
ENTRY = "entry"

#: A collection that discards this many duplicates in a row stops. A
#: collection still below its minimum size then rejects the case.
_MAX_DISCARDS = 10

_T = TypeVar("_T")


class Sizes:
    """The bounds of the length of a collection, both inclusive.

    Attributes:
        min_size: The smallest number of elements.
        max_size: The largest number of elements, or None without a bound.
    """

    def __init__(self, min_size: int = 0, max_size: int | None = None) -> None:
        """Return the sizes from min_size to max_size.

        Args:
            min_size: The smallest number of elements.
            max_size: The largest number of elements, or None without a bound.

        Raises:
            ValueError: min_size is negative, or max_size is below it.
        """
        if min_size < 0 or (max_size is not None and max_size < min_size):
            msg = f"prop: sizes [{min_size}, {max_size}] are empty"
            raise ValueError(msg)
        self.min_size: int = min_size
        self.max_size: int | None = max_size

    @property
    def average(self) -> int:
        """The average length of the collection in the random phase.

        Returns:
            The average length.
        """
        return draw.average_length(self.min_size, self.max_size)


def more(
    c: Case,
    count: int,
    sizes: Sizes,
    stopped: bool = False,
    average: int | None = None,
) -> bool:
    """Return the decision of a case to grow a collection of count elements.

    The decision is an integer choice that decides structure. draw.flag_bounds
    returns its bounds. A stopped collection decides in the same way as one
    at its maximum. The bounds then admit only 0. The edge phase gives a
    collection one element. Its edge is 1 at count 0 and 0 after.

    Args:
        c: The case.
        count: The number of elements so far.
        sizes: The sizes of the collection.
        stopped: When True, the collection does not take another element.
        average: The average length, in place of the average of the sizes.

    Returns:
        True when the collection grows.
    """
    lo = sizes.min_size
    hi = count if stopped else sizes.max_size
    mean = sizes.average if average is None else average
    request = Request(
        draw.flag_bounds(count, lo, hi),
        lambda source: draw.flag(source, count, lo, hi, mean),
        1 if count == 0 else 0,
    )
    return c.choose(request) == 1


def collect(
    c: Case,
    sizes: Sizes,
    label: str,
    decode: Callable[[], tuple[_T, str | None]],
    stop: Callable[[], bool] | None = None,
) -> list[_T]:
    """Decode a collection. A continue flag comes before each element.

    decode returns an element and its key. The key is None when the
    collection allows duplicates. An element whose key repeats an earlier
    key is discarded, and the next flag is decided for the same count. After
    ten discards in a row, the collection stops.

    Args:
        c: The case.
        sizes: The sizes of the collection.
        label: The span label of each element.
        decode: Decodes one element, and returns it with its key.
        stop: Called before each flag that the minimum does not force. When
            it returns True, the flag admits only 0.

    Returns:
        The elements.

    Raises:
        Rejected: The collection stopped below its minimum size.
    """
    items: list[_T] = []
    seen: set[str] = set()
    discards = 0
    while True:
        start = len(c.choices)
        stopped = stop is not None and len(items) >= sizes.min_size and stop()
        if not more(c, len(items), sizes, stopped):
            return items
        with c.span(label, start):
            item, key = decode()
        if key is not None and key in seen:
            discards += 1
            if discards < _MAX_DISCARDS:
                continue
            if len(items) < sizes.min_size:
                raise Rejected
            return items
        discards = 0
        if key is not None:
            seen.add(key)
        items.append(item)
