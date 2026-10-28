# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The derivation over the transactions of one history.

The derivation finds the committed transactions, the version order of each
key, the dependencies between committed transactions, and the first
instance of each anomaly.

The ok transactions are committed. A transaction whose outcome is unknown is
committed when a committed read observed one of its appends or writes. The
same rule applies to a pending transaction. The version order of a key is
its longest committed read. A key whose committed
reads are not prefixes of one list does not have a version order. Every
committed read is a prefix of the final list of its key, so a committed
append that no committed read observed follows the last value of the
version order.

In a register history, the initial value precedes each installed value, and
a transaction's first read of a register before its write precedes the value
that its last write installs. The dependencies follow from those pairs.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, TypeVar, cast

from dokimi_assert._history.cycle import (
    RELATIONS,
    Graph,
    Relation,
    components,
    path,
    simple,
)
from dokimi_assert._history.history import identity_of
from dokimi_assert._history.transaction import APPEND, READ, WRITE, Transaction

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Sequence
    from collections.abc import Set as AbstractSet

__all__ = [
    "ANOMALIES",
    "Analysis",
    "Anomaly",
    "Edge",
    "Evidence",
    "Instance",
    "Link",
    "Observation",
]

_K = TypeVar("_K")
_V = TypeVar("_V")

#: A kind of anomaly.
Anomaly = Literal[
    "garbage-read",
    "duplicate-append",
    "internal-inconsistency",
    "incompatible-order",
    "aborted-read",
    "intermediate-read",
    "G0",
    "G1c",
    "G-single",
    "G-nonadjacent",
    "G2",
]

#: The kinds of anomaly, in the order in which a record reports them.
ANOMALIES: tuple[Anomaly, ...] = (
    "garbage-read",
    "duplicate-append",
    "internal-inconsistency",
    "incompatible-order",
    "aborted-read",
    "intermediate-read",
    "G0",
    "G1c",
    "G-single",
    "G-nonadjacent",
    "G2",
)


@dataclass(frozen=True, slots=True)
class Edge:
    """The evidence of one dependency of a cycle.

    The edge joins two transactions by a relation. The meaning of value
    depends on the relation:

    - ww: a value of source in the version order of the key.
    - wr: the last value of the list that target read.
    - rw: the last value of the list that source read.

    For ww and rw, following is the value of target after value in the
    version order.

    Attributes:
        source: The call of the transaction that the dependency is on.
        target: The call of the transaction that depends on it.
        relation: The dependency of target on source.
        key: The key whose list proves the dependency.
        value: The value of source, or the last value of a read.
        empty: True for an rw edge whose source read the empty list, or the
            initial value of a register. Such an edge does not have a value.
        following: The value of target after value. Only ww and rw edges
            have it.
        register: True for an edge of a register history. Its value is the
            value that source installed for ww, and the value that the
            reading transaction read for wr and rw.
    """

    source: int
    target: int
    relation: Relation
    key: Any
    value: Any
    empty: bool
    following: Any
    register: bool = False


@dataclass(frozen=True, slots=True)
class Observation:
    """The evidence of an anomaly that is not a cycle.

    The evidence has the reads and the appends that show the anomaly. Each
    anomaly uses these fields:

    - garbage-read and duplicate-append: calls, key, reads and value.
    - internal-inconsistency: calls, key, reads, expected, whole, future and
      has_future.
    - incompatible-order: calls, key and reads, for two reads.
    - aborted-read: calls, key, value and appender.
    - intermediate-read: calls, key, value, appender and following.

    Attributes:
        anomaly: The anomaly that the observation shows.
        calls: The calls of the transactions that read.
        key: The key that they read.
        reads: The lists that they read, in the order of calls.
        value: The value at fault.
        appender: The call that appended value.
        following: The value that appender appended to key after value.
        expected: The list that the earlier micro-operations of the
            transaction require. It is the end of the list when whole is
            False.
        whole: True when expected is the whole list.
        future: The first value of the read that the transaction appends to
            key after the read.
        has_future: True when the read has such a value.
        register: True for an observation of a register history. Its read
            is read and not reads, and an internal inconsistency states known
            and not expected. appender wrote value.
        read: The value that a register read returned, None for the initial
            value.
        known: The value of the register that the transaction knew before
            the read, None when it knew none or knew the initial value.
    """

    anomaly: Anomaly
    calls: tuple[int, ...] = ()
    key: Any = None
    reads: tuple[list[Any], ...] = ()
    value: Any = None
    appender: int | None = None
    following: Any = None
    expected: tuple[Any, ...] = ()
    whole: bool = False
    future: Any = None
    has_future: bool = False
    register: bool = False
    read: Any = None
    known: Any = None


