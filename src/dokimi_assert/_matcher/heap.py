# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The ceiling on the heap that a call keeps reachable.

A reading collects the cycles of the heap with gc.collect, and returns the
current size of the memory that tracemalloc traces. The assertion starts
tracemalloc for the call when it is off, and stops it afterwards. When the
caller traces already, the assertion reads the caller's trace and leaves it
running.
"""

from __future__ import annotations

import gc
import tracemalloc
from array import array
from typing import TYPE_CHECKING, Any

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.verdict import Running
from dokimi_assert.failure import call_site

if TYPE_CHECKING:
    from collections.abc import Callable

    from dokimi_assert._matcher.seat import Mode, Seat

__all__ = ["LIVE_RUNS", "max_live_bytes"]

#: The most runs that max_live_bytes takes. The assertion fails when none of
#: them meets the ceiling.
LIVE_RUNS = 10


def max_live_bytes(
    seat: Seat,
    mode: Mode,
    fn: Callable[[Callable[[], None]], Any],
    ceiling: int,
    msg: str,
) -> None:
    """Report when fn keeps more than ceiling bytes reachable at a probe.

    The assertion first runs its probe once on a callable that only calls
    the probe, so the first run of fn reads no memory of a cold probe. It
    calls fn once with a probe that reads nothing to warm it. A run then
    reads the traced memory, and calls fn with a probe that reads
    it at each call. The excess of a run is its largest reading less the
    first reading, or 0. A run whose excess exceeds ceiling is taken again,
    ten runs at most. When no run meets ceiling, got is the smallest excess
    and probes the calls of the probe in its run. A fn that calls the probe
    in its first run 0 times ends the call with a fault.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        fn: The callable under test. It takes the probe.
        ceiling: The most bytes that fn keeps reachable at a probe.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    call = Running.of(seat, call_site())
    tracing = tracemalloc.is_tracing()
    if not tracing:
        tracemalloc.start()
    try:
        _run(lambda probe: probe())
        fn(lambda: None)
        runs: list[tuple[int, int]] = []
        while len(runs) < LIVE_RUNS:
            runs.append(_run(fn))
            if runs[0][1] == 0 or runs[-1][0] <= ceiling:
                break
    finally:
        if not tracing:
            tracemalloc.stop()
    if runs[0][1] == 0:
        call.faulted(
            mode,
            "max-live-bytes",
            msg,
            FaultError("", "the callable called the probe 0 times"),
        )
        return
    if runs[-1][0] <= ceiling:
        call.passed(mode, "max-live-bytes", msg)
        return
    excess, probes = min(runs)
    call.failed(
        mode,
        "max-live-bytes",
        msg,
        {"want": ceiling, "got": excess, "probes": probes},
    )


def _run(fn: Callable[[Callable[[], None]], Any]) -> tuple[int, int]:
    """Run fn once, and return its excess and the calls of its probe.

    The probe and its state exist before the first reading, so each reading
    contains them. The state is an array of machine words, so a reading
    contains no int object that a reading created.
    """
    first, largest, probes = 0, 1, 2
    state = array("q", [0, 0, 0])

    def probe() -> None:
        state[probes] += 1
        state[largest] = max(state[largest], _live() - state[first])

    state[first] = _live()
    fn(probe)
    return state[largest], state[probes]


def _live() -> int:
    """Return the size of the traced memory after a collection."""
    gc.collect()
    return tracemalloc.get_traced_memory()[0]
