"""The typed-literal encoding a corpus case states its values in."""

from __future__ import annotations

import math
from collections.abc import Callable

import pytest

from dokimi_assert import check
from dokimi_assert.conformance.literal import UnknownLiteralError, decode
from dokimi_assert.seat import Standard

OUTER = Standard()


def _positive_infinity(value: float) -> bool:
    """Report whether value is infinity in the positive direction."""
    return math.isinf(value) and value > 0


def _negative_infinity(value: float) -> bool:
    """Report whether value is infinity in the negative direction."""
    return math.isinf(value) and value < 0


@pytest.mark.parametrize(
    ("literal", "want"),
    [
        ({"type": "null"}, None),
        ({"type": "bool", "value": True}, True),
        ({"type": "int", "value": 1}, 1),
        ({"type": "float", "value": 1.5}, 1.5),
        ({"type": "string", "value": "abc"}, "abc"),
    ],
)
def test_a_scalar_decodes_to_its_native_value(
    literal: dict[str, object], want: object
) -> None:
    """Each tag names one native type."""
    check.equal(OUTER, decode(literal), want, "the literal decodes")


def test_an_empty_list_is_present_not_absent() -> None:
    """This is the rule the whole encoding exists to pin."""
    got = decode({"type": "list", "of": "int", "value": []})

    check.is_not_none(OUTER, got, "an empty list is not None")
    check.is_empty(OUTER, got, "an empty list holds nothing")


def test_an_empty_map_is_present_not_absent() -> None:
    """The same holds for a mapping."""
    got = decode({"type": "map", "key": "string", "of": "int", "value": {}})

    check.is_not_none(OUTER, got, "an empty map is not None")
    check.is_empty(OUTER, got, "an empty map holds nothing")


def test_a_populated_list_decodes_its_elements() -> None:
    """Elements take the type the literal names."""
    check.equal(
        OUTER,
        decode({"type": "list", "of": "int", "value": [1, 2]}),
        [1, 2],
        "the list decodes to its native form",
    )


def test_a_populated_map_decodes_its_values() -> None:
    """Values take the type the literal names."""
    check.equal(
        OUTER,
        decode({"type": "map", "key": "string", "of": "int", "value": {"a": 1}}),
        {"a": 1},
        "the map decodes to its native form",
    )


@pytest.mark.parametrize(
    ("name", "predicate"),
    [
        ("NaN", math.isnan),
        ("Inf", _positive_infinity),
        ("-Inf", _negative_infinity),
    ],
)
def test_a_named_float_decodes(name: str, predicate: Callable[[float], bool]) -> None:
    """JSON has no number for these, so the encoding names them."""
    got = decode({"type": "float", "value": name})
    check.is_true(OUTER, predicate(got), f"{name} decodes to itself")


@pytest.mark.parametrize(
    "literal",
    [
        {"type": "widget"},
        {"type": "list", "of": "widget", "value": []},
        {"type": "map", "key": "int", "of": "int", "value": {}},
        {"type": "float", "value": "Huge"},
    ],
)
def test_a_literal_the_encoding_does_not_cover_is_refused(
    literal: dict[str, object],
) -> None:
    """Refused rather than guessed at, so a gap is visible."""
    caught = check.raises(OUTER, lambda: decode(literal), "the literal is refused")
    check.is_true(
        OUTER, isinstance(caught, UnknownLiteralError), "it says what it could not read"
    )
