# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _history/checkpoint.py tests the searches that a checkpoint keeps.

Each check of the spec reports what a check of every call reports. The spec
counts the calls of the next of its register, so it reads which searches a
check continues and which it searches again from their first call.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from dokimi_assert import check
from dokimi_assert._history.checkpoint import Checkpoint
from dokimi_assert._history.history import History
from dokimi_assert._history.linearizable import check as checked
from dokimi_assert._history.linearizable import whole
from dokimi_assert._history.option import Option, budget, memo_limit, resume, workers
from dokimi_assert._history.search import SpecError
from dokimi_assert._override import override
from helpers import Register

if TYPE_CHECKING:
    from dokimi_assert._history.linearizable import Detail
    from dokimi_assert._history.spec import Operation
    from dokimi_assert.seat import Collector


class Counted(Register):
    """The register of the specs, which counts the calls of its next."""

    def __init__(self) -> None:
        """Return a register that has not stepped."""
        self.calls = 0

    @override
    def next(self, state: object, op: Operation) -> list[object]:
        """Count the call, and return the value after op."""
        self.calls += 1
        return super().next(state, op)


class Raising(Register):
    """A register whose next raises for each operation."""

    @override
    def next(self, state: object, op: Operation) -> list[object]:
        """Raise ValueError."""
        msg = f"no {op.name} after {state!r}"
        raise ValueError(msg)


def resumed(
    history: History, checkpoint: Checkpoint[Any], *options: Option
) -> tuple[str, int, int, int]:
    """Check history with checkpoint, and return its counts and calls of next."""
    spec = Counted()
    detail: Detail[Any] = checked(history, spec, [*options, resume(checkpoint)])
    return detail.outcome, detail.partitions, detail.steps, spec.calls


def every(history: History, *options: Option) -> tuple[str, int, int, int]:
    """Check history without a checkpoint, and return what resumed returns."""
    spec = Counted()
    detail: Detail[Any] = checked(history, spec, list(options))
    return detail.outcome, detail.partitions, detail.steps, spec.calls


class TestCheckpoint:
    """Checkpoint keeps the searches of the last check that passed with it."""

    def test_keeps_no_search_at_first(self, seat: Collector) -> None:
        """The first check searches the write and the read from the first call."""
        history = History()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(1, "read", [], "x").ok(1)
        check.equal(
            seat,
            resumed(history, Checkpoint()),
            ("passed", 1, 2, 2),
            "the first check steps each call once",
        )


