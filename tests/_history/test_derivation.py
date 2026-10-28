# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _history/derivation.py tests the derivation over the transactions.

Each instance of the spec is the instance that the reference implementation
of the definition finds in the same history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._history.derivation import (
    ANOMALIES,
    Analysis,
    Anomaly,
    Edge,
    Instance,
    Link,
    Observation,
)
from dokimi_assert._history.history import History
from dokimi_assert._history.transaction import transactions
from helpers import (
    append,
    invoke_txn,
    read_of,
    read_skew,
    run_txn,
    write,
    write_skew,
)

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


def instance(history: History, anomaly: Anomaly) -> Instance | None:
    """Return the first instance of an anomaly in a history."""
    return Analysis(transactions(history.events())).instance(anomaly)


def cycle_of(history: History, anomaly: Anomaly) -> list[int] | None:
    """Return the calls of the cycle of the first instance of anomaly in history."""
    found = instance(history, anomaly)
    if found is None or found.cycle is None:
        return None
    return [link.call for link in found.cycle]


def kinds(history: History) -> list[Anomaly]:
    """Return every kind of anomaly that a history has."""
    analysis = Analysis(transactions(history.events()))
    return [kind for kind in ANOMALIES if analysis.instance(kind) is not None]


def crossed_appends() -> History:
    """Return a history whose calls 0 and 1 append to x and to y in opposite orders."""
    history = History()
    first = invoke_txn(history, 0, append("x", 1), append("y", 4))
    second = invoke_txn(history, 1, append("x", 2), append("y", 3))
    first.ok([append("x", 1), append("y", 4)])
    second.ok([append("x", 2), append("y", 3)])
    run_txn(history, 2, read_of("x", [1, 2]), read_of("y", [3, 4]))
    return history


class TestAnomalies:
    """ANOMALIES lists the kinds of anomaly in the order of the report."""

    def test_lists_the_eleven_kinds_in_report_order(self, seat: Collector) -> None:
        """The order starts with the six kinds that do not need a graph."""
        check.equal(
            seat,
            ANOMALIES,
            (
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
            ),
            "ANOMALIES lists the eleven kinds in report order",
        )


class TestEdge:
    """Edge is the evidence of one dependency of a cycle."""

    def test_keeps_its_fields(self, seat: Collector) -> None:
        """A ww edge leads from call 0 to call 1 on x."""
        edge = Edge(0, 1, "ww", "x", 1, False, 2)
        check.equal(
            seat,
            [
                edge.source,
                edge.target,
                edge.relation,
                edge.key,
                edge.value,
                edge.empty,
                edge.following,
            ],
            [0, 1, "ww", "x", 1, False, 2],
            "the edge keeps its fields",
        )


class TestObservation:
    """Observation is the evidence of an anomaly that is not a cycle."""

    def test_has_empty_fields_by_default(self, seat: Collector) -> None:
        """An observation of G0 sets only its anomaly."""
        o = Observation("G0")
        check.equal(
            seat,
            [o.calls, o.reads, o.expected, o.whole, o.has_future, o.appender],
            [(), (), (), False, False, None],
            "the other fields are empty",
        )


class TestLink:
    """Link is one transaction of a cycle and the relations of its edge."""

    def test_keeps_its_fields(self, seat: Collector) -> None:
        """Call 0 leaves by a ww edge."""
        link = Link(0, ("ww",))
        check.equal(
            seat, [link.call, link.relations], [0, ("ww",)], "the link keeps its fields"
        )


class TestAnalysis:
    """Analysis derives the anomalies of the transactions of one history."""

    def test_does_not_derive_an_anomaly_of_a_serial_history(
        self, seat: Collector
    ) -> None:
        """Each transaction reads the appends before it."""
        history = History()
        run_txn(history, 0, append("x", 1))
        run_txn(history, 1, read_of("x", [1]), append("x", 2))
        run_txn(history, 0, read_of("x", [1, 2]))
        check.is_empty(seat, kinds(history), "the history does not have an anomaly")

    def test_does_not_derive_an_anomaly_of_a_read_of_its_own_intermediate_append(
        self, seat: Collector
    ) -> None:
        """Call 0 reads its own 1 before it appends 2."""
        history = History()
        run_txn(history, 0, append("x", 1), read_of("x", [1]), append("x", 2))
        run_txn(history, 1, read_of("x", [1, 2]))
        check.is_empty(seat, kinds(history), "the history does not have an anomaly")


