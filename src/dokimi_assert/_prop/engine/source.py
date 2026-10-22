# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The random source of every generated case.

The source is the 64-bit three-rotate variant of Bob Jenkins's small
noncryptographic generator. It adds, subtracts, takes the exclusive or and
rotates modulo 2^64. It works on Python integers that it masks to 64 bits.

Case i of a run with seed s reads the stream of s + i. The draws consume
that stream in an order that the definition fixes, so one seed gives the
same cases in every language.
"""

from __future__ import annotations

import re

__all__ = ["MASK", "Source", "case_source", "mix", "utf8"]

#: The number of bits of every value of the stream.
_BITS = 64

#: The largest unsigned 64-bit integer.
MASK = (1 << _BITS) - 1

#: The constant that the initialisation puts in the first word.
_FIRST_WORD = 0xF1EA5EED

#: The rounds that the initialisation discards, so that nearby seeds give
#: unrelated streams.
_WARMUP_ROUNDS = 20

#: The pattern of a lone surrogate and the character that replaces it. UTF-8
#: does not have bytes for a lone surrogate.
_SURROGATE = re.compile(f"[{chr(0xD800)}-{chr(0xDFFF)}]")
_REPLACEMENT = chr(0xFFFD)


def _rotl(value: int, count: int) -> int:
    """Return value rotated left by count bits, modulo 2^64."""
    return ((value << count) | (value >> (_BITS - count))) & MASK


class Source:
    """The stream of 64-bit values of one seed. Each case reads its own."""

    def __init__(self, seed: int) -> None:
        """Start the stream of seed.

        Args:
            seed: An unsigned 64-bit integer.

        Raises:
            ValueError: The seed is outside [0, 2^64).
        """
        if not 0 <= seed <= MASK:
            msg = f"prop: seed {seed} is not an unsigned 64-bit integer"
            raise ValueError(msg)
        self._a: int = _FIRST_WORD
        self._b: int = seed
        self._c: int = seed
        self._d: int = seed
        for _ in range(_WARMUP_ROUNDS):
            self.next()

    def next(self) -> int:
        """Return the next 64-bit value of the stream.

        Returns:
            The value, from 0 to 2^64 - 1.
        """
        e = (self._a - _rotl(self._b, 7)) & MASK
        self._a = self._b ^ _rotl(self._c, 13)
        self._b = (self._c + _rotl(self._d, 37)) & MASK
        self._c = (self._d + e) & MASK
        self._d = (e + self._a) & MASK
        return self._d

    def below(self, n: int) -> int:
        """Return a uniform value in [0, n).

        For an n of 1, the draw does not consume a value. Otherwise each
        attempt consumes one value and keeps as many top bits as n - 1 has.
        The draw repeats while the result is n or more.

        Args:
            n: The number of values, from 1 to 2^64.

        Returns:
            The value.

        Raises:
            ValueError: n is outside [1, 2^64].
        """
        if not 1 <= n <= MASK + 1:
            msg = f"prop: below({n}) needs 1 <= n <= 2^64"
            raise ValueError(msg)
        if n == 1:
            return 0
        shift = _BITS - (n - 1).bit_length()
        while True:
            value = self.next() >> shift
            if value < n:
                return value

    def coin(self, num: int, den: int) -> bool:
        """Return True with the probability num/den, from one draw of below(den).

        Args:
            num: The numerator, from 0 to den.
            den: The denominator, at least 1.

        Returns:
            True when the coin came up.

        Raises:
            ValueError: den is below 1, or num is outside [0, den].
        """
        if den < 1 or not 0 <= num <= den:
            msg = f"prop: coin({num}, {den}) needs 0 <= num <= den"
            raise ValueError(msg)
        return self.below(den) < num


def case_source(seed: int, index: int) -> Source:
    """Return the source of a case.

    The seed of the source is the seed of the run plus the index, modulo 2^64.

    Args:
        seed: The seed of the run.
        index: The index of the case in the run.

    Returns:
        The source of the case.
    """
    return Source((seed + index) & MASK)


def mix(data: bytes) -> int:
    """Fold bytes into one 64-bit value with the random source alone.

    The value starts at zero. For each byte it becomes the first output of
    the stream whose seed is the value xor the byte. The fold derives the
    seed of a contract and the name of a store entry without a hash
    function.

    Args:
        data: The bytes.

    Returns:
        The value.
    """
    value = 0
    for byte in data:
        value = Source(value ^ byte).next()
    return value


def utf8(text: str) -> bytes:
    """Return the UTF-8 bytes of text, with U+FFFD in place of each lone surrogate.

    The UTF-8 encoder of JavaScript writes a lone surrogate the same way, so
    mix gives one value for a text in every language.

    Args:
        text: The text.

    Returns:
        The bytes.
    """
    return _SURROGATE.sub(_REPLACEMENT, text).encode("utf-8")
