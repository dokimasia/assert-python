"""The seats an assertion reports through.

These use plain asserts rather than the library. A seat is what every
assertion reports through, so testing it with assertions that report
through a seat would let one bug hide another.
"""

from __future__ import annotations

import threading

import pytest

from dokimi_assert import check
from dokimi_assert._matcher.seat import Mode, Seat, report
from dokimi_assert.seat import Collector, Recorder, Standard

#: The seat these tests state their own verdicts on.
OUTER = Standard()


def test_both_seats_satisfy_the_protocol() -> None:
    """Anything an assertion is handed must answer the three methods."""
    assert isinstance(Standard(), Seat)
    assert isinstance(Recorder(), Seat)


def test_standard_raises_an_assertion_error() -> None:
    """Every test framework already treats AssertionError as a failure."""
    with pytest.raises(AssertionError, match="reported"):
        Standard().fail("reported")


def test_standard_raises_on_record_too() -> None:
    """A seat that cannot collect a failure says so by raising."""
    with pytest.raises(AssertionError, match="reported"):
        Standard().record("reported")


def test_a_fresh_recorder_has_not_failed() -> None:
    """Nothing recorded means nothing failed."""
    recorder = Recorder()
    assert not recorder.failed
    assert recorder.message == ""
    assert recorder.messages == []


def test_a_recorder_keeps_the_first_fatal_message() -> None:
    """In a real test nothing after the first fatal call runs."""
    recorder = Recorder()
    recorder.fail("first")
    recorder.fail("second")

    assert recorder.message == "first"


def test_a_recorder_keeps_every_recorded_message() -> None:
    """The recording surface reports each failure, not only the first."""
    recorder = Recorder()
    recorder.record("one")
    recorder.record("two")

    assert recorder.messages == ["one", "two"]
    assert recorder.failed


def test_message_prefers_the_fatal_path() -> None:
    """A fatal failure is the one a reader wants first."""
    recorder = Recorder()
    recorder.record("soft")
    recorder.fail("fatal")

    assert recorder.message == "fatal"


def test_messages_is_a_copy() -> None:
    """A caller may hold the list while the recorder keeps recording."""
    recorder = Recorder()
    recorder.record("one")

    held = recorder.messages
    recorder.record("two")

    assert held == ["one"]


def test_helper_calls_are_counted() -> None:
    """A test can check an assertion marks its own frame."""
    recorder = Recorder()
    recorder.helper()
    recorder.helper()

    assert recorder.helper_calls == 2


def test_report_sends_a_fatal_mode_to_fail() -> None:
    """The mode decides which of the seat's methods is used."""
    recorder = Recorder()
    report(recorder, Mode.FATAL, "reported")

    assert recorder.message == "reported"
    assert recorder.messages == []


def test_report_sends_a_soft_mode_to_record() -> None:
    """The recording mode leaves the fatal path untouched."""
    recorder = Recorder()
    report(recorder, Mode.SOFT, "reported")

    assert recorder.messages == ["reported"]


def test_report_marks_the_calling_frame() -> None:
    """A failure is attributed to the caller, not to the matcher."""
    recorder = Recorder()
    report(recorder, Mode.FATAL, "reported")

    assert recorder.helper_calls >= 1


def test_a_collector_raises_on_a_fatal_failure() -> None:
    """The aborting surface stops the test, so fail raises where it stands."""
    seat = Collector()

    with pytest.raises(AssertionError, match="the stated contract"):
        seat.fail("the stated contract")


def test_a_collector_keeps_a_recorded_failure() -> None:
    """The recording surface carries on, so record keeps the message."""
    seat = Collector()
    seat.record("the first contract")
    seat.record("the second contract")

    assert seat.collected == ["the first contract", "the second contract"]


def test_a_collector_flushes_nothing_when_nothing_failed() -> None:
    """A passing test must not raise at the end of its body."""
    Collector().flush()


def test_a_collector_flushes_one_failure_as_itself() -> None:
    """One failure numbered 1 of 1 reads worse than the failure alone."""
    seat = Collector()
    seat.record("the stated contract")

    with pytest.raises(AssertionError) as caught:
        seat.flush()

    assert str(caught.value) == "the stated contract"


def test_a_collector_flushes_several_as_a_numbered_list() -> None:
    """Seeing every failing property is the point of the recording surface."""
    seat = Collector()
    seat.record("the first contract")
    seat.record("the second contract")

    with pytest.raises(AssertionError) as caught:
        seat.flush()

    message = str(caught.value)
    assert "2 failures:" in message
    assert "1. the first contract" in message
    assert "2. the second contract" in message


def test_a_collector_does_not_report_the_same_failure_twice() -> None:
    """A seat reused across phases would otherwise repeat itself."""
    seat = Collector()
    seat.record("the stated contract")

    with pytest.raises(AssertionError):
        seat.flush()

    seat.flush()
    assert seat.collected == []


def test_a_collector_counts_helper_calls_without_failing() -> None:
    """Marking a frame decides nothing about the outcome."""
    seat = Collector()
    seat.helper()

    assert seat.collected == []


def test_a_seat_counts_every_helper_mark_from_many_threads() -> None:
    """A seat loses no count when several assertions mark at once.

    A test holds one seat and hands it to every assertion in the body,
    and several of them run the subject somewhere else.

    This does not prove the lock. Under a runtime with a global
    interpreter lock the unlocked version passes too, because the
    interpreter does not switch often enough to lose a mark at this
    scale. The lock is there for a free-threaded build, where it does;
    this drives the seat under real threads and would catch a seat that
    broke outright.
    """
    seat = Recorder()
    writers = 8
    each = 2000

    def mark() -> None:
        for _ in range(each):
            seat.helper()

    threads = [threading.Thread(target=mark) for _ in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    check.equal(
        OUTER,
        seat.helper_calls,
        writers * each,
        "every mark from every thread is counted",
    )


def test_a_seat_keeps_every_failure_reported_from_many_threads() -> None:
    """A seat loses nothing when several assertions report at once."""
    seat = Recorder()
    writers = 8
    each = 250

    def report(worker: int) -> None:
        for at in range(each):
            seat.record(f"worker {worker} failure {at}")

    threads = [threading.Thread(target=report, args=(n,)) for n in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    check.equal(
        OUTER,
        len(seat.messages),
        writers * each,
        "every failure reported from every thread is kept",
    )


def test_a_collector_keeps_every_failure_reported_from_many_threads() -> None:
    """The seat a real test uses answers for the same property."""
    seat = Collector()
    writers = 8
    each = 250

    def report(worker: int) -> None:
        for at in range(each):
            seat.record(f"worker {worker} failure {at}")

    threads = [threading.Thread(target=report, args=(n,)) for n in range(writers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    check.equal(
        OUTER, len(seat.collected), writers * each, "every failure is collected"
    )
