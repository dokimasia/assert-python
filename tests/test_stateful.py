"""The spec of stateful.py tests the names and the sentence of the machines."""

from __future__ import annotations

import importlib

from dokimi_assert import check, stateful
from dokimi_assert._history.sentence import sentence
from dokimi_assert.failure import Failure, register_sentence, render
from dokimi_assert.seat import Collector


class TestStateful:
    """The module stateful exports the machines, the steps and the task scheduler."""

    def test_exports_the_names_of_the_machines_and_their_steps(
        self, seat: Collector
    ) -> None:
        """Each of the 15 names in __all__ is an attribute of the module."""
        check.equal(
            seat,
            [
                sorted(stateful.__all__),
                [n for n in stateful.__all__ if not hasattr(stateful, n)],
            ],
            [
                [
                    "Action",
                    "Machine",
                    "Option",
                    "Scheduler",
                    "Strategy",
                    "clients",
                    "concurrent",
                    "max_steps",
                    "mean",
                    "pct",
                    "repeat",
                    "steps",
                    "swarm",
                    "tasks",
                    "uniform",
                ],
                [],
            ],
            "the module exports the 15 names",
        )

    def test_registers_the_sentence_of_the_check_of_the_steps(
        self, seat: Collector
    ) -> None:
        """The import of stateful registers the sentence of linearizable."""
        register_sentence(lambda _: "another sentence", "linearizable")
        importlib.reload(stateful)
        failure = Failure(
            "linearizable",
            "the history of the steps of the machine is linearizable",
            {
                "outcome": "violated",
                "partitions": 1,
                "steps": 1,
                "partition": (),
                "calls": 0,
                "concurrency": 0,
                "linearized": (),
                "states": (),
                "candidates": (),
                "limit": None,
            },
        )
        check.equal(
            seat, render(failure), sentence(failure), "render uses the sentence"
        )