class TestAnalysisInstance:
    """Analysis.instance returns the first instance of an anomaly."""

    def test_returns_a_garbage_read_of_a_value_without_an_append(
        self, seat: Collector
    ) -> None:
        """No call appended the 9 that call 0 reads."""
        history = History()
        run_txn(history, 0, read_of("x", [9]))
        check.equal(
            seat,
            instance(history, "garbage-read"),
            Instance(
                "garbage-read",
                (0,),
                None,
                (
                    Observation(
                        "garbage-read", calls=(0,), key="x", reads=([9],), value=9
                    ),
                ),
            ),
            "the instance has the read of 9",
        )

    def test_returns_a_duplicate_append_of_a_read_that_returned_one_value_twice(
        self, seat: Collector
    ) -> None:
        """Call 2 reads [1, 1] after one append of 1."""
        history = History()
        run_txn(history, 0, append("x", 1))
        run_txn(history, 1, read_of("x", [1, 1]))
        found = instance(history, "duplicate-append")
        check.equal(
            seat,
            None if found is None else found.explanation,
            (
                Observation(
                    "duplicate-append", calls=(2,), key="x", reads=([1, 1],), value=1
                ),
            ),
            "the explanation has the read of 1 twice",
        )

    def test_returns_an_internal_inconsistency_of_a_read_without_its_own_append(
        self, seat: Collector
    ) -> None:
        """Call 2 appends 2 to x and then reads [1]."""
        history = History()
        run_txn(history, 0, append("x", 1))
        run_txn(history, 1, append("x", 2), read_of("x", [1]))
        found = instance(history, "internal-inconsistency")
        check.equal(
            seat,
            None if found is None else found.explanation,
            (
                Observation(
                    "internal-inconsistency",
                    calls=(2,),
                    key="x",
                    reads=([1],),
                    expected=(2,),
                ),
            ),
            "the read must end with 2",
        )

    def test_returns_an_internal_inconsistency_of_a_read_of_its_own_later_append(
        self, seat: Collector
    ) -> None:
        """Call 0 reads [1] and then appends 1."""
        history = History()
        run_txn(history, 0, read_of("x", [1]), append("x", 1))
        found = instance(history, "internal-inconsistency")
        check.equal(
            seat,
            None if found is None else found.explanation,
            (
                Observation(
                    "internal-inconsistency",
                    calls=(0,),
                    key="x",
                    reads=([1],),
                    future=1,
                    has_future=True,
                ),
            ),
            "the read contains the later append of 1",
        )

    def test_returns_an_internal_inconsistency_of_a_read_that_differs_from_the_first(
        self, seat: Collector
    ) -> None:
        """The two reads of x return [] and then [1]."""
        history = History()
        reader = invoke_txn(history, 0, read_of("x", None), read_of("x", None))
        run_txn(history, 1, append("x", 1))
        reader.ok([read_of("x", []), read_of("x", [1])])
        found = instance(history, "internal-inconsistency")
        check.equal(
            seat,
            None if found is None else found.explanation,
            (
                Observation(
                    "internal-inconsistency",
                    calls=(0,),
                    key="x",
                    reads=([1],),
                    whole=True,
                ),
            ),
            "the second read differs from the first",
        )

    def test_returns_an_incompatible_order_of_reads_that_are_not_prefixes_of_one_list(
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
            instance(history, "incompatible-order"),
            Instance(
                "incompatible-order",
                (6, 8),
                None,
                (
                    Observation(
                        "incompatible-order",
                        calls=(6, 8),
                        key="x",
                        reads=([1, 2], [1, 3]),
                    ),
                ),
            ),
            "the instance has the reads of calls 6 and 8",
        )

    def test_returns_the_incompatible_order_of_the_first_key_of_the_history(
        self, seat: Collector
    ) -> None:
        """Both keys have clashing reads. The history uses y first."""
        history = History()
        run_txn(history, 0, append("y", 1))
        run_txn(history, 1, append("y", 2))
        run_txn(history, 2, append("x", 1))
        run_txn(history, 3, append("x", 2))
        run_txn(history, 0, read_of("x", [1]))
        run_txn(history, 0, read_of("x", [2]))
        run_txn(history, 0, read_of("y", [1]))
        run_txn(history, 0, read_of("y", [2]))
        found = instance(history, "incompatible-order")
        check.equal(
            seat,
            None if found is None else found.explanation,
            (
                Observation(
                    "incompatible-order", calls=(12, 14), key="y", reads=([1], [2])
                ),
            ),
            "the explanation has the reads of y",
        )

    def test_returns_one_call_of_an_incompatible_order_of_one_transaction(
        self, seat: Collector
    ) -> None:
        """Call 4 reads [1] and then [2]."""
        history = History()
        for value in (1, 2):
            run_txn(history, value, append("x", value))
        reader = invoke_txn(history, 0, read_of("x", None), read_of("x", None))
        reader.ok([read_of("x", [1]), read_of("x", [2])])
        found = instance(history, "incompatible-order")
        check.equal(
            seat,
            None if found is None else (found.calls, found.explanation[0]),
            (
                (4,),
                Observation(
                    "incompatible-order", calls=(4, 4), key="x", reads=([1], [2])
                ),
            ),
            "the instance lists call 4 once",
        )

    def test_returns_an_aborted_read_of_a_value_that_a_failed_call_appended(
        self, seat: Collector
    ) -> None:
        """Call 2 reads the 1 that the aborted call 0 appended."""
        history = History()
        invoke_txn(history, 0, append("x", 1)).fail("aborted")
        run_txn(history, 1, read_of("x", [1]))
        check.equal(
            seat,
            instance(history, "aborted-read"),
            Instance(
                "aborted-read",
                (2, 0),
                None,
                (
                    Observation(
                        "aborted-read", calls=(2,), key="x", value=1, appender=0
                    ),
                ),
            ),
            "the instance has the read and its appender",
        )

    def test_returns_an_intermediate_read_that_ends_inside_the_appends_of_one_call(
        self, seat: Collector
    ) -> None:
        """Call 2 reads [1] after call 0 appended 1 and then 2."""
        history = History()
        run_txn(history, 0, append("x", 1), append("x", 2))
        run_txn(history, 1, read_of("x", [1]))
        found = instance(history, "intermediate-read")
        check.equal(
            seat,
            None if found is None else found.explanation,
            (
                Observation(
                    "intermediate-read",
                    calls=(2,),
                    key="x",
                    value=1,
                    appender=0,
                    following=2,
                ),
            ),
            "the explanation has the value that follows 1",
        )

    def test_returns_a_g0_cycle_of_write_dependencies_with_the_evidence_of_each(
        self, seat: Collector
    ) -> None:
        """The order of x has call 0 first. The order of y has call 1 first."""
        check.equal(
            seat,
            instance(crossed_appends(), "G0"),
            Instance(
                "G0",
                (0, 1),
                (Link(0, ("ww",)), Link(1, ("ww",))),
                (
                    Edge(0, 1, "ww", "x", 1, False, 2),
                    Edge(1, 0, "ww", "y", 3, False, 4),
                ),
            ),
            "the instance has the cycle and the evidence of each edge",
        )

    def test_returns_a_g0_cycle_of_registers_that_each_overwrite_a_read_value(
        self, seat: Collector
    ) -> None:
        """Call 2 overwrites the 1 of call 0, and call 0 overwrites the 3 of call 2."""
        history = History()
        run_txn(history, 0, write("x", 1), read_of("y", 3), write("y", 4))
        run_txn(history, 1, read_of("x", 1), write("x", 2), write("y", 3))
        check.equal(
            seat,
            Analysis(transactions(history.events()), register=True).instance("G0"),
            Instance(
                "G0",
                (0, 2),
                (Link(0, ("ww",)), Link(2, ("ww",))),
                (
                    Edge(0, 2, "ww", "x", 1, False, 2, register=True),
                    Edge(2, 0, "ww", "y", 3, False, 4, register=True),
                ),
            ),
            "each edge of the cycle is a write dependency of a register",
        )

    def test_drops_an_edge_from_a_transaction_to_itself(self, seat: Collector) -> None:
        """The two appends of call 0 to x order call 0 after itself."""
        history = History()
        run_txn(
            history, 0, append("x", 1), append("x", 2), append("y", 1), append("z", 4)
        )
        run_txn(history, 1, append("y", 2), append("z", 3))
        run_txn(
            history, 2, read_of("x", [1, 2]), read_of("y", [1, 2]), read_of("z", [3, 4])
        )
        check.equal(
            seat, cycle_of(history, "G0"), [0, 2], "the cycle has calls 0 and 2"
        )

    def test_returns_a_g1c_cycle_of_calls_that_each_read_the_append_of_the_other(
        self, seat: Collector
    ) -> None:
        """Each call reads the append of the other."""
        history = History()
        first = invoke_txn(history, 0, append("x", 1), read_of("y", None))
        second = invoke_txn(history, 1, append("y", 2), read_of("x", None))
        first.ok([append("x", 1), read_of("y", [2])])
        second.ok([append("y", 2), read_of("x", [1])])
        found = instance(history, "G1c")
        check.equal(
            seat,
            None if found is None else found.cycle,
            (Link(0, ("wr",)), Link(1, ("wr",))),
            "the cycle has two wr edges",
        )

    def test_returns_a_g_single_cycle_of_a_read_skew_with_an_empty_rw_edge(
        self, seat: Collector
    ) -> None:
        """Call 0 reads [] from x and [2] from y."""
        check.equal(
            seat,
            instance(read_skew("ok", True), "G-single"),
            Instance(
                "G-single",
                (0, 1),
                (Link(0, ("rw",)), Link(1, ("wr",))),
                (
                    Edge(0, 1, "rw", "x", None, True, 1),
                    Edge(1, 0, "wr", "y", 2, False, None),
                ),
            ),
            "the instance has the cycle of the read skew",
        )

    def test_lists_only_rw_for_the_closing_edge_of_a_g_single_cycle(
        self, seat: Collector
    ) -> None:
        """The edge from call 0 to call 2 has both ww and rw."""
        history = History()
        run_txn(history, 0, append("x", 1), read_of("y", []), read_of("z", [7]))
        run_txn(history, 1, append("x", 2), append("y", 5), append("z", 7))
        run_txn(history, 2, read_of("x", [1, 2]))
        found = instance(history, "G-single")
        check.equal(
            seat,
            None if found is None else found.cycle,
            (Link(0, ("rw",)), Link(2, ("wr",))),
            "the cycle lists only rw for the closing edge",
        )

    def test_reduces_a_walk_with_two_adjacent_rw_edges_to_a_g_single_cycle_alone(
        self, seat: Collector
    ) -> None:
        """The loop 4, 6, 8 has two adjacent rw edges."""
        history = History()
        run_txn(history, 0, read_of("k1", []), read_of("k6", [6]))
        run_txn(history, 1, append("k1", 1), append("k2", "b"))
        run_txn(
            history,
            2,
            append("k2", "v"),
            read_of("k3", []),
            append("k5", 5),
            append("k6", 6),
        )
        run_txn(history, 3, append("k3", 3), append("k4", "p"))
        run_txn(history, 4, append("k4", "q"), read_of("k5", []))
        run_txn(history, 5, read_of("k2", ["b", "v"]), read_of("k4", ["p", "q"]))
        check.equal(
            seat,
            [
                instance(history, "G-single") is not None,
                instance(history, "G-nonadjacent"),
            ],
            [True, None],
            "the history has a G-single cycle and not a G-nonadjacent one",
        )

    def test_orders_an_unobserved_append_after_the_read_of_its_own_transaction(
        self, seat: Collector
    ) -> None:
        """The append of 2 follows the 1 that call 0 read."""
        history = History()
        run_txn(history, 0, append("x", 1), read_of("x", [1]), read_of("y", [3]))
        run_txn(history, 1, append("x", 2), append("y", 3))
        found = instance(history, "G1c")
        check.equal(
            seat,
            None if found is None else found.cycle,
            (Link(2, ("wr",)), Link(0, ("ww",))),
            "the cycle orders the append of 2 after the read",
        )

    def test_returns_a_g2_cycle_of_two_adjacent_rw_edges_for_a_write_skew(
        self, seat: Collector
    ) -> None:
        """Each call reads the key that the other appends to."""
        found = instance(write_skew(), "G2")
        check.equal(
            seat,
            None if found is None else found.cycle,
            (Link(0, ("rw",)), Link(1, ("rw",))),
            "the cycle has two rw edges",
        )

    def test_does_not_return_a_g_single_cycle_for_a_write_skew(
        self, seat: Collector
    ) -> None:
        """The write skew has two rw edges."""
        check.is_none(
            seat,
            instance(write_skew(), "G-single"),
            "a cycle of two rw edges is not G-single",
        )

    def test_does_not_return_a_g_nonadjacent_cycle_for_a_write_skew(
        self, seat: Collector
    ) -> None:
        """The two rw edges of the write skew are adjacent."""
        check.is_none(
            seat,
            instance(write_skew(), "G-nonadjacent"),
            "a cycle of two adjacent rw edges is not G-nonadjacent",
        )

    def test_returns_a_g_nonadjacent_cycle_of_a_long_fork(
        self, seat: Collector
    ) -> None:
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
        found = instance(history, "G-nonadjacent")
        check.equal(
            seat,
            None if found is None else found.cycle,
            (
                Link(2, ("rw",)),
                Link(1, ("wr",)),
                Link(3, ("rw",)),
                Link(0, ("wr",)),
            ),
            "the cycle has two rw edges that are not adjacent",
        )

    def test_orders_an_unobserved_append_after_the_last_observed_value(
        self, seat: Collector
    ) -> None:
        """No read observes the append of 2 to k1 by call 4."""
        history = History()
        run_txn(history, 0, append("k1", 1))
        run_txn(history, 1, read_of("k1", [1]))
        run_txn(history, 2, read_of("k0", []), append("k1", 2))
        run_txn(history, 3, read_of("k1", []), append("k0", 1))
        check.equal(
            seat,
            cycle_of(history, "G2"),
            [2, 4, 6, 0],
            "the cycle visits calls 2, 4, 6 and 0",
        )

    def test_drops_the_dependency_of_an_unobserved_append_that_did_not_commit(
        self, seat: Collector
    ) -> None:
        """Call 1 of the write skew ends without an outcome."""
        history = History()
        first = invoke_txn(history, 0, read_of("x", None), append("y", 1))
        second = invoke_txn(history, 1, read_of("y", None), append("x", 2))
        first.ok([read_of("x", []), append("y", 1)])
        second.unknown("timed out")
        check.is_none(
            seat, instance(history, "G2"), "the history does not have a G2 cycle"
        )

    tests: ClassVar[list[tuple[str, str | None]]] = [
        ("unknown", "unknown"),
        ("pending", None),
    ]

    @pytest.mark.parametrize(
        "completes", [t[1] for t in tests], ids=[t[0] for t in tests]
    )
    def test_takes_a_call_of_an_unknown_outcome_as_committed_when_a_read_observed_it(
        self, seat: Collector, completes: str | None
    ) -> None:
        """Call 0 reads the append of call 1 to y."""
        check.equal(
            seat,
            cycle_of(read_skew(completes, True), "G-single"),
            [0, 1],
            "the cycle has calls 0 and 1",
        )

    @pytest.mark.parametrize(
        "completes", [t[1] for t in tests], ids=[t[0] for t in tests]
    )
    def test_leaves_out_an_unobserved_call_of_an_unknown_outcome(
        self, seat: Collector, completes: str | None
    ) -> None:
        """Call 0 reads both keys empty."""
        check.is_empty(
            seat,
            kinds(read_skew(completes, False)),
            "the history does not have an anomaly",
        )

    def test_returns_the_cycle_of_the_component_with_the_lowest_call(
        self, seat: Collector
    ) -> None:
        """The history has two write skews."""
        history = write_skew()
        third = invoke_txn(history, 2, read_of("a", None), append("b", 1))
        fourth = invoke_txn(history, 3, read_of("b", None), append("a", 2))
        third.ok([read_of("a", []), append("b", 1)])
        fourth.ok([read_of("b", []), append("a", 2)])
        check.equal(
            seat, cycle_of(history, "G2"), [0, 1], "the cycle is the first write skew"
        )

    def test_returns_the_shortest_path_back_from_the_closing_edge(
        self, seat: Collector
    ) -> None:
        """Call 0 reads the appends of calls 1 and 2."""
        history = History()
        zero = invoke_txn(
            history, 0, append("x", 1), read_of("y", None), read_of("z", None)
        )
        one = invoke_txn(history, 1, append("y", 2), read_of("x", None))
        two = invoke_txn(history, 2, append("z", 3), read_of("y", None))
        zero.ok([append("x", 1), read_of("y", [2]), read_of("z", [3])])
        one.ok([append("y", 2), read_of("x", [1])])
        two.ok([append("z", 3), read_of("y", [2])])
        check.equal(
            seat, cycle_of(history, "G1c"), [0, 1], "the cycle has calls 0 and 1"
        )

    def test_returns_a_g_single_cycle_of_the_component_that_has_one(
        self, seat: Collector
    ) -> None:
        """The history has a write skew and a read skew."""
        history = write_skew()
        reader = invoke_txn(history, 2, read_of("a", None), read_of("b", None))
        writer = invoke_txn(history, 3, append("a", 1), append("b", 2))
        writer.ok([append("a", 1), append("b", 2)])
        reader.ok([read_of("a", []), read_of("b", [2])])
        check.equal(
            seat, cycle_of(history, "G-single"), [4, 5], "the cycle is the read skew"
        )
