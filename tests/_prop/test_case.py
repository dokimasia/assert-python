"""The spec of _prop/case.py tests the case of a property."""

from __future__ import annotations

import asyncio
import contextlib
import threading
from collections.abc import Callable
from typing import ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._history.history import History
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.loop import Loop
from dokimi_assert._matcher.seat import Seat
from dokimi_assert._prop import case as case_module
from dokimi_assert._prop.case import (
    Case,
    Failing,
    FaultSignal,
    Location,
    case_of,
    execute,
    on_engine,
)
from dokimi_assert._prop.engine.case import Case as Engine
from dokimi_assert._prop.engine.case import Failed, Rejected, Replaying
from dokimi_assert._prop.engine.choice import UINT64_MAX, IntegerBounds
from dokimi_assert._prop.engine.generator import Filter, Integer, Mapped
from dokimi_assert._prop.engine.traces import TraceError
from dokimi_assert._prop.engine.tree import Diverged, Repeated
from dokimi_assert._prop.identity import Identity
from dokimi_assert.clock import Controlled
from dokimi_assert.failure import Failure, Where
from dokimi_assert.seat import Collector, Recorder
from helpers import integers

#: The call site of the property of the cases.
SITE = Where("/work/tests/test_total.py", 4)

#: The location of the records of a case that finds them by the frame of the
#: caller.
FREE = Location(SITE)

#: The location of the records of a case that keeps them at the call site.
PINNED = Location(SITE, pinned=True)

#: A generator of one digit.
DIGITS = Integer(IntegerBounds(0, 9))


def case_on(location: Location = FREE, *values: int) -> tuple[Case, Engine]:
    """Return a case on a recorder and its engine case.

    The engine case replays values as integer choices.
    """
    engine = Engine(Replaying(integers(*values)))
    return Case(engine, Recorder(), None, location), engine


def ending(c: Case, body: Callable[[Case], object]) -> BaseException | None:
    """Return the exception that c raises when body runs on it.

    The result is None when the case passes.
    """
    with Loop("prop-for-all") as loop:
        try:
            execute(c, body, loop)
        except (Exception, Failed, Rejected, Repeated, Diverged, FaultSignal) as error:
            return error
    return None


def record_of(raised: BaseException | None) -> Failing:
    """Return the Failing of a failed case."""
    return cast("Failing", cast("Failed", raised).record)


class TestFailing:
    """Failing has the failure record and the identity of a failed case."""

    def test_keeps_the_record_and_its_identity(self, seat: Collector) -> None:
        """The identity has the call site."""
        failure = Failure("", "it broke")
        failing = Failing(failure, Identity(where=SITE))
        check.equal(
            seat,
            [failing.failure, failing.identity],
            [failure, Identity(where=SITE)],
            "Failing keeps the record and its identity",
        )


class TestFaultSignal:
    """FaultSignal is the signal that ends the run of a property with a fault."""

    def test_keeps_its_fault_and_its_text(self, seat: Collector) -> None:
        """The signal of a fault at a member has the text of the fault."""
        fault = FaultError("sock_recv", "the member is not implemented")
        signal = FaultSignal(fault)
        check.equal(
            seat,
            [signal.fault is fault, str(signal)],
            [True, "sock_recv: the member is not implemented"],
            "the signal has the fault and its text",
        )


class TestLocation:
    """Location is the location of the records of a case."""

    def test_finds_the_records_by_the_frame_of_the_caller_by_default(
        self, seat: Collector
    ) -> None:
        """The location does not set pinned."""
        check.is_false(seat, Location(SITE).pinned, "the location is not pinned")


class TestCase:
    """Case is one call of the body of a property."""

    def test_makes_itself_the_owner_of_its_engine_case(self, seat: Collector) -> None:
        """The engine case finds the case of its body."""
        c, engine = case_on()
        check.is_true(
            seat, engine.owner is c, "the case is the owner of its engine case"
        )


class TestCaseHelper:
    """Case.helper does nothing."""

    def test_returns_without_a_record(self, seat: Collector) -> None:
        """The case passes."""
        c, _ = case_on()
        check.is_none(seat, ending(c, lambda one: one.helper()), "the case passes")


