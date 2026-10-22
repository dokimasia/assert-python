# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The history of the concurrent calls to one object, and the checks of a history.

A test records each call in a History. The test calls History.invoke before
each call to the subject starts. After the call returns, the test calls
Call.ok, Call.fail or Call.unknown. concurrently runs the clients at the same
time. is_linearizable checks the history against a Spec:

    class Register:
        def initial(self) -> int:
            return 0

        def next(self, state: int, op: history.Operation) -> list[int]:
            if op.name == "write":
                return [op.args[0]]
            return [state] if op.returned(state) else []

    def test_the_register_is_linearizable(seat):
        h = history.History()
        store = Store()

        def client(i: int) -> None:
            for n in range(50):
                write = h.invoke(i, "write", [i * 1000 + n], "x")
                store.write(i * 1000 + n)
                write.ok(None)
                read = h.invoke(i, "read", [], "x")
                read.ok(store.read())

        history.concurrently(2, 60, client)
        history.is_linearizable(seat, h, Register(), "the register is linearizable")

A history is linearizable when some order of its calls respects their
real-time order. The sequential specification of the object must also
accept that order. The definition fixes the recording order, the processes,
the partitions, the search, its budget and its record. One history has the
same verdict and the same record in every implementation of the definition.

spec_from builds a spec from a factory of the subject. A check against that
spec finds a call that was not atomic. is_serializable and
has_snapshot_isolation read each call of the operation txn as a transaction
of list appends and list reads.
"""

from __future__ import annotations

from dokimi_assert._history.concurrently import Outcome, concurrently
from dokimi_assert._history.derivation import Edge, Evidence, Link, Observation
from dokimi_assert._history.event import Completion, Event, Invocation, Kind
from dokimi_assert._history.history import Call, History
from dokimi_assert._history.interval import Interval, IntervalError, from_intervals
from dokimi_assert._history.isolation import (
    SERIALIZABLE,
    SNAPSHOT_ISOLATION,
    has_snapshot_isolation,
    is_serializable,
)
from dokimi_assert._history.linearizable import LINEARIZABLE, is_linearizable
from dokimi_assert._history.option import (
    Option,
    budget,
    memo_limit,
    time_limit,
    workers,
)
from dokimi_assert._history.partition import Span
from dokimi_assert._history.sentence import isolation_sentence, sentence
from dokimi_assert._history.spec import Operation, Spec, spec_from
from dokimi_assert._history.transaction import Transaction
from dokimi_assert.failure import register_sentence

__all__ = [
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
]

register_sentence(sentence, LINEARIZABLE)
register_sentence(isolation_sentence, SERIALIZABLE, SNAPSHOT_ISOLATION)
