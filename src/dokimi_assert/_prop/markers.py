# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The constraints of prop for the constraints that annotated-types does not have.

A caller adds a constraint as an argument of typing.Annotated, as with the
constraints of annotated-types:

    quantity: Annotated[int, Width(32), Ge(1), Le(99)]
    code: Annotated[str, Pattern(r"[A-Z]{3}-[0-9]{4}")]
    price: Annotated[Decimal, Scale(2), Ge(0)]

Each marker is a frozen dataclass, so two markers of equal fields are equal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "AllowInfinity",
    "AllowNan",
    "Alphabet",
    "Char",
    "Pattern",
    "Scale",
    "Unit",
    "Version",
    "Width",
]


@dataclass(frozen=True, slots=True)
class Width:
    """The width of an int or a float in bits.

    Without this constraint, an int is 64 bits wide and signed. A float is 64
    bits wide.

    Attributes:
        bits: 8, 16, 32, 64 or 128 for an int, and 32 or 64 for a float.
        signed: When True, the int is signed. It does not apply to a float.
    """

    bits: int
    signed: bool = True


@dataclass(frozen=True, slots=True)
class Pattern:
    """A pattern of the portable subset that every value of a str matches.

    Attributes:
        regex: The pattern.
    """

    regex: str


@dataclass(frozen=True, slots=True)
class Alphabet:
    """The characters of a str. They replace the default alphabet.

    Attributes:
        characters: The characters.
    """

    characters: str


@dataclass(frozen=True, slots=True)
class AllowNan:
    """The constraint that a float can be NaN."""


@dataclass(frozen=True, slots=True)
class AllowInfinity:
    """The constraint that a float can be infinite."""


@dataclass(frozen=True, slots=True)
class Unit:
    """The resolution of a datetime, a time or a timedelta.

    The default is us. datetime, time and timedelta have a resolution of one
    microsecond, so they do not take ns.

    Attributes:
        name: s, ms or us.
    """

    name: Literal["s", "ms", "us", "ns"]


@dataclass(frozen=True, slots=True)
class Scale:
    """The number of digits after the point of a Decimal.

    A Decimal needs this constraint.

    Attributes:
        digits: The number of digits.
    """

    digits: int


@dataclass(frozen=True, slots=True)
class Version:
    """The version of an IP address of the type IPv4Address | IPv6Address.

    Attributes:
        number: 4 or 6.
    """

    number: Literal[4, 6]


@dataclass(frozen=True, slots=True)
class Char:
    """The constraint that a str has one code point.

    The type reader then reads the str as a char of the default alphabet.
    """
