"""The spec of conformance/driver.py tests the driver of a case with a behaviour."""

from __future__ import annotations

from dokimi_assert import check
from dokimi_assert.clock import Controlled
from dokimi_assert.conformance.corpus import cases
from dokimi_assert.conformance.driver import DRIVERS, run_subject
from dokimi_assert.seat import Collector, Recorder


class TestDrivers:
    """DRIVERS has the call of each assertion that takes a callable."""

    def test_contains_a_driver_of_each_assertion_whose_cases_have_a_behaviour(
        self, seat: Collector
    ) -> None:
        """The cases of the corpus have the behaviours."""
        named = sorted({c.assertion for c in cases() if c.subject is not None})
        check.equal(
            seat,
            sorted(DRIVERS),
            named,
            "DRIVERS has a driver for each assertion of the corpus",
        )


class TestRunSubject:
    """run_subject drives one case with a behaviour in place of values."""

    def test_returns_true_for_a_case_that_it_ran(self, seat: Collector) -> None:
        """A subject that raises passes raises."""
        recorder = Recorder()
        ran = run_subject("check", "throws", "raises", recorder, "throws/raises")
        check.is_true(seat, ran, "the driver ran the case")
        check.is_false(seat, recorder.failed, "a subject that raises passes raises")

    def test_returns_false_for_a_behaviour_that_it_does_not_know(
        self, seat: Collector
    ) -> None:
        """No builder has that kind."""
        ran = run_subject("check", "throws", "no-such-kind", Recorder(), "a case")
        check.is_false(
            seat, ran, "the driver does not have a builder for the behaviour"
        )

    def test_returns_false_for_an_assertion_that_does_not_take_a_behaviour(
        self, seat: Collector
    ) -> None:
        """The assertion equal takes values."""
        ran = run_subject("check", "equal", "raises", Recorder(), "a case")
        check.is_false(seat, ran, "equal takes values")

    def test_returns_false_for_a_surface_that_it_does_not_know(
        self, seat: Collector
    ) -> None:
        """The library does not have a surface soft."""
        ran = run_subject("soft", "throws", "raises", Recorder(), "a case")
        check.is_false(seat, ran, "the library does not have a surface soft")

    def test_drives_eventually_true_with_a_predicate_of_the_seated_body(
        self, seat: Collector
    ) -> None:
        """The predicate returns True when an attempt of the body passes."""
        recorder = Recorder().with_clock(Controlled(0))
        run_subject("expect", "eventually-true", "settles-after", recorder, "a case")
        check.is_false(
            seat, recorder.failed, "the behaviour settles at its third attempt"
        )
