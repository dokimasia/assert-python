# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The ceilings of a benchmark and the measurement of its iterations.

A benchmark that prints numbers reports what happened. With a ceiling, the
run also fails when the result is not acceptable.

    c = bench.Contract(seat).warmup(1_000).max_latency(0.00005).max_bytes(4096)

    for _ in c.loop(10_000):
        store.get(id)

    c.check()

The library does not have a ceiling on allocations, because CPython does
not keep a running count of allocations. Each of its primitives returns the
memory that is live at one moment. A body that allocates ten blocks and
frees them then measures the same as a body that does not allocate. The
overlay of the definition for Python marks the allocation ceilings as
blocked for this reason. allocs_checked returns False with this reason, so
a test can report that its run does not check an allocation ceiling.

max_bytes measures with tracemalloc. Tracing slows the body, so set the
ceiling from a run that traced.
"""

from __future__ import annotations

import time
import tracemalloc
from typing import TYPE_CHECKING, TypeVar

from dokimi_assert._matcher.seat import Mode, Seat
from dokimi_assert._matcher.verdict import fail, pass_

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

__all__ = ["Contract", "allocs_checked"]

#: The quantile that max_latency bounds. A caller waits for the tail, and a
#: mean hides the tail.
P99 = 0.99

#: Why no run of this library checks an allocation ceiling.
_UNCOUNTED = "CPython does not count allocations"

#: The contract of each ceiling. The keys are the ids of the assertions.
_CONTRACTS = {
    "bench-max-latency": "the p99 latency per iteration stays within its ceiling",
    "bench-max-mean": "the mean latency per iteration stays within its ceiling",
    "bench-max-bytes": "the peak bytes per iteration stay within their ceiling",
}

#: The type of the value that the setup of excluding returns.
_T = TypeVar("_T")


def allocs_checked() -> tuple[bool, str]:
    """Return whether a run checks allocation ceilings, and the reason when not.

    No run of this library checks an allocation ceiling, so the result is
    False with the same reason in every run.

        checked, reason = bench.allocs_checked()

    Returns:
        False, and the reason.
    """
    return False, _UNCOUNTED


class Contract:
    """The ceilings of a benchmark, and the measurement of its iterations.

    check reports a verdict for each ceiling that the contract has, and no
    verdict for a ceiling that it does not have. A contract is not safe for
    concurrent use, because one loop drives it.
    """

    def __init__(self, seat: Seat) -> None:
        """Return a contract on seat without ceilings.

        Args:
            seat: The seat that receives each verdict.
        """
        self._seat: Seat = seat
        self._warmup: int = 0
        self._ran: bool = False
        self._each: list[float] = []
        self._traced: bool = False
        self._excluded: float = 0.0
        self._peaks: list[int] = []
        self._held: int = 0
        self._base: int = 0

        self._max_latency: float | None = None
        self._max_mean: float | None = None
        self._max_bytes: int | None = None

    def warmup(self, iterations: int) -> Contract:
        """State iterations that loop runs before the measured ones, and chain.

        A warm-up iteration runs the whole body. excluding runs its setup
        there and does not take anything out. The ceilings do not cover a
        warm-up iteration. The default is 0.

        Args:
            iterations: The number of iterations that loop runs before it
                measures one.

        Returns:
            The contract, so the calls chain.

        Raises:
            ValueError: iterations is not an int of 0 or more, or loop has
                started.
        """
        if type(iterations) is not int or iterations < 0:
            msg = f"bench: warmup takes an int of 0 or more, not {iterations!r}"
            raise ValueError(msg)
        if self._ran:
            msg = "bench: warmup cannot run after loop has started"
            raise ValueError(msg)
        self._warmup = iterations
        return self

    def max_latency(self, seconds: float) -> Contract:
        """State the highest p99 latency of an iteration, and chain.

        The ceiling covers the p99 and not the mean, because a caller waits
        for the tail. With fewer than a hundred iterations, the p99 is the
        slowest iteration.

        Args:
            seconds: The highest p99 latency in seconds.

        Returns:
            The contract, so the calls chain.
        """
        self._max_latency = seconds
        return self

    def max_mean(self, seconds: float) -> Contract:
        """State the highest mean latency of an iteration, and chain.

        Use it together with max_latency. A mean can stay within its ceiling
        while the tail grows, and max_latency catches that regression.

        Args:
            seconds: The highest mean latency in seconds.

        Returns:
            The contract, so the calls chain.
        """
        self._max_mean = seconds
        return self

    def max_bytes(self, count: int) -> Contract:
        """State the most bytes that an iteration can have live at once, and chain.

        The measure of an iteration is the peak that tracemalloc traces
        during the iteration minus the memory that was live when it started.
        A body that allocates a megabyte and frees it measures a megabyte.
        check compares the mean of the measures of the measured iterations
        with the ceiling.

        The ceiling turns tracemalloc on for the measured iterations, and
        tracing slows them. Set the ceiling from a run that traced.

        Args:
            count: The most bytes of an iteration.

        Returns:
            The contract, so the calls chain.
        """
        self._max_bytes = count
        return self

    def loop(self, iterations: int) -> Iterator[int]:
        """Yield the index of each iteration, and measure the body between yields.

        The loop yields the iterations of warmup first and does not measure
        them. It then yields iterations more times and measures each.
        Tracing starts at the first measured iteration, so the memory of what
        the caller built before it does not count.

        Args:
            iterations: The number of measured iterations.

        Yields:
            The index of each iteration from 0. The indices include the
            iterations of warmup.
        """
        self._ran = True
        for index in range(self._warmup):
            yield index

        if self._max_bytes is not None:
            tracemalloc.start()
            self._traced = True

        for index in range(self._warmup, self._warmup + iterations):
            self._held = 0
            self._excluded = 0.0
            self._rebase()
            started = time.perf_counter()

            yield index

            stopped = time.perf_counter()
            if self._traced:
                self._peaks.append(self._held + self._reached())
            self._each.append(stopped - started - self._excluded)

        if self._traced:
            tracemalloc.stop()
            self._traced = False

    def excluding(self, setup: Callable[[], _T]) -> _T:
        """Run setup outside the measurement, and return what it returns.

        A benchmark whose operation consumes its input builds a new input in
        each iteration. Without excluding, the ceilings cover the build and
        the operation together:

            for _ in contract.loop(10_000):
                store = contract.excluding(fresh_store)
                store.settle()

        Neither the time of setup nor the memory that it has live counts
        against a ceiling. The memory that setup leaves live is part of the
        baseline of the rest of the iteration. Two calls in one body split
        the iteration into spans, and the measure of the iteration is the
        sum of the peaks of its spans. In an iteration of warmup and outside
        the loop, excluding runs setup and does not take anything out.

        Args:
            setup: The work to run outside the measurement.

        Returns:
            The value that setup returns.
        """
        if self._traced:
            self._held += self._reached()

        started = time.perf_counter()
        made = setup()
        self._excluded += time.perf_counter() - started

        self._rebase()
        return made

    def check(self) -> None:
        """Report a verdict for each ceiling that the contract has.

        Each verdict is a call of the assertion of the ceiling on the
        recording surface. The assertions are bench-max-latency,
        bench-max-mean and bench-max-bytes. A ceiling that the measurement
        crosses fails with the ceiling as want and the measurement as got, so
        one run reports every crossed ceiling. A run without a measured
        iteration does not report a verdict.
        """
        __tracebackhide__ = True
        self._seat.helper()
        if not self._each:
            return

        ordered = sorted(self._each)
        tail = ordered[int((len(ordered) - 1) * P99)]
        mean = sum(ordered) / len(ordered)

        if self._max_latency is not None:
            self._ceiling("bench-max-latency", self._max_latency, tail)
        if self._max_mean is not None:
            self._ceiling("bench-max-mean", self._max_mean, mean)
        if self._max_bytes is not None and self._peaks:
            self._ceiling(
                "bench-max-bytes", self._max_bytes, sum(self._peaks) / len(self._peaks)
            )

    def _ceiling(self, assertion: str, want: float, got: float) -> None:
        """Report the verdict of one ceiling. It is a failure when got crosses want."""
        __tracebackhide__ = True
        contract = _CONTRACTS[assertion]
        if got > want:
            fail(self._seat, Mode.SOFT, assertion, contract, {"want": want, "got": got})
            return
        pass_(self._seat, Mode.SOFT, assertion, contract)

    def _rebase(self) -> None:
        """Start a new span that measures above the memory that is live now."""
        if self._traced:
            tracemalloc.reset_peak()
            self._base = tracemalloc.get_traced_memory()[0]

    def _reached(self) -> int:
        """Return the peak of the current span above its baseline."""
        return tracemalloc.get_traced_memory()[1] - self._base
