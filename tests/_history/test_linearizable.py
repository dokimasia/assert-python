# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _history/linearizable.py tests the check of linearizability.

Each outcome, each count of steps and each record of the spec matches the
result of the reference implementation of the definition on the same history
and spec.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._history.history import Call, History
from dokimi_assert._history.linearizable import (
    LINEARIZABLE,
    Detail,
    detail_json,
    fields_of,
    is_linearizable,
    whole,
)
from dokimi_assert._history.linearizable import check as checked
from dokimi_assert._history.option import budget, memo_limit, time_limit, workers
from dokimi_assert._history.search import SpecError
from dokimi_assert._override import override
from dokimi_assert.seat import Collector, Recorder, Standard
from helpers import REGISTER, Register, records

if TYPE_CHECKING:
    from dokimi_assert._history.partition import Span
    from dokimi_assert._history.spec import Operation

#: The typed literal of None.
NULL = {"type": "null"}


def literal(value: int | str) -> dict[str, Any]:
    """Return the typed literal of an int or a str."""
    return {"type": "int" if isinstance(value, int) else "string", "value": value}


def write(history: History, client: int, value: object, *keys: object) -> Call:
    """Invoke a write of value by client on keys, or on x without keys."""
    return history.invoke(client, "write", [value], *(keys or ("x",)))


def read(history: History, client: int, *keys: object) -> Call:
    """Invoke a read by client on keys, or on x without keys."""
    return history.invoke(client, "read", [], *(keys or ("x",)))


def calls_in(spans: tuple[Span, ...]) -> list[int]:
    """Return the invocations of the calls of spans."""
    return [span.call for span in spans]


def two_partitions() -> History:
    """Return a history with a partition x of two steps and a partition y of one."""
    history = History()
    write(history, 0, 1).ok(None)
    read(history, 1).ok(1)
    read(history, 2, "y").ok(None)
    return history


class Raising(Register):
    """A register whose next raises for each operation."""

    @override
    def next(self, state: object, op: Operation) -> list[object]:
        """Raise ValueError."""
        msg = f"no {op.name} after {state!r}"
        raise ValueError(msg)


class RaisingInitial(Register):
    """A register whose initial raises."""

    @override
    def initial(self) -> object:
        """Raise ValueError."""
        msg = "boom"
        raise ValueError(msg)


class RaisingRead(Register):
    """A register whose next raises for a read."""

    @override
    def next(self, state: object, op: Operation) -> list[object]:
        """Raise ValueError for a read."""
        if op.name == "read":
            msg = "boom"
            raise ValueError(msg)
        return super().next(state, op)


class RaisingNine(Register):
    """A register whose next raises for a write of 9."""

    @override
    def next(self, state: object, op: Operation) -> list[object]:
        """Raise ValueError for a write of 9."""
        if op.name == "write" and op.args[0] == 9:
            msg = "boom"
            raise ValueError(msg)
        return super().next(state, op)


class InitialOnly:
    """A spec that does not have a next."""

    def initial(self) -> object:
        """Return None."""
        return None


class TestLinearizable:
    """LINEARIZABLE is the id of the assertion of linearizability."""

    def test_is_the_id_of_the_assertion(self, seat: Collector) -> None:
        """The value is the string linearizable."""
        check.equal(
            seat,
            LINEARIZABLE,
            "linearizable",
            "LINEARIZABLE is the string linearizable",
        )


class TestDetail:
    """Detail is the detail of the record of a check of linearizability."""

    def test_keeps_the_ten_fields_of_the_definition(self, seat: Collector) -> None:
        """The detail of a pass has three steps over two partitions."""
        detail: Detail[Any] = Detail("passed", 2, 3, (), 0, 0, (), (), (), None)
        check.equal(
            seat,
            [detail.outcome, detail.partitions, detail.steps, detail.limit],
            ["passed", 2, 3, None],
            "the detail keeps its fields",
        )


