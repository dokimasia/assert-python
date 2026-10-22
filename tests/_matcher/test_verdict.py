"""The spec of _matcher/verdict.py tests the pass, the failure and the fault of a call.

Every assertion reports through this module, so this spec checks its
verdicts with the assert statement of pytest.
"""

from __future__ import annotations

import pytest

from dokimi_assert._matcher.seat import Mode
from dokimi_assert._matcher.verdict import (
    Running,
    as_fault,
    end,
    fail,
    fault,
    fault_text,
    note_fault,
    pass_,
)
from dokimi_assert._record.calls import own, run
from dokimi_assert.failure import Failure, Where
from dokimi_assert.seat import Recorder, Standard
from helpers import records, run_python


class TestFaultText:
    """fault_text returns the text of the error that ended a call."""

    def test_returns_the_text_of_an_exception(self) -> None:
        """The text of an exception is its str."""
        assert fault_text(ValueError("no such shape")) == "no such shape"


class TestAsFault:
    """as_fault returns a fault as an exception."""

    def test_returns_an_exception_itself(self) -> None:
        """An exception is already a fault."""
        refused = ValueError("no such shape")
        assert as_fault(refused) is refused

    def test_returns_an_exception_of_the_text_of_another_value(self) -> None:
        """A text becomes an Exception with that text."""
        made = as_fault("no such shape")
        assert (type(made), str(made)) == (Exception, "no such shape")


class TestEnd:
    """end ends a call with a fault."""

    def test_passes_the_fault_to_a_seat_with_report_fault(self) -> None:
        """A recorder keeps the fault, fails with its text and keeps no record."""
        seat = Recorder()
        refused = ValueError("refused")
        end(seat, refused)
        assert (seat.faults, seat.message, seat.records) == ([refused], "refused", [])

    def test_raises_the_fault_on_a_seat_without_report_fault(self) -> None:
        """A standard seat ends the call with the exception itself."""
        refused = ValueError("refused")
        with pytest.raises(ValueError) as raised:
            end(Standard(), refused)
        assert raised.value is refused


class TestNoteFault:
    """note_fault notes a fault that does not end the call."""

    def test_passes_the_fault_to_a_seat_with_report_fault(self) -> None:
        """A recorder keeps a noted fault and does not fail."""
        seat = Recorder()
        noted = OSError("the store skips a file")
        note_fault(seat, noted)
        assert (seat.faults, seat.failed) == ([noted], False)

    def test_warns_with_the_text_on_a_seat_without_report_fault(self) -> None:
        """A standard seat receives the text as a warning."""
        with pytest.warns(UserWarning, match=r"^the store skips a file$"):
            note_fault(Standard(), OSError("the store skips a file"))


class TestPass:
    """pass_ reports that a call passed."""

    def test_writes_the_record_of_a_pass(self) -> None:
        """The record of a pass has the surface and does not have a detail."""
        seat = Recorder()
        pass_(seat, Mode.SOFT, "true", "the flag is set")
        [record] = records(seat)
        assert (record["verdict"], record["aborting"], "detail" in record) == (
            "pass",
            False,
            False,
        )


class TestFail:
    """fail reports that a call failed."""

    def test_sends_the_record_to_a_seat_that_takes_records(self) -> None:
        """A recorder receives the record with its call site."""
        seat = Recorder()
        fail(seat, Mode.FATAL, "equal", "the count is right", {"want": 2, "got": 1})
        [failure] = seat.failures
        assert (failure.assertion, failure.contract, dict(failure.detail)) == (
            "equal",
            "the count is right",
            {"want": 2, "got": 1},
        )
        assert failure.where is not None
        assert failure.where.file == __file__

    def test_writes_the_typed_literals_of_the_detail(self) -> None:
        """The record has each field of the detail as a typed literal."""
        seat = Recorder()
        fail(seat, Mode.SOFT, "nil", "c", {"got": 0})
        assert records(seat)[0]["detail"] == {"got": {"type": "int", "value": 0}}

    def test_sends_the_sentence_to_a_seat_without_report(self) -> None:
        """A standard seat receives the rendered sentence."""
        with pytest.raises(
            AssertionError, match=r"^the count is right: want 2, got 1$"
        ):
            fail(
                Standard(),
                Mode.FATAL,
                "equal",
                "the count is right",
                {"want": 2, "got": 1},
            )

    def test_has_an_empty_detail_for_none(self) -> None:
        """A failure without detail has an empty detail."""
        seat = Recorder()
        fail(seat, Mode.FATAL, "true", "c")
        assert dict(seat.failures[0].detail) == {}


class TestFault:
    """fault reports that a call ended without a verdict."""

    def test_ends_the_call_with_a_record_of_the_error(self) -> None:
        """The record has the verdict error, and the seat fails with the text."""
        seat = Recorder()
        fault(seat, Mode.SOFT, "matches", "c", ValueError("no pattern"))
        [record] = records(seat)
        assert (record["verdict"], record["error"]) == ("error", "no pattern")
        assert seat.message == "no pattern"


class TestRunningOf:
    """Running.of returns a call that does not run a body."""

    def test_returns_a_call_whose_failure_has_the_given_call_site(self) -> None:
        """The failure has the call site that the call read when it started."""
        seat = Recorder()
        Running.of(seat, Where("start.py", 3)).failed(Mode.FATAL, "true", "c", {})
        assert seat.failures[0].where == Where("start.py", 3)
        assert records(seat)[0]["where"] == {"file": "start.py", "line": 3}


