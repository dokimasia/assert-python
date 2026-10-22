# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of conformance/history/vectors.py tests the runners of the history vectors.

A runner computes the verdict of every history vector, so the spec checks
its own verdicts with the assert statement of pytest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.history.vectors import (
    ISOLATION_CONTRACT,
    LINEARIZABLE_CONTRACT,
    RUNNERS,
)
from dokimi_assert.conformance.vector import vectors

if TYPE_CHECKING:
    from collections.abc import Mapping

#: The history vectors of the definition, by id.
VECTORS = {v.id: v.raw for v in vectors() if v.kind in RUNNERS}

#: The id of a passing linearizable vector of six steps over one partition.
PASSING = "linearizable/concurrent-writes-take-effect-in-the-order-a-read-needs"

#: The id of a failing linearizable vector.
FAILING = "linearizable/a-read-after-a-completed-write-misses-it"

#: The id of a seam vector of a script.
SCRIPT = "history/a-client-continues-on-a-new-process-after-unknown"

#: The id of a seam vector of intervals.
INTERVALS = "history/from-intervals-puts-an-invocation-before-a-completion-at-one-time"

#: The invocation of a read of the key x by client 0.
READ = {
    "invoke": 0,
    "client": 0,
    "operation": "read",
    "args": [],
    "keys": [{"type": "string", "value": "x"}],
}


def vector(vector_id: str, **changes: Any) -> dict[str, Any]:
    """Return the vector of an id with changes to its members."""
    return {**VECTORS[vector_id], **changes}


def fault_of(kind: str, raw: Mapping[str, Any]) -> tuple[str, str]:
    """Return the place and the reason of the fault of a runner, or empty strings."""
    try:
        RUNNERS[kind](raw, "")
    except FaultError as error:
        return error.at, error.reason
    return "", ""


def test_contracts_are_the_contracts_of_the_checks() -> None:
    """A check of a vector has the contract of its kind."""
    assert (LINEARIZABLE_CONTRACT, ISOLATION_CONTRACT) == (
        "the history of the vector is linearizable",
        "the transactions of the vector are isolated",
    )