class TestCaseFail:
    """Case.fail records a message and ends the case."""

    def test_ends_the_case_with_a_record_at_the_frame_of_this_file(
        self, seat: Collector
    ) -> None:
        """The body does not run past the call."""
        c, _ = case_on()
        after: list[bool] = []

        def fails(reporting: Seat) -> None:
            reporting.fail("it broke")

        def body(one: Case) -> None:
            fails(one)
            after.append(True)

        failing = record_of(ending(c, body))
        failure = failing.failure
        check.equal(
            seat,
            [failure.assertion, failure.contract, after],
            ["", "it broke", []],
            "the message ends the case",
        )
        where = failing.identity.where
        check.has_suffix(
            seat,
            None if where is None else where.file,
            "test_case.py",
            "the record is at a frame of this file",
        )

    def test_keeps_the_record_of_a_pinned_case_at_the_call_site(
        self, seat: Collector
    ) -> None:
        """The record of a pinned case is at the call site of the property."""
        c, _ = case_on(PINNED)
        failure = record_of(ending(c, lambda one: one.fail("it broke"))).failure
        check.equal(seat, failure.where, SITE, "the record is at the call site")


class TestCaseRecord:
    """Case.record records a message and lets the body run on."""

    def test_fails_the_case_with_the_first_message_once_the_body_ends(
        self, seat: Collector
    ) -> None:
        """The body runs on past both records."""
        c, _ = case_on()
        after: list[bool] = []

        def body(one: Case) -> None:
            one.record("first")
            one.record("second")
            after.append(True)

        failure = record_of(ending(c, body)).failure
        check.equal(
            seat,
            [failure.contract, after],
            ["first", [True]],
            "the first record fails the case",
        )

    def test_keeps_the_record_of_a_pinned_case_at_the_call_site(
        self, seat: Collector
    ) -> None:
        """The record of a pinned case is at the call site of the property."""
        c, _ = case_on(PINNED)
        failure = record_of(ending(c, lambda one: one.record("x"))).failure
        check.equal(seat, failure.where, SITE, "the record is at the call site")


class TestCaseReport:
    """Case.report keeps the failure record of an assertion."""

    def test_ends_the_case_at_an_aborting_record(self, seat: Collector) -> None:
        """The record ends the case."""
        c, _ = case_on()
        record = Failure("equal", "the totals agree", {}, Where("/w/a.py", 2))
        after: list[bool] = []

        def body(one: Case) -> None:
            one.report(record, True)
            after.append(True)

        failure = record_of(ending(c, body)).failure
        check.equal(seat, [failure, after], [record, []], "the record ends the case")

    def test_lets_the_body_run_on_past_a_recording_record(
        self, seat: Collector
    ) -> None:
        """The case fails when the body ends."""
        c, _ = case_on()
        record = Failure("equal", "c")
        after: list[bool] = []

        def body(one: Case) -> None:
            one.report(record, False)
            after.append(True)

        failure = record_of(ending(c, body)).failure
        check.equal(seat, [failure, after], [record, [True]], "the body runs on")

    def test_keeps_the_record_of_a_pinned_case_at_the_call_site(
        self, seat: Collector
    ) -> None:
        """The record keeps its assertion, its contract and its detail."""
        c, _ = case_on(PINNED)
        record = Failure("equal", "c", {"want": 1}, Where("/w/a.py", 2))
        failure = record_of(ending(c, lambda one: one.report(record, True))).failure
        check.equal(
            seat,
            failure,
            Failure("equal", "c", {"want": 1}, SITE),
            "the record is at the call site",
        )


class TestCaseReportFault:
    """Case.report_fault receives a fault of a call of the body."""

    def test_ends_the_case_with_the_text_of_a_fault_that_ends_its_call(
        self, seat: Collector
    ) -> None:
        """An ending fault fails the case as fail does."""
        c, _ = case_on()
        after: list[bool] = []

        def body(one: Case) -> None:
            one.report_fault(ValueError("the seed is not a number"), True)
            after.append(True)

        failure = record_of(ending(c, body)).failure
        check.equal(
            seat,
            [failure.assertion, failure.contract, after],
            ["", "the seed is not a number", []],
            "the fault ends the case",
        )

    def test_passes_a_noted_fault_to_the_seat_of_the_property(
        self, seat: Collector
    ) -> None:
        """The body runs on past a noted fault, and the case passes."""
        recorder = Recorder()
        c = Case(Engine(Replaying(integers())), recorder, None, FREE)
        noted = OSError("the store skips a file")
        check.is_none(
            seat,
            ending(c, lambda one: one.report_fault(noted, False)),
            "the case passes",
        )
        check.equal(seat, recorder.faults, [noted], "the seat receives the fault")


