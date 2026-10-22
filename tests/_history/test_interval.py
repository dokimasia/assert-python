# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _history/interval.py tests the history of calls with a start and an end.

The reference implementation of the definition gives the same orders and the
same refusals.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._history.event import Completion, Invocation
from dokimi_assert._history.interval import Interval, IntervalError, from_intervals

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


def read(client: int, start: float, end: float | None = None) -> Interval:
    """Return a pending read of x by client, or an ok one that returned None at end."""
    if end is None:
        return Interval(client, "read", [], ["x"], start)
    return Interval(client, "read", [], ["x"], start, end, "ok", None)


def refused(entries: list[Interval]) -> tuple[int, str]:
    """Return the entry and the text of the refusal of entries by from_intervals."""
    with pytest.raises(IntervalError) as raised:
        from_intervals(entries)
    return raised.value.entry, str(raised.value)


class TestInterval:
    """Interval is a call with a start and an end."""

    def test_is_pending_by_default(self, seat: Collector) -> None:
        """An interval that sets only its start is pending."""
        entry = Interval(0, "read", [], [], 1)
        check.equal(
            seat,
            [entry.end, entry.kind, entry.output, entry.error],
            [None, None, None, None],
            "the interval does not have an end, a kind, an output or an error",
        )


class TestIntervalError:
    """IntervalError is the error for an entry that from_intervals refuses."""

    def test_is_a_value_error_whose_text_contains_the_entry(
        self, seat: Collector
    ) -> None:
        """Entry 3 ends before it starts."""
        error = IntervalError(3, "ends at 1 before it starts at 2")
        check.error_as(seat, error, ValueError, "the error is a ValueError")
        check.equal(
            seat,
            [error.entry, str(error)],
            [3, "history: entry 3 ends at 1 before it starts at 2"],
            "the error has the position and the text of the entry",
        )


class TestFromIntervals:
    """from_intervals returns the history of calls with a start and an end."""

    def test_puts_an_invocation_before_a_completion_at_one_time(
        self, seat: Collector
    ) -> None:
        """The read that starts at 5 is concurrent with the read that ends at 5."""
        events = from_intervals([read(0, 0, 5), read(1, 5, 9)]).events()
        check.equal(
            seat,
            [(event.kind, event.call) for event in events],
            [("invoke", 0), ("invoke", 1), ("ok", 0), ("ok", 1)],
            "the invocation at 5 comes before the completion at 5",
        )

    def test_keeps_the_order_of_the_entries_among_invocations_at_one_time(
        self, seat: Collector
    ) -> None:
        """Clients 2 and 0 both start at 5."""
        events = from_intervals([read(2, 5, 9), read(0, 5, 9), read(1, 0, 9)]).events()
        check.equal(
            seat,
            [(event.kind, event.client) for event in events],
            [
                ("invoke", 1),
                ("invoke", 2),
                ("invoke", 0),
                ("ok", 2),
                ("ok", 0),
                ("ok", 1),
            ],
            "client 2 starts before client 0",
        )

    def test_records_each_kind_with_the_process_after_an_unknown_call(
        self, seat: Collector
    ) -> None:
        """Client 0 moves to process 2. The pending read does not complete."""
        entries = [
            Interval(0, "write", [1], ["x"], 0, 1, "unknown", error="timed out"),
            Interval(1, "write", [2], ["x"], 0, 1, "fail", error="refused"),
            Interval(0, "read", [], ["x"], 2, 3, "ok", 1),
            Interval(1, "read", [], ["x"], 2),
        ]
        events = from_intervals(entries).events()
        check.equal(
            seat,
            [(event.kind, event.client, event.process) for event in events],
            [
                ("invoke", 0, 0),
                ("invoke", 1, 1),
                ("unknown", 0, 0),
                ("fail", 1, 1),
                ("invoke", 0, 2),
                ("invoke", 1, 1),
                ("ok", 0, 2),
            ],
            "the events have their kinds and their processes",
        )
        completions = [e for e in events if isinstance(e, Completion)]
        check.equal(
            seat,
            [completions[0].error, completions[1].error, completions[2].output],
            ["timed out", "refused", 1],
            "the completions keep their errors and their output",
        )

    def test_compares_times_of_ints_with_times_of_floats(self, seat: Collector) -> None:
        """The read at 0.0 starts before the read at 2**60."""
        events = from_intervals([read(0, 2**60, 2**60 + 1), read(1, 0.0, 5.5)]).events()
        check.equal(
            seat,
            [event.client for event in events],
            [1, 1, 0, 0],
            "the read at 0.0 comes first",
        )

    def test_accepts_an_entry_that_ends_when_it_starts(self, seat: Collector) -> None:
        """The read starts and ends at 4."""
        check.length(
            seat,
            from_intervals([read(0, 4, 4)]).events(),
            2,
            "the history has the two events of one call",
        )

    def test_accepts_entries_of_one_client_that_do_not_share_an_instant(
        self, seat: Collector
    ) -> None:
        """Client 0 reads from 0 to 3 and from 4 to 6."""
        events = from_intervals([read(0, 4, 6), read(0, 0, 3), read(1, 0, 9)]).events()
        check.length(seat, events, 6, "the history has the six events of three calls")

    def test_records_the_invocation_of_each_call(self, seat: Collector) -> None:
        """The write of 7 touches x and y."""
        entry = Interval(0, "write", [7], ["x", "y"], 0, 1, "ok", None)
        invocation = cast("Invocation", from_intervals([entry]).events()[0])
        check.equal(
            seat,
            [invocation.operation, invocation.args, invocation.keys],
            ["write", (7,), ("x", "y")],
            "the invocation has the operation, the arguments and the keys",
        )

    tests: ClassVar[list[tuple[str, list[Interval], tuple[int, str]]]] = [
        (
            "an entry of one client that shares an instant with an earlier one",
            [read(0, 3, 6), read(0, 0, 3)],
            (1, "history: entry 1 overlaps entry 0 of client 0"),
        ),
        (
            "an entry after a pending entry of its client",
            [read(0, 0, 1), read(0, 5), read(0, 9, 12)],
            (2, "history: entry 2 overlaps entry 1 of client 0"),
        ),
        (
            "the first entry that ends before it starts",
            [read(0, 0, 2), read(1, 5, 3), read(0, 1, 3)],
            (1, "history: entry 1 ends at 3 before it starts at 5"),
        ),
        (
            "an entry of a kind that does not complete a call",
            [replace(read(0, 0, 1), kind=cast("Any", "invoke"))],
            (
                0,
                "history: entry 0 has the kind 'invoke' instead of ok, fail or unknown",
            ),
        ),
        (
            "an entry with an end but without a kind",
            [Interval(0, "read", [], [], 0, 1)],
            (0, "history: entry 0 has a kind without an end, or an end without a kind"),
        ),
        (
            "an entry with a kind but without an end",
            [Interval(0, "read", [], [], 0, kind="ok")],
            (0, "history: entry 0 has a kind without an end, or an end without a kind"),
        ),
        (
            "an entry with a key that does not have a typed literal",
            [read(0, 0, 1), replace(read(1, 0, 1), keys=["x", object])],
            (
                1,
                "history: entry 1 has the key <class 'object'> without a typed literal",
            ),
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_interval_error_for(
        self, seat: Collector, give: list[Interval], want: tuple[int, str]
    ) -> None:
        """The error has the position of the entry and the rule that it breaks."""
        check.equal(seat, refused(give), want, "the error has the entry and the text")
