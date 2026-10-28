# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _record/calls.py tests the numbering of call records.

The records are the verdicts of the conformance runner, so this spec checks
its verdicts with the assert statement of pytest.
"""

from __future__ import annotations

import json
from typing import Any, cast

from dokimi_assert import check, prop
from dokimi_assert._record.call import Call
from dokimi_assert._record.calls import (
    Calls,
    Slot,
    add,
    calls_of,
    cut,
    keep,
    lines,
    own,
    run,
    write,
)
from dokimi_assert.call import Call as ObservedCall
from dokimi_assert.seat import Recorder, fault


class Seat:
    """An object in the role of a seat of the library."""


def call(contract: str) -> Call:
    """Return a passing call of true with contract."""
    return Call("true", contract, "pass", True)


def decoded(calls: Calls) -> list[dict[str, Any]]:
    """Return the decoded records that calls keep."""
    return [json.loads(line) for line in lines(calls)]


class TestOwn:
    """own returns the calls of a seat."""

    def test_returns_one_set_of_calls_per_seat(self) -> None:
        """A seat has one set of calls."""
        seat = Seat()
        assert own(seat) is own(seat)

    def test_returns_calls_that_are_off_at_first(self) -> None:
        """New calls are off."""
        assert own(Seat()).state == "off"


class TestCallsOf:
    """calls_of returns the calls that record a call on a seat."""

    def test_returns_none_for_a_seat_of_another_library(self) -> None:
        """A seat that own did not see does not have calls."""
        assert calls_of(Seat()) is None

    def test_returns_none_for_a_seat_that_cannot_be_a_key(self) -> None:
        """An unhashable seat does not have calls."""
        assert calls_of([]) is None

    def test_returns_none_for_calls_that_are_off(self) -> None:
        """Calls that are off do not record."""
        seat = Seat()
        own(seat)
        assert calls_of(seat) is None

    def test_returns_the_calls_of_a_recorder(self) -> None:
        """calls_of returns the calls that keep their records."""
        seat = Seat()
        keep(own(seat))
        assert calls_of(seat) is own(seat)


class TestKeep:
    """keep makes calls the calls of a recorder."""

    def test_numbers_each_record_from_1(self) -> None:
        """The calls of a recorder number their records in order."""
        calls = Calls()
        keep(calls)
        add(calls, call("a"))
        add(calls, call("b"))
        assert [(r["seq"], r["contract"]) for r in decoded(calls)] == [
            (1, "a"),
            (2, "b"),
        ]

    def test_drops_what_the_calls_kept_before(self) -> None:
        """The calls of a recorder start over."""
        calls = Calls()
        keep(calls)
        add(calls, call("a"))
        keep(calls)
        add(calls, call("b"))
        assert [(r["seq"], r["contract"]) for r in decoded(calls)] == [(1, "b")]


class TestWrite:
    """write makes calls the calls of a test."""

    def test_writes_each_record_through_the_sink(self) -> None:
        """The calls of a test write their records and do not keep them."""
        written: list[tuple[int, str]] = []
        calls = Calls()
        write(calls, lambda seq, line: written.append((seq, line)))
        add(calls, call("a"))
        assert [seq for seq, _ in written] == [1]
        assert json.loads(written[0][1])["contract"] == "a"
        assert lines(calls) == []


class TestLines:
    """lines returns the records that the calls of a recorder keep."""

    def test_returns_no_line_for_a_call_that_still_runs_a_body(self) -> None:
        """The call of a slot has a line once it writes its record."""
        seat = Seat()
        keep(own(seat))
        slot = Slot.begin(seat)
        add(own(seat), call("after"))
        assert slot is not None
        assert [(r["seq"], r["contract"]) for r in decoded(own(seat))] == [(2, "after")]


class TestAdd:
    """add puts a call among the calls of its seat."""

    def test_drops_a_call_on_calls_that_are_off(self) -> None:
        """Calls that are off drop a call."""
        calls = Calls()
        add(calls, call("a"))
        assert (calls.next, lines(calls)) == (0, [])


class TestRun:
    """run makes calls the calls of one run of a body."""

    def test_turns_off_the_body_of_a_call_that_is_not_recorded(self) -> None:
        """The body of a call without a slot does not record."""
        body = Calls()
        run(body, None)
        add(body, call("in the body"))
        assert body.state == "off"
        assert body.entries == []

    def test_records_the_position_of_each_call_of_a_run(self) -> None:
        """A run records the steps that its case walked at each call."""
        body = Calls()
        steps = iter([3, 5])
        seat = Seat()
        keep(own(seat))
        run(body, Slot.begin(seat), lambda: next(steps))
        add(body, call("at step 3"))
        add(body, call("at step 5"))
        assert [entry.steps for entry in body.entries] == [3, 5]

    def test_records_position_0_without_a_position(self) -> None:
        """A run without a position records its calls at step 0."""
        body = Calls()
        seat = Seat()
        keep(own(seat))
        run(body, Slot.begin(seat))
        add(body, call("a"))
        assert [entry.steps for entry in body.entries] == [0]


class TestCut:
    """cut keeps the calls of a run before the step at which its case stops."""

    def test_drops_the_calls_at_the_step_or_after_it(self) -> None:
        """A run on one worker does not make those calls."""
        body = Calls()
        steps = iter([3, 4, 5])
        seat = Seat()
        keep(own(seat))
        run(body, Slot.begin(seat), lambda: next(steps))
        add(body, call("at step 3"))
        add(body, call("at step 4"))
        add(body, call("at step 5"))
        cut(body, 4)
        assert [entry.steps for entry in body.entries] == [3]


class TestSlotBegin:
    """Slot.begin starts the record of a call that runs a body."""

    def test_returns_no_slot_for_a_call_that_is_not_recorded(self) -> None:
        """A seat that does not record does not have a slot."""
        assert Slot.begin(Seat()) is None

    def test_numbers_the_call_before_the_calls_after_it(self) -> None:
        """The call takes its number when it begins."""
        seat = Seat()
        keep(own(seat))
        slot = Slot.begin(seat)
        add(own(seat), call("after"))
        assert slot is not None
        slot.write(call("outer"))
        assert [(r["seq"], r["contract"]) for r in decoded(own(seat))] == [
            (1, "outer"),
            (2, "after"),
        ]


class TestSlotTake:
    """Slot.take takes the next run of the body of a slot."""

    def test_numbers_the_calls_of_a_body_after_the_call_that_ran_it(self) -> None:
        """The record of each call of a run has its parent, its run and its phase."""
        seat = Seat()
        keep(own(seat))
        slot = Slot.begin(seat)
        assert slot is not None
        body = Calls()
        run(body, slot)
        add(body, call("first run"))
        slot.take(body)
        add(body, call("second run"))
        slot.take(body, "shrink")
        slot.write(Call("eventually", "outer", "pass", True))
        stated = [
            (r["seq"], r.get("parent"), r.get("run"), r.get("phase"), r["contract"])
            for r in decoded(own(seat))
        ]
        assert stated == [
            (1, None, None, None, "outer"),
            (2, 1, 1, None, "first run"),
            (3, 1, 2, "shrink", "second run"),
        ]

    def test_keeps_the_parent_of_a_call_of_a_body_inside_a_run(self) -> None:
        """A call of an inner body keeps the call that ran the inner body."""
        seat = Seat()
        keep(own(seat))
        outer = Slot.begin(seat)
        assert outer is not None
        outer_seat = Seat()
        run(own(outer_seat), outer)
        inner = Slot.begin(outer_seat)
        assert inner is not None
        inner_seat = Seat()
        run(own(inner_seat), inner)
        add(own(inner_seat), call("in the inner body"))
        inner.take(own(inner_seat))
        inner.write(Call("eventually", "inner", "pass", True))
        outer.take(own(outer_seat))
        outer.write(Call("rejects", "outer", "pass", True))
        stated = [
            (r["seq"], r.get("parent"), r["contract"]) for r in decoded(own(seat))
        ]
        assert stated == [
            (1, None, "outer"),
            (2, 1, "inner"),
            (3, 2, "in the inner body"),
        ]


class Watching:
    """A seat of another library that observes each assertion call."""

    def __init__(self) -> None:
        """Return a seat that has observed nothing."""
        self.seen: list[ObservedCall] = []

    def observe_call(self, call: ObservedCall) -> None:
        """Keep call.

        Args:
            call: The assertion call.
        """
        self.seen.append(call)


class KeepingWatching(Watching):
    """A seat of this library that keeps its records and observes each call."""


class TestObserve:
    """The observe_call member of a seat receives each assertion call."""

    def test_receives_a_call_on_a_seat_that_records_nothing(self) -> None:
        """calls_of returns calls that pass each call to the seat."""
        seat = Watching()
        calls = calls_of(seat)
        assert calls is not None
        add(calls, Call("equal", "the totals match", "fail", True))
        assert seat.seen == [ObservedCall("equal", "the totals match")]

    def test_receives_a_call_once_on_a_seat_that_keeps_its_records(self) -> None:
        """The seat observes the call, and its calls keep the record."""
        seat = KeepingWatching()
        keep(own(seat))
        add(cast("Calls", calls_of(seat)), call("kept"))
        assert [c.contract for c in seat.seen] == ["kept"]
        assert [r["contract"] for r in decoded(own(seat))] == ["kept"]

    def test_receives_the_calls_of_a_body_when_the_call_takes_them(self) -> None:
        """The calls of a run, and then the call that ran the body."""
        seat = Watching()
        slot = Slot.begin(seat)
        assert slot is not None
        body = Calls()
        run(body, slot)
        add(body, call("in the body"))
        assert seat.seen == []
        slot.take(body, "random")
        slot.write(Call("prop-for-all", "it holds", "pass", True))
        assert [c.contract for c in seat.seen] == ["in the body", "it holds"]

    def test_receives_the_calls_of_a_body_once_on_a_seat_that_keeps_them(
        self,
    ) -> None:
        """Each call reaches the seat once, and the calls keep every record."""
        seat = KeepingWatching()
        keep(own(seat))
        slot = Slot.begin(seat)
        assert slot is not None
        body = Calls()
        run(body, slot)
        add(body, call("in the body"))
        slot.take(body)
        slot.write(Call("eventually", "it converges", "pass", True))
        assert [c.contract for c in seat.seen] == ["in the body", "it converges"]
        assert len(decoded(own(seat))) == 2

    def test_receives_the_calls_in_the_cases_of_a_property_then_the_property(
        self,
    ) -> None:
        """A recorder that observes receives every call of a run of a property."""
        seat = ObservingRecorder()

        def small(c: prop.Case) -> None:
            check.is_true(c, c.draw(prop.integer(0, 9), "x") < 10, "x is small")

        prop.for_all(seat, "every x is small", small, prop.seed(7), prop.cases(3))
        contracts = [c.contract for c in seat.seen]
        assert contracts[-1] == "every x is small"
        assert "x is small" in contracts[:-1]

    def test_does_not_receive_a_call_of_fault(self) -> None:
        """A fault ends the call of a helper and not an assertion call."""
        seat = ObservingRecorder()
        fault(seat, ValueError("the check misses an option"))
        assert seat.seen == []


class ObservingRecorder(Recorder):
    """A recorder that also observes each assertion call."""

    def __init__(self) -> None:
        """Return a recorder that has observed nothing."""
        super().__init__()
        self.seen: list[ObservedCall] = []

    def observe_call(self, call: ObservedCall) -> None:
        """Keep call.

        Args:
            call: The assertion call.
        """
        self.seen.append(call)


class TestSlotWrite:
    """Slot.write ends the call of a slot with its record."""

    def test_writes_a_record_of_a_test_through_the_sink(self) -> None:
        """A slot of a test writes its record when it ends."""
        written: list[int] = []
        seat = Seat()
        write(own(seat), lambda seq, _line: written.append(seq))
        slot = Slot.begin(seat)
        assert slot is not None
        slot.write(call("outer"))
        assert written == [1]