class TestCaseClock:
    """Case.clock returns the clock of the seat of the property."""

    def test_returns_the_clock_of_the_seat_of_the_property(
        self, seat: Collector
    ) -> None:
        """The recorder has a controlled clock."""
        clock = Controlled()
        c = Case(Engine(Replaying([])), Recorder().with_clock(clock), None, FREE)
        check.is_true(
            seat, c.clock() is clock, "the case returns the clock of the seat"
        )


class TestCaseDraw:
    """Case.draw returns a value of a generator under a label."""

    def test_returns_the_value_that_the_engine_records_under_the_label(
        self, seat: Collector
    ) -> None:
        """The engine records the value 7 under the label x."""
        c, engine = case_on(FREE, 7)
        drawn: list[int] = []
        ending(c, lambda one: drawn.append(one.draw(DIGITS, "x")))
        check.equal(
            seat,
            [drawn, engine.draws[0].label],
            [[7], "x"],
            "the draw returns 7 under the label x",
        )

    def test_raises_the_signal_of_a_draw_again_at_every_later_call(
        self, seat: Collector
    ) -> None:
        """A filter that does not keep a value rejects the case."""
        c, _ = case_on()
        raised: list[BaseException] = []

        def body(one: Case) -> None:
            try:
                one.draw(Filter(DIGITS, lambda _: False), "never")
            except Rejected as error:
                raised.append(error)
            try:
                one.note("too late")
            except Rejected as error:
                raised.append(error)

        ended = ending(c, body)
        check.error_as(seat, ended, Rejected, "the case is rejected")
        check.equal(
            seat,
            [len(raised), all(error is ended for error in raised)],
            [2, True],
            "the rejection is raised again",
        )

    def test_fails_the_case_with_an_error_of_the_generator(
        self, seat: Collector
    ) -> None:
        """The function of a map raises an error."""

        def refuse(_: int) -> int:
            raise ValueError("the map refuses")

        c, _ = case_on(FREE, 1)
        failure = record_of(
            ending(c, lambda one: one.draw(Mapped(DIGITS, refuse), "x"))
        )
        check.equal(
            seat,
            failure.failure.contract,
            "the map refuses",
            "the error fails the case",
        )


class TestCaseAssume:
    """Case.assume rejects a case for a false condition."""

    def test_rejects_the_case_for_a_false_condition(self, seat: Collector) -> None:
        """The rejection ends the case."""
        c, _ = case_on()
        check.error_as(
            seat,
            ending(c, lambda one: one.assume(False)),
            Rejected,
            "the case is rejected",
        )

    def test_lets_the_body_run_on_for_a_true_condition(self, seat: Collector) -> None:
        """The case passes."""
        c, _ = case_on()
        check.is_none(seat, ending(c, lambda one: one.assume(True)), "the case passes")


class TestCaseClassify:
    """Case.classify counts the case under a label."""

    def test_counts_the_case_under_the_label(self, seat: Collector) -> None:
        """The body classifies the case as even."""
        c, engine = case_on()
        ending(c, lambda one: one.classify("even"))
        check.equal(seat, engine.labels, {"even"}, "the case counts under even")


class TestCaseNote:
    """Case.note attaches a message to the case."""

    def test_attaches_the_message_to_the_case(self, seat: Collector) -> None:
        """The body notes the message saw 7."""
        c, engine = case_on()
        ending(c, lambda one: one.note("saw 7"))
        check.equal(seat, engine.notes, ["saw 7"], "the case has the note")


