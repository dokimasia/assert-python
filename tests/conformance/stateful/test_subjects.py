# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of conformance/stateful/subjects.py tests the machine subjects."""

from __future__ import annotations

import json
from typing import Any, ClassVar

import pytest

from dokimi_assert import check, prop, stateful
from dokimi_assert.conformance.stateful.subjects import SUBJECTS, Setup
from dokimi_assert.seat import Collector, Recorder

#: The setup of the definition has two clients and the uniform strategy.
SETUP = Setup([], [stateful.clients(2)], stateful.uniform())


def run_of(name: str, setup: Setup = SETUP) -> dict[str, Any]:
    """Return the verdict and the failure of a run of the subject of a name."""
    subject = SUBJECTS[name]()
    recorder = Recorder()
    prop.for_all(
        recorder,
        "the subject runs",
        lambda c: subject(c, setup),
        prop.seed(1),
        prop.hermetic(),
        prop.store(""),
    )
    record = json.loads(recorder.records[0])
    failure = record.get("detail", {}).get("failure")
    return {
        "verdict": record["verdict"],
        "failure": None if failure is None else failure["assertion"],
    }


class TestSubjects:
    """SUBJECTS has the builder of each machine subject of the definition."""

    def test_contains_the_machine_subjects(self, seat: Collector) -> None:
        """The names are those of the definition."""
        check.equal(
            seat,
            sorted(SUBJECTS),
            [
                "correct-counter",
                "correct-queue",
                "counter-overflows",
                "counter-refuses-every-third",
                "queue-loses-on-wrap",
                "racy-counter",
                "store-loses-on-crash",
            ],
            "the table has the machine subjects",
        )

    tests: ClassVar[list[tuple[str, str, Setup, dict[str, Any]]]] = [
        (
            "builds a queue that loses a value on wrap",
            "queue-loses-on-wrap",
            SETUP,
            {"verdict": "fail", "failure": "linearizable"},
        ),
        (
            "builds a queue that keeps every value",
            "correct-queue",
            SETUP,
            {"verdict": "pass", "failure": None},
        ),
        (
            "builds a counter that overflows at 3",
            "counter-overflows",
            SETUP,
            {"verdict": "fail", "failure": "linearizable"},
        ),
        (
            "builds a store that loses a put on a crash",
            "store-loses-on-crash",
            SETUP,
            {"verdict": "fail", "failure": "lost-write"},
        ),
        (
            "builds a counter whose increment races on two clients",
            "racy-counter",
            SETUP,
            {"verdict": "fail", "failure": "linearizable"},
        ),
        (
            "builds a counter whose increment does not await",
            "correct-counter",
            SETUP,
            {"verdict": "pass", "failure": None},
        ),
        (
            "builds a counter whose refusals change the actions of a replay",
            "counter-refuses-every-third",
            Setup([stateful.swarm(False)], [], stateful.uniform()),
            {"verdict": "fail", "failure": None},
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "give_setup", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_builds_the_subject_of_a_name(
        self, seat: Collector, give: str, give_setup: Setup, want: dict[str, Any]
    ) -> None:
        """A faulty subject fails its property, and a correct one passes.

        The runs have the seed and the setup of the machines vectors of the
        definition.
        """
        check.equal(
            seat,
            run_of(give, give_setup),
            want,
            "the subject behaves as the definition describes it",
        )

    def test_builds_a_queue_whose_steps_take_the_setup(self, seat: Collector) -> None:
        """Two steps cannot fill the ring and read it."""
        setup = Setup([stateful.max_steps(2)], [], stateful.uniform())
        check.equal(
            seat,
            run_of("queue-loses-on-wrap", setup),
            {"verdict": "pass", "failure": None},
            "the queue passes in two steps",
        )
