# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _matcher/compare.py tests the structural equality of the definition.

The verdict of every assertion that compares values comes from this
comparison, so this spec checks its verdicts with the assert statement of
pytest.
"""

from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, ClassVar

import pytest

from dokimi_assert._matcher.compare import (
    contains_element,
    equal,
    is_collection,
    is_reference,
)
from dokimi_assert._matcher.option import (
    Relaxations,
    by_identity,
    equate_by,
    settings,
)
from dokimi_assert._override import override
from dokimi_assert.conformance.literal import RefInt

NONE = Relaxations()
NANS = Relaxations(equate_nans=True)
EMPTY = Relaxations(equate_empty=True)
IDENTITY = Relaxations(by_identity=True)


@dataclass
class Point:
    """A dataclass with two fields."""

    x: Any
    y: Any


@dataclass(frozen=True)
class Cached:
    """A value with its text and a cache that a read of the value sets."""

    text: str
    cache: int = 0


@dataclass(frozen=True)
class Left:
    """A value whose transform returns a Right."""

    n: int


@dataclass(frozen=True)
class Right:
    """A value whose transform returns a Left."""

    n: int


def text_of(value: Cached) -> str:
    """Return the text of a cached value."""
    return value.text


def boom(_: Cached) -> str:
    """Raise ValueError for any value."""
    msg = "boom"
    raise ValueError(msg)


#: The relaxations that compare a cached value by its text.
BY_TEXT = settings([equate_by(Cached, text_of)])

#: The relaxations that compare a str by its lower case.
BY_LOWER = settings([equate_by(str, str.lower)])


class Always:
    """An object whose == returns a value that is not a bool."""

    @override
    def __eq__(self, other: object) -> Any:
        """Return a list with one item. The list is true."""
        return [1]

    @override
    def __hash__(self) -> int:
        """Return the hash of the identity of the object."""
        return id(self)


def cycle() -> list[Any]:
    """Return a list that contains itself."""
    out: list[Any] = [1]
    out.append(out)
    return out


class TestEqual:
    """equal compares two values under the rules of the definition."""

    equal_pairs: ClassVar[list[tuple[str, Any, Any, Relaxations]]] = [
        ("equates two ints of one value", 1, 1, NONE),
        ("equates -0.0 and 0.0", -0.0, 0.0, NONE),
        ("equates two nans under equate-nans", math.nan, math.nan, NANS),
        ("equates two lists of equal items", [1, [2]], [1, [2]], NONE),
        ("equates two tuples of equal items", (1, "a"), (1, "a"), NONE),
        (
            "equates two dicts of equal entries in any order",
            {"a": 1, "b": 2},
            {"b": 2, "a": 1},
            NONE,
        ),
        (
            "equates a nan key with a nan key under equate-nans",
            {math.nan: 1},
            {math.nan: 1},
            NANS,
        ),
        (
            "equates a key of a tuple with an equal tuple",
            {(1, 2): "a"},
            {(1, 2): "a"},
            NONE,
        ),
        ("equates two sets of equal elements", {1, 2}, {2, 1}, NONE),
        ("equates two dataclasses of equal fields", Point(1, [2]), Point(1, [2]), NONE),
        ("equates none and an empty list under equate-empty", None, [], EMPTY),
        ("equates an empty dict and none under equate-empty", {}, None, EMPTY),
        ("equates two nones", None, None, EMPTY),
        ("equates an object by its own ==", Always(), Always(), NONE),
        ("stops at a value that contains itself", cycle(), cycle(), NONE),
        (
            "equates a none key with a none key under equate-empty",
            {None: 1},
            {None: 1},
            EMPTY,
        ),
        (
            "equates two values that are not references under by-identity",
            (1, "a"),
            (1, "a"),
            IDENTITY,
        ),
    ]

    @pytest.mark.parametrize(
        ("name", "got", "want", "relax"), equal_pairs, ids=[t[0] for t in equal_pairs]
    )
    def test_equates(self, name: str, got: Any, want: Any, relax: Relaxations) -> None:
        """Each pair is equal under its relaxations."""
        assert equal(got, want, relax), name

    unequal_pairs: ClassVar[list[tuple[str, Any, Any, Relaxations]]] = [
        ("separates an int from a float", 1, 1.0, NONE),
        ("separates a bool from an int", True, 1, NONE),
        ("separates two ints of different values", 1, 2, NONE),
        ("separates two nans without equate-nans", math.nan, math.nan, NONE),
        ("separates two floats of different values", 1.0, 2.0, NONE),
        ("separates two lists of different lengths", [1], [1, 2], NONE),
        ("separates two lists of different items", [1, 2], [1, 3], NONE),
        ("separates a list from a tuple", [1], (1,), NONE),
        ("separates a dict from an ordered dict", {"a": 1}, OrderedDict(a=1), NONE),
        ("separates two dicts of different sizes", {"a": 1}, {"a": 1, "b": 2}, NONE),
        ("separates two dicts of different values", {"a": 1}, {"a": 2}, NONE),
        ("separates a key 1 from a key 1.0", {1: "a"}, {1.0: "a"}, NONE),
        (
            "separates two nan keys without equate-nans",
            {math.nan: 1},
            {math.nan: 1},
            NONE,
        ),
        ("separates two sets of different elements", {1}, {2}, NONE),
        ("separates two sets of different sizes", {1}, {1, 2}, NONE),
        (
            "separates two dataclasses of different fields",
            Point(1, 2),
            Point(1, 3),
            NONE,
        ),
        ("separates none from an empty list without equate-empty", None, [], NONE),
        (
            "separates none from a list with an item under equate-empty",
            None,
            [1],
            EMPTY,
        ),
        ("separates none from a str under equate-empty", None, "", EMPTY),
        (
            "separates two lists that are different objects under by-identity",
            [1],
            [1],
            IDENTITY,
        ),
        (
            "separates two references of one value under by-identity",
            RefInt(1),
            RefInt(1),
            IDENTITY,
        ),
    ]

    @pytest.mark.parametrize(
        ("name", "got", "want", "relax"),
        unequal_pairs,
        ids=[t[0] for t in unequal_pairs],
    )
    def test_separates(
        self, name: str, got: Any, want: Any, relax: Relaxations
    ) -> None:
        """Each pair differs under its relaxations."""
        assert not equal(got, want, relax), name

    def test_equates_one_reference_with_itself_under_by_identity(self) -> None:
        """A reference equals itself under by-identity.

        A tuple is a value, so the rule applies inside a tuple too.
        """
        reference = [1]
        assert equal(reference, reference, IDENTITY)
        assert equal((reference,), (reference,), IDENTITY)

    def test_equates_two_references_of_one_value_without_by_identity(self) -> None:
        """Without by-identity, two references of equal values are equal."""
        assert equal(RefInt(1), RefInt(1), NONE)


class TestEqualUnderEquateBy:
    """equal compares a value that an equate-by option matches by its transform."""

    equal_pairs: ClassVar[list[tuple[str, Any, Any, Relaxations]]] = [
        (
            "equates two values whose transforms are equal",
            Cached("a", 1),
            Cached("a", 2),
            BY_TEXT,
        ),
        (
            "equates two elements of a list by their transforms",
            [Cached("a", 1)],
            [Cached("a", 2)],
            BY_TEXT,
        ),
        (
            "equates two keys of a dict by their transforms",
            {Cached("a", 1): 0},
            {Cached("a", 2): 0},
            BY_TEXT,
        ),
        (
            "equates two values of a dict by their transforms",
            {"k": Cached("a", 1)},
            {"k": Cached("a", 2)},
            BY_TEXT,
        ),
        (
            "equates two fields of a record by their transforms",
            Point(Cached("a", 1), 0),
            Point(Cached("a", 2), 0),
            BY_TEXT,
        ),
        (
            "equates two elements of a set by their transforms",
            {Cached("a", 1)},
            {Cached("a", 2)},
            BY_TEXT,
        ),
        (
            "equates a value with the result of its transform",
            Cached("a", 1),
            "a",
            BY_TEXT,
        ),
        (
            "equates two keys of a hashed type by their transforms",
            {"A": 1},
            {"a": 1},
            BY_LOWER,
        ),
        (
            "equates a key of a hashed type with a key whose transform equals it",
            {"a": 1},
            {Cached("a", 1): 1},
            BY_TEXT,
        ),
        (
            "compares the parts of a result under the transforms again",
            Cached("A"),
            Cached("a"),
            settings(
                [equate_by(Cached, lambda c: [c.text]), equate_by(str, str.lower)]
            ),
        ),
        (
            "applies one transform at a place",
            Left(1),
            Left(1),
            settings(
                [
                    equate_by(Left, lambda v: Right(v.n)),
                    equate_by(Right, lambda v: Left(v.n)),
                ]
            ),
        ),
        (
            "applies the transform before by-identity",
            Cached("a", 1),
            Cached("a", 2),
            settings([by_identity(), equate_by(Cached, text_of)]),
        ),
        (
            "applies the last transform whose type matches",
            Cached("a", 1),
            Cached("a", 2),
            settings(
                [equate_by(Cached, lambda c: c.cache), equate_by(Cached, text_of)]
            ),
        ),
    ]

    @pytest.mark.parametrize(
        ("name", "got", "want", "relax"), equal_pairs, ids=[t[0] for t in equal_pairs]
    )
    def test_equates(self, name: str, got: Any, want: Any, relax: Relaxations) -> None:
        """Each pair is equal under its transforms."""
        assert equal(got, want, relax), name

    unequal_pairs: ClassVar[list[tuple[str, Any, Any, Relaxations]]] = [
        (
            "separates two values whose transforms differ",
            Cached("a"),
            Cached("b"),
            BY_TEXT,
        ),
        (
            "separates two values that differ in their cache without the option",
            Cached("a", 1),
            Cached("a", 2),
            NONE,
        ),
        (
            "separates two keys of a hashed type whose transforms differ",
            {"A": 1},
            {"b": 1},
            BY_LOWER,
        ),
        (
            "applies the last transform whose type matches",
            Cached("a", 1),
            Cached("a", 2),
            settings(
                [equate_by(Cached, text_of), equate_by(Cached, lambda c: c.cache)]
            ),
        ),
    ]

    @pytest.mark.parametrize(
        ("name", "got", "want", "relax"),
        unequal_pairs,
        ids=[t[0] for t in unequal_pairs],
    )
    def test_separates(
        self, name: str, got: Any, want: Any, relax: Relaxations
    ) -> None:
        """Each pair differs under its transforms."""
        assert not equal(got, want, relax), name

    def test_raises_the_exception_of_a_transform(self) -> None:
        """The exception passes through the comparison."""
        with pytest.raises(ValueError, match="boom"):
            equal(Cached("a"), Cached("a"), settings([equate_by(Cached, boom)]))


class TestContainsElement:
    """contains_element reports whether an element equals the needle."""

    def test_finds_an_element_that_equals_the_needle(self) -> None:
        """The second element equals the needle."""
        assert contains_element([1, 2], 2, NONE)

    def test_does_not_find_a_float_for_an_int(self) -> None:
        """An int needle does not match a float element."""
        assert not contains_element([1.0], 1, NONE)

    def test_finds_an_element_whose_transform_equals_the_transform_of_the_needle(
        self,
    ) -> None:
        """The element and the needle differ in their cache alone."""
        assert contains_element([Cached("a", 1)], Cached("a", 2), BY_TEXT)


class TestIsReference:
    """is_reference reports whether a value is a reference under by-identity."""

    @pytest.mark.parametrize("give", [None, True, 1, 1.5, "a", b"a", (1,)])
    def test_reports_false_for_a_value(self, give: object) -> None:
        """None, a bool, an int, a float, a str, bytes and a tuple are values."""
        assert not is_reference(give)

    @pytest.mark.parametrize("give", [[1], {}, set(), Point(1, 2), RefInt(1)])
    def test_reports_true_for_every_other_object(self, give: object) -> None:
        """Every other object is a reference.

        An instance of a subclass of int is a reference too.
        """
        assert is_reference(give)


class TestIsCollection:
    """is_collection reports whether a value is a collection under equate-empty."""

    @pytest.mark.parametrize("give", [[], (), {}, set(), frozenset()])
    def test_reports_true_for_a_collection(self, give: object) -> None:
        """A list, a tuple, a mapping, a set and a frozenset are collections."""
        assert is_collection(give)

    @pytest.mark.parametrize("give", ["", b"", None, 0])
    def test_reports_false_for_another_value(self, give: object) -> None:
        """A str, bytes, None and a number are not collections."""
        assert not is_collection(give)
