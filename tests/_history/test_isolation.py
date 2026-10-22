# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _history/isolation.py tests the checks of the isolation levels.

Each verdict and each record of the spec matches the result of the reference
implementation of the definition on the same history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._history.derivation import Edge
from dokimi_assert._history.history import History
from dokimi_assert._history.isolation import (
    SERIALIZABLE,
    SNAPSHOT_ISOLATION,
    IsolationDetail,
    Level,
    check_isolation,
    evidence_json,
    has_snapshot_isolation,
    is_serializable,
    isolation_json,
)
from dokimi_assert._history.transaction import TransactionError
from dokimi_assert._record.literal import detail as literal_of
from dokimi_assert.seat import Collector, Recorder, Seat, Standard
from helpers import (
    append,
    invoke_txn,
    read_of,
    read_skew,
    records,
    refusal,
    run_txn,
    write_skew,
)

if TYPE_CHECKING:
    from collections.abc import Callable

#: The two isolation levels.
LEVELS: tuple[Level, ...] = (SERIALIZABLE, SNAPSHOT_ISOLATION)

#: The assertion of each level.
ASSERTIONS: dict[Level, Callable[[Seat, History, str], None]] = {
    SERIALIZABLE: is_serializable,
    SNAPSHOT_ISOLATION: has_snapshot_isolation,
}


def outcome(history: History, level: Level) -> tuple[str, tuple[str, ...]] | None:
    """Return the anomaly and the kinds of a check of history at level."""
    detail = check_isolation(history.events(), level)
    return None if detail is None else (detail.anomaly, detail.kinds)


def json_of(history: History, level: Level) -> dict[str, Any]:
    """Return the JSON of the detail of a failing check of history at level."""
    return isolation_json(
        cast("IsolationDetail", check_isolation(history.events(), level))
    )


def without_transactions() -> History:
    """Return a history whose one call is a write and not a transaction."""
    history = History()
    history.invoke(0, "write", [1], "x").ok(None)
    return history


class TestSerializable:
    """SERIALIZABLE is the id of the assertion of serializability."""

    def test_is_the_id_of_the_assertion_of_serializability(
        self, seat: Collector
    ) -> None:
        """The value is the string serializable."""
        check.equal(
            seat,
            SERIALIZABLE,
            "serializable",
            "SERIALIZABLE is the string serializable",
        )


class TestSnapshotIsolation:
    """SNAPSHOT_ISOLATION is the id of the assertion of snapshot isolation."""

    def test_is_the_id_of_the_assertion_of_snapshot_isolation(
        self, seat: Collector
    ) -> None:
        """The value is the string snapshot-isolation."""
        check.equal(
            seat,
            SNAPSHOT_ISOLATION,
            "snapshot-isolation",
            "SNAPSHOT_ISOLATION is the string snapshot-isolation",
        )


class TestIsolationDetail:
    """IsolationDetail is the detail of the record of a failing isolation check."""

    def test_keeps_the_five_fields_of_the_definition(self, seat: Collector) -> None:
        """A detail of G2 keeps each field as the caller gave it."""
        detail = IsolationDetail("G2", ("G2",), (), None, ())
        check.equal(
            seat,
            [
                detail.anomaly,
                detail.kinds,
                detail.transactions,
                detail.cycle,
                detail.explanation,
            ],
            ["G2", ("G2",), (), None, ()],
            "the detail keeps its five fields",
        )


