# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The replay token that encodes the choice values of one case as a printable string.

A token is prop1: followed by the unpadded base64url encoding of the choice
values in order. Each value is a tag byte and then its payload.

- Tag 0 is a non-negative integer in unsigned LEB128.
- Tag 1 is a negative integer. Its magnitude is in unsigned LEB128.
- Tag 2 is a float. Its binary64 bits are in eight little-endian bytes, and
  every NaN has the canonical bits.
- Tag 3 is a sequence. Its length and then each element are in unsigned
  LEB128.

The token does not record bounds, because the generators request them again
when the case replays. A choice sequence has exactly one token. The name of a
store entry derives from the token, so the name is the same in every
language.
"""

from __future__ import annotations

import base64
import json
import math
import re
from typing import TYPE_CHECKING

from dokimi_assert._prop.engine.choice import Choice
from dokimi_assert._prop.engine.float import NAN_BITS, bits_of, from_bits

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["PREFIX", "decode", "encode"]

#: The text that every token of this version starts with.
PREFIX = "prop1:"

#: The tag byte before each choice value.
_TAG_NON_NEGATIVE = 0
_TAG_NEGATIVE = 1
_TAG_FLOAT = 2
_TAG_SEQUENCE = 3

#: The number of bytes of the payload of a float.
_FLOAT_BYTES = 8

#: Every number that a token encodes is below 2^64, and the magnitude of a
#: negative integer is at most 2^63.
_NUMBER_LIMIT = 1 << 64
_NEGATIVE_LIMIT = 1 << 63

#: The largest element of a sequence of this engine. A larger element replays
#: as this one.
_ELEMENT_LIMIT = 2**32 - 1

#: The characters of base64url.
_BASE64URL = re.compile(r"[A-Za-z0-9_-]*")

#: The bits of a byte of LEB128 that carry the number, and the bit that marks
#: a byte that another byte follows.
_PAYLOAD = 0x7F
_CONTINUED = 0x80


def _append_number(data: bytearray, number: int) -> None:
    """Append a number of 0 or more in unsigned LEB128."""
    rest = number
    while rest > _PAYLOAD:
        data.append((rest & _PAYLOAD) | _CONTINUED)
        rest >>= 7
    data.append(rest)


def _append_choice(data: bytearray, choice: Choice) -> None:
    """Append the tag and the payload of one choice."""
    value = choice.value
    if isinstance(value, tuple):
        data.append(_TAG_SEQUENCE)
        _append_number(data, len(value))
        for element in value:
            _append_number(data, element)
    elif isinstance(value, float):
        data.append(_TAG_FLOAT)
        bits = NAN_BITS if math.isnan(value) else bits_of(value)
        data.extend(bits.to_bytes(_FLOAT_BYTES, "little"))
    else:
        data.append(_TAG_NEGATIVE if value < 0 else _TAG_NON_NEGATIVE)
        _append_number(data, abs(value))


def encode(choices: Sequence[Choice]) -> str:
    """Return the token of a choice sequence.

    Args:
        choices: The choices.

    Returns:
        The token.
    """
    data = bytearray()
    for choice in choices:
        _append_choice(data, choice)
    return PREFIX + base64.urlsafe_b64encode(bytes(data)).rstrip(b"=").decode("ascii")


class _Reader:
    """The bytes of a token, read once from the start."""

    def __init__(self, data: bytes) -> None:
        self._data: bytes = data
        self._at: int = 0

    def done(self) -> bool:
        """Report whether every byte has been read."""
        return self._at == len(self._data)

    def _byte(self) -> int:
        """Return the next byte."""
        if self._at == len(self._data):
            msg = "prop: a token ends inside a choice"
            raise ValueError(msg)
        byte = self._data[self._at]
        self._at += 1
        return byte

    def number(self) -> int:
        """Return the next unsigned LEB128 number.

        The number must not have a superfluous byte.
        """
        number = 0
        shift = 0
        while True:
            byte = self._byte()
            number |= (byte & _PAYLOAD) << shift
            if number >= _NUMBER_LIMIT:
                msg = "prop: a token has a number of 2^64 or more"
                raise ValueError(msg)
            if byte < _CONTINUED:
                if byte == 0 and shift > 0:
                    msg = "prop: a token has a number with a superfluous byte"
                    raise ValueError(msg)
                return number
            shift += 7

    def choice(self) -> Choice:
        """Return the next choice."""
        tag = self._byte()
        if tag == _TAG_NON_NEGATIVE:
            return Choice("integer", self.number())
        if tag == _TAG_NEGATIVE:
            magnitude = self.number()
            if magnitude == 0 or magnitude > _NEGATIVE_LIMIT:
                msg = f"prop: a token has the negative of {magnitude}"
                raise ValueError(msg)
            return Choice("integer", -magnitude)
        if tag == _TAG_FLOAT:
            bits = 0
            for i in range(_FLOAT_BYTES):
                bits |= self._byte() << (8 * i)
            value = from_bits(bits)
            if math.isnan(value) and bits != NAN_BITS:
                msg = "prop: a token has a NaN without the canonical bits"
                raise ValueError(msg)
            return Choice("float", value)
        if tag == _TAG_SEQUENCE:
            length = self.number()
            elements = [min(self.number(), _ELEMENT_LIMIT) for _ in range(length)]
            return Choice("sequence", tuple(elements))
        msg = f"prop: a token has the unknown tag {tag}"
        raise ValueError(msg)


def _unpadded(token: str, text: str) -> bytes:
    """Return the bytes of base64url text in the one form that encode writes."""
    refused = f"prop: the token {json.dumps(token)} is not unpadded base64url"
    # Text of base64url characters always decodes when its length is not
    # 4k + 1, so b64decode does not raise here.
    if _BASE64URL.fullmatch(text) is None or len(text) % 4 == 1:
        raise ValueError(refused)
    data = base64.b64decode(text + "=" * (-len(text) % 4), altchars=b"-_")
    if base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii") != text:
        raise ValueError(refused)
    return data


def decode(token: str) -> list[Choice]:
    """Return the choice sequence of a token.

    A token is valid only in the form that encode returns.

    - The text is base64url without padding.
    - A LEB128 number does not have a superfluous byte.
    - A negative integer is not zero.
    - Every NaN has the canonical bits.

    The decoder reads an element at or above 2^32 as 2^32 - 1. That value
    replays in the same way as the element.

    Args:
        token: The token.

    Returns:
        The choices.

    Raises:
        ValueError: The token is not in the form that encode returns, or it
            has an unknown tag, a payload cut short, a number of 2^64 or
            more, or a negative integer below -2^63.
    """
    if not token.startswith(PREFIX):
        msg = f"prop: the token {json.dumps(token)} does not start with {PREFIX}"
        raise ValueError(msg)
    reader = _Reader(_unpadded(token, token[len(PREFIX) :]))
    choices: list[Choice] = []
    while not reader.done():
        choices.append(reader.choice())
    return choices
