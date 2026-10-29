# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of rejects.py: the assertion that a check fails."""

from __future__ import annotations

import asyncio
import contextlib
import unittest
from typing import TYPE_CHECKING, Any

from dokimi_assert import check, expect
from dokimi_assert._matcher.seat import Mode
from dokimi_assert.rejects import rejects
from dokimi_assert.seat import Collector, Recorder, Seat, Standard, cleanup, fault
from helpers import records

if TYPE_CHECKING:
    from dokimi_assert.failure import Failure


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
            lambda: rejects(Standard(), Mode.FATAL, "it is refused", lambda _: None),
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

    def test_runs_the_cleanups_of_the_check_before_it_returns(
        self, seat: Collector
    ) -> None:
        """The check's cleanups run once the check ends, the last registered first."""
        order: list[str] = []

        def body(inner: Seat) -> None:
            cleanup(inner, lambda: order.append("first"))
            cleanup(inner, lambda: order.append("second"))
            check.is_true(inner, False, "the check fails")

        rejects(Recorder(), Mode.FATAL, "the check fails", body)
        check.equal(
            seat, order, ["second", "first"], "the cleanups ran before rejects returned"
        )

    def test_returns_the_record_of_a_failure_in_a_cleanup(
        self, seat: Collector
    ) -> None:
        """A failure in a cleanup fails the check, and rejects passes."""
        recorder = Recorder()

        def body(inner: Seat) -> None:
            cleanup(inner, lambda: check.is_true(inner, False, "the server stopped"))

        failures = rejects(
            recorder, Mode.FATAL, "a stopped server fails the check", body
        )
        check.equal(
            seat,
            [f.contract for f in failures],
            ["the server stopped"],
            "rejects returns the record of the cleanup",
        )
        check.is_false(seat, recorder.failed, "rejects passes")

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

    def test_ends_with_the_fault_that_ends_a_call_of_the_check(
        self, seat: Collector
    ) -> None:
        """A check that ends with a fault rejects nothing."""
        recorder = Recorder()
        refused = ValueError("the check calls restart without restartable")
        reached: list[str] = []

        def body(inner: Seat) -> None:
            fault(inner, refused)
            reached.append("after")

        failures = rejects(recorder, Mode.SOFT, "a check that faults", body)
        check.is_empty(seat, reached, "the fault ended the check")
        check.is_empty(seat, failures, "the fault has no record")
        check.equal(seat, recorder.faults, [refused], "the seat receives the fault")
        check.equal(
            seat,
            [(r["assertion"], r["verdict"], r.get("error")) for r in records(recorder)],
            [("rejects", "error", "the check calls restart without restartable")],
            "the call of rejects ends with the fault",
        )

    def test_ends_with_the_first_fault_of_a_check_that_runs_on_past_it(
        self, seat: Collector
    ) -> None:
        """A check that suppresses the end of its first fault still ends with it."""
        recorder = Recorder()
        first = ValueError("the first fault")

        def body(inner: Seat) -> None:
            with contextlib.suppress(BaseException):
                fault(inner, first)
            fault(inner, ValueError("the second fault"))

        rejects(recorder, Mode.SOFT, "a check with two faults", body)
        check.equal(seat, recorder.faults, [first], "the seat receives the first")

    def test_passes_a_noted_fault_of_the_check_to_its_seat(
        self, seat: Collector
    ) -> None:
        """The check runs on past a noted fault."""
        recorder = Recorder()
        noted = OSError("the store skips a file")

        def body(inner: Any) -> None:
            inner.report_fault(noted, False)
            check.is_none(inner, 1, "it fails after the note")

        failures = rejects(recorder, Mode.FATAL, "a check with a note", body)
        check.equal(
            seat,
            [f.contract for f in failures],
            ["it fails after the note"],
            "the check ran on",
        )
        check.equal(seat, recorder.faults, [noted], "the seat receives the note")
        check.is_false(seat, recorder.failed, "rejects passes")

    def test_ends_as_skipped_for_a_check_that_skips_before_it_fails(
        self, seat: Collector
    ) -> None:
        """A check that cannot run has no verdict on the subject."""
        recorder = Recorder()
        reached: list[str] = []

        def body(inner: Any) -> None:
            inner.skip("the check needs a disk")
            reached.append("after")

        failures = rejects(recorder, Mode.FATAL, "a check that skips", body)
        check.is_empty(seat, reached, "the skip ended the check")
        check.is_empty(seat, failures, "the skip has no record")
        check.is_false(seat, recorder.failed, "the skip fails nothing")
        check.equal(
            seat,
            [(r["assertion"], r["verdict"], r["reason"]) for r in records(recorder)],
            [("rejects", "skip", "the check needs a disk")],
            "the call of rejects ends as skipped",
        )

    def test_skips_the_test_of_a_seat_that_skips(self, seat: Collector) -> None:
        """A standard seat raises unittest.SkipTest with the reason of the check."""
        raised = check.raises(
            seat,
            lambda: rejects(
                Standard(),
                Mode.SOFT,
                "a check that skips",
                lambda inner: inner.skip("the check needs a disk"),
            ),
            "rejects skips the test",
        )
        check.is_true(seat, isinstance(raised, unittest.SkipTest), "a SkipTest")
        check.equal(seat, str(raised), "the check needs a disk", "the reason")

    def test_keeps_the_reason_of_the_first_skip(self, seat: Collector) -> None:
        """A check that suppresses the end of its first skip still ends with it."""
        recorder = Recorder()

        def body(inner: Any) -> None:
            with contextlib.suppress(BaseException):
                inner.skip("the first reason")
            inner.skip("the second reason")

        rejects(recorder, Mode.FATAL, "a check with two skips", body)
        check.equal(
            seat,
            [r.get("reason") for r in records(recorder)],
            ["the first reason"],
            "the call of rejects has the first reason",
        )

    def test_passes_a_check_that_fails_and_then_skips(self, seat: Collector) -> None:
        """The failure has already rejected the subject."""
        recorder = Recorder()

        def body(inner: Any) -> None:
            expect.is_none(inner, 1, "it fails first")
            inner.skip("the check needs a disk")

        failures = rejects(recorder, Mode.FATAL, "a check that skips late", body)
        check.equal(
            seat, [f.contract for f in failures], ["it fails first"], "the records"
        )
        check.equal(
            seat,
            [r["verdict"] for r in records(recorder) if r["assertion"] == "rejects"],
            ["pass"],
            "rejects passes",
        )

    def test_passes_a_noted_fault_of_a_check_that_then_skips_to_its_seat(
        self, seat: Collector
    ) -> None:
        """The seat receives the note before the skip ends the call."""
        recorder = Recorder()
        noted = OSError("the store skips a file")

        def body(inner: Any) -> None:
            inner.report_fault(noted, False)
            inner.skip("the check needs a disk")

        failures = rejects(recorder, Mode.FATAL, "a check with a note", body)
        check.is_empty(seat, failures, "the skip has no record")
        check.equal(seat, recorder.faults, [noted], "the seat receives the note")
        check.equal(
            seat,
            [r["verdict"] for r in records(recorder)],
            ["skip"],
            "the call of rejects ends as skipped",
        )

    def test_lets_a_skip_test_of_the_check_leave_the_call(
        self, seat: Collector
    ) -> None:
        """A raised unittest.SkipTest is not a call of skip."""
        skipped = unittest.SkipTest("the check needs a disk")

        def body(_: Any) -> None:
            raise skipped

        raised = check.raises(
            seat,
            lambda: rejects(Recorder(), Mode.FATAL, "a check that raises", body),
            "rejects raises the SkipTest of the check",
        )
        check.is_true(seat, raised is skipped, "the SkipTest of the check")

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