#: One entry of the explanation of an anomaly.
Evidence = Edge | Observation


@dataclass(frozen=True, slots=True)
class Link:
    """One transaction of a cycle, and the relations of its edge to the next one.

    Attributes:
        call: The call of the transaction.
        relations: The relations of the edge to the next transaction. They
            are in the order ww, wr, rw.
    """

    call: int
    relations: tuple[Relation, ...]


@dataclass(frozen=True, slots=True)
class Instance:
    """One instance of an anomaly.

    Attributes:
        anomaly: The anomaly.
        calls: The calls of the transactions that it involves. The record
            lists them in this order.
        cycle: The cycle. It is None for an anomaly that is not a cycle.
        explanation: The evidence. It has an edge for each link of a cycle,
            or one observation.
    """

    anomaly: Anomaly
    calls: tuple[int, ...]
    cycle: tuple[Link, ...] | None
    explanation: tuple[Evidence, ...]


@dataclass(frozen=True, slots=True)
class _CycleSearch:
    """The settings with which the search finds one kind of cycle.

    Attributes:
        component: The relations of the components that the search takes.
        closing: The relation of the edges that the search tries as the
            closing edge.
        path: The relations of the path from the target of the closing edge
            back to its source.
    """

    component: frozenset[Relation]
    closing: Relation
    path: frozenset[Relation]


#: Every relation.
_ALL: frozenset[Relation] = frozenset(RELATIONS)

#: The relations other than a read-write dependency.
_NON_RW: frozenset[Relation] = frozenset({"ww", "wr"})

#: The search of each kind of cycle but G-nonadjacent.
_SEARCHES: dict[Anomaly, _CycleSearch] = {
    "G0": _CycleSearch(frozenset({"ww"}), "ww", frozenset({"ww"})),
    "G1c": _CycleSearch(_NON_RW, "wr", _NON_RW),
    "G-single": _CycleSearch(_ALL, "rw", _NON_RW),
    "G2": _CycleSearch(_ALL, "rw", _ALL),
}

#: The fewest read-write edges of a G-nonadjacent cycle. A cycle with one is
#: G-single.
_NONADJACENT_RW = 2


@dataclass(frozen=True, slots=True)
class _Read:
    """The read of a key by an ok transaction, and the list that it returned."""

    call: int
    key: Any
    read: list[Any]


@dataclass(frozen=True, slots=True)
class _Versions:
    """The version order of a key, and the transactions that appended to the key.

    writers has the committed transaction that appended each value of the
    order. The unobserved appends are the committed appends that no read
    observed.
    """

    key: Any
    order: list[Any]
    writers: list[int | None]
    unobserved: list[tuple[int, Any]]


#: A state of the G-nonadjacent search. It has a transaction and two flags.
#: The first flag is True when the walk entered the transaction by an rw
#: edge. The second is True when the walk has taken an rw edge.
_State = tuple[int, bool, bool]

#: One step of a walk. It has the transaction that the step enters and the
#: relation of the edge that the step follows.
_Step = tuple[int, Relation]


def _id(value: object) -> str:
    """Return the identity of a key or a value that has a typed literal."""
    return cast("str", identity_of(value))


def _name_of(key: object, value: object) -> tuple[str, str]:
    """Return the name of the append of value to key as a pair of identities."""
    return (_id(key), _id(value))


def _add(table: dict[_K, list[_V]], key: _K, value: _V) -> None:
    """Add value to the list of key in table."""
    table.setdefault(key, []).append(value)


