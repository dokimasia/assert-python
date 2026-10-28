# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _matcher/heap.py tests the ceiling on the live heap of a call.

The module computes the verdicts, so this spec checks its verdicts with the
assert statement of pytest.
"""

from __future__ import annotations

import tracemalloc
from typing import TYPE_CHECKING, Any

from dokimi_assert._matcher import heap
from dokimi_assert._matcher.seat import Mode
from dokimi_assert.seat import Recorder

if TYPE_CHECKING:
    from collections.abc import Callable

#: The entries that the filters read: 8 of 32 KiB each. A reading collects
#: the whole heap of the suite, so the specs keep the probes few.
ENTRIES = [bytes(32 << 10) for _ in range(8)]

#: The ceiling of the specs: a quarter of the entries.
CEILING = 8 * (32 << 10) // 4

sink: Any = None


def stream(probe: Callable[[], None]) -> None:
    """Copy each entry and write it before the probe of the next one."""
    global sink  # noqa: PLW0603
    for entry in ENTRIES:
        probe()
        sink = bytearray(entry)
    sink = None


def buffer(probe: Callable[[], None]) -> None:
    """Copy every entry before it writes the first one."""
    global sink  # noqa: PLW0603
    kept = []
    for entry in ENTRIES:
        probe()
        kept.append(bytearray(entry))
    for copy in kept:
        sink = copy
    sink = None


def keeps(probe: Callable[[], None]) -> None:
    """Keep four times the ceiling at its one probe."""
    kept = bytearray(4 * CEILING)
    probe()
    del kept


def check(fn: Callable[[Callable[[], None]], Any]) -> Recorder:
    """Return a recorder after a call of max_live_bytes on fn."""
    seat = Recorder()
    heap.max_live_bytes(seat, Mode.FATAL, fn, CEILING, "the filter streams")
    return seat


class TestLiveRuns:
    """LIVE_RUNS is the most runs of a call."""

    def test_is_ten(self) -> None:
        """A call over its ceiling runs ten times."""
        assert heap.LIVE_RUNS == 10


class TestMaxLiveBytes:
    """max_live_bytes fails a call that keeps more than its ceiling at a probe."""

    def test_passes_a_callable_that_keeps_one_entry_at_each_probe(self) -> None:
        """A streaming filter keeps one entry of 1 KiB."""
        assert not check(stream).failed

    def test_fails_a_callable_that_keeps_every_entry(self) -> None:
        """A buffering filter keeps 224 KiB at its last probe."""
        seat = check(buffer)
        detail = seat.failures[0].detail
        assert (detail["want"], detail["probes"]) == (CEILING, 8)
        assert detail["got"] > CEILING

    def test_does_not_read_a_buffer_that_is_freed_before_the_probe(self) -> None:
        """A temporary buffer between two probes is not read."""

        def temporary(probe: Callable[[], None]) -> None:
            bytearray(4 * CEILING)
            probe()

        assert not check(temporary).failed

    def test_does_not_read_the_call_that_warms_the_callable(self) -> None:
        """A cache that the first call builds is part of the first reading."""
        cache: list[bytearray] = []

        def warms_once(probe: Callable[[], None]) -> None:
            if not cache:
                cache.append(bytearray(4 * CEILING))
            probe()

        assert not check(warms_once).failed
        assert cache

    def test_ends_with_a_fault_for_a_callable_that_never_calls_the_probe(
        self,
    ) -> None:
        """No reading compared anything with the ceiling."""
        seat = check(lambda _probe: None)
        assert [str(f) for f in seat.faults] == [
            "the callable called the probe 0 times"
        ]

    def test_runs_a_callable_over_its_ceiling_ten_times_after_warming_it(
        self,
    ) -> None:
        """Each run reads the excess again."""
        calls = 0

        def counted(probe: Callable[[], None]) -> None:
            nonlocal calls
            calls += 1
            keeps(probe)

        check(counted)
        assert calls == 11

    def test_calls_a_callable_that_meets_its_ceiling_twice(self) -> None:
        """The warm call and one run."""
        calls = 0

        def counted(probe: Callable[[], None]) -> None:
            nonlocal calls
            calls += 1
            probe()

        check(counted)
        assert calls == 2

    def test_stops_the_trace_that_it_started(self) -> None:
        """A call leaves tracemalloc off when it was off."""
        check(stream)
        assert not tracemalloc.is_tracing()

    def test_leaves_the_trace_of_the_caller_running(self) -> None:
        """A call reads the trace that the caller started."""
        tracemalloc.start()
        try:
            assert check(keeps).failed
            assert tracemalloc.is_tracing()
        finally:
            tracemalloc.stop()