class TestCheck:
    """check checks a history against a spec under options."""

    def test_returns_the_frontier_of_a_read_that_misses_a_completed_write(
        self, seat: Collector
    ) -> None:
        """The write forms the frontier. The read is its one candidate."""
        history = History()
        write(history, 0, 1).ok(None)
        read(history, 1).ok(None)
        check.equal(
            seat,
            detail_json(checked(history, REGISTER, [])),
            {
                "outcome": "violated",
                "partitions": 1,
                "steps": 2,
                "partition": [literal("x")],
                "calls": 2,
                "concurrency": 1,
                "linearized": [
                    {
                        "call": 0,
                        "completion": 1,
                        "process": 0,
                        "operation": "write",
                        "args": [literal(1)],
                        "output": NULL,
                    }
                ],
                "states": [literal(1)],
                "candidates": [
                    {
                        "call": 2,
                        "completion": 3,
                        "process": 1,
                        "operation": "read",
                        "args": [],
                        "output": NULL,
                    }
                ],
                "limit": None,
            },
            "the read is the one candidate after the write",
        )

    def test_returns_only_the_counts_for_a_pass(self, seat: Collector) -> None:
        """A read of 1 follows a write of 1."""
        history = History()
        write(history, 0, 1).ok(None)
        read(history, 1).ok(1)
        check.equal(
            seat,
            checked(history, REGISTER, []),
            Detail("passed", 1, 2, (), 0, 0, (), (), (), None),
            "the detail of a pass has only the counts",
        )

    def test_passes_a_history_without_calls_over_zero_partitions(
        self, seat: Collector
    ) -> None:
        """An empty history and a history of one failed write both pass."""
        history = History()
        empty = checked(history, REGISTER, [])
        write(history, 0, 1).fail("refused")
        failed = checked(history, REGISTER, [])
        check.equal(
            seat,
            [empty.partitions, failed.outcome, failed.partitions, failed.steps],
            [0, "passed", 0, 0],
            "neither history has a partition",
        )

    def test_passes_a_failed_call_that_does_not_join_a_partition(
        self, seat: Collector
    ) -> None:
        """The failed write of x and y does not join the reads of x and y."""
        history = History()
        write(history, 0, 5, "x", "y").fail("refused")
        read(history, 1, "x").ok(None)
        read(history, 2, "y").ok(None)
        detail = checked(history, REGISTER, [])
        check.equal(
            seat,
            [detail.outcome, detail.partitions, detail.steps],
            ["passed", 2, 2],
            "x and y are two partitions",
        )

    def test_omits_the_completion_of_a_pending_call(self, seat: Collector) -> None:
        """The pending write lacks a completion. The unknown write lacks an output."""
        history = History()
        write(history, 0, 1)
        write(history, 1, 2).unknown("timed out")
        read(history, 2).ok(9)
        detail = checked(history, REGISTER, [])
        check.equal(
            seat,
            [
                detail.outcome,
                detail.steps,
                detail.calls,
                detail.concurrency,
                detail_json(detail)["linearized"],
                detail.states,
                calls_in(detail.candidates),
            ],
            [
                "violated",
                9,
                3,
                3,
                [
                    {
                        "call": 0,
                        "process": 0,
                        "operation": "write",
                        "args": [literal(1)],
                    },
                    {
                        "call": 1,
                        "completion": 2,
                        "process": 1,
                        "operation": "write",
                        "args": [literal(2)],
                    },
                ],
                (2,),
                [3],
            ],
            "the frontier lists both writes",
        )

    def test_reports_the_first_violated_partition_in_the_order_of_first_invocation(
        self, seat: Collector
    ) -> None:
        """The partition y passes. The partition x then fails at its start."""
        history = History()
        write(history, 0, 1, "y").ok(None)
        read(history, 1, "x").ok(5)
        read(history, 2, "y").ok(1)
        detail = checked(history, REGISTER, [])
        check.equal(
            seat,
            [
                detail.outcome,
                detail.partitions,
                detail.steps,
                detail.partition,
                calls_in(detail.linearized),
                detail.states,
                calls_in(detail.candidates),
            ],
            ["violated", 2, 3, ("x",), [], (None,), [2]],
            "the check reports x after y passes",
        )

    def test_joins_the_partitions_of_the_keys_of_one_call(
        self, seat: Collector
    ) -> None:
        """One write touches both x and y."""
        history = History()
        read(history, 0, "x").ok(None)
        write(history, 1, 2, "y", "x").ok(None)
        read(history, 2, "y").ok(3)
        detail = checked(history, REGISTER, [])
        check.equal(
            seat,
            [
                detail.partition,
                detail.partitions,
                detail.calls,
                detail.steps,
                calls_in(detail.linearized),
                detail.states,
            ],
            [("x", "y"), 1, 3, 3, [0, 2], (2,)],
            "x and y form one partition",
        )

    def test_puts_every_call_in_one_partition_for_a_call_without_keys(
        self, seat: Collector
    ) -> None:
        """The read of client 1 does not have keys."""
        history = History()
        write(history, 0, 1, "x").ok(None)
        history.invoke(1, "read", []).ok(2)
        write(history, 2, 1, "y").ok(None)
        detail = checked(history, REGISTER, [])
        check.equal(
            seat,
            [detail.partitions, detail.partition, detail.calls],
            [1, (), 3],
            "every call is in one partition",
        )

    def test_puts_two_dicts_of_equal_entries_in_one_partition(
        self, seat: Collector
    ) -> None:
        """The two dicts list their entries in different orders."""
        history = History()
        write(history, 0, 1, {1: "a", 2: "b"}).ok(None)
        read(history, 1, {2: "b", 1: "a"}).ok(1)
        check.equal(
            seat,
            checked(history, REGISTER, []).partitions,
            1,
            "the two dicts are one key",
        )

    def test_passes_within_a_budget_that_its_steps_spend_exactly(
        self, seat: Collector
    ) -> None:
        """The two steps of partition x spend the whole budget."""
        detail = checked(two_partitions(), REGISTER, [budget(2)])
        check.equal(
            seat,
            [detail.outcome, detail.steps],
            ["passed", 3],
            "the check passes in three steps",
        )

    def test_stops_before_a_step_past_its_budget(self, seat: Collector) -> None:
        """The partition x stops after one step. The step of y does not count."""
        detail = checked(two_partitions(), REGISTER, [budget(1)])
        check.equal(
            seat,
            [
                detail.outcome,
                detail.partitions,
                detail.steps,
                detail.partition,
                detail.limit,
                calls_in(detail.linearized),
                detail.states,
                detail.candidates,
            ],
            ["undecided", 2, 1, ("x",), "steps", [0], (1,), ()],
            "the search of x stops after one step",
        )

    def test_reports_a_violated_partition_after_an_undecided_one(
        self, seat: Collector
    ) -> None:
        """The partition x stops at its budget. The read of y then fails."""
        history = History()
        write(history, 0, 1).ok(None)
        read(history, 1).ok(1)
        read(history, 2, "y").ok(7)
        detail = checked(history, REGISTER, [budget(1)])
        check.equal(
            seat,
            [detail.outcome, detail.partition, detail.steps, detail.limit],
            ["violated", ("y",), 2, None],
            "the check reports y with the steps of x and y",
        )

    def test_reports_the_first_of_two_undecided_partitions(
        self, seat: Collector
    ) -> None:
        """Both partitions stop at their budget."""
        history = History()
        write(history, 0, 1).ok(None)
        read(history, 1).ok(1)
        write(history, 2, 2, "y").ok(None)
        read(history, 3, "y").ok(2)
        detail = checked(history, REGISTER, [budget(1)])
        check.equal(
            seat,
            [detail.outcome, detail.partition, detail.steps],
            ["undecided", ("x",), 1],
            "the check reports x",
        )

    def test_counts_a_bit_per_call_for_each_configuration_of_the_memo(
        self, seat: Collector
    ) -> None:
        """The second configuration of x needs four bits."""
        passed = checked(two_partitions(), REGISTER, [memo_limit(4)])
        stopped = checked(two_partitions(), REGISTER, [memo_limit(3)])
        check.equal(
            seat,
            [
                passed.outcome,
                stopped.outcome,
                stopped.limit,
                stopped.steps,
                stopped.partition,
                calls_in(stopped.linearized),
                stopped.candidates,
            ],
            ["passed", "undecided", "memo", 2, ("x",), [0], ()],
            "the second configuration of x needs four bits",
        )

    def test_counts_an_unknown_call_as_open_to_the_end_of_the_history(
        self, seat: Collector
    ) -> None:
        """The unknown write is open while two reads are open."""
        history = History()
        first = write(history, 0, 1)
        lost = write(history, 1, 2)
        lost.unknown("timed out")
        first.ok(None)
        late = read(history, 2)
        read(history, 3).ok(9)
        late.ok(9)
        detail = checked(history, REGISTER, [])
        check.equal(
            seat,
            [detail.outcome, detail.calls, detail.concurrency],
            ["violated", 4, 3],
            "three calls are open at once",
        )

    def test_stops_at_the_time_limit_once_the_time_has_passed(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The search stops before its first step."""
        readings = iter([0.0])
        monkeypatch.setattr(time, "monotonic", lambda: next(readings, 5.0))
        detail = checked(two_partitions(), REGISTER, [time_limit(1)])
        check.equal(
            seat,
            [detail.outcome, detail.limit, detail.steps, detail.states],
            ["undecided", "time", 0, (None,)],
            "the search stops before its first step",
        )

    def test_reports_the_same_detail_on_four_workers_as_on_one(
        self, seat: Collector
    ) -> None:
        """Four workers search the two partitions under a budget of one step."""
        check.equal(
            seat,
            checked(two_partitions(), REGISTER, [workers(4), budget(1)]),
            checked(two_partitions(), REGISTER, [budget(1)]),
            "four workers report the same detail as one",
        )

    def test_reports_a_violation_before_a_partition_whose_spec_raises_on_more_workers(
        self, seat: Collector
    ) -> None:
        """The partition x fails before the error of y counts."""
        history = History()
        read(history, 0, "x").ok(5)
        write(history, 1, 9, "y").ok(None)
        detail = checked(history, RaisingNine(), [workers(2)])
        check.equal(
            seat,
            [detail.outcome, detail.partition],
            ["violated", ("x",)],
            "the check reports the violation of x",
        )

    def test_raises_spec_error_for_a_function_of_the_spec_that_raises(
        self, seat: Collector
    ) -> None:
        """The next of the spec raises."""
        error = check.raises(
            seat,
            lambda: checked(two_partitions(), Raising(), []),
            "the check raises the error of next",
        )
        check.error_as(seat, error, SpecError, "the error is a SpecError")

    def test_raises_the_spec_error_of_a_worker_thread(self, seat: Collector) -> None:
        """The first partition raises on a worker thread."""
        error = check.raises(
            seat,
            lambda: checked(two_partitions(), Raising(), [workers(2)]),
            "the check raises the error of next",
        )
        check.error_as(seat, error, SpecError, "the error is a SpecError")


class TestWhole:
    """whole checks every call of a history as one partition."""

    def test_passes_a_history_without_calls_with_the_initial_state(
        self, seat: Collector
    ) -> None:
        """The empty history keeps the initial state None."""
        detail, states = whole(History(), REGISTER)
        check.equal(
            seat,
            [detail.outcome, detail.partitions, detail.steps, states],
            ["passed", 0, 0, (None,)],
            "the pass has the initial state",
        )

    def test_passes_the_calls_of_two_keys_in_one_partition_with_the_states_after_them(
        self, seat: Collector
    ) -> None:
        """The read of y follows the write of x."""
        history = History()
        write(history, 0, 1, "x").ok(None)
        read(history, 1, "y").ok(1)
        detail, states = whole(history, REGISTER)
        check.equal(
            seat,
            [detail.outcome, detail.partitions, detail.steps, states],
            ["passed", 1, 2, (1,)],
            "the calls of x and y form one partition",
        )

    def test_returns_the_frontier_without_states_for_a_violation(
        self, seat: Collector
    ) -> None:
        """The read of 2 follows the write of 1."""
        history = History()
        write(history, 0, 1).ok(None)
        read(history, 1).ok(2)
        detail, states = whole(history, REGISTER)
        check.equal(
            seat,
            [detail_json(detail), states],
            [
                {
                    "outcome": "violated",
                    "partitions": 1,
                    "steps": 2,
                    "partition": [],
                    "calls": 2,
                    "concurrency": 1,
                    "linearized": [
                        {
                            "call": 0,
                            "completion": 1,
                            "process": 0,
                            "operation": "write",
                            "args": [literal(1)],
                            "output": NULL,
                        }
                    ],
                    "states": [literal(1)],
                    "candidates": [
                        {
                            "call": 2,
                            "completion": 3,
                            "process": 1,
                            "operation": "read",
                            "args": [],
                            "output": literal(2),
                        }
                    ],
                    "limit": None,
                },
                (),
            ],
            "the violation has the frontier and empty states",
        )


class TestFieldsOf:
    """fields_of returns the detail fields of the record of a failing check."""

    def test_returns_none_as_the_limit_of_a_violated_check(
        self, seat: Collector
    ) -> None:
        """A read of 1 from the initial None violates the spec."""
        history = History()
        read(history, 0).ok(1)
        check.is_none(
            seat,
            fields_of(checked(history, REGISTER, []))["limit"],
            "a violated check does not have a limit",
        )

    def test_returns_the_limit_of_an_undecided_check(self, seat: Collector) -> None:
        """A budget of one step stops the check."""
        detail = checked(two_partitions(), REGISTER, [budget(1)])
        check.equal(seat, fields_of(detail)["limit"], "steps", "the limit is steps")


class TestDetailJson:
    """detail_json returns the detail of a failing check as JSON."""

    def test_returns_the_limit_of_an_undecided_check_by_its_name(
        self, seat: Collector
    ) -> None:
        """A budget of one step stops the check."""
        detail = checked(two_partitions(), REGISTER, [budget(1)])
        check.equal(
            seat, detail_json(detail)["limit"], "steps", "the JSON has the limit steps"
        )


class TestIsLinearizable:
    """is_linearizable fails for a partition without a linearization."""

    def test_records_a_pass_for_a_history_that_the_spec_accepts(
        self, seat: Collector
    ) -> None:
        """Both partitions of the history pass."""
        recorder = Recorder()
        is_linearizable(recorder, two_partitions(), REGISTER, "linearizable")
        check.equal(
            seat,
            [recorder.failures, records(recorder)[0]["verdict"]],
            [[], "pass"],
            "the assertion records a pass",
        )

    def test_fails_with_one_record_of_linearizable_at_its_call(
        self, seat: Collector
    ) -> None:
        """A read of None follows a write of 1."""
        history = History()
        write(history, 0, 1).ok(None)
        read(history, 1).ok(None)
        recorder = Recorder()
        is_linearizable(recorder, history, REGISTER, "the register is linearizable")
        failure = recorder.failures[0]
        check.equal(
            seat,
            [
                failure.assertion,
                failure.contract,
                sorted(failure.detail),
                records(recorder)[0]["detail"],
            ],
            [
                "linearizable",
                "the register is linearizable",
                [
                    "calls",
                    "candidates",
                    "concurrency",
                    "limit",
                    "linearized",
                    "outcome",
                    "partition",
                    "partitions",
                    "states",
                    "steps",
                ],
                detail_json(checked(history, REGISTER, [])),
            ],
            "the failure and its call record have the ten fields",
        )
        where = failure.where
        check.has_suffix(
            seat,
            None if where is None else where.file,
            "test_linearizable.py",
            "the failure is at the call in this file",
        )

    def test_raises_the_text_of_the_record_on_a_seat_that_stops(
        self, seat: Collector
    ) -> None:
        """A Standard seat raises AssertionError for each failure."""
        history = History()
        read(history, 0).ok(1)
        error = check.raises(
            seat,
            lambda: is_linearizable(
                Standard(), history, REGISTER, "the register is linearizable"
            ),
            "the check stops the test",
        )
        check.has_prefix(
            seat,
            str(error),
            "the register is linearizable: ",
            "the text starts with the contract",
        )

    tests: ClassVar[list[tuple[str, Any, Any, str]]] = [
        (
            "a history that is not a History",
            [],
            REGISTER,
            "history.is_linearizable: the history is not a History",
        ),
        (
            "a spec without next",
            History(),
            InitialOnly(),
            "history.is_linearizable: the spec does not have an initial and a next",
        ),
        (
            "an initial that raises",
            two_partitions(),
            RaisingInitial(),
            "history.is_linearizable: the function initial of the spec raises: boom",
        ),
        (
            "a next that raises",
            two_partitions(),
            RaisingRead(),
            (
                "history.is_linearizable: calls[2]: the function next of the spec "
                'raises for "read": boom'
            ),
        ),
    ]

    @pytest.mark.parametrize(
        ("history", "spec", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_ends_the_call_with_a_fault_for(
        self, seat: Collector, history: Any, spec: Any, want: str
    ) -> None:
        """The text of the fault starts with the name of the assertion."""
        recorder = Recorder()
        is_linearizable(recorder, history, spec, "c")
        check.equal(seat, recorder.message, want, "the call ends with the fault")