def _single(anomaly: Anomaly, calls: Sequence[int], evidence: Observation) -> Instance:
    """Return the instance of an anomaly that is not a cycle."""
    return Instance(anomaly, tuple(calls), None, (evidence,))


def _ww(
    source: int, target: int, key: object, value: object, following: object
) -> Edge:
    """Return the evidence that following comes after value in the order of key."""
    return Edge(source, target, "ww", key, value, False, following)


def _future(txn: Transaction, position: int, read: Sequence[Any]) -> list[Any]:
    """Return the values of the read at position that txn appends to the key later."""
    key = _id(txn.mops[position].key)
    later = {
        _id(mop.value)
        for mop in txn.mops[position + 1 :]
        if mop.fn == APPEND and _id(mop.key) == key
    }
    return [value for value in read if _id(value) in later]


def _agrees(read: Sequence[Any], whole: bool, expected: Sequence[Any]) -> bool:
    """Report whether a read is the expected list.

    When expected is only the end of the list, the read must end with
    expected.
    """
    got = [_id(value) for value in read]
    want = [_id(value) for value in expected]
    tail = got if whole else got[max(0, len(got) - len(want)) :]
    return tail == want


def _internal(txn: Transaction) -> Instance | None:
    """Return the first read that the other micro-operations of txn contradict.

    Before the first read of a key, the appends of the transaction fix only
    the end of the list of the key. After a read, the read fixes the whole
    list. The later appends of the transaction extend that list. A read must
    not contain a value that the transaction appends to the key after the
    read.
    """
    known: dict[str, tuple[bool, tuple[Any, ...]]] = {}
    for position, mop in enumerate(txn.mops):
        key = _id(mop.key)
        whole, expected = known.get(key, (False, ()))
        if mop.fn == APPEND:
            known[key] = (whole, (*expected, mop.value))
            continue
        read: list[Any] = mop.value
        later = _future(txn, position, read)
        if later or (key in known and not _agrees(read, whole, expected)):
            return _single(
                "internal-inconsistency",
                [txn.call],
                Observation(
                    "internal-inconsistency",
                    calls=(txn.call,),
                    key=mop.key,
                    reads=(read,),
                    expected=expected,
                    whole=whole,
                    future=later[0] if later else None,
                    has_future=bool(later),
                ),
            )
        known[key] = (True, tuple(read))
    return None


#: The initial value of a register in a version pair and in a read. A read
#: list without a value states it.
_INITIAL: Any = object()


def _same(a: object, b: object) -> bool:
    """Report whether two register values, either of which may be _INITIAL, are one."""
    if a is _INITIAL or b is _INITIAL:
        return a is b
    return _id(a) == _id(b)


def _external_reads(txn: Transaction) -> dict[str, Any]:
    """Return the value of each external read of an ok register transaction, by key.

    An external read is the first read of a key before the transaction writes
    the key. Its value is _INITIAL for the initial value.
    """
    if txn.kind != "ok":
        return {}
    touched: set[str] = set()
    found: dict[str, Any] = {}
    for mop in txn.mops:
        key = _id(mop.key)
        if mop.fn == READ and key not in touched:
            found[key] = mop.value[0] if mop.value else _INITIAL
        touched.add(key)
    return found


def _external_writes(txn: Transaction) -> dict[str, Any]:
    """Return the value of the last write of each key of a register transaction."""
    return {_id(mop.key): mop.value for mop in txn.mops if mop.fn == WRITE}


def _internal_register(txn: Transaction) -> Instance | None:
    """Return the first read of a register that the other micro-operations contradict.

    After a write or a read of a key, the transaction knows the key's value. A
    later read returns that value, and no read returns a value that the
    transaction writes to the key after the read.
    """
    known: dict[str, Any] = {}
    for position, mop in enumerate(txn.mops):
        key = _id(mop.key)
        if mop.fn == WRITE:
            known[key] = mop.value
            continue
        read = mop.value[0] if mop.value else _INITIAL
        future = read is not _INITIAL and any(
            later.fn == WRITE and _id(later.key) == key and _same(later.value, read)
            for later in txn.mops[position + 1 :]
        )
        stale = key in known and not _same(known[key], read)
        if future or stale:
            expected = known.get(key, _INITIAL)
            return _single(
                "internal-inconsistency",
                [txn.call],
                Observation(
                    "internal-inconsistency",
                    calls=(txn.call,),
                    key=mop.key,
                    register=True,
                    read=None if read is _INITIAL else read,
                    known=None if expected is _INITIAL else expected,
                    whole=key in known,
                    future=read if future else None,
                    has_future=future,
                ),
            )
        known[key] = read
    return None


