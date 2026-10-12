"""The spec of history.py tests the names and the sentences of the history checks."""

from __future__ import annotations

from dokimi_assert import check, history
from dokimi_assert._history.sentence import isolation_sentence, sentence
from dokimi_assert.failure import Failure, render
from dokimi_assert.seat import Collector


class TestHistory:
    """The module history exports the checks and registers their sentences."""

    def test_exports_the_names_of_the_history_checks(self, seat: Collector) -> None:
        """Each of the 28 names in __all__ is an attribute of the module."""
        check.equal(
            seat,
            [
                sorted(history.__all__),
                [n for n in history.__all__ if not hasattr(history, n)],
            ],
            [
                [
                    "Call",
                    "Completion",
                    "Edge",
                    "Event",
                    "Evidence",
                    "History",
                    "Interval",
                    "IntervalError",
                    "Invocation",
                    "Kind",
                    "Link",
                    "Observation",
                    "Operation",
                    "Option",
                    "Outcome",
                    "Span",
                    "Spec",
                    "Transaction",
                    "budget",
                    "concurrently",
                    "from_intervals",
                    "has_snapshot_isolation",
                    "is_linearizable",
                    "is_serializable",
                    "memo_limit",
                    "spec_from",
                    "time_limit",
                    "workers",
                ],
                [],
            ],
            "the module exports the 28 names",
        )

    def test_registers_the_sentence_of_each_check_for_the_records_of_its_assertions(
        self, seat: Collector
    ) -> None:
        """The function render returns the registered sentence of each assertion."""
        linearizable = Failure(
            "linearizable",
            "c",
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
        isolated = [
            Failure(
                level,
                "c",
                {
                    "anomaly": "G2",
                    "kinds": ("G2",),
                    "transactions": (),
                    "cycle": (),
                    "explanation": (),
                },
            )
            for level in ("serializable", "snapshot-isolation")
        ]
        check.equal(
            seat,
            [render(linearizable), *(render(failure) for failure in isolated)],
            [sentence(linearizable), *(isolation_sentence(f) for f in isolated)],
            "render uses the sentence of each check",
        )
