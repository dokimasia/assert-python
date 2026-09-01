"""Ceilings a benchmark must stay within.

Written with the library, as a consumer would.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from dokimi_assert import bench, check
from dokimi_assert.seat import Recorder, Standard

#: The seat this file's own assertions report through.
OUTER = Standard()

#: Enough iterations that a p99 differs from the slowest sample, few
#: enough to stay quick.
ITERATIONS = 100


def _run(
    iterations: int,
    state: Callable[[bench.Contract], bench.Contract],
    body: Callable[[], object],
) -> Recorder:
    """Drive a contract over a body and answer the seat it reported to."""
    seat = Recorder()
    contract = state(bench.Contract(seat))

    for _ in contract.loop(iterations):
        body()
    contract.check()

    return seat


def _noop() -> object:
    """Cost as little as a body can."""
    return None


def test_the_body_runs_once_per_iteration() -> None:
    """Every iteration runs the body exactly once."""
    calls = 0

    def count() -> None:
        nonlocal calls
        calls += 1

    _run(ITERATIONS, lambda c: c, count)
    check.equal(OUTER, calls, ITERATIONS, "the body runs once per iteration")


def test_a_benchmark_of_no_iterations_reports_nothing() -> None:
    """Nothing measured means no ceiling to exceed."""
    seat = _run(0, lambda c: c.max_latency(1e-9), _noop)
    check.is_false(OUTER, seat.failed, "nothing measured reports nothing")


def test_an_unstated_ceiling_is_not_checked() -> None:
    """A ceiling nobody stated is not enforced."""
    seat = _run(ITERATIONS, lambda c: c, lambda: bytearray(4096))
    check.is_false(OUTER, seat.failed, "an unstated ceiling is not enforced")


def test_a_ceiling_that_holds_reports_nothing() -> None:
    """A second per iteration is not exceeded by an empty body."""
    seat = _run(ITERATIONS, lambda c: c.max_latency(1.0).max_mean(1.0), _noop)
    check.is_false(OUTER, seat.failed, "a ceiling that holds reports nothing")


def test_an_exceeded_latency_ceiling_names_the_p99() -> None:
    """A body slower than its ceiling is reported, naming which."""
    seat = _run(5, lambda c: c.max_latency(1e-9), lambda: time.sleep(0.001))

    check.is_true(OUTER, seat.failed, "a slow body reports")
    check.contains(OUTER, seat.message, "p99", "the failure names the ceiling")


def test_every_exceeded_ceiling_is_reported() -> None:
    """One run names each ceiling exceeded, not only the first."""
    seat = _run(
        5,
        lambda c: c.max_latency(1e-9).max_mean(1e-9),
        lambda: time.sleep(0.001),
    )
    check.length(OUTER, seat.messages, 2, "both exceeded ceilings are reported")


def test_an_exceeded_allocation_ceiling_reports() -> None:
    """A body that allocates exceeds a ceiling of none."""
    seat = _run(ITERATIONS, lambda c: c.max_allocs(0), lambda: bytearray(4096))
    check.is_true(OUTER, seat.failed, "a body that allocates reports")


def test_a_ceiling_returns_the_contract_so_they_chain() -> None:
    """Stating a ceiling answers the contract it was stated on."""
    contract = bench.Contract(Recorder())
    check.equal(
        OUTER,
        contract.max_latency(1.0).max_mean(1.0).max_allocs(1).max_bytes(1),
        contract,
        "every ceiling returns the contract",
    )


def test_excluding_answers_what_the_setup_made() -> None:
    """The fixture reaches the measured work, which is the point of it."""
    seat = Recorder()
    contract = bench.Contract(seat)

    for _ in contract.loop(1):
        held = contract.excluding(lambda: [1, 2, 3])
        check.equal(OUTER, held, [1, 2, 3], "it answers what setup answered")
    contract.check()


def test_excluding_takes_the_setup_time_out_of_the_ceiling() -> None:
    """Time spent in setup is not time the operation took."""
    seat = Recorder()
    contract = bench.Contract(seat).max_latency(0.005)

    for _ in contract.loop(3):
        contract.excluding(lambda: time.sleep(0.02))
    contract.check()

    check.is_false(OUTER, seat.failed, "an excluded sleep is not timed")


def test_the_same_sleep_unexcluded_crosses_the_ceiling() -> None:
    """Without this the case above passes against an excluding that does nothing."""
    seat = Recorder()
    contract = bench.Contract(seat).max_latency(0.005)

    for _ in contract.loop(3):
        time.sleep(0.02)
    contract.check()

    check.is_true(OUTER, seat.failed, "a sleep nobody excluded is timed")