def _longest(reads: Sequence[_Read]) -> tuple[list[Any], tuple[_Read, _Read] | None]:
    """Return the longest of the reads of a key, or the first two reads that clash.

    Two distinct reads clash when they are not prefixes of one list. The
    clash has the shorter read first.
    """
    distinct: dict[tuple[str, ...], _Read] = {}
    for one in reads:
        distinct.setdefault(tuple(_id(value) for value in one.read), one)
    ranked = sorted(distinct.items(), key=lambda entry: len(entry[0]))
    for (shorter, first), (longer, second) in itertools.pairwise(ranked):
        if any(longer[j] != one for j, one in enumerate(shorter)):
            return [], (first, second)
    return (ranked[-1][1].read if ranked else []), None


def _walk_to(
    state: _State, parent: dict[_State, tuple[_State, Relation] | None]
) -> list[_Step]:
    """Return the steps of the walk to state, from the first step to the last."""
    steps: list[_Step] = []
    current = state
    previous = parent[current]
    while previous is not None:
        steps.append((current[0], previous[1]))
        current = previous[0]
        previous = parent[current]
    return steps[::-1]


@dataclass(slots=True)
class _Index:
    """The appends and the keys of the transactions of a history.

    Attributes:
        appender: The call of each append, by the name of the append.
        appends: The calls and the values of the appends to each key. They
            are in the order of the transactions.
        later: The next value that the same call appended to the key after
            each append.
        keys: Each key in the form of its first use. The keys are in the
            order of their first use.
    """

    appender: dict[tuple[str, str], int] = field(default_factory=dict)
    appends: dict[str, list[tuple[int, Any]]] = field(default_factory=dict)
    later: dict[tuple[str, str], Any] = field(default_factory=dict)
    keys: dict[str, Any] = field(default_factory=dict)

    def take(self, txn: Transaction) -> None:
        """Index the keys that a transaction touches, and its appends or writes."""
        last: dict[str, tuple[str, str]] = {}
        for mop in txn.mops:
            key = _id(mop.key)
            self.keys.setdefault(key, mop.key)
            if mop.fn == READ:
                continue
            name = _name_of(mop.key, mop.value)
            self.appender[name] = txn.call
            _add(self.appends, key, (txn.call, mop.value))
            before = last.get(key)
            if before is not None:
                self.later[before] = mop.value
            last[key] = name


