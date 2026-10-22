# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The relaxations that a caller applies to one comparison."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "Option",
    "Relaxations",
    "by_identity",
    "equate_empty",
    "equate_nans",
    "settings",
]


@dataclass(frozen=True, slots=True)
class Option:
    """One relaxation of the comparison rules for the call that receives it.

    An option does not have a state, so a caller can reuse one across calls
    and threads. The order of the options does not matter. An option passed
    twice has the effect of one.

    Attributes:
        kind: The canonical id of the relaxation.
    """

    kind: Literal["equate-empty", "equate-nans", "by-identity"]


@dataclass(frozen=True, slots=True)
class Relaxations:
    """The relaxations that the options of one call allow.

    Attributes:
        equate_empty: When True, an absent collection equals an empty one.
        equate_nans: When True, a NaN equals another NaN.
        by_identity: When True, a reference equals only a reference to the
            same object.
    """

    equate_empty: bool = False
    equate_nans: bool = False
    by_identity: bool = False


def equate_empty() -> Option:
    """Make an absent collection equal an empty one.

    A collection is a list, a tuple, a mapping, a set or a frozenset. Without
    the option, None does not equal an empty collection, because an absent
    value and a value that is present and empty are different results.

    Returns:
        The option for a comparing assertion.
    """
    return Option("equate-empty")


def equate_nans() -> Option:
    """Make a NaN equal another NaN.

    Without the option, the comparison follows IEEE 754. Under IEEE 754, a
    NaN does not equal any value, and it does not equal itself.

    Returns:
        The option for a comparing assertion.
    """
    return Option("equate-nans")


def by_identity() -> Option:
    """Compare references by identity.

    Every object is a reference except None, a bool, an int, a float, a str,
    bytes and a tuple. The items of a tuple are compared one by one. Under
    the option, a reference equals only itself. The rule applies at the top,
    to an element of a list, to a key or a value of a map, and to a field of
    a record. A value that is not a reference is compared as it is without
    the option.

    Returns:
        The option for a comparing assertion.
    """
    return Option("by-identity")


def settings(options: Iterable[Option]) -> Relaxations:
    """Return the relaxations that the options of one call allow.

    Args:
        options: The options passed to the call.

    Returns:
        The relaxations in force for the comparison.
    """
    kinds = {option.kind for option in options}
    return Relaxations(
        equate_empty="equate-empty" in kinds,
        equate_nans="equate-nans" in kinds,
        by_identity="by-identity" in kinds,
    )
