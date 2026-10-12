"""The spec of rejects.py: the assertion that a check fails."""

from __future__ import annotations

import asyncio
from typing import Any

from dokimi_assert import check, expect
from dokimi_assert._matcher.seat import Mode
from dokimi_assert.failure import Failure
from dokimi_assert.rejects import rejects
from dokimi_assert.seat import Collector, Recorder, Seat, Standard
from helpers import records


class TestRejects:
    """rejects, a check driven against a subject that it must reject."""

    def test_passes_a_check_that_fails(self, seat: Collector) -> None:
        """A failing check passes rejects."""
        recorder = Recorder()
        rejects(
            recorder,
            Mode.FATAL,
            "an empty name is refused",
            lambda inner: check.is_none(inner, "not empty", "it passes"),
        )
        check.is_false(seat, recorder.failed, "a failing check passes rejects")

    def test_returns_the_failure_records_of_the_check(self, seat: Collector) -> None:
        """The records are those that the check reported."""
        failures = rejects(
            Recorder(),
            Mode.FATAL,
            "an empty name is refused",
            lambda inner: check.is_none(inner, "not empty", "it passes"),
        )
        check.equal(
            seat,
            [(f.assertion, f.contract, dict(f.detail)) for f in failures],
            [("nil", "it passes", {"got": "not empty"})],
            "the record is the failure of the check",
        )

    def test_reports_a_failure_without_detail_for_a_check_that_passes(
        self, seat: Collector
    ) -> None:
        """A check that cannot fail fails rejects."""
        recorder = Recorder()
        rejects(
            recorder,
            Mode.FATAL,
            "an empty name is refused",
            lambda inner: check.is_none(inner, None, "it passes"),
        )
        check.equal(
            seat,
            [(f.assertion, f.contract, dict(f.detail)) for f in recorder.failures],
            [("rejects", "an empty name is refused", {})],
            "rejects reports the passing check",
        )

    def test_returns_no_record_for_a_check_that_passes(self, seat: Collector) -> None:
        """A passing check has no record."""
        failures = rejects(
            Recorder(),
            Mode.SOFT,
            "it is refused",
            lambda inner: check.is_none(inner, None, "it passes"),
        )
        check.is_empty(seat, failures, "a passing check has no record")

    def test_raises_on_a_standard_seat_for_a_check_that_passes(
        self, seat: Collector
    ) -> None:
        """A standard seat raises the failure of rejects."""
        raised = check.raises(
            seat,
            lambda: rejects(
                Standard(), Mode.FATAL, "it is refused", lambda inner: None
            ),
            "rejects raises on a standard seat",
        )
        check.is_true(seat, isinstance(raised, AssertionError), "an AssertionError")

    def test_ends_the_check_at_its_first_failure_that_stops(
        self, seat: Collector
    ) -> None:
        """An aborting failure ends the check, as it ends a test."""
        reached: list[str] = []

        def body(inner: Seat) -> None:
            check.is_none(inner, 1, "the first")
            reached.append("after")
            check.is_none(inner, 2, "the second")

        failures = rejects(Recorder(), Mode.FATAL, "the first failure ends it", body)
        check.is_empty(seat, reached, "the check stopped at its first failure")
        check.equal(seat, [f.contract for f in failures], ["the first"], "one record")

    def test_ends_the_check_at_a_message_sent_to_fail_of_its_seat(
        self, seat: Collector
    ) -> None:
        """A bare message to fail fails the check and ends it."""
        reached: list[str] = []
        recorder = Recorder()

        def body(inner: Seat) -> None:
            inner.fail("a message of the check's own")
            reached.append("after")

        failures = rejects(recorder, Mode.FATAL, "a bare failure ends it", body)
        check.is_empty(seat, reached, "the check stopped at the message")
        check.is_false(seat, recorder.failed, "the message fails the check")
        check.is_empty(seat, failures, "the message has no record")

    def test_keeps_every_failure_that_the_recording_surface_reports(
        self, seat: Collector
    ) -> None:
        """A recorded failure does not end the check."""

        def body(inner: Seat) -> None:
            expect.is_none(inner, 1, "the first")
            expect.is_none(inner, 2, "the second")

        failures = rejects(Recorder(), Mode.FATAL, "both are kept", body)
        check.equal(
            seat,
            [f.contract for f in failures],
            ["the first", "the second"],
            "both records are kept",
        )

    def test_counts_a_message_sent_to_record_as_a_failure_without_a_record(
        self, seat: Collector
    ) -> None:
        """A bare message to record fails the check."""
        recorder = Recorder()
        failures = rejects(
            recorder,
            Mode.FATAL,
            "a bare message fails the check",
            lambda inner: inner.record("a message of the check's own"),
        )
        check.is_false(seat, recorder.failed, "the message fails the check")
        check.is_empty(seat, failures, "the message has no record")

    def test_runs_a_coroutine_check(self, seat: Collector) -> None:
        """A coroutine function runs on the loop of the call."""

        async def body(inner: Seat) -> None:
            await asyncio.sleep(0)
            check.is_true(inner, False, "it is true later")

        failures = rejects(Recorder(), Mode.FATAL, "an async check fails", body)
        check.equal(seat, [f.contract for f in failures], ["it is true later"], "it")

    def test_ends_with_a_fault_inside_a_running_event_loop(
        self, seat: Collector
    ) -> None:
        """A coroutine check that the call cannot run ends the call."""
        recorder = Recorder()

        async def body(_: Seat) -> None:
            return None

        async def test() -> list[Failure]:
            return rejects(recorder, Mode.SOFT, "a check in a loop", body)

        failures = asyncio.run(test())
        check.is_empty(seat, failures, "the fault has no record")
        check.has_prefix(
            seat, recorder.message, "rejects runs a coroutine", "the fault"
        )

    def test_lets_an_exception_of_the_check_leave_the_call(
        self, seat: Collector
    ) -> None:
        """An exception of the check is a defect and no rejection."""
        error = RuntimeError("the check broke")

        def body(_: Any) -> None:
            raise error

        raised = check.raises(
            seat,
            lambda: rejects(Recorder(), Mode.FATAL, "a broken check", body),
            "rejects raises the error of the check",
        )
        check.is_true(seat, raised is error, "the error of the check")

    def test_records_the_calls_of_the_check_under_the_call_of_rejects(
        self, seat: Collector
    ) -> None:
        """The calls of the check are a run of rejects."""
        recorder = Recorder()

        def body(inner: Seat) -> None:
            check.is_true(inner, True, "it passes first")
            check.is_true(inner, False, "it fails then")

        rejects(recorder, Mode.FATAL, "the calls of the check are recorded", body)
        check.equal(
            seat,
            [
                (r["seq"], r.get("parent"), r.get("run"), r["assertion"], r["verdict"])
                for r in records(recorder)
            ],
            [
                (1, None, None, "rejects", "pass"),
                (2, 1, 1, "true", "pass"),
                (3, 1, 1, "true", "fail"),
            ],
            "the calls of the check",
        )