class Analysis:
    """The derivation over the transactions of one history.

    A register read is a read of the list of its one value, so the appender
    of a value is its writer, and the reads show the anomalies that need no
    graph as the reads of a list-append history do.
    """

    def __init__(self, txns: Sequence[Transaction], *, register: bool = False) -> None:
        """Derive the dependencies between the committed transactions of txns.

        Args:
            txns: The transactions, in the order of their invocations. Each of
                their keys and values has a typed literal.
            register: True for a register history.
        """
        self._register: bool = register
        self._txns: Sequence[Transaction] = txns
        self._index: _Index = _Index()
        for txn in txns:
            self._index.take(txn)
        self._aborted: frozenset[int] = frozenset(
            txn.call for txn in txns if txn.kind == "fail"
        )
        self._reads: list[_Read] = [
            _Read(txn.call, mop.key, mop.value)
            for txn in txns
            if txn.kind == "ok"
            for mop in txn.mops
            if mop.fn == READ
        ]
        undecided = {txn.call for txn in txns if txn.kind in ("unknown", None)}
        committed = {txn.call for txn in txns if txn.kind == "ok"}
        for one in self._reads:
            for value in one.read:
                appender = self._index.appender.get(_name_of(one.key, value))
                if appender is not None and appender in undecided:
                    committed.add(appender)
        self._committed: frozenset[int] = frozenset(committed)
        self._incompatible: Instance | None = None
        self._edges: dict[tuple[int, int], list[Edge]] = {}
        if register:
            self._orders: dict[str, list[Any]] = {}
            self._derive_registers()
        else:
            self._orders = self._version_orders()
            self._derive()

    def instance(self, anomaly: Anomaly) -> Instance | None:
        """Return the first instance of an anomaly in the history.

        Args:
            anomaly: The kind of anomaly.

        Returns:
            The instance, or None when the history does not have one.
        """
        finders: dict[Anomaly, Callable[[], Instance | None]] = {
            "garbage-read": self._garbage_read,
            "duplicate-append": self._duplicate_append,
            "internal-inconsistency": self._internal_inconsistency,
            "incompatible-order": lambda: self._incompatible,
            "aborted-read": self._aborted_read,
            "intermediate-read": self._intermediate_read,
            "G-nonadjacent": self._nonadjacent,
        }
        finder = finders.get(anomaly)
        if finder is not None:
            return finder()
        return self._cycle(anomaly, _SEARCHES[anomaly])

    def _garbage_read(self) -> Instance | None:
        """Return the first committed read of a value without an append."""
        for one in self._reads:
            for value in one.read:
                if _name_of(one.key, value) not in self._index.appender:
                    return _single(
                        "garbage-read",
                        [one.call],
                        Observation(
                            "garbage-read",
                            calls=(one.call,),
                            key=one.key,
                            reads=(one.read,),
                            value=value,
                            register=self._register,
                            read=value if self._register else None,
                        ),
                    )
        return None

    def _duplicate_append(self) -> Instance | None:
        """Return the first committed read that returned one value twice."""
        for one in self._reads:
            seen: set[str] = set()
            for value in one.read:
                if _id(value) in seen:
                    return _single(
                        "duplicate-append",
                        [one.call],
                        Observation(
                            "duplicate-append",
                            calls=(one.call,),
                            key=one.key,
                            reads=(one.read,),
                            value=value,
                        ),
                    )
                seen.add(_id(value))
        return None

    def _internal_inconsistency(self) -> Instance | None:
        """Return the first committed read that contradicts its transaction."""
        internal = _internal_register if self._register else _internal
        for txn in self._txns:
            found = internal(txn) if txn.kind == "ok" else None
            if found is not None:
                return found
        return None

    def _aborted_read(self) -> Instance | None:
        """Return the first committed read of a value that an aborted call appended."""
        for one in self._reads:
            for value in one.read:
                appender = self._index.appender.get(_name_of(one.key, value))
                if appender is not None and appender in self._aborted:
                    return _single(
                        "aborted-read",
                        [one.call, appender],
                        Observation(
                            "aborted-read",
                            calls=(one.call,),
                            key=one.key,
                            value=value,
                            appender=appender,
                            register=self._register,
                        ),
                    )
        return None

    def _intermediate_read(self) -> Instance | None:
        """Return the first committed read that ends inside the appends of one call.

        A transaction that reads its own appends does not make an
        intermediate read.
        """
        for one in self._reads:
            if not one.read:
                continue
            value = one.read[-1]
            name = _name_of(one.key, value)
            appender = self._index.appender.get(name)
            if (
                appender is not None
                and appender != one.call
                and name in self._index.later
            ):
                return _single(
                    "intermediate-read",
                    [one.call, appender],
                    Observation(
                        "intermediate-read",
                        calls=(one.call,),
                        key=one.key,
                        value=value,
                        appender=appender,
                        following=self._index.later[name],
                        register=self._register,
                    ),
                )
        return None

    def _version_orders(self) -> dict[str, list[Any]]:
        """Return the version order of each key.

        The keys are in the order of their first use. The first key whose
        committed reads are not prefixes of one list becomes the incompatible
        order.
        """
        by_key: dict[str, list[_Read]] = {}
        for one in self._reads:
            _add(by_key, _id(one.key), one)
        orders: dict[str, list[Any]] = {}
        for key, stated in self._index.keys.items():
            order, clash = _longest(by_key.get(key, []))
            if clash is None:
                orders[key] = order
            elif self._incompatible is None:
                first, second = clash
                self._incompatible = _single(
                    "incompatible-order",
                    list(dict.fromkeys([first.call, second.call])),
                    Observation(
                        "incompatible-order",
                        calls=(first.call, second.call),
                        key=stated,
                        reads=(first.read, second.read),
                    ),
                )
        return orders

    def _writer(self, key: str, value: object) -> int | None:
        """Return the committed appender of value to the key whose identity is key."""
        appender = self._index.appender.get((key, _id(value)))
        return (
            appender if appender is not None and appender in self._committed else None
        )

    def _derive(self) -> None:
        """Derive the dependencies between committed transactions for each key.

        An unobserved committed append follows the last value of the version
        order. Its transaction depends on the appender of that value and on
        every read that returned the whole order.
        """
        reads: dict[str, list[_Read]] = {}
        for one in self._reads:
            _add(reads, _id(one.key), one)
        for key, order in self._orders.items():
            present = {_id(value) for value in order}
            versions = _Versions(
                self._index.keys[key],
                order,
                [self._writer(key, value) for value in order],
                [
                    (call, value)
                    for call, value in self._index.appends.get(key, [])
                    if call in self._committed and _id(value) not in present
                ],
            )
            for i in range(len(order) - 1):
                self._edge(
                    versions.writers[i],
                    versions.writers[i + 1],
                    _ww,
                    versions.key,
                    order[i],
                    order[i + 1],
                )
            last_writer = versions.writers[-1] if versions.writers else None
            last_value = order[-1] if order else None
            for call, value in versions.unobserved:
                self._edge(last_writer, call, _ww, versions.key, last_value, value)
            for one in reads.get(key, []):
                self._read_edges(one.call, one.read, versions)

    def _read_edges(self, call: int, read: Sequence[Any], versions: _Versions) -> None:
        """Derive the wr and the rw dependencies of one committed read."""
        seen = len(read)
        last = read[-1] if read else None
        if seen > 0:
            self._edge(
                versions.writers[seen - 1],
                call,
                lambda s, t, key, value, _: Edge(s, t, "wr", key, value, False, None),
                versions.key,
                last,
                None,
            )
        following: list[tuple[int | None, Any]] = (
            [(versions.writers[seen], versions.order[seen])]
            if seen < len(versions.order)
            else [(writer, value) for writer, value in versions.unobserved]
        )
        for writer, value in following:
            self._edge(
                call,
                writer,
                lambda s, t, key, read_last, nxt: Edge(
                    s, t, "rw", key, read_last, seen == 0, nxt
                ),
                versions.key,
                last,
                value,
            )

    def _derive_registers(self) -> None:
        """Derive the dependencies between committed transactions for each register.

        The initial value precedes each installed value, the value of a
        committed transaction's last write of a register. A committed
        transaction's external read, its first read of a register before it
        writes the register, precedes its own installed value. Each pair gives
        a ww edge from the transaction that installed its first value, and an
        rw edge from each transaction whose external read returned that value.
        Each external read gives a wr edge from the transaction that installed
        its value. A key adds its ww edges in the order of the pairs, then the
        wr and rw edges of each read in the order of the reading transactions.
        """
        reads: dict[str, list[tuple[int, Any]]] = {}
        installs: dict[str, list[tuple[int, Any]]] = {}
        for txn in self._txns:
            if txn.call not in self._committed:
                continue
            for key, read in _external_reads(txn).items():
                _add(reads, key, (txn.call, read))
            for key, value in _external_writes(txn).items():
                _add(installs, key, (txn.call, value))
        for key, stated in self._index.keys.items():
            read_by = dict(reads.get(key, []))
            pairs: list[tuple[Any, int, Any]] = []
            for call, value in installs.get(key, []):
                pairs.append((_INITIAL, call, value))
                before = read_by.get(call, _INITIAL)
                if before is not _INITIAL:
                    pairs.append((before, call, value))
            self._register_edges(key, stated, pairs, reads.get(key, []))

    def _register_edges(
        self,
        key: str,
        stated: object,
        pairs: Sequence[tuple[Any, int, Any]],
        reads: Sequence[tuple[int, Any]],
    ) -> None:
        """Derive the edges of one register from its version pairs and its reads.

        A pair has a value, the transaction that installed a later value, and
        that later value. A read has the reading transaction and the value it
        read, _INITIAL for the initial value.
        """
        for before, call, value in pairs:
            if before is not _INITIAL:
                self._edge(
                    self._installer(key, before),
                    call,
                    lambda s, t, k, v, n: Edge(s, t, "ww", k, v, False, n, True),
                    stated,
                    before,
                    value,
                )
        for reader, read in reads:
            if read is not _INITIAL:
                self._edge(
                    self._installer(key, read),
                    reader,
                    lambda s, t, k, v, _: Edge(s, t, "wr", k, v, False, None, True),
                    stated,
                    read,
                    None,
                )
            for before, call, value in pairs:
                if _same(before, read):
                    self._edge(
                        reader,
                        call,
                        lambda s, t, k, v, n: Edge(
                            s,
                            t,
                            "rw",
                            k,
                            None if v is _INITIAL else v,
                            v is _INITIAL,
                            n,
                            True,
                        ),
                        stated,
                        read,
                        value,
                    )

    def _installer(self, key: str, value: object) -> int | None:
        """Return the committed transaction that installed value on a register.

        A value that its writer wrote again later in the same transaction was
        never installed.
        """
        name = (key, _id(value))
        if name in self._index.later:
            return None
        return self._writer(key, value)

    def _edge(
        self,
        a: int | None,
        b: int | None,
        evidence: Callable[[int, int, Any, Any, Any], Edge],
        key: object,
        value: object,
        following: object,
    ) -> None:
        """Add the evidence that b depends on a when a and b are two committed calls."""
        if a is None or b is None or a == b:
            return
        _add(self._edges, (a, b), evidence(a, b, key, value, following))

    def _evidence(self, a: int, b: int) -> list[Edge]:
        """Return the evidence of the edge from a to b."""
        return self._edges[(a, b)]

    def _graph(self, relations: AbstractSet[Relation]) -> Graph:
        """Return the sorted targets of each transaction over the edges of relations."""
        out: dict[int, list[int]] = {}
        for (source, target), evidence in self._edges.items():
            if any(entry.relation in relations for entry in evidence):
                _add(out, source, target)
        return {node: sorted(targets) for node, targets in out.items()}

    def _has(self, a: int, b: int, relation: Relation) -> bool:
        """Report whether the edge from a to b has a relation."""
        return any(entry.relation == relation for entry in self._evidence(a, b))

    def _nodes(self) -> list[int]:
        """Return the committed transactions in ascending order."""
        return sorted(self._committed)

    def _cycle(self, anomaly: Anomaly, search: _CycleSearch) -> Instance | None:
        """Return the first cycle of a kind in the order of its search.

        The search takes the components of the graph over the component
        relations. In each, it tries the edges of the closing relation in the
        order of their sources and then their targets. An edge closes a cycle
        when a path over the path relations leads from its target back to its
        source. The closing edge of a G-single cycle counts as its one
        read-write dependency.
        """
        around = self._graph(search.component)
        back = self._graph(search.path)
        first: frozenset[Relation] = (
            frozenset({search.closing}) if anomaly == "G-single" else search.component
        )
        for a, b, members in self._closing(around, search.closing):
            found = path(b, a, back, members)
            if found is None:
                continue
            used = [first, *(search.path for _ in found[1:])]
            return self._cycle_instance(anomaly, [a, *found[:-1]], used)
        return None

    def _closing(
        self, around: Graph, relation: Relation
    ) -> Iterator[tuple[int, int, frozenset[int]]]:
        """Yield each edge of relation inside a component of around, and the component.

        The edges come in the order of the components, then of their
        sources, then of their targets. Every transaction of a component has
        an edge to another one.
        """
        for component in components(self._nodes(), around):
            members = frozenset(component)
            for a in component:
                for b in around[a]:
                    if b in members and self._has(a, b, relation):
                        yield a, b, members

    def _nonadjacent(self) -> Instance | None:
        """Return the first G-nonadjacent cycle.

        The search tries the rw edges of each component in the order of
        their sources and then their targets. From the target of each edge,
        it takes the shortest walk back to the source of the edge that meets
        three conditions:

        - An rw edge does not follow another rw edge.
        - The walk takes at least one more rw edge.
        - The last edge of the walk is not an rw edge.

        The search reduces the closed walk to a simple cycle without two
        adjacent rw edges. It reports that cycle when the cycle has two or
        more rw edges.
        """
        around = self._graph(_ALL)
        for a, b, members in self._closing(around, "rw"):
            steps = self._alternating(b, a, around, members)
            if steps is None:
                continue
            nodes = [a, b, *(node for node, _ in steps[:-1])]
            relations: list[Relation] = ["rw", *(relation for _, relation in steps)]
            cycle = simple(list(zip(nodes, relations, strict=True)))
            if sum(1 for _, relation in cycle if relation == "rw") < _NONADJACENT_RW:
                continue
            return self._cycle_instance(
                "G-nonadjacent",
                [node for node, _ in cycle],
                [
                    frozenset({"rw"}) if relation == "rw" else _NON_RW
                    for _, relation in cycle
                ],
            )
        return None

    def _alternating(
        self, start: int, goal: int, around: Graph, members: frozenset[int]
    ) -> list[_Step] | None:
        """Return the shortest alternating walk from start to goal.

        An rw edge leads into start. The search tries the edges of each
        transaction in the order of their targets and of the relations.
        """
        origin: _State = (start, True, False)
        parent: dict[_State, tuple[_State, Relation] | None] = {origin: None}
        queue: list[_State] = [origin]
        for state in queue:
            node, after_rw, taken = state
            if node == goal and not after_rw and taken:
                return _walk_to(state, parent)
            for following, relation in self._successors(state, around, members):
                if following in parent:
                    continue
                parent[following] = (state, relation)
                queue.append(following)
        return None

    def _successors(
        self, state: _State, around: Graph, members: frozenset[int]
    ) -> list[tuple[_State, Relation]]:
        """Return the states that follow state on an alternating walk inside members.

        Each state comes with the relation of its edge. The states are in the
        order of the targets and of the relations. An rw edge never follows
        an rw edge. members are the transactions of a component of around, so
        each has an edge.
        """
        node, after_rw, taken = state
        found: list[tuple[_State, Relation]] = []
        for target in around[node]:
            if target not in members:
                continue
            for relation in self._relations(node, target):
                if relation == "rw" and after_rw:
                    continue
                rw = relation == "rw"
                found.append(((target, rw, taken or rw), relation))
        return found

    def _relations(self, a: int, b: int) -> list[Relation]:
        """Return the relations of the edge from a to b in the order ww, wr, rw."""
        present = {entry.relation for entry in self._evidence(a, b)}
        return [relation for relation in RELATIONS if relation in present]

    def _cycle_instance(
        self,
        anomaly: Anomaly,
        nodes: Sequence[int],
        used: Sequence[frozenset[Relation]],
    ) -> Instance:
        """Return the instance of the cycle that visits nodes in order.

        The cycle returns from the last node to the first. used has the
        relations by which the search followed the edge from each transaction
        to the next. The cycle lists the relations of each edge that are in
        used. The explanation has the first evidence of one of them.
        """
        cycle: list[Link] = []
        explanation: list[Evidence] = []
        for position, node in enumerate(nodes):
            following = nodes[(position + 1) % len(nodes)]
            evidence = [
                entry
                for entry in self._evidence(node, following)
                if entry.relation in used[position]
            ]
            relations = {entry.relation for entry in evidence}
            cycle.append(Link(node, tuple(r for r in RELATIONS if r in relations)))
            explanation.append(evidence[0])
        return Instance(anomaly, tuple(nodes), tuple(cycle), tuple(explanation))
