# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The relaxations that a caller applies to one comparison."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, TypeVar

if TYPE_CHECKING:
    from collections.abc import Iterable

__all__ = [
    "Option",
    "Relaxations",
    "Transform",
    "by_identity",
    "equate_by",
    "equate_empty",
    "equate_nans",
    "settings",
    "transformed",
]

_T = TypeVar("_T")

#: The transform of an option of equate-by: the type of the values that it
#: matches, and the function that it applies to such a value.
Transform = tuple[type[Any], Callable[[Any], object]]


@dataclass(frozen=True, slots=True)
class Option:
    """One relaxation of the comparison rules for the call that receives it.

    An option of equate-empty, equate-nans or by-identity does not have a
    state, so a caller can reuse one across calls and threads. An option of
    equate-by keeps its transform, so it is safe to share across threads
    when its transform is. The order of the options matters only between
    two options of equate-by whose types match one value. An option passed
    twice has the effect of one.

    Attributes:
        kind: The canonical id of the relaxation.
        transform: The transform of an option of equate-by, and None for
            every other option.
    """

    kind: Literal["equate-empty", "equate-nans", "by-identity", "equate-by"]
    transform: Transform | None = None


@dataclass(frozen=True, slots=True)
class Relaxations:
    """The relaxations that the options of one call allow.

    Attributes:
        equate_empty: When True, an absent collection equals an empty one.
        equate_nans: When True, a NaN equals another NaN.
        by_identity: When True, a reference equals only a reference to the
            same object.
        transforms: The transforms of the options of equate-by in the order
            of the call.
    """

    equate_empty: bool = False
    equate_nans: bool = False
    by_identity: bool = False
    transforms: tuple[Transform, ...] = ()


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


def equate_by(kind: type[_T], f: Callable[[_T], object]) -> Option:
    """Make a value of kind compare by f(value), for the call it is passed to.

    A value matches when it is an instance of kind, so an instance of a
    subclass matches too. The rule applies at the top, to an element of a
    list, to a key or a value of a map, and to a field of a record. At one
    place at most one transform applies. The result compares as it is, and
    its parts compare under every transform again. The last equate_by of a
    call whose kind matches a value applies, and it applies before
    by_identity.

    The record of equal states f(want) and f(got) in place of want and got
    when they match, and the record of not_equal states f(got). An
    exception of f passes through the call. f must not change its argument,
    and its result must not contain its argument.

    A protobuf message compares by its text:

        check.equal(
            seat, got, want, "the stored book is the written book",
            equate_by(Message, text_format.MessageToString),
        )

    Args:
        kind: The type of the values that compare by f.
        f: The transform.

    Returns:
        The option for a comparing assertion.

    Raises:
        TypeError: kind is not a type, or f is not callable.
    """
    if not isinstance(kind, type):  # pyright: ignore[reportUnnecessaryIsInstance]
        msg = f"equate_by: {kind!r} is not a type"  # type: ignore[unreachable]
        raise TypeError(msg)  # pyright: ignore[reportUnreachable]
    if not callable(f):
        msg = f"equate_by: {f!r} is not callable"  # type: ignore[unreachable]
        raise TypeError(msg)  # pyright: ignore[reportUnreachable]
    return Option("equate-by", (kind, f))


def settings(options: Iterable[Option]) -> Relaxations:
    """Return the relaxations that the options of one call allow.

    Args:
        options: The options passed to the call.

    Returns:
        The relaxations in force for the comparison.
    """
    given = list(options)
    kinds = {option.kind for option in given}
    return Relaxations(
        equate_empty="equate-empty" in kinds,
        equate_nans="equate-nans" in kinds,
        by_identity="by-identity" in kinds,
        transforms=tuple(
            option.transform for option in given if option.transform is not None
        ),
    )


def transformed(value: object, relax: Relaxations) -> object:
    """Return a value under the last transform whose type matches it.

    Args:
        value: The value.
        relax: The relaxations of the comparison.

    Returns:
        The result of the transform, or the value itself when no transform
        matches it.
    """
    for kind, f in reversed(relax.transforms):
        if isinstance(value, kind):
            return f(value)
    return value
