"""The four edge cases. Each case has every value at one boundary.

A choice that decides structure takes the edge of its request. A collection
then gets one element, a one-of its first alternative and an optional its
value. A value choice takes the boundary of its case.

- min takes lo, and the elements of a sequence are 0.
- max takes hi, and the elements of a sequence are k - 1.
- above takes one above the target. A float takes the next float of the
  width, and the elements of a sequence are 1.
- below takes one below the target, and a float takes the next float below
  it.

A value that the bounds do not admit takes the target instead. A sequence
has one element, or min_size elements when min_size is more. It does not
have an element when its max_size is 0.
"""

from __future__ import annotations

from typing import Literal

from dokimi_assert._prop.engine.case import Provider, Request
from dokimi_assert._prop.engine.choice import (
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
    Value,
)
from dokimi_assert._prop.engine.float import next_down, next_up

__all__ = ["BOUNDARIES", "Boundary", "Edge"]

#: The boundary that every value choice of one edge case takes.
Boundary = Literal["min", "max", "above", "below"]

#: The edge cases in the order that a run tries them.
BOUNDARIES: tuple[Boundary, ...] = ("min", "max", "above", "below")


def _integer_at(bounds: IntegerBounds, boundary: Boundary) -> int:
    """Return the value of an integer choice at the boundary."""
    target = bounds.target
    values = {
        "min": bounds.lo,
        "max": bounds.hi,
        "above": target + 1,
        "below": target - 1,
    }
    value = values[boundary]
    return value if bounds.admits(value) else target


def _float_at(bounds: FloatBounds, boundary: Boundary) -> float:
    """Return the value of a float choice at the boundary."""
    target = bounds.target
    values = {
        "min": bounds.lo,
        "max": bounds.hi,
        "above": next_up(target, bounds.width),
        "below": next_down(target, bounds.width),
    }
    value = values[boundary]
    return value if bounds.admits(value) else target


def _sequence_at(bounds: SequenceBounds, boundary: Boundary) -> tuple[int, ...]:
    """Return the value of a sequence choice at the boundary."""
    length = max(bounds.min_size, 1)
    if bounds.max_size is not None:
        length = min(length, bounds.max_size)
    elements = {"min": 0, "max": bounds.k - 1, "above": 1, "below": -1}
    element = elements[boundary]
    return (element if 0 <= element < bounds.k else 0,) * length


class Edge(Provider):
    """A provider that gives every choice its value at one boundary."""

    def __init__(self, boundary: Boundary) -> None:
        """Return the provider that gives each value choice its value at a boundary.

        Args:
            boundary: The boundary.
        """
        self._boundary: Boundary = boundary

    def value(self, request: Request, index: int) -> Value:
        """Return the edge of the request, or its value at the boundary.

        Args:
            request: The request.
            index: The number of choices in the record of the case.

        Returns:
            The value.
        """
        del index
        bounds = request.bounds
        if request.edge is not None:
            return request.edge if bounds.admits(request.edge) else bounds.target
        if isinstance(bounds, IntegerBounds):
            return _integer_at(bounds, self._boundary)
        if isinstance(bounds, FloatBounds):
            return _float_at(bounds, self._boundary)
        return _sequence_at(bounds, self._boundary)