class TestCheckIsolation:
    """check_isolation checks the events of a history at an isolation level."""

    def test_passes_a_serial_history_at_both_levels(self, seat: Collector) -> None:
        """Each transaction reads the appends of the transactions before it."""
        history = History()
        run_txn(history, 0, append("x", 1))
        run_txn(history, 1, read_of("x", [1]), append("x", 2))
        run_txn(history, 0, read_of("x", [1, 2]))
        check.equal(
            seat,
            [check_isolation(history.events(), level) for level in LEVELS],
            [None, None],
            "neither level finds an anomaly",
        )

    def test_passes_an_empty_history(self, seat: Collector) -> None:
        """A history without events does not have an anomaly."""
        check.is_none(
            seat,
            check_isolation([], SERIALIZABLE),
            "the empty history does not have an anomaly",
        )

    def test_passes_one_value_appended_to_two_keys(self, seat: Collector) -> None:
        """The appends of 1 to x and of 1 to y are two appends."""
        history = History()
        run_txn(history, 0, append("x", 1), append("y", 1))
        run_txn(history, 0, read_of("x", [1]), read_of("y", [1]))
        check.equal(
            seat,
            [check_isolation(history.events(), level) for level in LEVELS],
            [None, None],
            "the two appends of 1 do not clash",
        )

    def test_lists_every_kind_of_a_second_read_that_differs_from_the_first(
        self, seat: Collector
    ) -> None:
        """The two reads of x return [] and then [1]."""
        history = History()
        reader = invoke_txn(history, 0, read_of("x", None), read_of("x", None))
        run_txn(history, 1, append("x", 1))
        reader.ok([read_of("x", []), read_of("x", [1])])
        check.equal(
            seat,
            outcome(history, SERIALIZABLE),
            ("internal-inconsistency", ("internal-inconsistency", "G-single", "G2")),
            "the check lists three kinds",
        )

    def test_lists_the_cycles_that_an_intermediate_read_closes(
        self, seat: Collector
    ) -> None:
        """Call 2 reads [1] after call 0 appended 1 and then 2."""
        history = History()
        run_txn(history, 0, append("x", 1), append("x", 2))
        run_txn(history, 1, read_of("x", [1]))
        check.equal(
            seat,
            outcome(history, SERIALIZABLE),
            ("intermediate-read", ("intermediate-read", "G-single", "G2")),
            "the check lists the intermediate read and two cycles",
        )

    def test_reports_a_duplicate_append_at_snapshot_isolation(
        self, seat: Collector
    ) -> None:
        """Call 2 reads [1, 1] after one append of 1."""
        history = History()
        run_txn(history, 0, append("x", 1))
        run_txn(history, 1, read_of("x", [1, 1]))
        check.equal(
            seat,
            outcome(history, SNAPSHOT_ISOLATION),
            ("duplicate-append", ("duplicate-append",)),
            "the check lists only the duplicate append",
        )

    def test_lists_g2_of_a_read_skew_only_at_serializability(
        self, seat: Collector
    ) -> None:
        """Snapshot isolation permits G2."""
        history = read_skew("ok", True)
        check.equal(
            seat,
            [outcome(history, level) for level in LEVELS],
            [("G-single", ("G-single", "G2")), ("G-single", ("G-single",))],
            "snapshot isolation permits G2",
        )

    def test_reports_g2_of_a_write_skew_at_serializability(
        self, seat: Collector
    ) -> None:
        """Each call reads the key that the other call appends to."""
        check.equal(
            seat,
            outcome(write_skew(), SERIALIZABLE),
            ("G2", ("G2",)),
            "the check reports G2 for two adjacent rw edges",
        )

    def test_passes_a_write_skew_at_snapshot_isolation(self, seat: Collector) -> None:
        """Snapshot isolation permits G2."""
        check.is_none(
            seat,
            outcome(write_skew(), SNAPSHOT_ISOLATION),
            "snapshot isolation permits G2",
        )

    def test_reports_a_long_fork_at_both_levels(self, seat: Collector) -> None:
        """Calls 2 and 3 each read one of the two appends and not the other."""
        history = History()
        calls = [
            invoke_txn(history, 0, append("x", 1)),
            invoke_txn(history, 1, append("y", 2)),
            invoke_txn(history, 2, read_of("x", None), read_of("y", None)),
            invoke_txn(history, 3, read_of("x", None), read_of("y", None)),
        ]
        calls[0].ok([append("x", 1)])
        calls[1].ok([append("y", 2)])
        calls[2].ok([read_of("x", [1]), read_of("y", [])])
        calls[3].ok([read_of("x", []), read_of("y", [2])])
        check.equal(
            seat,
            [outcome(history, level) for level in LEVELS],
            [
                ("G-nonadjacent", ("G-nonadjacent", "G2")),
                ("G-nonadjacent", ("G-nonadjacent",)),
            ],
            "both levels report G-nonadjacent",
        )

    def test_lists_the_transactions_of_an_aborted_read_with_their_kinds(
        self, seat: Collector
    ) -> None:
        """Call 2 reads the value that the aborted call 0 appended."""
        history = History()
        invoke_txn(history, 0, append("x", 1)).fail("aborted")
        run_txn(history, 1, read_of("x", [1]))
        detail = cast(
            "IsolationDetail", check_isolation(history.events(), SNAPSHOT_ISOLATION)
        )
        check.equal(
            seat,
            [(txn.call, txn.kind) for txn in detail.transactions],
            [(2, "ok"), (0, "fail")],
            "the record lists the reader before the appender",
        )

    def test_raises_a_transaction_error_for_a_history_whose_calls_are_not_transactions(
        self, seat: Collector
    ) -> None:
        """The one call of the history is a write."""
        history = without_transactions()
        check.equal(
            seat,
            refusal(
                seat,
                lambda: check_isolation(history.events(), SERIALIZABLE),
                TransactionError,
            ),
            'call 0 is "write", not "txn"',
            "the text of the error has the operation of call 0",
        )


