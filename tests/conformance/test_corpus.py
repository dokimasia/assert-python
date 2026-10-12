"""The spec of conformance/corpus.py tests the corpus and the verdict of each case.

The spec runs every case of the vendored corpus on both surfaces, and it
compares the failure and the call record of each run with the case. mismatch
computes the verdict of every case, so the spec checks its own verdicts with
the assert statement of pytest.
"""

from __future__ import annotations

import dataclasses
import os

import pytest

from dokimi_assert import check
from dokimi_assert._matcher.option import Option
from dokimi_assert._matcher.seat import Mode
from dokimi_assert._matcher.verdict import Running
from dokimi_assert.clock import Controlled
from dokimi_assert.conformance.corpus import (
    SURFACES,
    Case,
    cases,
    member_for,
    mismatch,
    options_of,
    skip_reason,
)
from dokimi_assert.conformance.driver import run_subject
from dokimi_assert.failure import Failure
from dokimi_assert.option import equate_empty
from dokimi_assert.seat import Recorder

CASES = cases()

#: A failing case of equal with the detail want 2.
FAILING = Case(
    id="equal/x",
    assertion="equal",
    expect="fail",
    detail={"want": 2},
    fields=("want", "got"),
)

#: A passing case of equal.
PASSING = dataclasses.replace(FAILING, expect="pass", detail={})


def matching() -> Failure:
    """Return the record of a failure of equal that matches the failing case."""
    return Failure("equal", "equal/x", {"want": 2, "got": 1})


def reported(assertion: str, contract: str, detail: dict[str, object]) -> Recorder:
    """Return a recorder that received one failure record directly."""
    seat = Recorder()
    seat.report(Failure(assertion, contract, detail), True)
    return seat


def drive(surface: str, case: Case) -> Recorder:
    """Drive one case on one surface, and return the recorder of its report."""
    options = options_of(case)
    seat = Recorder().with_clock(Controlled(0))
    if case.subject is not None:
        ran = run_subject(surface, case.assertion, case.subject, seat, case.id, options)
        assert ran, f"{surface} does not have the subject {case.subject!r}"
        return seat
    member = member_for(case)
    assert member is not None, f"{case.assertion} does not have a Python name"
    invoke = getattr(SURFACES[surface], member, None)
    assert callable(invoke), f"{surface} does not have a member for {case.assertion}"
    invoke(seat, *case.args, case.id, *options)
    return seat


class TestCases:
    """cases returns the cases of the vendored corpus."""

    def test_returns_the_cases_of_every_file(self) -> None:
        """The 8.0.0 corpus has 195 cases."""
        assert len(CASES) == 195

    def test_sets_the_fields_of_a_case_to_the_fields_of_its_assertion(self) -> None:
        """A case of equal has the fields want and got."""
        first = next(c for c in CASES if c.assertion == "equal")
        assert first.fields == ("want", "got")

    def test_decodes_the_references_of_one_case_to_one_object(self) -> None:
        """Two references of one id in one case are one object."""
        shared = [
            c
            for c in CASES
            if len(c.args) == 2 and c.args[0] is c.args[1] and c.args[0]
        ]
        assert shared, "a case passes one object twice"

    def test_has_the_behaviour_of_a_case_with_a_behaviour(self) -> None:
        """A case of raises has a behaviour and does not have values."""
        throwing = [c for c in CASES if c.assertion == "throws"]
        assert throwing and all(
            c.subject is not None and c.args == () for c in throwing
        )


class TestSurfaces:
    """SURFACES has the two surfaces of the corpus."""

    def test_contains_the_two_surfaces(self) -> None:
        """The corpus runs on check and on expect."""
        assert sorted(SURFACES) == ["check", "expect"]


class TestSkipReason:
    """skip_reason returns the reason that Python skips a case."""

    def test_returns_the_reason_of_a_skip_of_python(self) -> None:
        """A case that Python skips has the reason."""
        case = dataclasses.replace(PASSING, skip={"python": "one int type"})
        assert skip_reason(case) == "one int type"

    def test_returns_none_for_a_skip_of_another_language(self) -> None:
        """A skip of Go does not skip Python."""
        assert (
            skip_reason(dataclasses.replace(PASSING, skip={"go": "a reason"})) is None
        )


class TestMemberFor:
    """member_for returns the Python name of the assertion of a case."""

    def test_returns_the_name_of_the_naming_table(self) -> None:
        """not-equal is not_equal."""
        assert (
            member_for(dataclasses.replace(PASSING, assertion="not-equal"))
            == "not_equal"
        )

    def test_returns_none_for_an_assertion_without_a_name(self) -> None:
        """An unknown assertion does not have a name."""
        assert member_for(dataclasses.replace(PASSING, assertion="no-such")) is None


class TestOptionsOf:
    """options_of returns the options of the relaxations of a case."""

    def test_returns_the_option_of_each_relaxation(self) -> None:
        """equate-empty is the option equate_empty."""
        got = options_of(dataclasses.replace(PASSING, options=("equate-empty",)))
        assert got == [equate_empty()]
        assert all(isinstance(o, Option) for o in got)

    def test_raises_for_a_relaxation_without_a_python_name(self) -> None:
        """An unknown relaxation stops the run."""
        case = dataclasses.replace(PASSING, options=("no-such-relaxation",))
        with pytest.raises(
            LookupError,
            match=(
                r"^equal/x: the relaxation no-such-relaxation does not have a Python "
                r"option$"
            ),
        ):
            options_of(case)