class TestResumed:
    """resumed returns the partitions of a check with a checkpoint, and searches."""

    def test_continues_the_search_of_a_partition_over_its_new_calls(
        self, seat: Collector
    ) -> None:
        """A write and a read of 2 follow the checked write of 1."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        resumed(history, checkpoint)
        history.invoke(0, "write", [2], "x").ok(None)
        history.invoke(1, "read", [], "x").ok(2)
        check.equal(
            seat,
            [resumed(history, checkpoint), every(history)],
            [("passed", 1, 3, 2), ("passed", 1, 3, 3)],
            "the second check steps the two new calls",
        )

    def test_takes_no_step_for_a_partition_without_new_calls(
        self, seat: Collector
    ) -> None:
        """A read of y follows the checked writes of x and y."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(1, "write", [2], "y").ok(None)
        resumed(history, checkpoint)
        history.invoke(1, "read", [], "y").ok(2)
        check.equal(
            seat,
            resumed(history, checkpoint),
            ("passed", 2, 3, 1),
            "the partition of x keeps its outcome without a step",
        )

    def test_continues_a_partition_whose_call_states_two_of_its_keys(
        self, seat: Collector
    ) -> None:
        """A second write of x and z follows the checked write of x and z."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x", "z").ok(None)
        resumed(history, checkpoint)
        history.invoke(0, "write", [2], "x", "z").ok(None)
        check.equal(
            seat,
            resumed(history, checkpoint),
            ("passed", 1, 2, 1),
            "the second write joins the one partition of x and z",
        )

    @pytest.mark.parametrize("give", ["ok", "unknown"])
    def test_searches_the_partition_of_a_pending_call_that_completes_again(
        self, seat: Collector, give: str
    ) -> None:
        """The write of 1 is pending at the first check, and completes later."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        pending = history.invoke(0, "write", [1], "x")
        resumed(history, checkpoint)
        if give == "ok":
            pending.ok(None)
        else:
            pending.unknown("timed out")
        history.invoke(1, "read", [], "x").ok(1)
        check.equal(
            seat,
            [resumed(history, checkpoint), every(history)],
            [("passed", 1, 2, 2), ("passed", 1, 2, 2)],
            "the partition searches from its first call",
        )

    def test_splits_the_partition_of_a_pending_call_that_fails(
        self, seat: Collector
    ) -> None:
        """The pending write of x and y joined the writes of x and of y, and fails."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(1, "write", [2], "y").ok(None)
        pending = history.invoke(2, "write", [3], "x", "y")
        resumed(history, checkpoint)
        pending.fail("refused")
        history.invoke(0, "read", [], "x").ok(1)
        check.equal(
            seat,
            [resumed(history, checkpoint), every(history)],
            [("passed", 2, 3, 3), ("passed", 2, 3, 3)],
            "the failed write leaves, and x and y form two partitions",
        )

    def test_searches_a_partition_that_a_new_call_joins_again(
        self, seat: Collector
    ) -> None:
        """A write of x, w, y and z follows the checked writes of x and w and of y."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x", "w").ok(None)
        history.invoke(1, "write", [2], "y").ok(None)
        resumed(history, checkpoint)
        history.invoke(2, "write", [3], "x", "w", "y", "z").ok(None)
        check.equal(
            seat,
            [resumed(history, checkpoint), every(history)],
            [("passed", 1, 3, 3), ("passed", 1, 3, 3)],
            "the joined partition searches from its first call",
        )

    def test_joins_every_partition_for_a_new_call_without_keys(
        self, seat: Collector
    ) -> None:
        """A write without keys follows the checked writes of x and of y."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(1, "write", [2], "y").ok(None)
        resumed(history, checkpoint)
        history.invoke(2, "write", [3]).ok(None)
        check.equal(
            seat,
            [resumed(history, checkpoint), every(history)],
            [("passed", 1, 3, 3), ("passed", 1, 3, 3)],
            "the one partition of every key searches from its first call",
        )

    def test_continues_a_partition_that_a_call_without_keys_extends(
        self, seat: Collector
    ) -> None:
        """A write without keys and a read of x follow the checked write of x."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        resumed(history, checkpoint)
        history.invoke(1, "write", [2]).ok(None)
        resumed(history, checkpoint)
        history.invoke(0, "read", [], "x").ok(2)
        check.equal(
            seat,
            [resumed(history, checkpoint), every(history)],
            [("passed", 1, 3, 1), ("passed", 1, 3, 3)],
            "the read joins the partition of every key",
        )

    def test_starts_the_partition_of_every_key_with_a_call_without_keys(
        self, seat: Collector
    ) -> None:
        """The first call of the history has no key, and a write of x follows."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1]).ok(None)
        resumed(history, checkpoint)
        history.invoke(1, "write", [2], "x").ok(None)
        check.equal(
            seat,
            resumed(history, checkpoint),
            ("passed", 1, 2, 1),
            "the write of x joins the partition of every key",
        )

    def test_searches_every_partition_of_another_history_again(
        self, seat: Collector
    ) -> None:
        """The second check has another history with the same calls."""
        checkpoint: Checkpoint[Any] = Checkpoint()
        first = History()
        first.invoke(0, "write", [1], "x").ok(None)
        resumed(first, checkpoint)
        second = History()
        second.invoke(0, "write", [1], "x").ok(None)
        check.equal(
            seat,
            resumed(second, checkpoint),
            ("passed", 1, 1, 1),
            "the write steps once more",
        )

    @pytest.mark.parametrize(
        "give", [budget(100), memo_limit(1 << 20)], ids=["budget", "memo-limit"]
    )
    def test_searches_every_partition_under_another_limit_again(
        self, seat: Collector, give: Option
    ) -> None:
        """The second check states another limit than the first."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        resumed(history, checkpoint)
        history.invoke(1, "read", [], "x").ok(1)
        check.equal(
            seat,
            resumed(history, checkpoint, give),
            ("passed", 1, 2, 2),
            "the partition searches from its first call",
        )

    def test_searches_a_partition_whose_memo_passes_the_grown_capacity_again(
        self, seat: Collector
    ) -> None:
        """Two configurations fit five bits for two calls, and not for three."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(1, "read", [], "x").ok(1)
        resumed(history, checkpoint, memo_limit(5))
        history.invoke(0, "write", [2], "x").ok(None)
        check.equal(
            seat,
            resumed(history, checkpoint, memo_limit(5)),
            ("undecided", 1, 2, 2),
            "the search starts again and stops at the memo limit",
        )

    def test_searches_on_two_workers(self, seat: Collector) -> None:
        """A read of x and a read of y follow the checked writes of x and y."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(1, "write", [2], "y").ok(None)
        resumed(history, checkpoint, workers(2))
        history.invoke(0, "read", [], "x").ok(1)
        history.invoke(1, "read", [], "y").ok(2)
        check.equal(
            seat,
            resumed(history, checkpoint, workers(2)),
            ("passed", 2, 4, 2),
            "each partition steps its new read",
        )