class TestIsolationJson:
    """isolation_json returns the detail of a failing isolation check as JSON."""

    def test_returns_every_field_of_a_read_skew(self, seat: Collector) -> None:
        """Call 0 reads the append of call 1 to y and misses its append to x."""
        check.equal(
            seat,
            json_of(read_skew("ok", True), SERIALIZABLE),
            {
                "anomaly": "G-single",
                "kinds": ["G-single", "G2"],
                "transactions": [
                    {
                        "call": 0,
                        "completion": 3,
                        "kind": "ok",
                        "process": 0,
                        "args": [
                            literal_of(read_of("x", None)),
                            literal_of(read_of("y", None)),
                        ],
                        "output": literal_of([read_of("x", []), read_of("y", [2])]),
                    },
                    {
                        "call": 1,
                        "completion": 2,
                        "kind": "ok",
                        "process": 1,
                        "args": [
                            literal_of(append("x", 1)),
                            literal_of(append("y", 2)),
                        ],
                        "output": literal_of([append("x", 1), append("y", 2)]),
                    },
                ],
                "cycle": [
                    {"call": 0, "relations": ["rw"]},
                    {"call": 1, "relations": ["wr"]},
                ],
                "explanation": [
                    {
                        "from": 0,
                        "to": 1,
                        "relation": "rw",
                        "key": literal_of("x"),
                        "value": None,
                        "next": literal_of(1),
                    },
                    {
                        "from": 1,
                        "to": 0,
                        "relation": "wr",
                        "key": literal_of("y"),
                        "value": literal_of(2),
                    },
                ],
            },
            "the JSON has every field of the read skew",
        )

    def test_returns_the_explanation_of_a_garbage_read(self, seat: Collector) -> None:
        """No call appended the 9 that call 0 reads."""
        history = History()
        run_txn(history, 0, read_of("x", [9]))
        record = json_of(history, SERIALIZABLE)
        check.equal(
            seat,
            [record["cycle"], record["explanation"]],
            [
                None,
                [
                    {
                        "call": 0,
                        "key": literal_of("x"),
                        "read": literal_of([9]),
                        "value": literal_of(9),
                    }
                ],
            ],
            "the explanation has the read of 9",
        )

    def test_returns_the_explanation_of_an_internal_inconsistency_without_a_future(
        self, seat: Collector
    ) -> None:
        """Call 2 appends 2 to x and then reads [1]."""
        history = History()
        run_txn(history, 0, append("x", 1))
        run_txn(history, 1, append("x", 2), read_of("x", [1]))
        check.equal(
            seat,
            json_of(history, SERIALIZABLE)["explanation"],
            [
                {
                    "call": 2,
                    "key": literal_of("x"),
                    "read": literal_of([1]),
                    "expected": literal_of([2]),
                    "whole": False,
                    "future": None,
                }
            ],
            "the explanation expects a list that ends with 2",
        )

    def test_returns_the_explanation_of_an_internal_inconsistency_with_a_future(
        self, seat: Collector
    ) -> None:
        """Call 0 reads [1] and then appends 1."""
        history = History()
        run_txn(history, 0, read_of("x", [1]), append("x", 1))
        check.equal(
            seat,
            json_of(history, SNAPSHOT_ISOLATION)["explanation"],
            [
                {
                    "call": 0,
                    "key": literal_of("x"),
                    "read": literal_of([1]),
                    "expected": literal_of([]),
                    "whole": False,
                    "future": literal_of(1),
                }
            ],
            "the explanation has the later append of 1",
        )

    def test_returns_the_explanation_of_an_incompatible_order(
        self, seat: Collector
    ) -> None:
        """Calls 6 and 8 read [1, 2] and [1, 3]."""
        history = History()
        for value in (1, 2, 3):
            run_txn(history, value, append("x", value))
        run_txn(history, 0, read_of("x", [1, 2]))
        run_txn(history, 0, read_of("x", [1, 3]))
        check.equal(
            seat,
            json_of(history, SERIALIZABLE)["explanation"],
            [
                {
                    "calls": [6, 8],
                    "key": literal_of("x"),
                    "reads": [literal_of([1, 2]), literal_of([1, 3])],
                }
            ],
            "the explanation has both reads",
        )

    def test_returns_the_explanation_of_an_aborted_read(self, seat: Collector) -> None:
        """Call 2 reads the 1 that the aborted call 0 appended."""
        history = History()
        invoke_txn(history, 0, append("x", 1)).fail("aborted")
        run_txn(history, 1, read_of("x", [1]))
        check.equal(
            seat,
            json_of(history, SNAPSHOT_ISOLATION)["explanation"],
            [
                {
                    "call": 2,
                    "key": literal_of("x"),
                    "value": literal_of(1),
                    "appender": 0,
                }
            ],
            "the explanation has the read and its appender",
        )

    def test_returns_the_explanation_of_an_intermediate_read(
        self, seat: Collector
    ) -> None:
        """Call 2 reads [1] after call 0 appended 1 and then 2."""
        history = History()
        run_txn(history, 0, append("x", 1), append("x", 2))
        run_txn(history, 1, read_of("x", [1]))
        check.equal(
            seat,
            json_of(history, SERIALIZABLE)["explanation"],
            [
                {
                    "call": 2,
                    "key": literal_of("x"),
                    "value": literal_of(1),
                    "appender": 0,
                    "next": literal_of(2),
                }
            ],
            "the explanation has the value that follows 1",
        )


