"""Relaxations a caller may apply to one comparison."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Option:
    """Relaxes one comparison rule for the call it is passed to.

    An Option carries no state and is safe to reuse across calls and
    across threads. Order does not matter, passing one twice has the
    same effect as passing it once, and an Option never leaks into a
    call it was not passed to.
    """

    equate_empty: bool = False
    equate_nans: bool = False


def equate_empty() -> Option:
    """Make an absent collection equal an empty one of the same type.

    The default keeps them apart, because a value that is absent and a
    value that is present but empty are different answers, and a test
    may need to tell them apart.
    """
    return Option(equate_empty=True)


def equate_nans() -> Option:
    """Make a NaN float equal another NaN.

    The default keeps them unequal, following IEEE 754, where NaN
    compares unequal to every value including itself.
    """
    return Option(equate_nans=True)


def settings(options: tuple[Option, ...]) -> Option:
    """Fold an option list into the relaxations it asks for."""
    return Option(
        equate_empty=any(o.equate_empty for o in options),
        equate_nans=any(o.equate_nans for o in options),
    )
