# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/value.py tests decoded values and their equality."""

from __future__ import annotations

import dataclasses
import datetime
import decimal
import enum
import math
from typing import TYPE_CHECKING, Any, ClassVar, NamedTuple

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.value import Fields, Pairs, Variant, canonical

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


class Widget:
    """A class whose instances compare by identity."""


@dataclasses.dataclass
class Point:
    """A dataclass of the spec."""

    x: int
    y: int


@dataclasses.dataclass
class Other:
    """A dataclass of the spec with the fields of Point."""

    x: int
    y: int


class Pair(NamedTuple):
    """A named tuple of the spec."""

    left: int
    right: int


class Colour(enum.Enum):
    """An enum of the spec."""

    RED = 1
    BLUE = 2


class Level(enum.IntEnum):
    """An enum of the spec whose members are ints."""

    LOW = 1


class Speed(enum.StrEnum):
    """An enum of the spec whose members are strs."""

    FAST = "fast"


def named() -> int:
    """Return 1. A function compares by identity."""
    return 1


class TestPairs:
    """Pairs is a decoded dict."""

    def test_keeps_the_entries_in_order(self, seat: Collector) -> None:
        """The entries keep the order of their generation."""
        pairs = Pairs(((1, "a"), (2, "b")))
        check.equal(
            seat,
            pairs.items,
            ((1, "a"), (2, "b")),
            "Pairs keeps both entries in order",
        )


class TestFields:
    """Fields is a decoded record."""

    def test_keeps_the_fields_in_order(self, seat: Collector) -> None:
        """The fields keep their declaration order."""
        fields = Fields((("b", 1), ("a", 2)))
        check.equal(
            seat,
            fields.fields,
            (("b", 1), ("a", 2)),
            "Fields keeps both fields in order",
        )


class TestVariant:
    """Variant is a decoded variant of an enum."""

    def test_returns_a_variant_with_a_payload_when_one_is_given(
        self, seat: Collector
    ) -> None:
        """A payload of None is a payload."""
        variant = Variant("note", None)
        check.equal(
            seat,
            [variant.name, variant.has_payload, variant.payload],
            ["note", True, None],
            "the variant has the payload None",
        )

    def test_returns_a_variant_without_a_payload_by_default(
        self, seat: Collector
    ) -> None:
        """The call does not pass a payload."""
        variant = Variant("pending")
        check.equal(
            seat,
            [variant.name, variant.has_payload],
            ["pending", False],
            "the variant does not have a payload",
        )


class TestCanonical:
    """canonical returns the text that two equal values share."""

    equal: ClassVar[list[tuple[str, Any, Any]]] = [
        ("returns one text for every nan", math.nan, -math.nan),
        ("returns one text for two lists of equal elements", [1, [0]], [1, [0]]),
        ("returns one text for a list and a tuple of one item", [1], (1,)),
        (
            "returns one text for two dicts with their entries in another order",
            Pairs(((1, "a"), (2, "b"))),
            Pairs(((2, "b"), (1, "a"))),
        ),
        (
            "returns one text for a dict and pairs of the same entries",
            {1: "a"},
            Pairs(((1, "a"),)),
        ),
        (
            "returns one text for two sets with their elements in another order",
            {1, 2},
            frozenset((2, 1)),
        ),
        (
            "returns one text for two records of the same fields",
            Fields((("a", 1), ("b", 0.0))),
            Fields((("a", 1), ("b", 0.0))),
        ),
        (
            "returns one text for two dataclasses of the same fields",
            Point(1, 2),
            Point(1, 2),
        ),
        ("returns one text for two named tuples of one value", Pair(1, 2), Pair(1, 2)),
        (
            "returns one text for two variants of one name and payload",
            Variant("x", [1]),
            Variant("x", [1]),
        ),
        ("returns one text for two members of one enum", Colour.RED, Colour.RED),
        (
            "returns one text for two equal byte strings",
            b"\x01\x02",
            bytearray(b"\x01\x02"),
        ),
        (
            "returns one text for two dates of one day",
            datetime.date(2026, 10, 8),
            datetime.date(2026, 10, 8),
        ),
        (
            "returns one text for two decimals of one text",
            decimal.Decimal("1.50"),
            decimal.Decimal("1.50"),
        ),
        ("returns one text for a function and itself", named, named),
    ]

    @pytest.mark.parametrize(
        ("a", "b"), [t[1:] for t in equal], ids=[t[0] for t in equal]
    )
    def test_returns_one_text_for_equal_values(
        self, seat: Collector, a: Any, b: Any
    ) -> None:
        """Equal values share their text."""
        check.equal(seat, canonical(a), canonical(b), "the values have the same text")

    different: ClassVar[list[tuple[str, Any, Any]]] = [
        ("returns two texts for the two zeros", 0.0, -0.0),
        ("returns two texts for a bool and an int", True, 1),
        ("returns two texts for an int and a float", 1, 1.0),
        ("returns two texts for none and zero", None, 0),
        (
            "returns two texts for lists that differ in the sign of a nested zero",
            [1, [0.0]],
            [1, [-0.0]],
        ),
        (
            "returns two texts for dicts whose keys are a bool and an int",
            Pairs(((True, "a"),)),
            Pairs(((1, "a"),)),
        ),
        (
            "returns two texts for dicts with another value",
            Pairs(((1, "a"),)),
            Pairs(((1, "c"),)),
        ),
        ("returns two texts for a string and the bytes of its characters", "a", b"a"),
        (
            "returns two texts for records with their fields in another order",
            Fields((("a", 1), ("b", 2))),
            Fields((("b", 2), ("a", 1))),
        ),
        (
            "returns two texts for dataclasses of two types",
            Point(1, 2),
            Other(1, 2),
        ),
        (
            "returns two texts for a variant without a payload and one with None",
            Variant("x"),
            Variant("x", None),
        ),
        ("returns two texts for variants of two names", Variant("x"), Variant("y")),
        (
            "returns two texts for variants of two payloads",
            Variant("x", 1),
            Variant("x", 2),
        ),
        ("returns two texts for two members of an enum", Colour.RED, Colour.BLUE),
        ("returns two texts for a member of an int enum and its int", Level.LOW, 1),
        (
            "returns two texts for a member of a str enum and its str",
            Speed.FAST,
            "fast",
        ),
        ("returns two texts for a set and a list of the same elements", {1}, [1]),
        (
            "returns two texts for a date and a date and time",
            datetime.date(2026, 10, 8),
            datetime.datetime(2026, 10, 8),
        ),
        ("returns two texts for two functions", lambda: 1, lambda: 1),
        ("returns two texts for two instances of a class", Widget(), Widget()),
    ]

    @pytest.mark.parametrize(
        ("a", "b"), [t[1:] for t in different], ids=[t[0] for t in different]
    )
    def test_returns_two_texts_for_values_that_differ(
        self, seat: Collector, a: Any, b: Any
    ) -> None:
        """Values that differ have two texts."""
        check.not_equal(seat, canonical(a), canonical(b), "the values have two texts")

    def test_returns_one_text_for_an_instance_of_a_class_and_itself(
        self, seat: Collector
    ) -> None:
        """An object without a value compares by identity."""
        widget = Widget()
        check.equal(
            seat, canonical(widget), canonical(widget), "the instance has one text"
        )

    def test_returns_the_text_of_each_scalar(self, seat: Collector) -> None:
        """Each text starts with the type."""
        check.equal(
            seat,
            [canonical(None), canonical(False), canonical(-3), canonical("é")],
            ["null", "bool:false", "int:-3", 'string:"\\u00e9"'],
            "canonical returns the text of each scalar",
        )