class TestRunners:
    """RUNNERS has the runner of each kind of history vector."""

    def test_contains_a_runner_of_each_kind(self) -> None:
        """Each kind is the name of a vector file of the family history."""
        assert sorted(RUNNERS) == [
            "linearizable",
            "seam",
            "serializable",
            "snapshot-isolation",
        ]

    @pytest.mark.parametrize("vector_id", sorted(VECTORS))
    def test_returns_for_the_vector(self, vector_id: str) -> None:
        """The run agrees with the vector."""
        kind = next(v.kind for v in vectors() if v.id == vector_id)
        assert fault_of(kind, VECTORS[vector_id]) == ("", "")

    seams: ClassVar[list[tuple[str, dict[str, Any], tuple[str, str]]]] = [
        (
            "raises for a seam vector without a script or intervals",
            {"events": []},
            ("", "the vector has neither a script nor intervals, or both"),
        ),
        (
            "raises for a seam vector with a script and intervals",
            {"script": [], "intervals": [], "events": []},
            ("", "the vector has neither a script nor intervals, or both"),
        ),
        (
            "raises at the refused entry of a seam that refuses another",
            {**VECTORS[SCRIPT], "refused": 1},
            ("refused", "the seam refuses no entry, want 1"),
        ),
        (
            "raises at an event that differs",
            {
                **VECTORS[SCRIPT],
                "events": [{"index": 9}, *VECTORS[SCRIPT]["events"][1:]],
            },
            (
                "events[0]",
                (
                    'the event is {"index": 0, "kind": "invoke", "call": 0, '
                    '"client": 0, "process": 0, "operation": "write", "args": '
                    '[{"type": "int", "value": 1}], "keys": [{"type": "string", '
                    '"value": "x"}]}, want {"index": 9}'
                ),
            ),
        ),
        (
            "raises at the events for a different number of events",
            {**VECTORS[SCRIPT], "events": VECTORS[SCRIPT]["events"][:1]},
            ("events", "the number of events is 4, want 1"),
        ),
        (
            "raises at the events for events that are not a list",
            {**VECTORS[SCRIPT], "events": None},
            ("events", "the events are not a list"),
        ),
        (
            "raises for a script that is not a list",
            {"script": {}, "events": []},
            ("script", "the script is not a list"),
        ),
        (
            "raises at an entry without a call of the seam",
            {"script": [{"widget": 0}], "events": []},
            ("script[0]", "the entry does not have a call of the seam"),
        ),
        (
            "raises at an entry that completes a call that is not open",
            {"script": [{"ok": 0, "output": {"type": "null"}}], "events": []},
            ("script[0]", "the entry completes the call 0, which is not open"),
        ),
        (
            "raises at arguments that are not a list",
            {"script": [{**READ, "args": 1}], "events": []},
            ("script[0].args", "the member is not a list"),
        ),
        (
            "raises at a value that is not a typed literal",
            {"script": [{**READ, "keys": [{"type": "widget"}]}], "events": []},
            ("script[0].keys[0]", "the value is not a typed literal"),
        ),
        (
            "raises for intervals that are not a list",
            {"intervals": {}, "events": []},
            ("intervals", "the intervals are not a list"),
        ),
        (
            "raises at an interval with a kind and without an end",
            {"intervals": [{**VECTORS[INTERVALS]["intervals"][0], "end": None}]},
            (
                "intervals[0]",
                (
                    "the entry has a kind without an end, an end without a kind, or a "
                    "kind that does not complete a call"
                ),
            ),
        ),
        (
            "raises at an interval with a kind that does not complete a call",
            {"intervals": [{**VECTORS[INTERVALS]["intervals"][0], "kind": "widget"}]},
            (
                "intervals[0]",
                (
                    "the entry has a kind without an end, an end without a kind, or a "
                    "kind that does not complete a call"
                ),
            ),
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in seams], ids=[t[0] for t in seams]
    )
    def test_raises_for_a_seam_vector_that_the_run_contradicts(
        self, give: dict[str, Any], want: tuple[str, str]
    ) -> None:
        """The fault is at the member of the vector, and it can have a cause."""
        at, reason = fault_of("seam", give)
        assert (at, reason[: len(want[1])]) == want

    checks: ClassVar[list[tuple[str, dict[str, Any], tuple[str, str]]]] = [
        (
            "raises at the spec for a named spec that does not exist",
            vector(PASSING, spec="widget"),
            ("spec", '"widget" is not a named spec'),
        ),
        (
            "raises at the refused entry of a history",
            vector(PASSING, history=[READ, READ]),
            ("history[1]", "the seam refuses the entry"),
        ),
        (
            "raises for a vector that expects neither a pass nor a failure",
            vector(PASSING, expect="maybe"),
            ("expect", 'the vector expects "maybe", neither pass nor fail'),
        ),
        (
            "raises for a check that ends with another verdict",
            vector(FAILING, expect="pass"),
            ("expect", "the check ends as fail, want pass"),
        ),
        (
            "raises for a field that the record does not have",
            vector(FAILING, detail={"widget": 1}),
            ("detail.widget", "the record does not have the field, want 1"),
        ),
        (
            "raises for a field of another value",
            vector(FAILING, detail={"steps": 3}),
            ("detail.steps", "the field is 2, want 3"),
        ),
        (
            "raises for a passing vector without the steps of one partition",
            vector(PASSING, detail={"partitions": 2, "steps": 6}),
            (
                "detail",
                (
                    "the runner observes the steps of a pass over one partition in two "
                    "steps or more, and the vector has the partitions 2 and the steps 6"
                ),
            ),
        ),
        (
            "raises for a passing vector of fewer steps than the check takes",
            vector(PASSING, detail={"partitions": 1, "steps": 5}),
            ("detail.steps", "the check ends as fail within 5 steps, want pass"),
        ),
        (
            "raises for a passing vector of more steps than the check takes",
            vector(PASSING, detail={"partitions": 1, "steps": 7}),
            (
                "detail.steps",
                (
                    'the check within 6 steps ends as pass with {"outcome": null, '
                    '"partitions": null, "steps": null, "limit": null}, want '
                    '{"outcome": "undecided", "partitions": 1, "steps": 6, "limit": '
                    '"steps"}'
                ),
            ),
        ),
        (
            "raises at an option that is not an int of 1 or more",
            vector(PASSING, budget=0),
            ("budget", "the budget is 0, not an int of 1 or more"),
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in checks], ids=[t[0] for t in checks]
    )
    def test_raises_for_a_linearizable_vector_that_the_run_contradicts(
        self, give: dict[str, Any], want: tuple[str, str]
    ) -> None:
        """The fault is at the member of the vector."""
        assert fault_of("linearizable", give) == want

    def test_raises_for_an_isolation_vector_of_another_verdict(self) -> None:
        """The vector of a serializable history expects a failure."""
        vector_id = next(i for i in VECTORS if i.startswith("serializable/"))
        expected = VECTORS[vector_id]["expect"]
        other = "fail" if expected == "pass" else "pass"
        at, reason = fault_of("serializable", vector(vector_id, expect=other))
        assert (at, reason.startswith(f"the check ends as {expected}")) == (
            "expect",
            True,
        )