class TestRunningBegin:
    """Running.begin starts a call that runs a body."""

    def test_returns_a_call_whose_record_comes_before_the_records_of_its_body(
        self,
    ) -> None:
        """The call takes its number before the calls of its body."""
        seat = Recorder()
        call = Running.begin(seat)
        body = Recorder()
        run(own(body), call.slot)
        pass_(body, Mode.FATAL, "true", "in the body")
        assert call.slot is not None
        call.slot.take(own(body))
        call.passed(Mode.FATAL, "eventually", "outer")
        assert [(r["seq"], r["contract"]) for r in records(seat)] == [
            (1, "outer"),
            (2, "in the body"),
        ]


class TestRunningSlot:
    """Running.slot is the slot to which the runs of a body hand their calls."""

    def test_returns_none_for_a_call_on_a_seat_that_does_not_record_calls(self) -> None:
        """A standard seat does not keep call records."""
        call = Running.begin(Standard())
        call.passed(Mode.FATAL, "eventually", "outer")
        assert call.slot is None


class TestRunningPassed:
    """Running.passed reports the pass of a call."""

    def test_writes_the_record_of_a_pass_at_the_call_site_that_the_call_read(
        self,
    ) -> None:
        """The record has the site that the call read when it started."""
        seat = Recorder()
        Running.of(seat, Where("start.py", 3)).passed(Mode.SOFT, "true", "c")
        [record] = records(seat)
        assert (record["verdict"], record["where"]) == (
            "pass",
            {"file": "start.py", "line": 3},
        )


class TestRunningFailed:
    """Running.failed reports the failure of a call with its detail."""

    def test_writes_the_record_of_the_failure(self) -> None:
        """The failure and its record have the detail."""
        seat = Recorder()
        Running.of(seat).failed(Mode.SOFT, "equal", "c", {"want": 2, "got": 1})
        assert dict(seat.failures[0].detail) == {"want": 2, "got": 1}
        assert records(seat)[0]["verdict"] == "fail"


class TestRunningFaulted:
    """Running.faulted reports that a call ended without a verdict."""

    def test_ends_the_call_with_a_record_of_the_error(self) -> None:
        """The call ends through fail of the seat on both surfaces."""
        seat = Recorder()
        Running.of(seat).faulted(Mode.SOFT, "matches", "c", ValueError("no pattern"))
        [record] = records(seat)
        assert (record["verdict"], record["error"]) == ("error", "no pattern")
        assert seat.message == "no pattern"


class TestRunningPassedRun:
    """Running.passed_run reports the pass of a property with the detail of its run."""

    def test_writes_the_run_of_a_passing_property(self) -> None:
        """The record of a passing property has the detail of its run."""
        seat = Recorder()
        Running.of(seat).passed_run(
            Mode.FATAL, "prop-for-all", "c", Where("prop.py", 9), {"outcome": "passed"}
        )
        [record] = records(seat)
        assert (record["detail"], record["where"]) == (
            {"outcome": "passed"},
            {"file": "prop.py", "line": 9},
        )


class TestRunningFailedRun:
    """Running.failed_run reports a failure whose record has the detail of a run."""

    def test_writes_the_run_of_a_failure_in_place_of_its_literals(self) -> None:
        """The record of a failure of a run has the detail of the run.

        The assertion a-run does not have a registered sentence, so the
        recorder renders the contract and the detail of the record.
        """
        seat = Recorder()
        failure = Failure("a-run", "c", {"outcome": "failed"}, Where("p.py", 1))
        Running.of(seat).failed_run(Mode.SOFT, failure, {"outcome": "failed"})
        assert records(seat)[0]["detail"] == {"outcome": "failed"}
        assert seat.failures == [failure]


def test_ends_every_call_with_the_fault_of_a_switch_without_a_defined_value() -> None:
    """Each call ends with a fault when DOKIMI_ASSERT_RECORD is neither 0 nor 1."""
    child = run_python(
        """
        from dokimi_assert._matcher.seat import Mode
        from dokimi_assert._matcher.verdict import Running
        from dokimi_assert.failure import Failure
        from dokimi_assert.seat import Recorder

        for verdict in ("passed", "failed", "faulted", "passed_run", "failed_run"):
            seat = Recorder()
            call = Running.of(seat)
            if verdict == "passed":
                call.passed(Mode.FATAL, "true", "c")
            elif verdict == "failed":
                call.failed(Mode.FATAL, "true", "c", {})
            elif verdict == "faulted":
                call.faulted(Mode.FATAL, "true", "c", "boom")
            elif verdict == "passed_run":
                call.passed_run(Mode.FATAL, "prop-for-all", "c", None, {})
            else:
                call.failed_run(Mode.FATAL, Failure("true", "c"), {})
            print(verdict, seat.message, len(seat.records), len(seat.failures))
        """,
        DOKIMI_ASSERT_RECORD="2",
    )
    fault_line = "DOKIMI_ASSERT_RECORD: '2' is neither 0 nor 1"
    assert child.stdout.splitlines() == [
        f"{verdict} {fault_line} 0 0"
        for verdict in ("passed", "failed", "faulted", "passed_run", "failed_run")
    ], child.stderr
