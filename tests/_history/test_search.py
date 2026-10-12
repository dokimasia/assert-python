"""The spec of _history/search.py tests the search of one partition.

Each verdict, each count of steps and each frontier of the spec matches the
reference implementation of the definition on the same calls and spec.
"""

from __future__ import annotations

import math
import time
from collections.abc import Hashable, Sequence
from typing import Any, ClassVar, NoReturn

import pytest

from dokimi_assert import check
from dokimi_assert._history.history import History, recorded
from dokimi_assert._history.option import Option, budget, configure, memo_limit
from dokimi_assert._history.option import time_limit as time_limited
from dokimi_assert._history.partition import Span, calls_of
from dokimi_assert._history.search import Deadline, Ending, Search, SpecError, Verdict
from dokimi_assert._history.spec import CallOperation, Operation, Spec, spec_from
from dokimi_assert.option import equate_nans
from dokimi_assert.seat import Collector
from helpers import REGISTER, Register


def searched(history: History, spec: Spec[Any], *options: Option) -> Ending[Any]:
    """Return the ending of the search of every call of a history against spec."""
    events, ids = recorded(history)
    config = configure(options)
    return Search(
        calls_of(events, ids), spec, config, Deadline(config.time_limit)
    ).run()


def write_then_read() -> History:
    """Return a write of 1 and a later read of 1 by another client."""
    history = History()
    history.invoke(0, "write", [1], "x").ok(None)
    history.invoke(1, "read", [], "x").ok(1)
    return history


def writes(value: object) -> History:
    """Return two concurrent writes of value and a later read of 5."""
    history = History()
    first = history.invoke(0, "write", [value], "x")
    second = history.invoke(1, "write", [value], "x")
    first.ok(None)
    second.ok(None)
    history.invoke(0, "read", [], "x").ok(5)
    return history


def ending(
    outcome: Verdict,
    steps: int,
    linearized: tuple[int, ...],
    states: tuple[Any, ...],
    candidates: tuple[int, ...],
) -> Ending[Any]:
    """Return an ending without a limit."""
    return Ending(outcome, steps, linearized, states, candidates, None)


class Lock:
    """A lock that acquire(c) takes for c and release(c) frees."""

    def initial(self) -> object:
        """Return a free lock."""
        return None

    def next(self, state: object, op: Operation) -> list[object]:
        """Return the holder after op. The list is empty when the lock refuses op."""
        client = op.args[0]
        if op.name == "acquire":
            return [client] if state is None else []
        return [None] if state == client else []


class Lossy(Register):
    """A register that can lose a write. A write leaves the new or the old value."""

    def next(self, state: object, op: Operation) -> list[object]:
        """Return the new value and the old value after a write."""
        if op.name == "write":
            return [op.args[0], state]
        return super().next(state, op)


class Paths:
    """A spec of three operations. The operations a and b step 0 to other states.

    The operation c fails. Every state has one key.
    """

    #: The states after a and b. A state without an entry steps to itself.
    after: ClassVar[dict[str, dict[int, list[int]]]] = {
        "a": {0: [1, 2], 5: [1]},
        "b": {0: [5]},
    }

    def initial(self) -> int:
        """Return 0."""
        return 0

    def next(self, state: int, op: Operation) -> list[int]:
        """Return the states after op."""
        if op.name == "c":
            return []
        return self.after[op.name].get(state, [state])

    def key(self, state: int) -> Hashable:
        """Return one key for every state."""
        del state
        return "0"


class Parity:
    """A register that compares its values by their parity."""

    def initial(self) -> int:
        """Return 0."""
        return 0

    def next(self, state: int, op: Operation) -> list[int]:
        """Return the value of a write and 2. A read of the parity keeps the state."""
        if op.name == "write":
            return [op.args[0], 2]
        return [state] if op.returned(state % 2) else []

    def equal(self, a: int, b: int) -> bool:
        """Report whether two values have the same parity."""
        return a % 2 == b % 2

    def key(self, state: int) -> Hashable:
        """Return the parity of a value."""
        return state % 2