class TestForget:
    """forget leaves a checkpoint without a search."""

    def test_follows_a_check_that_does_not_pass(self, seat: Collector) -> None:
        """The first check fails on a read of 3, and the second has a longer history."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(1, "read", [], "x").ok(3)
        resumed(history, checkpoint)
        history.invoke(0, "write", [2], "x").ok(None)
        check.equal(
            seat,
            [resumed(history, checkpoint), every(history)],
            [("violated", 1, 2, 2), ("violated", 1, 2, 2)],
            "the second check searches from the first call",
        )

    def test_follows_a_check_whose_spec_raises(self, seat: Collector) -> None:
        """The first check raises in next, and the second check passes."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        with pytest.raises(SpecError):
            checked(history, Raising(), [resume(checkpoint)])
        check.equal(
            seat,
            resumed(history, checkpoint),
            ("passed", 1, 1, 1),
            "the second check searches from the first call",
        )


class TestWhole:
    """A checkpoint of whole keeps one search of every call."""

    def test_continues_the_search_of_every_call(self, seat: Collector) -> None:
        """A read of y follows the checked write of x."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        whole(history, Counted(), checkpoint)
        history.invoke(1, "read", [], "y").ok(1)
        spec = Counted()
        detail, states = whole(history, spec, checkpoint)
        check.equal(
            seat,
            [detail.outcome, detail.partitions, detail.steps, states, spec.calls],
            ["passed", 1, 2, (1,), 1],
            "the read joins the one partition, and steps once",
        )

    def test_drops_a_pending_call_that_fails(self, seat: Collector) -> None:
        """The pending write of 2 fails after the first check."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        pending = history.invoke(1, "write", [2], "y")
        whole(history, Counted(), checkpoint)
        pending.fail("refused")
        spec = Counted()
        detail, states = whole(history, spec, checkpoint)
        check.equal(
            seat,
            [detail.outcome, detail.steps, states, spec.calls],
            ["passed", 1, (1,), 1],
            "the one partition searches the write of 1 again",
        )

    def test_searches_a_history_of_partitions_after_whole_again(
        self, seat: Collector
    ) -> None:
        """A check of partitions follows a check of whole with the same checkpoint."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        whole(history, Counted(), checkpoint)
        check.equal(
            seat,
            resumed(history, checkpoint),
            ("passed", 1, 1, 1),
            "the check of partitions searches from the first call",
        )

    def test_passes_a_history_without_calls(self, seat: Collector) -> None:
        """The history has no event."""
        detail, states = whole(History(), Counted(), Checkpoint())
        check.equal(
            seat,
            [detail.outcome, detail.partitions, detail.steps, states],
            ["passed", 0, 0, (None,)],
            "the check passes without a partition in the initial state",
        )

    def test_forgets_the_search_of_a_violated_check(self, seat: Collector) -> None:
        """A read of 3 follows the write of 1."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        history.invoke(1, "read", [], "x").ok(3)
        whole(history, Counted(), checkpoint)
        spec = Counted()
        detail, _ = whole(history, spec, checkpoint)
        check.equal(
            seat,
            [detail.outcome, spec.calls],
            ["violated", 2],
            "the second check searches from the first call",
        )

    def test_forgets_the_search_of_a_check_whose_spec_raises(
        self, seat: Collector
    ) -> None:
        """The first check raises in next, and the second check passes."""
        history = History()
        checkpoint: Checkpoint[Any] = Checkpoint()
        history.invoke(0, "write", [1], "x").ok(None)
        with pytest.raises(SpecError):
            whole(history, Raising(), checkpoint)
        spec = Counted()
        detail, _ = whole(history, spec, checkpoint)
        check.equal(
            seat,
            [detail.outcome, spec.calls],
            ["passed", 1],
            "the second check searches from the first call",
        )