class TestMismatch:
    """mismatch returns how a run differs from its case."""

    def test_returns_the_failure_of_a_case_that_expects_a_pass(self) -> None:
        """A failure of a passing case is a mismatch."""
        failed = Recorder()
        failed.fail("it broke")
        assert mismatch(PASSING, failed, True) == "expected a pass, got: it broke"

    def test_returns_the_pass_of_a_case_that_expects_a_failure(self) -> None:
        """A pass of a failing case is a mismatch."""
        assert mismatch(FAILING, Recorder(), True) == "expected a failure, got a pass"

    def test_returns_a_failure_without_a_record(self) -> None:
        """A bare message does not have a record."""
        failed = Recorder()
        failed.fail("it broke")
        assert mismatch(FAILING, failed, True) == (
            "the assertion did not report a failure record"
        )

    def test_returns_a_record_of_another_assertion(self) -> None:
        """The record has its assertion."""
        seat = reported("not-equal", "equal/x", {})
        assert mismatch(FAILING, seat, True) == "the record is of not-equal, want equal"

    def test_returns_a_record_of_another_contract(self) -> None:
        """The record has the id of the case as its contract."""
        seat = reported("equal", "x", {"want": 1, "got": 2})
        assert mismatch(FAILING, seat, True) == (
            'the record has the contract "x", want "equal/x"'
        )

    def test_returns_a_record_of_different_fields(self) -> None:
        """The record has exactly the fields of its assertion."""
        seat = reported("equal", "equal/x", {"want": 1})
        assert mismatch(FAILING, seat, True) == (
            'the record has the fields ["want"], want ["got", "want"]'
        )

    def test_returns_a_field_of_a_record_whose_value_differs(self) -> None:
        """A field of the case is compared by its canonical text."""
        seat = reported("equal", "equal/x", {"want": 1, "got": 2})
        assert mismatch(FAILING, seat, True) == 'detail "want" is int:1, want int:2'

    def test_returns_a_recorder_that_does_not_keep_a_call_record(self) -> None:
        """A record that the seat receives directly does not write a call record."""
        case = dataclasses.replace(FAILING, detail={})
        seat = reported("equal", "equal/x", {"want": 1, "got": 2})
        assert mismatch(case, seat, True) == "the recorder keeps 0 call records, want 1"

    def test_returns_a_call_record_of_the_other_surface(self) -> None:
        """The call record has the surface of the call."""
        seat = Recorder()
        check.equal(seat, 1, 2, "equal/x")
        verdict = mismatch(FAILING, seat, False)
        assert verdict is not None and verdict.startswith("the call record is ")

    def test_returns_a_field_of_a_failure_whose_value_differs(self) -> None:
        """The first failure must have the value of the case."""
        seat = Recorder()
        check.equal(seat, 1, 2, "equal/x")
        case = dataclasses.replace(FAILING, detail={"want": 3})
        assert mismatch(case, seat, True) == 'detail "want" is int:2, want int:3'

    def test_returns_none_for_a_failure_that_matches_the_case(self) -> None:
        """A run that reports the values of the case agrees with the case."""
        seat = Recorder()
        check.equal(seat, 1, 2, "equal/x")
        assert mismatch(FAILING, seat, True) is None

    def test_returns_none_for_a_pass_that_matches_the_case(self) -> None:
        """A passing run agrees with a passing case."""
        seat = Recorder()
        check.equal(seat, 1, 1, "equal/x")
        assert mismatch(PASSING, seat, True) is None

    def test_returns_the_detail_of_a_passing_call_record(self) -> None:
        """A passing call record does not have a detail."""
        seat = Recorder()
        Running.of(seat).passed_run(Mode.FATAL, "equal", "equal/x", None, {"x": 1})
        assert mismatch(PASSING, seat, True) == (
            'a passing call record has the detail {"x": 1}'
        )

    def test_returns_the_fields_of_a_call_record_that_differ_from_the_case(
        self,
    ) -> None:
        """A call record has exactly the fields of its assertion."""
        seat = Recorder()
        Running.of(seat).failed_run(Mode.FATAL, matching(), {"x": 1})
        assert mismatch(FAILING, seat, True) == (
            'the call record has the fields ["x"], want ["got", "want"]'
        )

    def test_returns_a_field_of_a_call_record_that_is_not_a_typed_literal(
        self,
    ) -> None:
        """A field of a call record decodes as a typed literal."""
        seat = Recorder()
        detail = {"want": {"type": "decimal"}, "got": {"type": "int", "value": 1}}
        Running.of(seat).failed_run(Mode.FATAL, matching(), detail)
        assert mismatch(FAILING, seat, True) == (
            "the field want of the call record is not a typed literal: unknown "
            "literal type: decimal"
        )

    def test_returns_a_field_of_a_call_record_whose_value_differs(self) -> None:
        """A field of a call record is compared by its canonical text."""
        seat = Recorder()
        detail = {
            "want": {"type": "int", "value": 3},
            "got": {"type": "int", "value": 1},
        }
        Running.of(seat).failed_run(Mode.FATAL, matching(), detail)
        assert mismatch(FAILING, seat, True) == (
            'the field want of the call record is {"type": "int", "value": 3}, '
            "want int:2"
        )

    @pytest.mark.parametrize("surface", sorted(SURFACES))
    @pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
    def test_returns_none_for_every_case_of_the_corpus(
        self, case: Case, surface: str
    ) -> None:
        """The library agrees with the corpus on both surfaces."""
        reason = skip_reason(case)
        if reason is not None:
            pytest.skip(f"Python skips the case: {reason}")
        seat = drive(surface, case)
        assert mismatch(case, seat, surface == "check") is None
        for failure in seat.failures:
            assert failure.where is not None, (
                f"{failure.assertion} did not report a call site"
            )
            assert failure.where.line > 0
            assert os.path.basename(failure.where.file) == "test_corpus.py"
