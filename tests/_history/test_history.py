"""The spec of _history/history.py tests the recording of a history.

The reference implementation of the definition gives the same orders and the
same processes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from dokimi_assert import check
from dokimi_assert._history.event import Completion, Invocation
from dokimi_assert._history.history import Call, History, identity_of, recorded
from dokimi_assert.seat import Collector
from helpers import refusal


@dataclass(frozen=True)
class AB:
    """A record whose fields are a and then b."""

    a: int
    b: int


@dataclass(frozen=True)
class BA:
    """A record whose fields are b and then a."""

    b: int
    a: int


class TestIdentityOf:
    """identity_of returns the identity of a key or a value."""

    def test_returns_one_identity_for_two_maps_of_equal_entries_in_another_order(
        self, seat: Collector
    ) -> None:
        """The order of the entries of a nested map does not matter either."""
        a = {"x": {1: "one", 2: "two"}, "y": 2}
        b = {"y": 2, "x": {2: "two", 1: "one"}}
        check.equal(
            seat, identity_of([a]), identity_of([b]), "the two lists have one identity"
        )

    def test_returns_two_identities_for_records_with_their_fields_in_two_orders(
        self, seat: Collector
    ) -> None:
        """The order of the fields of a record matters."""
        check.not_equal(
            seat,
            identity_of(AB(1, 2)),
            identity_of(BA(2, 1)),
            "the records have two identities",
        )

    def test_returns_two_identities_for_a_float_and_an_int_of_one_value(
        self, seat: Collector
    ) -> None:
        """The type of a number matters."""
        check.not_equal(
            seat, identity_of(1.0), identity_of(1), "1.0 and 1 have two identities"
        )

    def test_returns_none_for_a_value_without_a_typed_literal(
        self, seat: Collector
    ) -> None:
        """An object does not have a typed literal."""
        check.is_none(
            seat, identity_of(object()), "an object does not have an identity"
        )


class TestHistory:
    """History records the events of one history in recording order."""

    def test_starts_without_events(self, seat: Collector) -> None:
        """A new history does not have events."""
        check.is_empty(seat, History().events(), "the new history is empty")


class TestHistoryInvoke:
    """History.invoke records the invocation of a call."""

    def test_numbers_the_processes_in_the_order_of_their_first_invocations(
        self, seat: Collector
    ) -> None:
        """Client 7 moves to process 2 after its unknown call."""
        history = History()
        first = history.invoke(7, "read", [])
        second = history.invoke(3, "read", [])
        second.ok(None)
        first.unknown("lost")
        history.invoke(3, "read", []).ok(None)
        history.invoke(7, "read", [])
        check.equal(
            seat,
            [(event.client, event.process) for event in history.events()],
            [(7, 0), (3, 1), (3, 1), (7, 0), (3, 1), (3, 1), (7, 2)],
            "client 7 moves to process 2 after its unknown call",
        )

    def test_records_the_invocation_of_a_call(self, seat: Collector) -> None:
        """The write of 1 touches x and y."""
        history = History()
        history.invoke(0, "write", [1], "x", "y")
        check.equal(
            seat,
            history.events(),
            [Invocation(0, 0, 0, 0, "write", (1,), ("x", "y"))],
            "the history has the one invocation",
        )

    def test_raises_runtime_error_for_a_second_open_call_of_one_client(
        self, seat: Collector
    ) -> None:
        """Client 0 already has an open call."""
        history = History()
        history.invoke(0, "read", [])
        check.equal(
            seat,
            refusal(seat, lambda: history.invoke(0, "read", []), RuntimeError),
            'history: invoke(0, "read") while call 0 of client 0 is open',
            "the text of the refusal has the open call",
        )

    def test_raises_type_error_for_a_key_without_a_typed_literal(
        self, seat: Collector
    ) -> None:
        """An object does not have a typed literal."""
        key = object()
        check.equal(
            seat,
            refusal(seat, lambda: History().invoke(0, "read", [], key), TypeError),
            f'history: the key {key!r} of invoke(0, "read") does not have a typed '
            "literal",
            "the text of the refusal has the key",
        )


class TestHistoryEvents:
    """History.events returns the recorded events in recording order."""

    def test_gives_each_event_the_index_of_the_invocation_of_its_call(
        self, seat: Collector
    ) -> None:
        """Call 1 completes before call 0."""
        history = History()
        a = history.invoke(0, "write", [1], "x")
        b = history.invoke(1, "write", [2], "x")
        b.ok(None)
        a.ok(None)
        check.equal(
            seat,
            [event.call for event in history.events()],
            [0, 1, 1, 0],
            "each event has the index of the invocation of its call",
        )

    def test_returns_a_copy_that_a_later_event_does_not_change(
        self, seat: Collector
    ) -> None:
        """The earlier copy is still empty."""
        history = History()
        events = history.events()
        history.invoke(0, "read", [])
        check.is_empty(seat, events, "the earlier copy is still empty")


class TestCall:
    """Call records the completion of an open call."""

    def test_calls_the_function_with_each_completion(self, seat: Collector) -> None:
        """The call completes as ok, as fail and as unknown."""
        completed: list[tuple[str, Any]] = []
        call = Call(lambda kind, value: completed.append((kind, value)))
        call.ok(1)
        call.fail("e")
        call.unknown("u")
        check.equal(
            seat,
            completed,
            [("ok", 1), ("fail", "e"), ("unknown", "u")],
            "the function receives the three completions",
        )


class TestCallOk:
    """Call.ok records that a call returned an output and took effect."""

    def test_records_the_output_of_the_call(self, seat: Collector) -> None:
        """The read returns 5."""
        history = History()
        history.invoke(0, "read", []).ok(5)
        check.equal(
            seat,
            history.events()[1],
            Completion(1, "ok", 0, 0, 0, output=5),
            "the completion has the output 5",
        )

    def test_raises_runtime_error_for_a_call_that_has_completed(
        self, seat: Collector
    ) -> None:
        """The client has opened another call."""
        history = History()
        call = history.invoke(0, "read", [])
        call.ok(1)
        history.invoke(0, "read", [])
        check.equal(
            seat,
            refusal(seat, lambda: call.ok(1), RuntimeError),
            "history: call 0 completes a second time",
            "the text of the refusal has the call",
        )


class TestCallFail:
    """Call.fail records that a call did not take effect."""

    def test_records_the_error_of_the_call_on_the_same_process(
        self, seat: Collector
    ) -> None:
        """The client continues on process 0."""
        history = History()
        history.invoke(0, "write", [1]).fail("refused")
        history.invoke(0, "read", [])
        check.equal(
            seat,
            [(event.kind, event.process) for event in history.events()],
            [("invoke", 0), ("fail", 0), ("invoke", 0)],
            "the client continues on process 0",
        )

    def test_raises_runtime_error_for_a_call_that_has_completed(
        self, seat: Collector
    ) -> None:
        """The call completed as unknown."""
        history = History()
        call = history.invoke(0, "read", [])
        call.unknown("lost")
        check.equal(
            seat,
            refusal(seat, lambda: call.fail("e"), RuntimeError),
            "history: call 0 completes a second time",
            "the text of the refusal has the call",
        )


class TestCallUnknown:
    """Call.unknown records that a call ended without an outcome."""

    def test_records_the_error_of_the_call(self, seat: Collector) -> None:
        """The write times out."""
        history = History()
        history.invoke(0, "write", [1]).unknown("timed out")
        check.equal(
            seat,
            history.events()[1],
            Completion(1, "unknown", 0, 0, 0, error="timed out"),
            "the completion has the error",
        )

    def test_raises_runtime_error_for_a_call_that_has_completed(
        self, seat: Collector
    ) -> None:
        """The call failed."""
        history = History()
        call = history.invoke(0, "read", [])
        call.fail("refused")
        check.equal(
            seat,
            refusal(seat, lambda: call.unknown("e"), RuntimeError),
            "history: call 0 completes a second time",
            "the text of the refusal has the call",
        )


class TestRecorded:
    """recorded returns the events of a history and the identities of their keys."""

    def test_returns_the_identities_of_the_keys_of_each_event(
        self, seat: Collector
    ) -> None:
        """The invocation has the key x. The completion does not have a key."""
        history = History()
        history.invoke(0, "write", [1], "x").ok(None)
        events, ids = recorded(history)
        check.equal(
            seat,
            [len(events), ids],
            [2, [('{"type":"string","value":"x"}',), ()]],
            "the completion has an empty tuple of identities",
        )
