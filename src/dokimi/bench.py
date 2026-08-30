"""Ceilings a benchmark must stay within.

A benchmark records numbers; somebody has to read them to notice a
regression. A contract states the ceiling in the benchmark, so
exceeding it fails the run instead.

    c = bench.Contract(seat).max_latency(0.00005).max_allocs(2)

    for _ in c.loop(1000):
        store.get(id)

    c.end()

Python cannot count heap allocations per iteration the way a runtime
with a counter can. ``max_allocs`` and ``max_bytes`` measure with
:mod:`tracemalloc`, which counts allocations Python itself made and
carries real overhead; a ceiling set from a run without tracing will
not hold in one with it. Latency needs no such caveat.
"""

from __future__ import annotations

import time
import tracemalloc
from collections.abc import Iterator

from dokimi import expect
from dokimi._matcher.seat import Seat

__all__ = ["Contract"]

#: The quantile max_latency holds. The tail is what a caller waits
#: for; a mean hides it.
P99 = 0.99


class Contract:
    """Measures a benchmark and fails it for exceeding a ceiling.

    A ceiling nobody states is not checked. Every stated ceiling is
    checked, so one run names each one exceeded rather than the first.

    Not safe for concurrent use: it belongs to the loop running the
    benchmark.
    """

    def __init__(self, seat: Seat) -> None:
        """Return a contract on seat with no ceilings stated."""
        self._seat: Seat = seat
        self._each: list[float] = []
        self._traced: bool = False
        self._peak_blocks: int = 0
        self._peak_bytes: int = 0

        self._max_latency: float | None = None
        self._max_mean: float | None = None
        self._max_allocs: int | None = None
        self._max_bytes: int | None = None

    def max_latency(self, seconds: float) -> Contract:
        """State the highest p99 latency per iteration, and chain.

        The p99 rather than the mean, because the tail is what a caller
        waits for. With fewer than a hundred iterations it is the
        slowest one.
        """
        self._max_latency = seconds
        return self

    def max_mean(self, seconds: float) -> Contract:
        """State the highest mean latency per iteration, and chain.

        Use it beside :meth:`max_latency` rather than instead of it: a
        mean that holds while the tail grows is the regression a mean
        alone misses.
        """
        self._max_mean = seconds
        return self

    def max_allocs(self, count: int) -> Contract:
        """State the most allocations per iteration, and chain.

        Turns on :mod:`tracemalloc`, which slows the benchmark. Set the
        ceiling from a traced run.
        """
        self._max_allocs = count
        return self

    def max_bytes(self, count: int) -> Contract:
        """State the most bytes allocated per iteration, and chain."""
        self._max_bytes = count
        return self

    def loop(self, iterations: int) -> Iterator[int]:
        """Yield each iteration index, timing the body between yields.

        Allocation tracing starts here rather than at construction, so
        the setup before the loop is not counted.
        """
        if self._tracing_wanted():
            tracemalloc.start()
            self._traced = True

        for index in range(iterations):
            started = time.perf_counter()
            yield index
            self._each.append(time.perf_counter() - started)

        if self._traced:
            blocks, size = tracemalloc.get_traced_memory()
            self._peak_blocks, self._peak_bytes = blocks, size
            tracemalloc.stop()

    def end(self) -> None:
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
        if self._max_allocs is not None:
            expect.in_range(
                self._seat,
                self._peak_blocks / count,
                0,
                self._max_allocs,
                "the allocations per iteration stay within their ceiling",
            )
        if self._max_bytes is not None:
            expect.in_range(
                self._seat,
                self._peak_bytes / count,
                0,
                self._max_bytes,
                "the bytes allocated per iteration stay within their ceiling",
            )

    def _tracing_wanted(self) -> bool:
        """Whether a stated ceiling needs allocation tracing."""
        return self._max_allocs is not None or self._max_bytes is not None
