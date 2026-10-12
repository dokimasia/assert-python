"""The checks that the transactions of a history do not have a forbidden anomaly.

A check first reads the micro-operations for the six anomalies that do not
need a dependency graph. It then derives the write-write, write-read and
read-write dependencies between committed transactions and searches the
graph for the five kinds of cycle. An isolation level forbids a set of the
eleven kinds. The record reports the first forbidden kind that the history
has.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from dokimi_assert._history.derivation import (
    ANOMALIES,
    Analysis,
    Anomaly,
    Edge,
    Evidence,
    Instance,
    Link,
    Observation,
)
from dokimi_assert._history.event import Event
from dokimi_assert._history.history import History
from dokimi_assert._history.transaction import (
    Transaction,
    TransactionError,
    transaction_json,
    transactions,
)
from dokimi_assert._matcher.fault import of_operation
from dokimi_assert._matcher.seat import Mode, Seat
from dokimi_assert._matcher.verdict import Running
from dokimi_assert._record.literal import detail as literal_of
from dokimi_assert.failure import Failure, call_site

__all__ = [
    "SERIALIZABLE",
    "SNAPSHOT_ISOLATION",
    "IsolationDetail",
    "Level",
    "check_isolation",
    "evidence_json",
    "has_snapshot_isolation",
    "is_serializable",
    "isolation_json",
]

#: The id of the assertion of serializability.
SERIALIZABLE: Final = "serializable"

#: The id of the assertion of snapshot isolation.
SNAPSHOT_ISOLATION: Final = "snapshot-isolation"

#: An isolation level. The assertion with the same id checks the level.
Level = Literal["serializable", "snapshot-isolation"]

#: The kinds that each level forbids. Snapshot isolation permits a cycle with
#: two adjacent read-write dependencies. A write skew is such a cycle.
_FORBIDS: dict[Level, tuple[Anomaly, ...]] = {
    "serializable": ANOMALIES,
    "snapshot-isolation": tuple(kind for kind in ANOMALIES if kind != "G2"),
}


@dataclass(frozen=True, slots=True)
class IsolationDetail:
    """The detail of the record of a failing isolation check.

    The detail has the five fields of the definition.

    Attributes:
        anomaly: The first kind that the level forbids and the history has.
        kinds: Every kind that the level forbids and the history has. The
            kinds are in the order of the report.
        transactions: The transactions that the anomaly involves.
        cycle: The cycle of a cycle anomaly. It is None for any other anomaly.
        explanation: The evidence of the anomaly. It has an edge for each link
            of a cycle, or one observation for any other anomaly.
    """

    anomaly: Anomaly
    kinds: tuple[Anomaly, ...]
    transactions: tuple[Transaction, ...]
    cycle: tuple[Link, ...] | None
    explanation: tuple[Evidence, ...]


def check_isolation(events: Sequence[Event], level: Level) -> IsolationDetail | None:
    """Check the events of a history at an isolation level.

    Args:
        events: The events of the history.
        level: The isolation level.

    Returns:
        The detail, or None when the history does not have an anomaly that
        the level forbids.

    Raises:
        TransactionError: The history is not a history of list-append
            transactions.
    """
    txns = transactions(events)
    analysis = Analysis(txns)
    found: list[tuple[Anomaly, Instance]] = []
    for kind in _FORBIDS[level]:
        instance = analysis.instance(kind)
        if instance is not None:
            found.append((kind, instance))
    if not found:
        return None
    first = found[0][1]
    by_call = {txn.call: txn for txn in txns}
    return IsolationDetail(
        first.anomaly,
        tuple(kind for kind, _ in found),
        tuple(by_call[call] for call in first.calls),
        first.cycle,
        first.explanation,
    )


def _edge_json(edge: Edge) -> dict[str, Any]:
    """Return the JSON of an edge of a cycle in an explanation."""
    stated: dict[str, Any] = {
        "from": edge.source,
        "to": edge.target,
        "relation": edge.relation,
        "key": literal_of(edge.key),
        "value": None if edge.empty else literal_of(edge.value),
    }
    if edge.relation != "wr":
        stated["next"] = literal_of(edge.following)
    return stated


def _observation_json(o: Observation) -> dict[str, Any]:
    """Return the JSON of an observation in an explanation.

    Each anomaly has its own fields.
    """
    key = literal_of(o.key)
    if o.anomaly == "internal-inconsistency":
        return {
            "call": o.calls[0],
            "key": key,
            "read": literal_of(o.reads[0]),
            "expected": literal_of(list(o.expected)),
            "whole": o.whole,
            "future": literal_of(o.future) if o.has_future else None,
        }
    if o.anomaly == "incompatible-order":
        return {
            "calls": list(o.calls),
            "key": key,
            "reads": [literal_of(read) for read in o.reads],
        }
    if o.anomaly == "aborted-read":
        return {
            "call": o.calls[0],
            "key": key,
            "value": literal_of(o.value),
            "appender": o.appender,
        }
    if o.anomaly == "intermediate-read":
        return {
            "call": o.calls[0],
            "key": key,
            "value": literal_of(o.value),
            "appender": o.appender,
            "next": literal_of(o.following),
        }
    return {
        "call": o.calls[0],
        "key": key,
        "read": literal_of(o.reads[0]),
        "value": literal_of(o.value),
    }


def evidence_json(evidence: Evidence) -> dict[str, Any]:
    """Return the JSON of one entry of an explanation.

    Args:
        evidence: The entry.

    Returns:
        The JSON value.
    """
    if isinstance(evidence, Edge):
        return _edge_json(evidence)
    return _observation_json(evidence)


def isolation_json(detail: IsolationDetail) -> dict[str, Any]:
    """Return the JSON of the detail of a failing isolation check.

    The call record of the check contains the JSON. Each kind is a string.
    Each transaction has the JSON form of the history. The cycle is None for
    an anomaly that is not a cycle. The values of each entry of the
    explanation are typed literals.

    Args:
        detail: The detail.

    Returns:
        The JSON value.
    """
    return {
        "anomaly": detail.anomaly,
        "kinds": list(detail.kinds),
        "transactions": [transaction_json(txn) for txn in detail.transactions],
        "cycle": None
        if detail.cycle is None
        else [
            {"call": link.call, "relations": list(link.relations)}
            for link in detail.cycle
        ],
        "explanation": [evidence_json(entry) for entry in detail.explanation],
    }


def _fields_of(detail: IsolationDetail) -> dict[str, Any]:
    """Return the detail fields of the record of a failing isolation check."""
    return {
        "anomaly": detail.anomaly,
        "kinds": detail.kinds,
        "transactions": detail.transactions,
        "cycle": detail.cycle,
        "explanation": detail.explanation,
    }


def _isolated(seat: Seat, history: object, msg: str, level: Level, op: str) -> None:
    """Check history at level, and report the verdict of the assertion of level."""
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat)
    if not isinstance(history, History):
        error = of_operation(op, "the history is not a History")
        run.faulted(Mode.FATAL, level, msg, error)
        return
    try:
        detail = check_isolation(history.events(), level)
    except TransactionError as error:
        run.faulted(Mode.FATAL, level, msg, of_operation(op, error))
        return
    if detail is None:
        run.passed(Mode.FATAL, level, msg)
        return
    failure = Failure(level, msg, _fields_of(detail), call_site())
    run.failed_run(Mode.FATAL, failure, isolation_json(detail))


def is_serializable(seat: Seat, history: History, msg: str) -> None:
    """Fail when history has an anomaly that serializability forbids.

    Serializability forbids every kind of anomaly. The check derives the
    dependencies between the transactions from their reads and searches them
    for anomalies. The failure is one record of the assertion serializable.

    A transaction is a call of the operation "txn" whose arguments are its
    micro-operations. An append is ["append", key, value]. A read is
    ["read", key, None]. An ok completion commits the transaction. Its output
    repeats the micro-operations. Each read in the output has the list that
    it returned, or None for the empty list. A fail completion aborts the
    transaction. A transaction whose outcome is unknown is committed when a
    committed read observed one of its appends. The same rule applies to a
    pending transaction. A value can be appended to its key only once. Keys
    and values compare by their typed literals.

    The detail of the record has the five fields of the definition. They are
    anomaly, kinds, transactions, cycle and explanation. The call ends with a
    fault for a history that is not a History, and for a history whose calls
    are not list-append transactions.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        history: The history.
        msg: The contract under test.

    Example:
        history.is_serializable(seat, h, "the store is serializable")
    """
    __tracebackhide__ = True
    _isolated(seat, history, msg, SERIALIZABLE, "history.is_serializable")


def has_snapshot_isolation(seat: Seat, history: History, msg: str) -> None:
    """Fail when history has an anomaly that snapshot isolation forbids.

    Snapshot isolation forbids every kind of anomaly but G2. It permits a
    cycle with two adjacent read-write dependencies. A write skew is such a
    cycle. The failure is one record of the assertion snapshot-isolation. The
    workload, the derivation, the record and the faults are those of
    is_serializable.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        history: The history.
        msg: The contract under test.

    Example:
        history.has_snapshot_isolation(seat, h, "the store has snapshot isolation")
    """
    __tracebackhide__ = True
    _isolated(seat, history, msg, SNAPSHOT_ISOLATION, "history.has_snapshot_isolation")
