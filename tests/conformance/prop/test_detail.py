# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of conformance/prop/detail.py tests the detail of a call record."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from dokimi_assert import check
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.prop.detail import detail_of

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


def failure(assertion: str) -> dict[str, Any]:
    """Return the JSON of a failure record of an assertion."""
    return {"assertion": assertion, "contract": "", "detail": {}, "where": None}


class TestDetailOf:
    """detail_of returns the detail of a call record in the form of a vector."""

    def test_returns_each_failure_as_its_assertion(self, seat: Collector) -> None:
        """The failure of the run and of each other failure is an identity."""
        record = {
            "detail": {
                "outcome": "counterexample",
                "failure": failure("odd"),
                "others": [{"failure": failure("big"), "choices": "prop1:ADQ"}],
            }
        }
        check.equal(
            seat,
            detail_of(record),
            {
                "outcome": "counterexample",
                "failure": "odd",
                "others": [{"failure": "big", "choices": "prop1:ADQ"}],
            },
            "every failure of the detail is its assertion",
        )

    def test_returns_the_null_fields_of_a_passing_run_unchanged(
        self, seat: Collector
    ) -> None:
        """A run without a failure has null for its failure and its others."""
        record = {"detail": {"outcome": "passed", "failure": None, "others": None}}
        check.equal(
            seat,
            detail_of(record),
            {"outcome": "passed", "failure": None, "others": None},
            "a passing run keeps its null fields",
        )

    def test_raises_for_a_record_of_a_fault(self, seat: Collector) -> None:
        """A call that a fault ended does not have a detail."""
        record = {"verdict": "error", "error": "prop.for_all: boom"}
        error = check.raises(seat, lambda: detail_of(record), "detail_of refuses")
        found = cast("FaultError", check.error_as(seat, error, FaultError, "a fault"))
        check.equal(
            seat,
            (found.at, found.reason),
            ("", 'the run ends with the fault "prop.for_all: boom"'),
            "the fault has the error of the record",
        )