class TestCaseRand:
    """Case.rand returns a random.Random that makes its values from choices."""

    def test_returns_bits_that_are_integer_choices_of_the_case(
        self, seat: Collector
    ) -> None:
        """Each call of getrandbits takes one choice of 64 bits."""
        c, engine = case_on(FREE, 5, UINT64_MAX)
        values: list[int] = []

        def body(one: Case) -> None:
            source = one.rand()
            values.extend([source.getrandbits(64), source.getrandbits(64)])

        ending(c, body)
        check.equal(
            seat,
            [values, len(engine.choices)],
            [[5, UINT64_MAX], 2],
            "the source takes two choices",
        )

    tests: ClassVar[list[tuple[str, list[int], int, int]]] = [
        ("takes the high bits of one choice for 8 bits", [2**63], 8, 128),
        ("takes one choice per 64 bits for 128 bits", [1, 2], 128, 2**64 + 2),
        ("does not take a choice for 0 bits", [], 0, 0),
    ]

    @pytest.mark.parametrize(
        ("give", "k", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_bits_of_the_choices(
        self, seat: Collector, give: list[int], k: int, want: int
    ) -> None:
        """The result of getrandbits has the bits of the choices."""
        c, engine = case_on(FREE, *give)
        got: list[int] = []
        ending(c, lambda one: got.append(one.rand().getrandbits(k)))
        check.equal(
            seat,
            [got, len(engine.choices)],
            [[want], len(give)],
            "getrandbits returns the bits",
        )

    def test_returns_a_float_of_the_high_53_bits_of_one_choice(
        self, seat: Collector
    ) -> None:
        """Half of 2^64 is half of 1."""
        c, _ = case_on(FREE, 2**63)
        got: list[float] = []
        ending(c, lambda one: got.append(one.rand().random()))
        check.equal(seat, got, [0.5], "random returns 0.5")

    def test_ignores_a_seed(self, seat: Collector) -> None:
        """A seed does not change the values."""
        c, _ = case_on(FREE, 3)
        got: list[int] = []

        def body(one: Case) -> None:
            source = one.rand()
            source.seed(99)
            got.append(source.getrandbits(64))

        ending(c, body)
        check.equal(seat, got, [3], "the value is the choice")

    def test_raises_value_error_for_a_negative_number_of_bits(
        self, seat: Collector
    ) -> None:
        """random.Random refuses a negative number of bits too."""
        source = case_on()[0].rand()
        error = check.raises(seat, lambda: source.getrandbits(-1), "getrandbits raises")
        check.error_as(seat, error, ValueError, "the error is a ValueError")

    def test_raises_not_implemented_error_for_its_state(self, seat: Collector) -> None:
        """The choices of the case are the state."""
        source = case_on()[0].rand()
        error = check.raises(seat, source.getstate, "getstate raises")
        check.error_as(
            seat, error, NotImplementedError, "the error is a NotImplementedError"
        )
        error = check.raises(seat, lambda: source.setstate(()), "setstate raises")
        check.error_as(
            seat, error, NotImplementedError, "the error is a NotImplementedError"
        )

    def test_ends_the_case_at_a_value_past_the_cap_on_choices(
        self, seat: Collector
    ) -> None:
        """The second value overruns a cap of one choice."""
        c = Case(Engine(Replaying([]), 1), Recorder(), None, FREE)

        def body(one: Case) -> None:
            source = one.rand()
            source.random()
            source.random()

        check.error_as(seat, ending(c, body), Rejected, "the case is rejected")


class TestCaseObserve:
    """Case.observe records a fingerprint of the state of the subject."""

    def test_records_the_fingerprint(self, seat: Collector) -> None:
        """The body observes the fingerprint 42."""
        c, engine = case_on()
        ending(c, lambda one: one.observe(42))
        check.equal(
            seat, engine.fingerprints, [42], "the engine records the fingerprint"
        )


class TestCaseCleanup:
    """Case.cleanup registers a function that runs when the case ends."""

    def test_runs_the_cleanups_after_the_body_the_last_registered_first(
        self, seat: Collector
    ) -> None:
        """The run awaits a coroutine of a cleanup."""
        c, _ = case_on()
        order: list[str] = []

        async def second() -> None:
            await asyncio.sleep(0)
            order.append("second")

        def body(one: Case) -> None:
            one.cleanup(lambda: order.append("first"))
            one.cleanup(second)
            order.append("body")

        ending(c, body)
        check.equal(
            seat,
            order,
            ["body", "second", "first"],
            "the cleanups run after the body in reverse order",
        )

    def test_runs_a_cleanup_that_a_cleanup_registers_before_the_case_ends(
        self, seat: Collector
    ) -> None:
        """The nested cleanup runs."""
        c, _ = case_on()
        order: list[str] = []

        def body(one: Case) -> None:
            def outer() -> None:
                order.append("outer")
                one.cleanup(lambda: order.append("inner"))

            one.cleanup(outer)

        ending(c, body)
        check.equal(seat, order, ["outer", "inner"], "the nested cleanup runs")

    def test_runs_the_remaining_cleanups_after_a_cleanup_that_fails_the_case(
        self, seat: Collector
    ) -> None:
        """The later cleanup fails, and the earlier cleanup still runs."""
        c, _ = case_on()
        ran: list[bool] = []

        def breaks() -> None:
            raise TypeError("the cleanup broke")

        def body(one: Case) -> None:
            one.cleanup(lambda: ran.append(True))
            one.cleanup(breaks)

        failure = record_of(ending(c, body)).failure
        check.equal(
            seat,
            [failure.contract, ran],
            ["the cleanup broke", [True]],
            "the cleanup fails the case, and the other cleanup runs",
        )

    def test_keeps_the_exception_of_the_body_over_the_exception_of_a_cleanup(
        self, seat: Collector
    ) -> None:
        """The first exception fails the case."""
        c, _ = case_on()

        def breaks() -> None:
            raise TypeError("second")

        def body(one: Case) -> None:
            one.cleanup(breaks)
            raise ValueError("first")

        failure = record_of(ending(c, body)).failure
        check.equal(
            seat, failure.contract, "first", "the exception of the body fails the case"
        )


class TestCaseHistory:
    """Case.history returns the history of the calls of the body."""

    def test_returns_one_empty_history_for_every_call_of_a_case(
        self, seat: Collector
    ) -> None:
        """Two calls return the same empty history."""
        c, _ = case_on()
        histories: list[History] = []
        ending(c, lambda one: histories.extend([one.history(), one.history()]))
        check.equal(
            seat,
            [histories[0] is histories[1], histories[0].events()],
            [True, []],
            "both calls return the same empty history",
        )

    def test_raises_the_signal_of_an_ended_case_again(self, seat: Collector) -> None:
        """The body catches the rejection and calls on."""
        c, _ = case_on()
        raised: list[BaseException] = []

        def body(one: Case) -> None:
            with contextlib.suppress(Rejected):
                one.assume(False)
            try:
                one.history()
            except Rejected as error:
                raised.append(error)

        ended = ending(c, body)
        check.is_true(seat, raised[0] is ended, "history raises the rejection again")

    def test_returns_one_history_to_two_threads_that_call_at_once(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both threads call history before either thread has a history."""
        met = threading.Barrier(2, timeout=60)

        def created() -> History:
            met.wait()
            return History()

        monkeypatch.setattr(case_module, "History", created)
        c, _ = case_on()
        histories: list[History] = []
        threads = [
            threading.Thread(target=lambda: histories.append(c.history()))
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)
        check.is_true(
            seat, histories[0] is histories[1], "both threads receive one history"
        )


class TestCaseTarget:
    """Case.target records a score under a label."""

    def test_records_the_higher_of_two_scores_of_a_label(self, seat: Collector) -> None:
        """The body targets the scores 3 and 2 under one label."""
        c, engine = case_on()

        def body(one: Case) -> None:
            one.target("depth", 3)
            one.target("depth", 2)

        ending(c, body)
        check.equal(
            seat, engine.targets, {"depth": 3}, "the case keeps the higher score"
        )


class TestCaseOf:
    """case_of returns the case that runs a body on an engine case."""

    def test_returns_the_case_that_runs_a_body_on_the_engine_case(
        self, seat: Collector
    ) -> None:
        """A body runs on the engine case."""
        c, engine = case_on()
        check.is_true(seat, case_of(engine) is c, "case_of returns the case")

    def test_returns_a_case_of_a_standard_seat_for_an_engine_case_without_a_body(
        self, seat: Collector
    ) -> None:
        """The case keeps its failure."""
        c = case_of(Engine(Replaying([])))
        check.error_as(
            seat, ending(c, lambda one: one.fail("x")), Failed, "the case fails"
        )


class TestOnEngine:
    """on_engine calls a function on the record of a case in the engine."""

    def test_returns_the_result_of_fn_on_the_engine_case(self, seat: Collector) -> None:
        """The function returns the engine case itself."""
        c, engine = case_on()
        check.is_true(
            seat,
            on_engine(c, lambda e: e) is engine,
            "on_engine returns the engine case",
        )

    def test_raises_the_signal_that_ended_the_case(self, seat: Collector) -> None:
        """The case was rejected."""
        c, _ = case_on()
        with pytest.raises(Rejected):
            c.assume(False)
        with pytest.raises(Rejected) as raised:
            on_engine(c, lambda _: 1)
        check.error_as(seat, raised.value, Rejected, "on_engine raises the rejection")

    def test_ends_the_case_with_a_signal_that_fn_raises(self, seat: Collector) -> None:
        """A later call raises the signal again."""
        c, _ = case_on()

        def rejects(_: Engine) -> None:
            raise Rejected

        with pytest.raises(Rejected):
            on_engine(c, rejects)
        with pytest.raises(Rejected) as raised:
            c.note("later")
        check.error_as(
            seat, raised.value, Rejected, "a later call raises the rejection"
        )

    def test_leaves_the_case_running_after_an_error_that_is_not_a_signal(
        self, seat: Collector
    ) -> None:
        """The case runs on."""
        c, _ = case_on()

        def breaks(_: Engine) -> None:
            raise TypeError("bad")

        check.raises(seat, lambda: on_engine(c, breaks), "on_engine raises the error")
        check.does_not_raise(seat, lambda: c.note("later"), "the case runs on")


class TestExecute:
    """execute runs one case of a property and ends it."""

    def test_returns_for_a_coroutine_body_that_passes(self, seat: Collector) -> None:
        """The loop of the run awaits the body."""
        c, _ = case_on()

        async def body(_: Case) -> None:
            await asyncio.sleep(0)

        check.is_none(seat, ending(c, body), "the case passes")

    def test_ends_the_case_with_a_record_of_an_exception_at_its_frame(
        self, seat: Collector
    ) -> None:
        """The record has the class of the exception and its traceback."""
        c, _ = case_on()

        def breaks(_: Case) -> None:
            raise TypeError("bad input")

        failing = record_of(ending(c, breaks))
        failure = failing.failure
        check.equal(
            seat,
            [
                failure.assertion,
                failure.contract,
                failure.detail["error"],
                failing.identity.error,
            ],
            ["", "bad input", "TypeError", "TypeError"],
            "the case fails with a record of the exception",
        )
        check.contains(
            seat, failure.detail["stack"], "bad input", "the record has the traceback"
        )
        where = failing.identity.where
        check.has_suffix(
            seat,
            None if where is None else where.file,
            "test_case.py",
            "the record is at a frame of this file",
        )

    def test_ends_the_case_with_a_record_of_a_coroutine_that_raises(
        self, seat: Collector
    ) -> None:
        """The awaited body raises."""
        c, _ = case_on()

        async def late(_: Case) -> None:
            raise ValueError("late")

        failure = record_of(ending(c, late)).failure
        check.equal(seat, failure.contract, "late", "the exception fails the case")

    def test_raises_the_failure_of_a_case_that_a_later_assumption_rejects(
        self, seat: Collector
    ) -> None:
        """The failure has priority."""
        c, _ = case_on()

        def body(one: Case) -> None:
            one.record("first")
            one.assume(False)

        failure = record_of(ending(c, body)).failure
        check.equal(seat, failure.contract, "first", "the failure has priority")

    tests: ClassVar[list[tuple[str, Callable[[], BaseException]]]] = [
        ("raises the signal of a repeat over an earlier failure", Repeated),
        (
            "raises the signal of a divergence over an earlier failure",
            lambda: Diverged(0, None, None),
        ),
        (
            "raises the signal of a trace that the body cannot follow",
            lambda: TraceError(0, "x", "label"),
        ),
        (
            "raises the signal of a fault over an earlier failure",
            lambda: FaultSignal(FaultError("", "the subject opened a socket")),
        ),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in tests], ids=[t[0] for t in tests])
    def test_raises_the_signal_over_an_earlier_failure(
        self, seat: Collector, give: Callable[[], BaseException]
    ) -> None:
        """The signal ends the case."""
        c, _ = case_on()
        signal = give()

        def body(one: Case) -> None:
            one.record("a failure first")
            raise signal

        check.is_true(seat, ending(c, body) is signal, "execute raises the signal")

    def test_raises_the_fault_of_a_coroutine_body_inside_a_running_loop(
        self, seat: Collector
    ) -> None:
        """The fault ends the call of the property."""
        c, _ = case_on()

        async def body(_: Case) -> None:
            await asyncio.sleep(0)

        async def inside() -> None:
            with Loop("prop-for-all") as loop:
                execute(c, body, loop)

        error = check.raises(seat, lambda: asyncio.run(inside()), "execute raises")
        check.error_as(seat, error, FaultError, "the error is a FaultError")