def counter() -> Any:
    """Return a counter subject. Its add adds the argument and returns the total."""
    total = [0]

    def apply(_: str, args: Sequence[Any]) -> int:
        total[0] += args[0]
        return total[0]

    return apply


def boom(*_: object) -> NoReturn:
    """Raise ValueError for any arguments."""
    raise ValueError("boom")


class BrokenInitial(Register):
    """A register whose initial raises."""

    def initial(self) -> object:
        """Raise ValueError."""
        return boom()


class BrokenNext(Register):
    """A register whose next raises."""

    def next(self, state: object, op: Operation) -> list[object]:
        """Raise ValueError."""
        return boom(state, op)


class BrokenEqual(Register):
    """A register whose next returns two states and whose equal raises."""

    def next(self, state: object, op: Operation) -> list[object]:
        """Return 1 and 2."""
        del state, op
        return [1, 2]

    def equal(self, a: object, b: object) -> bool:
        """Raise ValueError."""
        return boom(a, b)


class BrokenKey(Register):
    """A register whose key raises."""

    def key(self, state: object) -> Hashable:
        """Raise ValueError."""
        return boom(state)


class TestEnding:
    """Ending is the verdict of the search of one partition and its frontier."""

    def test_keeps_its_fields(self, seat: Collector) -> None:
        """The search passed in two steps."""
        done = Ending("passed", 2, (), (1,), (), None)
        check.equal(
            seat,
            [done.outcome, done.steps, done.states, done.limit],
            ["passed", 2, (1,), None],
            "the ending keeps its fields",
        )


class TestDeadline:
    """Deadline is the deadline of a check and the signal that the check stopped."""

    def test_does_not_pass_without_a_limit(self, seat: Collector) -> None:
        """A deadline of 0 seconds does not set a limit."""
        check.is_false(seat, Deadline(0).passed(), "the time has not passed")

    def test_passes_once_the_check_has_stopped(self, seat: Collector) -> None:
        """The check stopped its searches."""
        deadline = Deadline(0)
        deadline.stopped.set()
        check.is_true(seat, deadline.passed(), "the deadline has passed")


class TestSpecError:
    """SpecError is the error of a function of a spec that raised during a search."""

    def test_records_the_stepped_call(self, seat: Collector) -> None:
        """The function next raises for the read at call 4."""
        cause = ValueError("boom")
        span = Span(4, None, 0, CallOperation("read", (), True, 1))
        error = SpecError("next", span, cause)
        check.equal(
            seat,
            [str(error), error.fn, error.call, error.__cause__],
            ['the function next of the spec raises for "read"', "next", 4, cause],
            "the error has the text, the function, the call and the cause",
        )

    def test_omits_the_call_before_the_first_step(self, seat: Collector) -> None:
        """The function initial raises before the first step."""
        error = SpecError("initial", None, ValueError("boom"))
        check.equal(
            seat,
            [str(error), error.call],
            ["the function initial of the spec raises", None],
            "the error does not have a call",
        )


