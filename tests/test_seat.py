# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of seat.py tests the seats that receive the failures of an assertion.

It uses pytest's assert alone, because every other spec asserts on a seat.
"""

from __future__ import annotations

import unittest
from typing import Any, cast

import pytest

from dokimi_assert import check, expect
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.clock import Controlled, System
from dokimi_assert.failure import Failure
from dokimi_assert.seat import (
    Collector,
    Recorder,
    Seat,
    Standard,
    clean_up,
    cleanup,
    fault,
)
from helpers import Uncleaned, records

FAILURE = Failure("equal", "the count is right", {"want": 1, "got": 2})

SENTENCE = "the count is right: want 1, got 2"


class TestFault:
    """fault ends the call of a helper with a fault."""

    def test_passes_the_fault_to_a_seat_with_report_fault(self) -> None:
        """A recorder keeps the fault, fails with its text, and keeps no record."""
        seat = Recorder()
        refused = ValueError("the check calls restart without restartable")
        fault(seat, refused)
        assert (seat.faults, seat.message, seat.records) == (
            [refused],
            "the check calls restart without restartable",
            [],
        )

    def test_raises_the_fault_on_a_seat_without_report_fault(self) -> None:
        """A standard seat ends the call with the exception itself."""
        refused = ValueError("the check calls restart without restartable")
        with pytest.raises(ValueError, match="without restartable") as raised:
            fault(Standard(), refused)
        assert raised.value is refused

    def test_raises_type_error_for_a_value_that_is_not_an_exception(self) -> None:
        """A fault is an exception."""
        with pytest.raises(
            TypeError, match=r"^seat\.fault\('refused'\) needs an exception$"
        ):
            fault(Recorder(), cast("Any", "refused"))


class TestSeat:
    """Seat describes the methods of a seat."""

    def test_describes_every_seat_of_the_module(self) -> None:
        """Every seat has helper, fail and record."""
        assert all(isinstance(s, Seat) for s in (Standard(), Recorder(), Collector()))


class TestStandard:
    """Standard raises on every failure."""

    def test_returns_a_seat_without_call_records(self) -> None:
        """A standard seat does not have records."""
        assert not hasattr(Standard(), "records")


class TestStandardHelper:
    """Standard.helper marks a frame of the library."""

    def test_returns_without_a_failure(self) -> None:
        """The seat does not do anything for a helper mark."""
        Standard().helper()


class TestStandardFail:
    """Standard.fail reports a failure that stops the test."""

    def test_raises_assertion_error_with_the_message(self) -> None:
        """The seat raises the message of fail."""
        with pytest.raises(AssertionError, match=r"^the stated contract$"):
            Standard().fail("the stated contract")


class TestStandardRecord:
    """Standard.record reports a failure after which the test would continue."""

    def test_raises_assertion_error_with_the_message(self) -> None:
        """The seat does not have an end of a test, so it raises the message."""
        with pytest.raises(AssertionError, match=r"^the stated contract$"):
            Standard().record("the stated contract")


class TestStandardSkip:
    """Standard.skip skips the test."""

    def test_raises_skip_test_with_the_reason(self) -> None:
        """The runner reports the test as skipped."""
        with pytest.raises(unittest.SkipTest, match=r"^the disk refuses direct I/O$"):
            Standard().skip("the disk refuses direct I/O")


class TestRecorder:
    """Recorder collects every failure and does not raise."""

    def test_returns_a_recorder_without_failures(self) -> None:
        """A new recorder does not have a failure or a record."""
        seat = Recorder()
        assert (seat.failed, seat.message, seat.messages, seat.failures) == (
            False,
            "",
            [],
            [],
        )
        assert (seat.records, seat.helper_calls) == ([], 0)

    def test_returns_a_recorder_that_keeps_the_call_record_of_each_call(
        self,
    ) -> None:
        """The recorder keeps records whatever the value of the switch."""
        seat = Recorder()
        check.is_true(seat, True, "the count is right")
        check.is_true(seat, False, "it fails")
        assert [r["verdict"] for r in records(seat)] == ["pass", "fail"]


class TestRecorderHelper:
    """Recorder.helper counts the marks of the frames of the library."""

    def test_counts_each_call(self) -> None:
        """helper_calls counts the calls of helper."""
        seat = Recorder()
        seat.helper()
        seat.helper()
        assert seat.helper_calls == 2


class TestRecorderReport:
    """Recorder.report receives the record of a failure."""

    def test_keeps_the_record_of_the_failure(self) -> None:
        """The recorder keeps the record that report receives."""
        seat = Recorder()
        seat.report(FAILURE, True)
        assert seat.failures == [FAILURE]

    def test_sends_the_sentence_of_an_aborting_failure_to_fail(self) -> None:
        """An aborting record goes to fail."""
        seat = Recorder()
        seat.report(FAILURE, True)
        assert (seat.message, seat.messages) == (SENTENCE, [])

    def test_sends_the_sentence_of_a_recording_failure_to_record(self) -> None:
        """A recording record goes to record."""
        seat = Recorder()
        seat.report(FAILURE, False)
        assert seat.messages == [SENTENCE]


class TestRecorderFailures:
    """Recorder.failures returns the records of the failures."""

    def test_does_not_return_a_record_of_a_bare_message(self) -> None:
        """A message that a caller passes to fail does not leave a record."""
        seat = Recorder()
        seat.fail("a bare message")
        assert seat.failures == []


class TestRecorderReportFault:
    """Recorder.report_fault receives a fault as the exception it is."""

    def test_fails_with_the_text_of_a_fault_that_ends_its_call(self) -> None:
        """An ending fault fails the recorder as fail does."""
        seat = Recorder()
        seat.report_fault(OSError("the store refuses a write"), True)
        assert (seat.message, seat.messages) == ("the store refuses a write", [])

    def test_does_not_fail_for_a_noted_fault(self) -> None:
        """The call runs on past a noted fault."""
        seat = Recorder()
        seat.report_fault(OSError("the store skips a file"), False)
        assert (seat.failed, seat.message) == (False, "")


class TestRecorderFaults:
    """Recorder.faults returns the faults that arrived."""

    def test_returns_every_fault_in_call_order(self) -> None:
        """The recorder keeps the ending faults and the noted ones."""
        seat = Recorder()
        noted = OSError("the store skips a file")
        ending = ValueError("the seed is not a number")
        seat.report_fault(noted, False)
        seat.report_fault(ending, True)
        assert seat.faults == [noted, ending]

    def test_returns_a_copy(self) -> None:
        """A caller can keep the list while the recorder takes faults."""
        seat = Recorder()
        kept = seat.faults
        seat.report_fault(OSError("the store skips a file"), False)
        assert kept == []


class TestRecorderRecords:
    """Recorder.records returns the call records of the calls."""

    def test_returns_the_records_in_the_order_of_their_numbers(self) -> None:
        """Both surfaces write into one sequence."""
        seat = Recorder()
        check.is_true(seat, True, "the first")
        expect.is_true(seat, True, "the second")
        assert [(r["seq"], r["contract"]) for r in records(seat)] == [
            (1, "the first"),
            (2, "the second"),
        ]


class TestRecorderClock:
    """Recorder.clock returns the clock that the assertions of the recorder read."""

    def test_returns_the_platform_clock_without_one(self) -> None:
        """A recorder without a clock reads the platform clock."""
        assert isinstance(Recorder().clock(), System)

    def test_returns_the_clock_that_with_clock_set(self) -> None:
        """with_clock sets the clock."""
        clock = Controlled(100)
        assert Recorder().with_clock(clock).clock() is clock


class TestRecorderWithClock:
    """Recorder.with_clock sets a clock of the test."""

    def test_returns_the_recorder(self) -> None:
        """with_clock chains."""
        seat = Recorder()
        assert seat.with_clock(Controlled(0)) is seat


class TestRecorderFail:
    """Recorder.fail keeps a failure that would stop a pytest test."""

    def test_keeps_the_first_message(self) -> None:
        """A pytest test stops at the first aborting failure."""
        seat = Recorder()
        seat.fail("the first")
        seat.fail("the second")
        assert seat.message == "the first"


class TestRecorderRecord:
    """Recorder.record keeps a failure after which the test continues."""

    def test_keeps_every_message_in_call_order(self) -> None:
        """The recorder keeps each message of record."""
        seat = Recorder()
        seat.record("the first")
        seat.record("the second")
        assert seat.messages == ["the first", "the second"]


class TestRecorderFailed:
    """Recorder.failed is True when the recorder received a failure."""

    def test_returns_true_after_a_message_to_fail(self) -> None:
        """A message to fail fails the recorder."""
        seat = Recorder()
        seat.fail("the stated contract")
        assert seat.failed

    def test_returns_true_after_a_message_to_record(self) -> None:
        """A message to record fails the recorder."""
        seat = Recorder()
        seat.record("the stated contract")
        assert seat.failed


class TestRecorderMessage:
    """Recorder.message returns the message of the failure that comes first."""

    def test_returns_the_message_of_fail_before_one_of_record(self) -> None:
        """The aborting failure comes first."""
        seat = Recorder()
        seat.record("the recorded one")
        seat.fail("the fatal one")
        assert seat.message == "the fatal one"

    def test_returns_the_first_message_of_record_without_fail(self) -> None:
        """Without an aborting failure, the first recorded one comes first."""
        seat = Recorder()
        seat.record("the first")
        seat.record("the second")
        assert seat.message == "the first"


class TestRecorderMessages:
    """Recorder.messages returns the messages of record."""

    def test_does_not_return_a_message_of_fail(self) -> None:
        """The list contains the messages of record alone."""
        seat = Recorder()
        seat.fail("the fatal one")
        assert seat.messages == []

    def test_returns_a_copy(self) -> None:
        """A caller can keep the list while the recorder records."""
        seat = Recorder()
        seat.record("the first")
        kept = seat.messages
        seat.record("the second")
        assert kept == ["the first"]


class TestRecorderHelperCalls:
    """Recorder.helper_calls returns the number of calls of helper."""

    def test_returns_0_for_a_recorder_without_a_call_of_helper(self) -> None:
        """A failure is not a call of helper."""
        seat = Recorder()
        seat.record("the stated contract")
        assert seat.helper_calls == 0


class TestCollector:
    """Collector is the seat of a pytest test."""

    def test_returns_a_collector_without_call_records(self) -> None:
        """A collector writes its records through the fixture alone."""
        assert not hasattr(Collector(), "records")


class TestCollectorHelper:
    """Collector.helper marks a frame of the library."""

    def test_does_not_collect_a_message(self) -> None:
        """The collector does not do anything for a helper mark."""
        seat = Collector()
        seat.helper()
        assert seat.collected == []


class TestCollectorReport:
    """Collector.report receives the record of a failure."""

    def test_raises_the_sentence_of_an_aborting_failure(self) -> None:
        """An aborting record stops the test, and the seat keeps the record."""
        seat = Collector()
        with pytest.raises(AssertionError, match=f"^{SENTENCE}$"):
            seat.report(FAILURE, True)
        assert (seat.failures, seat.collected) == ([FAILURE], [])

    def test_collects_the_sentence_of_a_recording_failure(self) -> None:
        """A recording record waits for flush, and the seat keeps the record."""
        seat = Collector()
        seat.report(FAILURE, False)
        assert (seat.failures, seat.collected) == ([FAILURE], [SENTENCE])


class TestCollectorFailures:
    """Collector.failures returns the records of the failures."""

    def test_does_not_return_a_record_of_a_bare_message(self) -> None:
        """A message that a caller passes to record does not leave a record."""
        seat = Collector()
        seat.record("a bare message")
        assert seat.failures == []


class TestCollectorClock:
    """Collector.clock returns the clock that the assertions of the collector read."""

    def test_returns_the_platform_clock_without_one(self) -> None:
        """A collector without a clock reads the platform clock."""
        assert isinstance(Collector().clock(), System)


class TestCollectorWithClock:
    """Collector.with_clock sets a clock of the test."""

    def test_sets_the_clock_and_returns_the_collector(self) -> None:
        """with_clock chains."""
        seat = Collector()
        clock = Controlled(0)
        assert seat.with_clock(clock) is seat
        assert seat.clock() is clock


class TestCollectorFail:
    """Collector.fail raises a failure that stops the test."""

    def test_raises_assertion_error_with_the_message(self) -> None:
        """The message of fail stops the test."""
        with pytest.raises(AssertionError, match=r"^the stated contract$"):
            Collector().fail("the stated contract")


class TestCollectorRecord:
    """Collector.record collects a failure after which the test continues."""

    def test_collects_the_message(self) -> None:
        """A message to record lets the test continue."""
        seat = Collector()
        seat.record("the stated contract")
        assert seat.collected == ["the stated contract"]


class TestCollectorSkip:
    """Collector.skip skips the test."""

    def test_raises_skip_test_with_the_reason(self) -> None:
        """The runner reports the test as skipped."""
        with pytest.raises(unittest.SkipTest, match=r"^the disk refuses direct I/O$"):
            Collector().skip("the disk refuses direct I/O")


class TestCollectorCleanup:
    """Collector.cleanup registers a function that runs when the test ends."""

    def test_registers_a_function_that_clean_up_runs(self) -> None:
        """clean_up runs what cleanup registered."""
        seat = Collector()
        ran: list[bool] = []
        seat.cleanup(lambda: ran.append(True))
        clean_up(seat)
        assert ran == [True]


class TestCollectorCollected:
    """Collector.collected returns the messages that wait for the end of the test."""

    def test_returns_the_messages_in_call_order(self) -> None:
        """The messages keep the order of the calls."""
        seat = Collector()
        seat.record("the first")
        seat.record("the second")
        assert seat.collected == ["the first", "the second"]


class TestCollectorFlush:
    """Collector.flush raises the failures of the test at its end."""

    def test_returns_for_a_collector_without_messages(self) -> None:
        """A passing test does not raise at its end."""
        Collector().flush()

    def test_raises_one_collected_message_as_itself(self) -> None:
        """One failure does not need a numbered list."""
        seat = Collector()
        seat.record("the stated contract")
        with pytest.raises(AssertionError, match=r"^the stated contract$"):
            seat.flush()

    def test_raises_several_collected_messages_as_a_numbered_list(self) -> None:
        """The list has every failure."""
        seat = Collector()
        seat.record("the first contract")
        seat.record("the second contract")
        with pytest.raises(AssertionError) as raised:
            seat.flush()
        assert str(raised.value) == (
            "2 failures:\n  1. the first contract\n  2. the second contract"
        )

    def test_drops_the_messages_that_it_raised(self) -> None:
        """A seat that a test reuses reports a failure once."""
        seat = Collector()
        seat.record("the stated contract")
        with pytest.raises(AssertionError):
            seat.flush()
        assert seat.collected == []
        seat.flush()


class TestCleanUp:
    """clean_up runs the functions that a test registered."""

    def test_runs_the_last_registered_function_first(self) -> None:
        """The functions run in the reverse order of their registration."""
        seat = Collector()
        order: list[int] = []
        seat.cleanup(lambda: order.append(1))
        seat.cleanup(lambda: order.append(2))
        clean_up(seat)
        assert order == [2, 1]

    def test_runs_each_function_once(self) -> None:
        """A second clean_up does not run a function again."""
        seat = Collector()
        runs: list[int] = []
        seat.cleanup(lambda: runs.append(1))
        clean_up(seat)
        clean_up(seat)
        assert runs == [1]

    def test_collects_the_error_of_a_function_and_runs_the_ones_after_it(self) -> None:
        """A function that raises does not stop the others."""
        seat = Collector()
        ran: list[bool] = []

        def busy() -> None:
            msg = "the directory is busy"
            raise OSError(msg)

        seat.cleanup(lambda: ran.append(True))
        seat.cleanup(busy)
        clean_up(seat)
        assert (ran, seat.collected) == (
            [True],
            ["a cleanup failed: the directory is busy"],
        )

    def test_does_not_run_a_function_for_a_collector_without_cleanups(self) -> None:
        """A collector without cleanups does not collect a message."""
        seat = Collector()
        clean_up(seat)
        assert seat.collected == []

    def test_runs_a_function_that_a_function_registers_in_the_same_pass(self) -> None:
        """A cleanup that registers another runs it before clean_up returns."""
        seat = Collector()
        order: list[str] = []

        def registering() -> None:
            order.append("registering")
            seat.cleanup(lambda: order.append("registered"))

        seat.cleanup(registering)
        clean_up(seat)
        assert order == ["registering", "registered"]

    def test_runs_an_awaitable_that_a_function_returns(self) -> None:
        """A coroutine function runs to its end on an event loop of its own."""
        seat = Collector()
        ran: list[bool] = []

        async def close() -> None:
            ran.append(True)

        seat.cleanup(close)
        clean_up(seat)
        assert ran == [True]


class TestCleanup:
    """cleanup registers a function through the member cleanup of a seat."""

    def test_registers_the_function_with_the_member_of_the_seat(self) -> None:
        """A recorder runs the function at run_cleanups."""
        seat = Recorder()
        ran: list[bool] = []
        cleanup(seat, lambda: ran.append(True))
        seat.run_cleanups()
        assert ran == [True]

    def test_ends_the_call_with_a_fault_on_a_seat_without_the_member(self) -> None:
        """The seat keeps the fault, and the function does not run."""
        seat = Uncleaned()
        ran: list[bool] = []
        cleanup(seat, lambda: ran.append(True))
        assert (seat.faults, ran) == (
            [("seat.cleanup: the seat has no member cleanup", True)],
            [],
        )

    def test_raises_the_fault_on_a_standard_seat(self) -> None:
        """A standard seat has no end of a test, so the call raises the fault."""
        with pytest.raises(Exception, match=r"^seat\.cleanup: ") as raised:
            cleanup(Standard(), lambda: None)
        assert isinstance(raised.value.__cause__, FaultError)


class TestRecorderCleanup:
    """Recorder.cleanup keeps a function until run_cleanups."""

    def test_keeps_the_function_until_run_cleanups(self) -> None:
        """The recorder does not run the function at its registration."""
        seat = Recorder()
        ran: list[bool] = []
        seat.cleanup(lambda: ran.append(True))
        assert ran == []


class TestRecorderRunCleanups:
    """Recorder.run_cleanups runs the functions that cleanup registered."""

    def test_runs_the_last_registered_function_first(self) -> None:
        """The functions run in the reverse order of their registration."""
        seat = Recorder()
        order: list[int] = []
        seat.cleanup(lambda: order.append(1))
        seat.cleanup(lambda: order.append(2))
        seat.run_cleanups()
        assert order == [2, 1]

    def test_leaves_a_function_that_arrives_after_it_to_the_next_call(self) -> None:
        """A second call runs only the function that arrived after the first."""
        seat = Recorder()
        order: list[str] = []
        seat.cleanup(lambda: order.append("first run"))
        seat.run_cleanups()
        seat.cleanup(lambda: order.append("second run"))
        assert order == ["first run"]
        seat.run_cleanups()
        assert order == ["first run", "second run"]

    def test_keeps_the_error_of_a_function_as_a_failure(self) -> None:
        """A function that raises fails the recorder, and the others still run."""
        seat = Recorder()
        ran: list[bool] = []

        def busy() -> None:
            msg = "the port is busy"
            raise OSError(msg)

        seat.cleanup(lambda: ran.append(True))
        seat.cleanup(busy)
        seat.run_cleanups()
        assert (ran, seat.messages) == (
            [True],
            ["a cleanup failed: the port is busy"],
        )

    def test_runs_an_awaitable_that_a_function_returns(self) -> None:
        """A coroutine function runs to its end on an event loop of its own."""
        seat = Recorder()
        ran: list[bool] = []

        async def close() -> None:
            ran.append(True)

        seat.cleanup(close)
        seat.run_cleanups()
        assert ran == [True]
