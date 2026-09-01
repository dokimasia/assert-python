"""Ceilings a benchmark must stay within.

A benchmark records numbers; somebody has to read them to notice a
regression. A contract states the ceiling in the benchmark, so
exceeding it fails the run instead.

    c = bench.Contract(seat).max_latency(0.00005).max_bytes(4096)

    for _ in c.loop(1000):
        store.get(id)

    c.check()

There is no ceiling on allocations here. CPython counts no allocations:
every primitive it offers answers a level of live memory rather than a
running total, so a body that allocates ten blocks and frees them reads
the same as one that allocates nothing. The standard's overlay for this
language records that.

max_bytes measures with tracemalloc, which carries real overhead. Set
the ceiling from a run that had it on.
"""

from __future__ import annotations

import time
import tracemalloc
from collections.abc import Callable, Iterator
from typing import TypeVar

from dokimi_assert import expect
from dokimi_assert._matcher.seat import Seat

__all__ = ["Contract"]

#: The quantile max_latency holds. The tail is what a caller waits
#: for; a mean hides it.
P99 = 0.99


#: What a benchmark's setup answers, threaded to the measured work.
_T = TypeVar("_T")


class Contract:
    """Measures a benchmark and fails it for exceeding a ceiling.

    A ceiling nobody states is not checked. Every stated ceiling is
    checked, so one run names each one exceeded rather than the first.

    Not safe for concurrent use: it belongs to the loop running the
    benchmark.
    """

    def __init__(self, seat: Seat) -> None:
        """Return a contract on seat with no ceilings stated.

        Args:
            seat: Where the failure is reported.
        """
        self._seat: Seat = seat
        self._each: list[float] = []
        self._traced: bool = False
        self._excluded: float = 0.0
        self._peaks: list[int] = []
        self._held: int = 0
        self._base: int = 0

        self._max_latency: float | None = None
        self._max_mean: float | None = None
        self._max_bytes: int | None = None

    def max_latency(self, seconds: float) -> Contract:
        """State the highest p99 latency per iteration, and chain.

        The p99 rather than the mean, because the tail is what a caller
        waits for. With fewer than a hundred iterations it is the
        slowest one.

        Args:
            seconds: The highest acceptable p99 latency, in seconds.

        Returns:
            The contract, so ceilings can be chained.
        """
        self._max_latency = seconds
        return self

    def max_mean(self, seconds: float) -> Contract:
        """State the highest mean latency per iteration, and chain.

        Use it beside max_latency rather than instead of it: a
        mean that holds while the tail grows is the regression a mean
        alone misses.

        Args:
            seconds: The highest acceptable mean latency, in seconds.

        Returns:
            The contract, so ceilings can be chained.
        """
        self._max_mean = seconds
        return self

    def max_bytes(self, count: int) -> Contract:
        """State the most bytes an iteration may hold at once, and chain.

        The number held is the high-water mark of traced memory reached
        during one iteration, measured above what was already live when
        that iteration started. A body that allocates a megabyte and
        frees it is measured at a megabyte, which is what a ceiling on
        allocation is asked to catch.

        Turns on tracemalloc, which slows the benchmark. Set the ceiling
        from a traced run.

        Args:
            count: The highest acceptable bytes held per iteration.

        Returns:
            The contract, so ceilings can be chained.
        """
        self._max_bytes = count
        return self

    def loop(self, iterations: int) -> Iterator[int]:
        """Yield each iteration index, measuring the body between yields.

        Tracing starts here rather than at construction, so whatever the
        caller built before the loop is not measured.

        Args:
            iterations: How many times to run the body.

        Returns:
            The measurement, for a later assertion to read.
        """
        if self._max_bytes is not None:
            tracemalloc.start()
            self._traced = True

        for index in range(iterations):
            self._held = 0
            self._rebase()
            started = time.perf_counter()

            yield index

            stopped = time.perf_counter()
            if self._traced:
                self._peaks.append(self._held + self._reached())
            self._each.append(stopped - started - self._excluded)
            self._excluded = 0.0

        if self._traced:
            tracemalloc.stop()

    def excluding(self, setup: Callable[[], _T]) -> _T:
        """Run setup outside the measurement and answer what it made.

        A benchmark whose operation consumes its input builds a fresh one
        each iteration, and without this the ceilings state what the
        build and the operation cost together::

            for _ in contract.loop(10_000):
                store = contract.excluding(fresh_store)
                store.settle()

        Neither the time setup spends nor the memory it holds counts
        against a ceiling. The bytes it left live become part of the
        baseline the rest of the iteration is measured above.

        Calling it more than once in a body splits the iteration into
        spans, and what each span held at once is summed. Calling it
        outside a loop body is allowed and changes nothing a caller would
        notice, because there is no iteration to take the time from.

        Args:
            setup: The work to run outside the measurement.

        Returns:
            Whatever setup answered.
        """
        if self._traced:
            self._held += self._reached()

        started = time.perf_counter()
        made = setup()
        self._excluded += time.perf_counter() - started

        self._rebase()
        return made

    def check(self) -> None:
        """Fail the benchmark for every ceiling exceeded.

        Ceilings report through the recording surface, so one run names
        each one exceeded rather than stopping at the first.
        """
        self._seat.helper()
        if not self._each:
            return

        ordered = sorted(self._each)
        count = len(ordered)
        tail = ordered[int((count - 1) * P99)]
        mean = sum(ordered) / count

        if self._max_latency is not None:
            expect.in_range(
                self._seat,
                tail,
                0,
                self._max_latency,
                "the p99 latency per iteration stays within its ceiling",
            )
        if self._max_mean is not None:
            expect.in_range(
                self._seat,
                mean,
                0,
                self._max_mean,
                "the mean latency per iteration stays within its ceiling",
            )
        if self._max_bytes is not None and self._peaks:
            expect.in_range(
                self._seat,
                sum(self._peaks) / len(self._peaks),
                0,
                self._max_bytes,
                "the bytes held per iteration stay within their ceiling",
            )

    def _rebase(self) -> None:
        """Start a fresh span, measured above what is live right now."""
        if self._traced:
            tracemalloc.reset_peak()
            self._base = tracemalloc.get_traced_memory()[0]

    def _reached(self) -> int:
        """Return the most the current span held above its baseline."""
        return tracemalloc.get_traced_memory()[1] - self._base
