# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of conformance/prop/fixture.py tests the fixture types and their vectors."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

import pytest

from dokimi_assert import check
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.prop.fixture import FIXTURES, fixtures_of
from dokimi_assert.conformance.vector import vectors

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

#: The fixtures vectors of the definition, by the name of the fixture.
FIXTURE_VECTORS = {v.raw["fixture"]: v.raw for v in vectors() if v.kind == "fixtures"}

#: The shape of the definition of tree, with the name #0 for its refs.
TREE = {
    "fields": [
        ["value", {"shape": "int", "signed": True, "width": 32}],
        ["children", {"of": {"name": "#0", "shape": "ref"}, "shape": "list"}],
    ],
    "shape": "record",
}


def fault_of(seat: Collector, raw: dict[str, Any]) -> tuple[str, str]:
    """Return the place and the reason of the fault that fixtures_of raises for raw."""
    error = check.raises(seat, lambda: fixtures_of(raw), "fixtures_of refuses")
    found = cast("FaultError", check.error_as(seat, error, FaultError, "a fault"))
    return found.at, found.reason


class TestFixtures:
    """FIXTURES has the Python type of each fixture type of the definition."""

    def test_contains_a_type_of_each_fixture_of_the_definition(
        self, seat: Collector
    ) -> None:
        """Every fixtures vector has a type."""
        check.equal(
            seat,
            sorted(FIXTURES),
            sorted(FIXTURE_VECTORS),
            "the table has a type of each fixture",
        )


class TestFixturesOf:
    """fixtures_of compares the shape of a fixture type with its vector."""

    @pytest.mark.parametrize("name", sorted(FIXTURE_VECTORS))
    def test_returns_no_outputs_for_the_shape_of_the_fixture_type(
        self, seat: Collector, name: str
    ) -> None:
        """The type reads as the shape of its vector."""
        check.equal(
            seat,
            fixtures_of(FIXTURE_VECTORS[name]),
            {},
            "the fixture type reads as the shape of its vector",
        )

    def test_raises_at_the_fixture_for_a_fixture_that_does_not_exist(
        self, seat: Collector
    ) -> None:
        """The table does not have the name."""
        check.equal(
            seat,
            fault_of(seat, {"fixture": "widget", "shape": {"shape": "bool"}}),
            ("fixture", '"widget" is not a fixture type'),
            "the fault is at the fixture",
        )

    def test_raises_at_the_shape_for_another_shape(self, seat: Collector) -> None:
        """The fault has both shapes with sorted keys."""
        raw = {"fixture": "flag", "shape": {"shape": "bool"}}
        check.equal(
            seat,
            fault_of(seat, raw),
            (
                "shape",
                (
                    'the fixture type has the shape {"fields": [["enabled", {"shape": '
                    '"bool"}]], "shape": "record"}, want {"shape": "bool"}'
                ),
            ),
            "the fault is at the shape",
        )

    def test_keeps_the_name_of_a_definition_outside_the_walk(
        self, seat: Collector
    ) -> None:
        """A definition outside the walk of the shape keeps its name."""
        shape = FIXTURE_VECTORS["tree"]["shape"]
        raw = {
            "fixture": "tree",
            "shape": {
                **shape,
                "definitions": {**shape["definitions"], "leaf": {"shape": "bool"}},
            },
        }
        _, reason = fault_of(seat, raw)
        check.has_suffix(
            seat,
            reason,
            'want {"definitions": {"#0": '
            + json.dumps(TREE, sort_keys=True)
            + ', "leaf": {"shape": "bool"}}, "name": "#0", "shape": "ref"}',
            "the definition leaf keeps its name, and tree is #0",
        )
