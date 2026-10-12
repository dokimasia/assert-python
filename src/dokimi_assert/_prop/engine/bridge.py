"""The decoding of the bytes of a fuzzer into the choices of one case.

Bridging is a provider that reads each value from the bytes in request
order.

- For an integer in [lo, hi], it reads ceil(bit_length(hi - lo) / 8) bytes
  as a little-endian unsigned u. The integer is lo + u mod (hi - lo + 1). It
  does not read a byte for bounds with one value.
- For a float, it reads 8 bytes, or 4 for width 32, as the little-endian
  bits of a float of the width. A value that the bounds do not admit takes
  the target. It does not read a byte for bounds that admit one value.
- For a sequence, it reads the length as an integer in [min_size, max_size],
  or in [min_size, min_size + 65,535] when max_size is None. It then reads
  each element as an integer in [0, k - 1]. A byte string takes one byte of
  the fuzzer per byte after its length.
- A value that needs more bytes than remain takes its target. The bytes
  that remain are spent, so every later value takes its target too. An
  element that is cut short ends its sequence, and zeros extend the
  sequence to min_size.

Every byte string decodes to a valid case, so a failure that a fuzzer finds
is a choice sequence that the shrinker can minimise and the store can keep.
"""

from __future__ import annotations

from dokimi_assert._prop.engine.case import Provider, Request
from dokimi_assert._prop.engine.choice import (
    Choice,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
    Value,
)
from dokimi_assert._prop.engine.float import from_bits, from_bits32

__all__ = ["Bridging"]

#: The largest length beyond its minimum that a sequence without a maximum
#: can take. Bridging reads the length from two bytes.
_UNBOUNDED_LENGTHS = 0xFFFF


def _width(span: int) -> int:
    """Return the number of bytes that cover an integer range of span + 1 values."""
    return -(-span.bit_length() // 8)


class Bridging(Provider):
    """A provider that decodes every value from the bytes of a fuzzer."""

    def __init__(self, data: bytes) -> None:
        """Return the provider that decodes from the first byte of data.

        Args:
            data: The bytes of the fuzzer.
        """
        self._data: bytes = data
        self._at: int = 0

    def value(self, request: Request, index: int) -> Value:
        """Return the value of the next bytes under the bounds of a request.

        Args:
            request: The request.
            index: The number of choices in the record of the case.

        Returns:
            The value.
        """
        del index
        bounds = request.bounds
        if isinstance(bounds, IntegerBounds):
            return self._integer(bounds)
        if isinstance(bounds, FloatBounds):
            return self._float(bounds)
        return self._sequence(bounds)

    def _take(self, count: int) -> int | None:
        """Return the next count bytes as a little-endian unsigned integer.

        The result is None when fewer than count bytes remain, and the bytes
        that remain are then spent.
        """
        if count > len(self._data) - self._at:
            self._at = len(self._data)
            return None
        value = int.from_bytes(self._data[self._at : self._at + count], "little")
        self._at += count
        return value

    def _below(self, span: int) -> int | None:
        """Return an integer in [0, span] from the bytes that cover it, or None."""
        u = self._take(_width(span))
        return None if u is None else u % (span + 1)

    def _integer(self, bounds: IntegerBounds) -> int:
        """Return lo plus the offset that the bytes encode, or the target."""
        offset = self._below(bounds.hi - bounds.lo)
        return bounds.target if offset is None else bounds.lo + offset

    def _float(self, bounds: FloatBounds) -> float:
        """Return the float of the bits of the bytes.

        A float outside the bounds becomes the target. Both zeros lie inside
        any range that contains either, so only a nonzero range of one value
        without NaN does not read a byte.
        """
        if bounds.lo == bounds.hi and bounds.lo != 0 and not bounds.allow_nan:
            return bounds.target
        bits = self._take(bounds.width // 8)
        if bits is None:
            return bounds.target
        value = from_bits(bits) if bounds.width == 64 else from_bits32(bits)
        return bounds.coerce(Choice("float", value))

    def _sequence(self, bounds: SequenceBounds) -> tuple[int, ...]:
        """Return a sequence of the length that the bytes encode.

        The elements follow the length, as many as the bytes contain.
        """
        if bounds.max_size is None:
            spread = _UNBOUNDED_LENGTHS
        else:
            spread = bounds.max_size - bounds.min_size
        extra = self._below(spread)
        if extra is None:
            return bounds.target
        elements: list[int] = []
        for _ in range(bounds.min_size + extra):
            element = self._below(bounds.k - 1)
            if element is None:
                break
            elements.append(element)
        elements.extend([0] * (bounds.min_size - len(elements)))
        return tuple(elements)
