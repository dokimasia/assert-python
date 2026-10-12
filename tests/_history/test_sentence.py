"""The spec of _history/sentence.py tests the sentences of the history records."""

from __future__ import annotations

from typing import ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._history.derivation import Anomaly, Edge, Evidence, Observation
from dokimi_assert._history.history import History
from dokimi_assert._history.linearizable import check as checked
from dokimi_assert._history.linearizable import fields_of
from dokimi_assert._history.option import budget
from dokimi_assert._history.sentence import isolation_sentence, sentence
from dokimi_assert.failure import Failure
from dokimi_assert.seat import Collector
from helpers import REGISTER


def record_of(history: History, *budgets: int) -> Failure:
    """Return the record of the check of history against the register under budgets."""
    detail = checked(history, REGISTER, [budget(steps) for steps in budgets])
    return Failure("linearizable", "c", fields_of(detail))


def isolated(anomaly: Anomaly, explanation: tuple[Evidence, ...]) -> Failure:
    """Return the record of an isolation check of anomaly with explanation."""
    return Failure(
        "serializable",
        "c",
        {
            "anomaly": anomaly,
            "kinds": (anomaly, "G2"),
            "transactions": (),
            "cycle": None,
            "explanation": explanation,
        },
    )


class TestSentence:
    """sentence renders the record of a failing check of linearizability."""

    def test_returns_the_frontier_of_a_violated_partition(
        self, seat: Collector
    ) -> None:
        """A read of None follows a write of 1, so the spec rejects the read."""
        history = History()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(1, "read", [], "x").ok(None)
        check.equal(
            seat,
            sentence(record_of(history)),
            "\n".join(
                [
                    "c: violated in the partition of 'x'",
                    "    steps 2, partitions 1, calls 2, concurrency 1",
                    "    linearized: call 0 write(1) -> None",
                    "    states: 1",
                    "    rejected: call 2 read() -> None",
                ]
            ),
            "the sentence lists the frontier of the partition of x",
        )

    def test_returns_the_limit_of_an_undecided_partition_of_every_key(
        self, seat: Collector
    ) -> None:
        """A budget of one step stops the check before the read."""
        history = History()
        history.invoke(0, "write", [1]).ok(None)
        history.invoke(1, "read", []).ok(1)
        check.equal(
            seat,
            sentence(record_of(history, 1)),
            "\n".join(
                [
                    "c: undecided in the partition of every key, at the steps limit",
                    "    steps 1, partitions 1, calls 2, concurrency 1",
                    "    linearized: call 0 write(1) -> None",
                    "    states: 1",
                    "    rejected: none",
                ]
            ),
            "the first line of the sentence ends with the steps limit",
        )

    def test_returns_outcome_unknown_in_place_of_a_missing_output(
        self, seat: Collector
    ) -> None:
        """The write of 1 has an unknown outcome. The read returns 9."""
        history = History()
        history.invoke(0, "write", [1]).unknown("lost")
        history.invoke(1, "read", []).ok(9)
        check.equal(
            seat,
            sentence(record_of(history)),
            "\n".join(
                [
                    "c: violated in the partition of every key",
                    "    steps 3, partitions 1, calls 2, concurrency 2",
                    "    linearized: call 0 write(1), outcome unknown",
                    "    states: 1",
                    "    rejected: call 2 read() -> 9",
                ]
            ),
            "the write has the text outcome unknown",
        )


class TestIsolationSentence:
    """isolation_sentence renders the record of a failing isolation check."""

    def test_returns_a_line_for_each_edge_of_a_cycle(self, seat: Collector) -> None:
        """The cycle has one edge of each relation and a second rw edge."""
        record = isolated(
            "G0",
            (
                Edge(0, 1, "ww", "x", 1, False, 2),
                Edge(1, 2, "wr", "y", 3, False, None),
                Edge(2, 3, "rw", "z", None, True, 4),
                Edge(3, 0, "rw", "z", 5, False, 6),
            ),
        )
        check.equal(
            seat,
            isolation_sentence(record),
            "\n".join(
                [
                    "c: G0",
                    "    kinds: G0, G2",
                    "    call 0 -ww-> call 1: call 1 appended 2 to 'x' after 1",
                    "    call 1 -wr-> call 2: call 2 read 'y' ending in 3",
                    "    call 2 -rw-> call 3: call 2 read [] from 'z', and call 3 "
                    "appended 4 to it",
                    "    call 3 -rw-> call 0: call 3 read 'z' ending in 5, and call 0 "
                    "appended 6 after it",
                ]
            ),
            "each edge has a line of its own",
        )

    tests: ClassVar[list[tuple[str, Observation, str]]] = [
        (
            "a garbage read",
            Observation("garbage-read", calls=(0,), key="x", reads=([9],), value=9),
            "call 0 read [9] from 'x', and no transaction appended 9",
        ),
        (
            "a duplicate append",
            Observation(
                "duplicate-append", calls=(0,), key="x", reads=([1, 1],), value=1
            ),
            "call 0 read [1, 1] from 'x', and the list contains 1 twice",
        ),
        (
            "a read that contradicts the whole list",
            Observation(
                "internal-inconsistency", calls=(0,), key="x", reads=([1],), whole=True
            ),
            "call 0 read [1] from 'x', and its earlier micro-operations require the "
            "list []",
        ),
        (
            "a read that contradicts the end of the list",
            Observation(
                "internal-inconsistency",
                calls=(0,),
                key="x",
                reads=([1],),
                expected=(2,),
            ),
            "call 0 read [1] from 'x', and its earlier appends require a list that "
            "ends with [2]",
        ),
        (
            "a read of a later append",
            Observation(
                "internal-inconsistency",
                calls=(0,),
                key="x",
                reads=([1],),
                future=1,
                has_future=True,
            ),
            "call 0 read [1] from 'x', and 1 is a value that call 0 appends later",
        ),
        (
            "an incompatible order",
            Observation(
                "incompatible-order", calls=(6, 8), key="x", reads=([1, 2], [1, 3])
            ),
            "calls 6 and 8 read [1, 2] and [1, 3] from 'x', and neither is a prefix "
            "of the other",
        ),
        (
            "an aborted read",
            Observation("aborted-read", calls=(2,), key="x", value=1, appender=0),
            "call 2 read 1 from 'x', and call 0 appended 1 and aborted",
        ),
        (
            "an intermediate read",
            Observation(
                "intermediate-read",
                calls=(2,),
                key="x",
                value=1,
                appender=0,
                following=2,
            ),
            "call 2 read 'x' ending in 1, and call 0 appended 1 and then 2",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_text_of(
        self, seat: Collector, give: Observation, want: str
    ) -> None:
        """The sentence has the anomaly, the kinds and the text of the observation."""
        check.equal(
            seat,
            isolation_sentence(isolated(give.anomaly, (give,))),
            f"c: {give.anomaly}\n    kinds: {give.anomaly}, G2\n    {want}",
            "the observation is on the third line",
        )