class TestSearchRun:
    """Search.run searches a partition and returns its ending."""

    def test_returns_a_pass_with_the_states_after_the_order_that_it_found(
        self, seat: Collector
    ) -> None:
        """The read of 1 follows the write of 1."""
        check.equal(
            seat,
            searched(write_then_read(), REGISTER),
            ending("passed", 2, (), (1,), ()),
            "the pass ends in the state 1",
        )

    def test_returns_the_frontier_of_a_violation(self, seat: Collector) -> None:
        """The read of 2 follows the write of 1."""
        history = History()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(1, "read", [], "x").ok(2)
        check.equal(
            seat,
            searched(history, REGISTER),
            ending("violated", 2, (0,), (1,), (1,)),
            "the read is the candidate after the write",
        )

    def test_backtracks_to_try_another_order_of_two_concurrent_calls(
        self, seat: Collector
    ) -> None:
        """The read of 1 needs the write of 2 first."""
        history = History()
        first = history.invoke(0, "write", [1], "x")
        second = history.invoke(1, "write", [2], "x")
        first.ok(None)
        second.ok(None)
        history.invoke(0, "read", [], "x").ok(1)
        done = searched(history, REGISTER)
        check.equal(
            seat,
            [done.outcome, done.steps],
            ["passed", 6],
            "the search passes at the sixth step",
        )

    def test_lists_only_the_candidates_that_the_spec_rejects_at_the_frontier(
        self, seat: Collector
    ) -> None:
        """The read of 3 fails after both writes."""
        history = History()
        first = history.invoke(0, "write", [1], "x")
        second = history.invoke(1, "write", [2], "x")
        reader = history.invoke(2, "read", [], "x")
        first.ok(None)
        second.ok(None)
        reader.ok(3)
        check.equal(
            seat,
            searched(history, REGISTER),
            ending("violated", 9, (0, 1), (2,), (2,)),
            "the read is the one candidate",
        )

    def test_passes_a_write_whose_outcome_is_unknown_that_takes_effect_later(
        self, seat: Collector
    ) -> None:
        """The lost write takes effect between the reads."""
        history = History()
        history.invoke(0, "write", [1], "x").ok(None)
        lost = history.invoke(1, "write", [2], "x")
        history.invoke(0, "read", [], "x").ok(1)
        lost.unknown("timed out")
        history.invoke(0, "read", [], "x").ok(2)
        check.equal(
            seat,
            searched(history, REGISTER),
            ending("passed", 6, (), (2,), ()),
            "the lost write takes effect",
        )

    def test_passes_a_call_whose_outcome_is_unknown_that_never_takes_effect(
        self, seat: Collector
    ) -> None:
        """Client 0 has the lock."""
        history = History()
        history.invoke(0, "acquire", [0], "lock").ok(None)
        history.invoke(1, "acquire", [1], "lock").unknown("timed out")
        history.invoke(2, "acquire", [2], "lock")
        check.equal(
            seat,
            searched(history, Lock()),
            ending("passed", 1, (), (0,), ()),
            "client 0 has the lock",
        )

    def test_passes_a_pending_write_that_a_later_read_needs(
        self, seat: Collector
    ) -> None:
        """The pending write takes effect before the read."""
        history = History()
        history.invoke(0, "write", [1], "x")
        history.invoke(1, "read", [], "x").ok(1)
        check.equal(
            seat,
            searched(history, REGISTER),
            ending("passed", 2, (), (1,), ()),
            "the pending write takes effect",
        )

    def test_backtracks_over_a_call_whose_outcome_is_unknown(
        self, seat: Collector
    ) -> None:
        """Every order of the writes fails the read of 9."""
        history = History()
        history.invoke(0, "write", [1], "x")
        history.invoke(1, "write", [2], "x").unknown("timed out")
        history.invoke(2, "read", [], "x").ok(9)
        check.equal(
            seat,
            searched(history, REGISTER),
            ending("violated", 9, (0, 1), (2,), (2,)),
            "every order of the writes fails the read of 9",
        )

    def test_keeps_one_of_each_group_of_equal_states(self, seat: Collector) -> None:
        """A lossy write leaves 1 or None."""
        history = History()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(0, "read", [], "x").ok(7)
        check.equal(
            seat,
            searched(history, Lossy()),
            ending("violated", 5, (0, 1), (1, None), (2,)),
            "the frontier has the states 1 and None",
        )

    def test_skips_a_configuration_that_the_memo_contains(
        self, seat: Collector
    ) -> None:
        """The second order of the writes is skipped."""
        check.equal(
            seat,
            searched(writes(1), REGISTER),
            ending("violated", 5, (0, 1), (1,), (2,)),
            "the second order is skipped",
        )

    def test_does_not_merge_a_state_that_is_nan(self, seat: Collector) -> None:
        """The second order of the writes is searched."""
        check.equal(
            seat,
            searched(writes(math.nan), REGISTER),
            ending("violated", 6, (0, 1), (math.nan,), (2,)),
            "the second order is searched",
            equate_nans(),
        )

    def test_merges_two_lists_of_states_only_at_one_length(
        self, seat: Collector
    ) -> None:
        """The operations a and b leave lists of different lengths."""
        history = History()
        a = history.invoke(0, "a", [], "x")
        b = history.invoke(1, "b", [], "x")
        a.ok(None)
        b.ok(None)
        history.invoke(2, "c", [], "x").ok(None)
        check.equal(
            seat,
            searched(history, Paths()),
            ending("violated", 8, (0, 1), (1, 2), (2,)),
            "the search takes eight steps",
        )

    def test_counts_a_step_of_a_spec_of_a_subject_as_its_depth_plus_one(
        self, seat: Collector
    ) -> None:
        """The second add replays the first."""
        history = History()
        history.invoke(0, "add", [1]).ok(1)
        history.invoke(1, "add", [2]).ok(3)
        spec = spec_from(counter)
        passed = searched(history, spec)
        stopped = searched(history, spec, budget(2))
        check.equal(
            seat,
            [
                passed.outcome,
                passed.steps,
                stopped.outcome,
                stopped.limit,
                stopped.steps,
            ],
            ["passed", 3, "undecided", "steps", 1],
            "the second add replays the first",
        )

    def test_stops_before_a_step_past_its_budget(self, seat: Collector) -> None:
        """The budget is one step."""
        done = searched(write_then_read(), REGISTER, budget(1))
        check.equal(
            seat,
            [done.outcome, done.limit, done.steps, done.linearized, done.states],
            ["undecided", "steps", 1, (0,), (1,)],
            "the search stops after one step",
        )

    def test_stops_before_a_configuration_past_its_memo_limit(
        self, seat: Collector
    ) -> None:
        """The second configuration needs four bits."""
        done = searched(write_then_read(), REGISTER, memo_limit(3))
        check.equal(
            seat,
            [done.outcome, done.limit, done.steps, done.linearized],
            ["undecided", "memo", 2, (0,)],
            "the search stops before the second configuration",
        )

    def test_stops_once_its_time_has_passed(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The clock reads 0 for the deadline and 5 before the first step."""
        readings = iter([0.0])
        monkeypatch.setattr(time, "monotonic", lambda: next(readings, 5.0))
        done = searched(write_then_read(), REGISTER, time_limited(1))
        check.equal(
            seat,
            [done.outcome, done.limit, done.steps],
            ["undecided", "time", 0],
            "the search stops before its first step",
        )

    def test_reads_the_clock_once_in_1024_steps(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The clock is read for the deadline and before the first step."""
        readings: list[float] = []
        clock = time.monotonic

        def read() -> float:
            readings.append(clock())
            return readings[-1]

        monkeypatch.setattr(time, "monotonic", read)
        done = searched(write_then_read(), REGISTER, time_limited(60))
        check.equal(
            seat,
            [done.outcome, len(readings)],
            ["passed", 2],
            "the search reads the clock twice",
        )

    def test_compares_the_states_with_the_equal_of_the_spec(
        self, seat: Collector
    ) -> None:
        """The parity spec treats 4 and 2 as one state."""
        history = History()
        history.invoke(0, "write", [4], "x").ok(None)
        history.invoke(1, "read", [], "x").ok(0)
        done = searched(history, Parity())
        check.equal(
            seat,
            [done.outcome, done.states],
            ["passed", (4,)],
            "the pass ends in one state",
        )

    tests: ClassVar[list[tuple[str, Spec[Any], tuple[str, int | None]]]] = [
        ("initial", BrokenInitial(), ("initial", None)),
        ("next", BrokenNext(), ("next", 0)),
        ("equal", BrokenEqual(), ("equal", 0)),
        ("key", BrokenKey(), ("key", 0)),
    ]

    @pytest.mark.parametrize(
        ("spec", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_a_spec_error_at_the_stepped_call_for_a_function_that_raises(
        self, seat: Collector, spec: Spec[Any], want: tuple[str, int | None]
    ) -> None:
        """The error has the name of the function and the stepped call."""
        with pytest.raises(SpecError) as raised:
            searched(write_then_read(), spec)
        check.equal(
            seat,
            (raised.value.fn, raised.value.call),
            want,
            "the error has the function and the call",
        )