class TestEvidenceJson:
    """evidence_json returns the JSON of one entry of an explanation."""

    tests: ClassVar[list[tuple[str, Edge, dict[str, Any]]]] = [
        (
            "a ww edge with both values",
            Edge(0, 1, "ww", "x", 1, False, 2),
            {
                "from": 0,
                "to": 1,
                "relation": "ww",
                "key": literal_of("x"),
                "value": literal_of(1),
                "next": literal_of(2),
            },
        ),
        (
            "a wr edge without a next value",
            Edge(1, 0, "wr", "y", 2, False, None),
            {
                "from": 1,
                "to": 0,
                "relation": "wr",
                "key": literal_of("y"),
                "value": literal_of(2),
            },
        ),
        (
            "an rw edge of an empty read without a value",
            Edge(0, 1, "rw", "x", None, True, 1),
            {
                "from": 0,
                "to": 1,
                "relation": "rw",
                "key": literal_of("x"),
                "value": None,
                "next": literal_of(1),
            },
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_json_of(
        self, seat: Collector, give: Edge, want: dict[str, Any]
    ) -> None:
        """The JSON has the fields of the relation of the edge."""
        check.equal(seat, evidence_json(give), want, "the JSON of the edge")


class _Assertion:
    """The cases of an isolation assertion. Each subclass runs them at its level."""

    level: ClassVar[Level]
    op: ClassVar[str]

    def test_records_a_pass_for_a_serial_history(self, seat: Collector) -> None:
        """Call 1 reads the append of call 0."""
        history = History()
        run_txn(history, 0, append("x", 1))
        run_txn(history, 1, read_of("x", [1]))
        recorder = Recorder()
        ASSERTIONS[self.level](recorder, history, "the store is isolated")
        check.equal(
            seat,
            [recorder.failures, records(recorder)[0]["verdict"]],
            [[], "pass"],
            "the assertion records a pass",
        )

    def test_fails_with_one_record_of_the_assertion_at_its_call(
        self, seat: Collector
    ) -> None:
        """A read skew fails both levels."""
        history = read_skew("ok", True)
        recorder = Recorder()
        ASSERTIONS[self.level](recorder, history, "the store is isolated")
        failure = recorder.failures[0]
        check.equal(
            seat,
            [
                failure.assertion,
                failure.contract,
                list(failure.detail),
                records(recorder)[0]["detail"],
            ],
            [
                self.level,
                "the store is isolated",
                ["anomaly", "kinds", "transactions", "cycle", "explanation"],
                json_of(history, self.level),
            ],
            "the failure and its call record have the five fields",
        )
        where = failure.where
        check.has_suffix(
            seat,
            None if where is None else where.file,
            "test_isolation.py",
            "the failure is at the call in this file",
        )

    def test_raises_the_text_of_the_record_on_a_seat_that_stops(
        self, seat: Collector
    ) -> None:
        """A Standard seat raises AssertionError for each failure."""
        error = check.raises(
            seat,
            lambda: ASSERTIONS[self.level](
                Standard(), read_skew("ok", True), "the store is isolated"
            ),
            "the check stops the test",
        )
        check.has_prefix(
            seat,
            str(error),
            "the store is isolated: ",
            "the text starts with the contract",
        )

    def test_ends_the_call_with_a_fault_for_a_history_that_is_not_a_history(
        self, seat: Collector
    ) -> None:
        """An empty list is not a History."""
        recorder = Recorder()
        not_a_history: Any = []
        ASSERTIONS[self.level](recorder, not_a_history, "c")
        check.equal(
            seat,
            recorder.message,
            f"{self.op}: the history is not a History",
            "the fault has the name of the assertion",
        )

    def test_ends_the_call_with_a_fault_for_a_history_whose_calls_are_not_transactions(
        self, seat: Collector
    ) -> None:
        """The one call of the history is a write."""
        recorder = Recorder()
        ASSERTIONS[self.level](recorder, without_transactions(), "c")
        check.equal(
            seat,
            recorder.message,
            f'{self.op}: call 0 is "write", not "txn"',
            "the fault has the operation of call 0",
        )


class TestIsSerializable(_Assertion):
    """is_serializable fails for an anomaly that serializability forbids."""

    level: ClassVar[Level] = SERIALIZABLE
    op: ClassVar[str] = "history.is_serializable"


class TestHasSnapshotIsolation(_Assertion):
    """has_snapshot_isolation fails for an anomaly that snapshot isolation forbids."""

    level: ClassVar[Level] = SNAPSHOT_ISOLATION
    op: ClassVar[str] = "history.has_snapshot_isolation"
