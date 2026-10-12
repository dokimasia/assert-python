"""The spec of bench.py tests the ceilings of a benchmark and their verdicts."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any, ClassVar

import pytest

from dokimi_assert import bench, check
from dokimi_assert.seat import Collector, Recorder
from helpers import records

#: The iterations of a case. A p99 of 100 samples differs from the slowest
#: sample, and 100 iterations run quickly.
ITERATIONS = 100

#: About the bytes that tracemalloc counts for one bytearray(4096) with its
#: header. The ceilings of the cases are far from it.
BLOCK = 4200

#: A ceiling of latency far above the latency of an iteration without work.
GENEROUS = 1.0

#: A ceiling of latency that a sleep of 20 ms crosses.
TIGHT = 0.01


def run(
    iterations: int,
    state: Callable[[bench.Contract], bench.Contract],
    body: Callable[[int], object],
) -> Recorder:
    """Drive a contract over body, and return the recorder of its verdicts."""
    recorder = Recorder()
    contract = state(bench.Contract(recorder))
    for index in contract.loop(iterations):
        body(index)
    contract.check()
    return recorder


def verdicts(recorder: Recorder) -> list[tuple[str, str]]:
    """Return the assertion and the verdict of each call record of recorder."""
    return [(r["assertion"], r["verdict"]) for r in records(recorder)]


def nothing(_: int) -> None:
    """Return at once. This is the cheapest body."""


def churn(_: int) -> None:
    """Allocate ten blocks, and free them all before the iteration ends."""
    held = [bytearray(4096) for _ in range(10)]
    del held


def first_call_allocates() -> Callable[[int], None]:
    """Return a body that allocates 64 KiB on its first call alone."""
    first = [True]

    def body(_: int) -> None:
        if first:
            first.clear()
            bytearray(64 * 1024)

    return body


class TestContract:
    """Contract checks the ceilings of a benchmark."""

    def test_returns_a_contract_without_ceilings(self, seat: Collector) -> None:
        """A contract without ceilings does not report a verdict."""
        recorder = run(5, lambda c: c, lambda _: time.sleep(0.001))
        check.equal(
            seat, recorder.records, [], "the contract does not report a verdict"
        )


class TestContractWarmup:
    """Contract.warmup sets the iterations before the measured ones."""

    def test_returns_the_contract(self, seat: Collector) -> None:
        """The calls chain."""
        contract = bench.Contract(Recorder())
        check.equal(seat, contract.warmup(3), contract, "warmup returns the contract")

    def test_runs_the_warm_up_iterations_before_the_measured_ones(
        self, seat: Collector
    ) -> None:
        """The loop yields two iterations more than it measures."""
        contract = bench.Contract(Recorder()).warmup(2)
        check.equal(
            seat,
            list(contract.loop(3)),
            [0, 1, 2, 3, 4],
            "the loop yields five indexes",
        )

    def test_leaves_the_warm_up_iterations_out_of_the_latency(
        self, seat: Collector
    ) -> None:
        """A sleep in the warm-up alone stays within a ceiling that it would cross."""
        recorder = run(
            3,
            lambda c: c.warmup(2).max_latency(TIGHT),
            lambda i: time.sleep(0.02) if i < 2 else None,
        )
        check.equal(
            seat,
            verdicts(recorder),
            [("bench-max-latency", "pass")],
            "the latency passes",
        )

    def test_leaves_the_warm_up_iterations_out_of_the_bytes(
        self, seat: Collector
    ) -> None:
        """The allocation of the first call falls in the warm-up."""
        recorder = run(
            1, lambda c: c.warmup(1).max_bytes(BLOCK * 2), first_call_allocates()
        )
        check.equal(
            seat, verdicts(recorder), [("bench-max-bytes", "pass")], "the bytes pass"
        )

    def test_measures_the_first_iteration_by_default(self, seat: Collector) -> None:
        """The default warm-up is 0."""
        recorder = run(1, lambda c: c.max_bytes(BLOCK * 2), first_call_allocates())
        check.equal(
            seat, verdicts(recorder), [("bench-max-bytes", "fail")], "the bytes fail"
        )

    tests: ClassVar[list[tuple[str, Any, str]]] = [
        (
            "raises value error for a negative count",
            -1,
            "bench: warmup takes an int of 0 or more, not -1",
        ),
        (
            "raises value error for a count that is not an int",
            1.5,
            "bench: warmup takes an int of 0 or more, not 1.5",
        ),
        (
            "raises value error for a bool",
            True,
            "bench: warmup takes an int of 0 or more, not True",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for_a_count_that_it_refuses(
        self, seat: Collector, give: Any, want: str
    ) -> None:
        """The error has the count."""
        contract = bench.Contract(Recorder())
        error = check.raises(seat, lambda: contract.warmup(give), "warmup raises")
        check.error_as(seat, error, ValueError, "the error is a ValueError")
        check.equal(seat, str(error), want, "the error has the count")

    def test_raises_value_error_after_loop_has_started(self, seat: Collector) -> None:
        """The warm-up comes before the first iteration."""
        contract = bench.Contract(Recorder())
        iterations = contract.loop(2)
        next(iterations)
        error = check.raises(seat, lambda: contract.warmup(1), "warmup raises")
        check.equal(
            seat,
            str(error),
            "bench: warmup cannot run after loop has started",
            "the error has the reason",
        )


class TestContractMaxLatency:
    """Contract.max_latency sets the ceiling of the p99 latency."""

    def test_returns_the_contract(self, seat: Collector) -> None:
        """The calls chain."""
        contract = bench.Contract(Recorder())
        check.equal(
            seat,
            contract.max_latency(GENEROUS),
            contract,
            "max_latency returns the contract",
        )

    def test_passes_a_body_within_its_ceiling(self, seat: Collector) -> None:
        """An iteration without work takes far less than a second."""
        recorder = run(ITERATIONS, lambda c: c.max_latency(GENEROUS), nothing)
        check.equal(
            seat,
            verdicts(recorder),
            [("bench-max-latency", "pass")],
            "the latency passes",
        )

    def test_fails_a_body_past_its_ceiling_with_the_ceiling_as_want(
        self, seat: Collector
    ) -> None:
        """The failure has the ceiling and the p99."""
        recorder = run(5, lambda c: c.max_latency(1e-9), lambda _: time.sleep(0.001))
        [failure] = recorder.failures
        check.equal(
            seat,
            failure.assertion,
            "bench-max-latency",
            "the failure is of bench-max-latency",
        )
        check.equal(seat, failure.want, 1e-9, "want is the ceiling")
        check.in_range(
            seat, failure.got, 0.0009, GENEROUS, "got is the p99 of the sleep"
        )


class TestContractMaxMean:
    """Contract.max_mean sets the ceiling of the mean latency."""

    def test_returns_the_contract(self, seat: Collector) -> None:
        """The calls chain."""
        contract = bench.Contract(Recorder())
        check.equal(
            seat, contract.max_mean(GENEROUS), contract, "max_mean returns the contract"
        )

    def test_passes_a_body_within_its_ceiling(self, seat: Collector) -> None:
        """An iteration without work takes far less than a second."""
        recorder = run(ITERATIONS, lambda c: c.max_mean(GENEROUS), nothing)
        check.equal(
            seat, verdicts(recorder), [("bench-max-mean", "pass")], "the mean passes"
        )

    def test_fails_a_body_past_its_ceiling_with_the_ceiling_as_want(
        self, seat: Collector
    ) -> None:
        """The failure has the ceiling and the mean."""
        recorder = run(5, lambda c: c.max_mean(1e-9), lambda _: time.sleep(0.001))
        [failure] = recorder.failures
        check.equal(
            seat,
            failure.assertion,
            "bench-max-mean",
            "the failure is of bench-max-mean",
        )
        check.equal(seat, failure.want, 1e-9, "want is the ceiling")
        check.in_range(
            seat, failure.got, 0.0009, GENEROUS, "got is the mean of the sleep"
        )


class TestContractMaxBytes:
    """Contract.max_bytes sets the ceiling of the peak bytes of an iteration."""

    def test_returns_the_contract(self, seat: Collector) -> None:
        """The calls chain."""
        contract = bench.Contract(Recorder())
        check.equal(
            seat, contract.max_bytes(1), contract, "max_bytes returns the contract"
        )

    def test_passes_a_body_within_its_ceiling(self, seat: Collector) -> None:
        """One block per iteration stays within a ceiling of two."""
        recorder = run(
            ITERATIONS, lambda c: c.max_bytes(BLOCK * 2), lambda _: bytearray(4096)
        )
        check.equal(
            seat, verdicts(recorder), [("bench-max-bytes", "pass")], "the bytes pass"
        )

    def test_fails_a_body_past_its_ceiling_with_the_ceiling_as_want(
        self, seat: Collector
    ) -> None:
        """The failure has the ceiling and the mean of the peaks."""
        recorder = run(
            ITERATIONS,
            lambda c: c.max_bytes(BLOCK * 2),
            lambda _: bytearray(64 * 1024),
        )
        [failure] = recorder.failures
        check.equal(seat, failure.want, BLOCK * 2, "want is the ceiling")
        check.in_range(
            seat, failure.got, 64 * 1024, 64 * 1024 + BLOCK, "got is a peak of 64 KiB"
        )

    def test_counts_memory_that_the_body_frees_before_the_iteration_ends(
        self, seat: Collector
    ) -> None:
        """Ten blocks that the body frees still cross a ceiling of four."""
        recorder = run(ITERATIONS, lambda c: c.max_bytes(BLOCK * 4), churn)
        check.equal(
            seat, verdicts(recorder), [("bench-max-bytes", "fail")], "the bytes fail"
        )

    def test_does_not_count_the_memory_of_the_contract_itself(
        self, seat: Collector
    ) -> None:
        """An iteration without work stays within a ceiling of 1024 bytes."""
        recorder = run(ITERATIONS, lambda c: c.max_bytes(1024), nothing)
        check.equal(
            seat, verdicts(recorder), [("bench-max-bytes", "pass")], "the bytes pass"
        )


class TestContractLoop:
    """Contract.loop yields the measured iterations of the body."""

    def test_runs_the_body_once_per_iteration(self, seat: Collector) -> None:
        """Every iteration runs the body once."""
        calls: list[int] = []
        run(ITERATIONS, lambda c: c, calls.append)
        check.length(seat, calls, ITERATIONS, "the body runs once per iteration")

    def test_yields_the_index_of_each_iteration(self, seat: Collector) -> None:
        """The indexes count from 0."""
        contract = bench.Contract(Recorder())
        check.equal(
            seat, list(contract.loop(3)), [0, 1, 2], "the indexes are 0, 1 and 2"
        )


class TestContractExcluding:
    """Contract.excluding runs work outside the measurement."""

    def test_returns_what_setup_returns(self, seat: Collector) -> None:
        """The measured work receives the input."""
        contract = bench.Contract(Recorder())
        for _ in contract.loop(1):
            made = contract.excluding(lambda: [1, 2, 3])
            check.equal(seat, made, [1, 2, 3], "excluding returns the input")

    def test_takes_the_time_of_setup_out_of_the_ceiling(self, seat: Collector) -> None:
        """The contract does not time a sleep inside excluding."""
        recorder = Recorder()
        contract = bench.Contract(recorder).max_latency(TIGHT)
        for _ in contract.loop(3):
            contract.excluding(lambda: time.sleep(0.02))
        contract.check()
        check.equal(
            seat,
            verdicts(recorder),
            [("bench-max-latency", "pass")],
            "the latency passes",
        )

    def test_leaves_a_sleep_outside_it_in_the_measurement(
        self, seat: Collector
    ) -> None:
        """The same sleep without excluding crosses the ceiling."""
        recorder = run(3, lambda c: c.max_latency(TIGHT), lambda _: time.sleep(0.02))
        check.equal(
            seat,
            verdicts(recorder),
            [("bench-max-latency", "fail")],
            "the latency fails",
        )

    def test_takes_the_bytes_of_setup_out_of_the_ceiling(self, seat: Collector) -> None:
        """The memory that setup has live does not count for the operation."""
        recorder = Recorder()
        contract = bench.Contract(recorder).max_bytes(BLOCK * 2)
        for _ in contract.loop(ITERATIONS):
            held = contract.excluding(lambda: [bytearray(4096) for _ in range(10)])
            del held
        contract.check()
        check.equal(
            seat, verdicts(recorder), [("bench-max-bytes", "pass")], "the bytes pass"
        )

    def test_leaves_memory_outside_it_in_the_measurement(self, seat: Collector) -> None:
        """The same blocks without excluding cross the ceiling."""
        recorder = run(ITERATIONS, lambda c: c.max_bytes(BLOCK * 2), churn)
        check.equal(
            seat, verdicts(recorder), [("bench-max-bytes", "fail")], "the bytes fail"
        )

    def test_does_not_shorten_a_measured_iteration_from_a_warm_up_one(
        self, seat: Collector
    ) -> None:
        """A long setup in the warm-up does not shorten the measured iteration."""
        recorder = Recorder()
        contract = bench.Contract(recorder).warmup(1).max_latency(TIGHT)
        for index in contract.loop(1):
            if index == 0:
                contract.excluding(lambda: time.sleep(0.05))
            else:
                time.sleep(0.02)
        contract.check()
        check.equal(
            seat,
            verdicts(recorder),
            [("bench-max-latency", "fail")],
            "the latency fails",
        )

    def test_does_not_shorten_a_measured_iteration_from_before_the_loop(
        self, seat: Collector
    ) -> None:
        """A setup before the loop does not shorten the first iteration."""
        recorder = Recorder()
        contract = bench.Contract(recorder).max_latency(TIGHT)
        contract.excluding(lambda: time.sleep(0.05))
        for _ in contract.loop(1):
            time.sleep(0.02)
        contract.check()
        check.equal(
            seat,
            verdicts(recorder),
            [("bench-max-latency", "fail")],
            "the latency fails",
        )


class TestContractCheck:
    """Contract.check reports the verdict of each ceiling."""

    def test_does_not_report_a_verdict_for_a_run_without_measured_iterations(
        self, seat: Collector
    ) -> None:
        """A run without measured iterations does not cross a ceiling."""
        recorder = run(0, lambda c: c.warmup(3).max_latency(1e-9), nothing)
        check.equal(seat, recorder.records, [], "check does not report a verdict")

    def test_writes_a_record_of_each_ceiling(self, seat: Collector) -> None:
        """Each ceiling that the body meets passes."""
        recorder = run(
            ITERATIONS, lambda c: c.max_latency(GENEROUS).max_mean(GENEROUS), nothing
        )
        check.equal(
            seat,
            verdicts(recorder),
            [("bench-max-latency", "pass"), ("bench-max-mean", "pass")],
            "both ceilings pass",
        )

    def test_reports_every_crossed_ceiling_on_the_recording_surface(
        self, seat: Collector
    ) -> None:
        """One run reports each crossed ceiling."""
        recorder = run(
            5, lambda c: c.max_latency(1e-9).max_mean(1e-9), lambda _: time.sleep(0.001)
        )
        check.equal(
            seat,
            [(r["assertion"], r["verdict"], r["aborting"]) for r in records(recorder)],
            [
                ("bench-max-latency", "fail", False),
                ("bench-max-mean", "fail", False),
            ],
            "both ceilings fail without aborting",
        )
        check.length(seat, recorder.messages, 2, "two failures are recorded")
