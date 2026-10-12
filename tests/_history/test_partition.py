"""The spec of _history/partition.py tests the calls of a history and their partitions.

The reference implementation of the definition gives the same partitions.
"""

from __future__ import annotations

from dokimi_assert import check
from dokimi_assert._history.history import History, recorded
from dokimi_assert._history.partition import (
    Checked,
    Partition,
    calls_of,
    concurrency,
    partitions_of,
    span_json,
)
from dokimi_assert.seat import Collector


def calls(history: History) -> list[Checked]:
    """Return the calls of a history."""
    events, ids = recorded(history)
    return calls_of(events, ids)


def grouped(history: History) -> list[list[int]]:
    """Return the invocations of the calls of each partition of a history."""
    return [[c.span.call for c in p.calls] for p in partitions_of(calls(history))]


class TestCallsOf:
    """calls_of returns the calls of a history that a check reads."""

    def test_returns_each_call_that_did_not_fail(self, seat: Collector) -> None:
        """The history has an ok, a failed, an unknown and a pending call."""
        history = History()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(1, "write", [2], "x").fail("refused")
        history.invoke(2, "write", [3], "x").unknown("lost")
        history.invoke(3, "read", [], "x")
        check.equal(
            seat,
            [
                (c.span.call, c.span.completion, c.span.operation.known)
                for c in calls(history)
            ],
            [(0, 1, True), (4, 5, False), (6, None, False)],
            "calls_of leaves out the failed call",
        )

    def test_returns_the_output_of_a_known_call_alone(self, seat: Collector) -> None:
        """The read returns 3. The write ends without an outcome."""
        history = History()
        history.invoke(0, "read", [], "x").ok(3)
        history.invoke(1, "write", [2], "x").unknown(4)
        check.equal(
            seat,
            [c.span.operation.output for c in calls(history)],
            [3, None],
            "only the known read has an output",
        )

    def test_returns_the_keys_of_each_call_with_their_identities(
        self, seat: Collector
    ) -> None:
        """The write touches x and y."""
        history = History()
        history.invoke(0, "write", [1], "x", "y")
        call = calls(history)[0]
        check.equal(
            seat,
            [call.keys, call.ids],
            [
                ("x", "y"),
                ('{"type":"string","value":"x"}', '{"type":"string","value":"y"}'),
            ],
            "the call has both keys and their identities",
        )


class TestPartition:
    """Partition is a group of calls that share keys."""

    def test_keeps_its_fields(self, seat: Collector) -> None:
        """The partition of every key is empty."""
        check.equal(
            seat,
            [Partition((), ()).keys, Partition((), ()).calls],
            [(), ()],
            "the partition keeps its fields",
        )


class TestPartitionsOf:
    """partitions_of returns the partitions of the calls of a history."""

    def test_returns_an_empty_list_without_calls(self, seat: Collector) -> None:
        """The list of calls is empty."""
        check.is_empty(seat, partitions_of([]), "the history does not have a partition")

    def test_returns_one_partition_of_every_key_for_a_call_without_keys(
        self, seat: Collector
    ) -> None:
        """The read of client 1 does not have keys."""
        history = History()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(1, "read", []).ok(1)
        partition = partitions_of(calls(history))[0]
        check.equal(
            seat,
            [partition.keys, len(partition.calls)],
            [(), 2],
            "the two calls form one partition of every key",
        )

    def test_joins_the_calls_that_share_a_key_in_the_order_of_their_first_invocation(
        self, seat: Collector
    ) -> None:
        """The first call touches y. The second call touches x."""
        history = History()
        history.invoke(0, "write", [1], "y").ok(None)
        history.invoke(1, "read", [], "x").ok(None)
        history.invoke(2, "write", [2], "x", "z").ok(None)
        history.invoke(3, "read", [], "y").ok(1)
        check.equal(
            seat,
            grouped(history),
            [[0, 6], [2, 4]],
            "the partition of y comes before the partition of x and z",
        )

    def test_lists_the_keys_of_a_partition_in_the_order_of_the_history(
        self, seat: Collector
    ) -> None:
        """The read of x comes before the write of y and x."""
        history = History()
        history.invoke(0, "read", [], "x").ok(None)
        history.invoke(1, "write", [2], "y", "x").ok(None)
        check.equal(
            seat,
            partitions_of(calls(history))[0].keys,
            ("x", "y"),
            "the keys are x and then y",
        )

    def test_joins_two_partitions_through_a_later_call_on_both_keys(
        self, seat: Collector
    ) -> None:
        """The write touches both keys after the reads."""
        history = History()
        history.invoke(0, "read", [], "x").ok(None)
        history.invoke(1, "read", [], "y").ok(None)
        history.invoke(2, "write", [1], "y", "x").ok(None)
        check.equal(
            seat, grouped(history), [[0, 2, 4]], "the three calls form one partition"
        )


class TestConcurrency:
    """concurrency returns the most calls that are open at one event."""

    def test_returns_the_most_calls_that_are_open_at_one_event(
        self, seat: Collector
    ) -> None:
        """The two writes overlap."""
        history = History()
        a = history.invoke(0, "write", [1], "x")
        b = history.invoke(1, "write", [2], "x")
        a.ok(None)
        history.invoke(0, "read", [], "x").ok(1)
        b.ok(None)
        check.equal(seat, concurrency(calls(history)), 2, "two calls are open at once")

    def test_counts_a_call_that_is_not_known_as_open_to_the_end_of_the_history(
        self, seat: Collector
    ) -> None:
        """The unknown write overlaps each later read."""
        history = History()
        history.invoke(0, "write", [1], "x").unknown("lost")
        history.invoke(0, "read", [], "x").ok(1)
        history.invoke(1, "read", [], "x").ok(1)
        check.equal(
            seat, concurrency(calls(history)), 2, "the write is open with each read"
        )

    def test_returns_0_without_calls(self, seat: Collector) -> None:
        """The list of calls is empty."""
        check.equal(seat, concurrency([]), 0, "concurrency is 0")


class TestSpanJson:
    """span_json returns a call in the JSON form of the history."""

    def test_returns_a_known_call_with_its_output(self, seat: Collector) -> None:
        """The write completes as ok."""
        history = History()
        history.invoke(0, "write", [1], "x").ok(None)
        check.equal(
            seat,
            span_json(calls(history)[0].span),
            {
                "call": 0,
                "completion": 1,
                "process": 0,
                "operation": "write",
                "args": [{"type": "int", "value": 1}],
                "output": {"type": "null"},
            },
            "the JSON has the completion and the output",
        )

    def test_returns_a_pending_call_without_a_completion(self, seat: Collector) -> None:
        """The read does not complete."""
        history = History()
        history.invoke(0, "read", [], "x")
        check.equal(
            seat,
            span_json(calls(history)[0].span),
            {"call": 0, "process": 0, "operation": "read", "args": []},
            "the JSON has only the invocation",
        )

    def test_returns_a_call_whose_outcome_is_unknown_without_an_output(
        self, seat: Collector
    ) -> None:
        """The read completes as unknown."""
        history = History()
        history.invoke(0, "read", [], "x").unknown("lost")
        check.equal(
            seat,
            span_json(calls(history)[0].span),
            {"call": 0, "completion": 1, "process": 0, "operation": "read", "args": []},
            "the JSON does not have an output",
        )
