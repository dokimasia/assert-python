# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The default alphabet of the string generator in order from the simplest.

A string is a sequence of indices into an alphabet, so the order of the
alphabet decides what a string shrinks towards. The default alphabet puts
the 95 printable ASCII characters first: the digits, the lowercase and the
uppercase letters, then space and the punctuation. A string shrinks towards
"0", then "00". The other code points of the Basic Multilingual Plane follow
in ascending order without the surrogates. The code points above the plane
come last.
"""

from __future__ import annotations

__all__ = ["SIZE", "Interval", "character", "index_of", "indices", "merge"]

#: An inclusive range of indices or code points.
Interval = tuple[int, int]

#: The first 95 characters in their order.
_PRINTABLE = (
    "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    " !\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
)

#: The inclusive code point ranges that follow the printable characters in
#: ascending order. They are the controls below space, the code points from
#: DEL to the surrogates, the code points after the surrogates in the plane,
#: and the supplementary planes.
_REST: tuple[Interval, ...] = (
    (0x00, 0x1F),
    (0x7F, 0xD7FF),
    (0xE000, 0xFFFF),
    (0x10000, 0x10FFFF),
)

#: The number of characters of the default alphabet. The alphabet has every
#: Unicode scalar value.
SIZE = len(_PRINTABLE) + sum(hi - lo + 1 for lo, hi in _REST)

#: The index of each printable character.
_PRINTABLE_INDEX = {char: index for index, char in enumerate(_PRINTABLE)}

#: The first printable code point is space, and the last is tilde.
_FIRST_PRINTABLE = 0x20
_LAST_PRINTABLE = 0x7E


def character(index: int) -> str:
    """Return the character at an index of the default alphabet.

    Args:
        index: An index in [0, SIZE).

    Returns:
        The character.

    Raises:
        ValueError: The index is outside [0, SIZE).
    """
    if not 0 <= index < SIZE:
        msg = f"prop: index {index} is outside the default alphabet"
        raise ValueError(msg)
    if index < len(_PRINTABLE):
        return _PRINTABLE[index]
    offset = index - len(_PRINTABLE)
    at = 0
    lo, hi = _REST[at]
    while offset > hi - lo:
        offset -= hi - lo + 1
        at += 1
        lo, hi = _REST[at]
    return chr(lo + offset)


def index_of(char: str) -> int | None:
    """Return the index of a character in the default alphabet.

    Args:
        char: One code point.

    Returns:
        The index, or None for a lone surrogate. A lone surrogate is not a
        scalar value.
    """
    printable = _PRINTABLE_INDEX.get(char)
    if printable is not None:
        return printable
    point = ord(char)
    offset = len(_PRINTABLE)
    for lo, hi in _REST:
        if lo <= point <= hi:
            return offset + point - lo
        offset += hi - lo + 1
    return None


def indices(lo: int, hi: int) -> list[Interval]:
    """Return the indices of the code points in [lo, hi] as inclusive intervals.

    The intervals are sorted, and they neither overlap nor touch. The
    surrogates in the range do not have an index, so the intervals leave
    them out.

    Args:
        lo: The first code point.
        hi: The last code point.

    Returns:
        The intervals.
    """
    found: list[Interval] = []
    for point in range(max(lo, _FIRST_PRINTABLE), min(hi, _LAST_PRINTABLE) + 1):
        position = _PRINTABLE_INDEX[chr(point)]
        found.append((position, position))
    offset = len(_PRINTABLE)
    for first, last in _REST:
        start = max(lo, first)
        end = min(hi, last)
        if start <= end:
            found.append((offset + start - first, offset + end - first))
        offset += last - first + 1
    return merge(found)


def merge(intervals: list[Interval]) -> list[Interval]:
    """Return the sorted union of inclusive intervals.

    The union joins intervals that overlap or touch.

    Args:
        intervals: The intervals.

    Returns:
        The union.
    """
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
