# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/runner.py tests the phases, counts and outcomes of a run.

The reference implementation of the definition computed the counts of this
spec on the same bodies and seeds.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.case import MAX_CHOICES, Case, Generating, Replaying
from dokimi_assert._prop.engine.choice import Choice, FloatBounds, IntegerBounds
from dokimi_assert._prop.engine.collection import Sizes
from dokimi_assert._prop.engine.execution import (
    Body,
    Divergence,
    Execution,
    Observer,
    Phase,
    Status,
    execute,
    unobserved,
)
from dokimi_assert._prop.engine.generator import (
    Bool,
    Filter,
    Float,
    Integer,
    List,
    SampledFrom,
)
from dokimi_assert._prop.engine.runner import (
    DEFAULT_CASES,
    Outcome,
    Requirement,
    Settings,
    Tally,
    Values,
    conclude_case,
    known_cases,
    run,
    run_stored,
    shortfall_of,
)
from dokimi_assert._prop.engine.source import case_source
from dokimi_assert._prop.engine.tokens import decode
from dokimi_assert._prop.engine.traces import Draw, TraceError
from helpers import integers, refusal

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

SEED = 7
DIGIT = Integer(IntegerBounds(0, 9))
DIGITS = List(DIGIT, Sizes(0, 8))
BOOLEAN = Bool(Fraction(1, 2))
THREE = SampledFrom([1, 2, 3])
WIDE = Integer(IntegerBounds(0, 2**32))
SMALL = Integer(IntegerBounds(0, 1000))
BILLION = Integer(IntegerBounds(0, 10**9))
MILLION = 1_000_000


def recorded(*values: int) -> tuple[Choice, ...]:
    """Return the integer choices of values in the form of the settings of a run."""
    return tuple(integers(*values))


class Seen:
    """The calls of the body that a run made with the phase and the status of each.

    Attributes:
        calls: The phase and the status of each call in order.
    """

    def __init__(self) -> None:
        """Return the record of a run that has not called the body."""
        self.calls: list[tuple[Phase, Status]] = []

    def observer(self, phase: Phase, execution: Execution) -> None:
        """Keep one call."""
        self.calls.append((phase, execution.status))

    @property
    def phases(self) -> list[Phase]:
        """The phase of every call in order."""
        return [phase for phase, _ in self.calls]


def ran(body: Body, settings: Settings, seen: Seen | None = None) -> Outcome:
    """Return the outcome of a run."""
    observer: Observer = unobserved if seen is None else seen.observer
    return run(body, settings, observer)


def executed(body: Body, choices: list[Choice]) -> Execution:
    """Return the execution of a body on recorded choices."""
    return execute(body, Replaying(choices), MAX_CHOICES)


def passes(c: Case) -> None:
    """Draw a list of digits and pass."""
    c.draw(DIGITS, "digits")


def above_million(c: Case) -> None:
    """Fail when a wide integer is above a million."""
    if c.draw(WIDE, "n") > MILLION:
        c.fail("big")


def tenths(c: Case) -> None:
    """Classify each tenth of the wide integers."""
    if c.draw(WIDE, "n") % 10 == 0:
        c.classify("tenth")


def requests_nothing(_: Case) -> None:
    """Pass without a draw."""


def rejects(c: Case) -> None:
    """Draw a digit and reject the case."""
    c.draw(DIGIT, "n")
    c.assume(False)


def wide(c: Case) -> None:
    """Draw a wide integer and pass."""
    c.draw(WIDE, "n")


def overflow(c: Case) -> None:
    """Fail at the largest wide integer."""
    if c.draw(WIDE, "n") == 2**32:
        c.fail("overflow")


def zero_after_nonzero(c: Case) -> None:
    """Fail when a wide integer that is not 0 is followed by a 0."""
    n = c.draw(WIDE, "n")
    if n != 0 and c.draw(WIDE, "m") == 0:
        c.fail("zero after nonzero")


def sevens(c: Case) -> None:
    """Classify the digit 7."""
    if c.draw(DIGIT, "n") == 7:
        c.classify("seven")


def flag(c: Case) -> None:
    """Draw a boolean and pass."""
    c.draw(BOOLEAN, "flag")


def skips_at_thousand(c: Case) -> None:
    """Skip the run at the integer 1000."""
    if c.draw(SMALL, "n") == 1000:
        c.skip("the largest value")


class TestDefaultCases:
    """DEFAULT_CASES is the number of valid cases of a run without a number."""

    def test_aims_for_100_valid_cases(self, seat: Collector) -> None:
        """The definition sets 100 cases."""
        check.equal(seat, DEFAULT_CASES, 100, "the default is 100 cases")


class TestValues:
    """Values is an example that gives the values of the draws of a case."""

    def test_keeps_the_values_of_the_draws(self, seat: Collector) -> None:
        """Values keeps two values."""
        check.equal(
            seat, Values((1, "x")).values, (1, "x"), "the example keeps its values"
        )


class TestSettings:
    """Settings is the configuration of a run."""

    def test_fills_in_every_default(self, seat: Collector) -> None:
        """The defaults are those of the definition."""
        s = Settings(SEED)
        check.equal(
            seat,
            [
                s.seed,
                s.cases,
                s.max_choices,
                s.requirements,
                s.traces,
                s.examples,
                s.stored,
                s.shrink,
                s.shrink_time,
                s.explain,
                s.workers,
                s.replay,
            ],
            [SEED, 100, MAX_CHOICES, (), (), (), (), 2000, 0.0, True, 1, None],
            "the settings have the defaults of the definition",
        )

    def test_raises_value_error_for_a_run_of_zero_cases(self, seat: Collector) -> None:
        """A run of zero cases is refused."""
        check.equal(
            seat,
            refusal(seat, lambda: Settings(SEED, cases=0)),
            "prop: a run of 0 cases does not test anything",
            "the error has the reason",
        )

    def test_raises_value_error_for_a_run_on_zero_workers(
        self, seat: Collector
    ) -> None:
        """A run on zero workers is refused."""
        check.equal(
            seat,
            refusal(seat, lambda: Settings(SEED, workers=0)),
            "prop: a run on 0 workers does not run anything",
            "the error has the reason",
        )


class TestKnownCases:
    """known_cases returns the cases that a run tries before it generates any."""

    def test_returns_the_stored_cases_after_every_case_of_the_example_phase(
        self, seat: Collector
    ) -> None:
        """The settings give four known cases."""
        known = known_cases(
            Settings(
                SEED,
                traces=((Draw("n", 5),),),
                examples=(recorded(3), Values((4,))),
                stored=(recorded(6),),
            )
        )
        check.equal(
            seat,
            [(phase, type(provider).__name__) for phase, provider in known],
            [
                ("example", "Tracing"),
                ("example", "Replaying"),
                ("example", "Valuing"),
                ("stored", "Replaying"),
            ],
            "the stored case follows the three example cases",
        )


class TestTally:
    """Tally keeps the counts of a run so far."""

    def test_starts_with_zero_counts(self, seat: Collector) -> None:
        """The tally starts at zero."""
        tally = Tally(SEED)
        check.equal(
            seat,
            [
                tally.seed,
                tally.valid,
                tally.rejected,
                tally.requested,
                len(tally.labels),
            ],
            [SEED, 0, 0, False, 0],
            "every count is zero",
        )

    def test_ends_the_run_at_a_case_that_skips_with_its_reason(
        self, seat: Collector
    ) -> None:
        """A skip ends the run after the valid case before it."""
        tally = Tally(SEED)
        tally.take(executed(passes, []))
        outcome = tally.take(executed(lambda c: c.skip("unsupported"), []))
        check.equal(
            seat,
            outcome,
            Outcome("skipped", 1, 0, SEED, reason="unsupported"),
            "the run skips with the count of the valid case",
        )


class TestTallyFailureWithoutCounterexample:
    """Tally.failure_without_counterexample checks a run without a failure."""

    def test_returns_rejected_for_more_than_ten_rejections_per_valid_case(
        self, seat: Collector
    ) -> None:
        """Ten rejections per valid case do not end the run, and eleven do."""
        tally = Tally(SEED)
        tally.take(executed(passes, []))
        for _ in range(10):
            tally.take(executed(rejects, []))
        at_limit = tally.failure_without_counterexample()
        tally.take(executed(rejects, []))
        past = tally.failure_without_counterexample()
        check.equal(
            seat,
            [at_limit, None if past is None else past.kind],
            [None, "rejected"],
            "ten rejections per valid case do not end the run, and eleven do",
        )

    def test_returns_vacuous_for_a_run_whose_cases_did_not_request_an_input(
        self, seat: Collector
    ) -> None:
        """The body does not draw."""
        tally = Tally(SEED)
        tally.take(executed(requests_nothing, []))
        outcome = tally.failure_without_counterexample()
        check.equal(
            seat,
            None if outcome is None else outcome.kind,
            "vacuous",
            "the outcome is vacuous",
        )


class TestShortfallOf:
    """shortfall_of finds the first requirement that a run misses."""

    def test_returns_the_first_requirement_that_the_counts_leave_unmet(
        self, seat: Collector
    ) -> None:
        """The second requirement is unmet."""
        tally = Tally(SEED)
        tally.valid = 10
        tally.labels["seven"] = 1
        requirements = (Requirement("seven", 0.1), Requirement("never", 0.5))
        shortfall, met = shortfall_of(tally, requirements, True, True)
        check.equal(
            seat,
            [
                None if shortfall is None else shortfall.requirement,
                None if shortfall is None else shortfall.counted,
                None if shortfall is None else shortfall.valid,
                None if shortfall is None else shortfall.verdict,
                met,
            ],
            [Requirement("never", 0.5), 0, 10, "unmet", False],
            "the shortfall is the second requirement",
        )

    def test_reports_that_the_counts_meet_every_requirement(
        self, seat: Collector
    ) -> None:
        """The counts meet every requirement."""
        tally = Tally(SEED)
        tally.valid = 10
        tally.labels["seven"] = 1
        check.equal(
            seat,
            shortfall_of(tally, (Requirement("seven", 0.1),), True, True),
            (None, True),
            "the counts meet every requirement",
        )


class TestRun:
    """run runs the phases and returns the outcome."""

    def test_passes_a_body_that_never_fails_after_the_default_number_of_cases(
        self, seat: Collector
    ) -> None:
        """The run passes after 100 valid cases."""
        outcome = ran(passes, Settings(SEED))
        check.equal(
            seat,
            [outcome.kind, outcome.cases],
            ["passed", 100],
            "the run passes after 100 valid cases",
        )

    def test_passes_an_exhausted_domain_after_its_inputs(self, seat: Collector) -> None:
        """The domain has six inputs."""

        def flag_and_three(c: Case) -> None:
            c.draw(BOOLEAN, "flag")
            c.draw(THREE, "one of three")

        outcome = ran(flag_and_three, Settings(SEED))
        check.equal(
            seat,
            [outcome.kind, outcome.cases],
            ["passed", 6],
            "the run passes after six inputs",
        )

    def test_does_not_count_a_repeated_case(self, seat: Collector) -> None:
        """A boolean has two inputs."""
        check.equal(
            seat, ran(flag, Settings(SEED)).cases, 2, "a boolean has two inputs"
        )

    def test_stops_generating_after_ten_times_the_cases(self, seat: Collector) -> None:
        """The run makes the simplest case, the edge cases and 200 random cases."""
        calls = 0
        one = Float(FloatBounds(1.0, 1.0))

        def draws_one(c: Case) -> None:
            nonlocal calls
            calls += 1
            c.draw(one, "one")

        outcome = ran(draws_one, Settings(SEED, cases=20))
        check.equal(
            seat,
            [outcome.kind, outcome.cases, calls],
            ["passed", 1, 1 + 4 + 10 * 20],
            "the run makes 205 calls",
        )

    def test_finds_a_failure_on_the_empty_input_in_the_simplest_case(
        self, seat: Collector
    ) -> None:
        """The first case fails."""

        def empty(c: Case) -> None:
            if len(c.draw(DIGITS, "digits")) == 0:
                c.fail("empty")

        outcome = ran(empty, Settings(SEED))
        check.equal(
            seat,
            [
                outcome.kind,
                outcome.cases,
                None if outcome.failing is None else outcome.failing.case.choices,
            ],
            ["counterexample", 0, integers(0)],
            "the simplest case fails",
        )

    def test_finds_an_overflow_at_the_maximum_in_an_edge_case(
        self, seat: Collector
    ) -> None:
        """Edge case 1 fails after three valid cases."""
        outcome = ran(overflow, Settings(SEED))
        check.equal(
            seat,
            [outcome.kind, outcome.cases],
            ["counterexample", 3],
            "edge case 1 fails after three valid cases",
        )

    def test_reports_the_case_and_the_identity_of_a_random_failure(
        self, seat: Collector
    ) -> None:
        """The failing digits sum to more than 10."""

        def sum_above(c: Case) -> None:
            if sum(c.draw(DIGITS, "digits")) > 10:
                c.fail("sum-above")

        outcome = ran(sum_above, Settings(SEED))
        failing = outcome.failing
        failure = None if failing is None else failing.failure
        drawn = [] if failing is None else failing.case.draws[0].value
        check.equal(
            seat,
            [
                outcome.kind,
                None if failure is None else failure.identity,
                sum(drawn) > 10,
            ],
            ["counterexample", "sum-above", True],
            "the counterexample sums to more than 10",
        )

    def test_runs_a_stored_failing_case_before_any_generated_case(
        self, seat: Collector
    ) -> None:
        """The stored case fails first."""

        def seven(c: Case) -> None:
            if c.draw(DIGIT, "n") == 7:
                c.fail("seven")

        outcome = ran(seven, Settings(SEED, stored=(recorded(7),)))
        check.equal(
            seat,
            [outcome.kind, outcome.cases, len(outcome.stored)],
            ["counterexample", 0, 1],
            "the stored case fails first",
        )

    def test_decodes_random_case_i_from_the_stream_of_the_seed_plus_i(
        self, seat: Collector
    ) -> None:
        """The case and the stream give the same digits."""
        execution = execute(passes, Generating(case_source(SEED, 3)), MAX_CHOICES)
        check.equal(
            seat,
            execution.case.draws[0].value,
            DIGITS.decode(Case(Generating(case_source(SEED, 3)))),
            "the case has the digits of the stream",
        )

    def test_fills_a_prefix_case_with_target_choices_after_its_random_prefix(
        self, seat: Collector
    ) -> None:
        """Prefix case 0 fails."""
        outcome = ran(zero_after_nonzero, Settings(SEED, shrink=0))
        first = WIDE.decode(Case(Generating(case_source(SEED, 0))))
        check.equal(
            seat,
            [
                outcome.kind,
                outcome.cases,
                None if outcome.failing is None else outcome.failing.case.choices,
            ],
            ["counterexample", 2, integers(first, 0)],
            "prefix case 0 ends with a target choice",
        )

    def test_runs_a_prefix_case_while_the_valid_cases_equal_the_limit(
        self, seat: Collector
    ) -> None:
        """A run of 20 cases tries prefix cases up to two valid cases."""
        outcome = ran(zero_after_nonzero, Settings(SEED, cases=20, shrink=0))
        check.equal(
            seat,
            [outcome.kind, outcome.cases],
            ["counterexample", 2],
            "the prefix case runs at two valid cases",
        )

    def test_runs_every_edge_case_when_the_random_cases_stop_first(
        self, seat: Collector
    ) -> None:
        """The simplest case runs before four edge cases."""
        seen = Seen()
        outcome = ran(wide, Settings(SEED, cases=1), seen)
        check.equal(
            seat,
            [outcome.kind, seen.phases],
            ["passed", ["simplest", "edge", "edge", "edge", "edge"]],
            "the simplest case runs before four edge cases",
        )

    def test_ends_the_run_at_an_edge_case_after_the_random_cases_stop(
        self, seat: Collector
    ) -> None:
        """The edge case of the maximum fails."""
        seen = Seen()
        outcome = ran(overflow, Settings(SEED, cases=1, shrink=0), seen)
        check.equal(
            seat,
            [outcome.kind, seen.phases],
            ["counterexample", ["simplest", "edge", "edge"]],
            "the edge case of the maximum fails",
        )

    def test_returns_rejected_for_a_body_that_rejects_every_case(
        self, seat: Collector
    ) -> None:
        """The body rejects every case."""

        def rejects_digits(c: Case) -> None:
            c.draw(DIGITS, "digits")
            c.assume(False)

        outcome = ran(rejects_digits, Settings(SEED, cases=10))
        check.equal(seat, outcome.kind, "rejected", "the outcome is rejected")

    def test_returns_rejected_for_cases_past_their_cap(self, seat: Collector) -> None:
        """Lists overrun three choices."""
        check.equal(
            seat,
            ran(passes, Settings(SEED, max_choices=3)).kind,
            "rejected",
            "lists overrun three choices",
        )

    def test_returns_vacuous_for_a_body_that_does_not_request_an_input(
        self, seat: Collector
    ) -> None:
        """One case runs without a draw."""
        outcome = ran(requests_nothing, Settings(SEED))
        check.equal(
            seat,
            [outcome.kind, outcome.cases],
            ["vacuous", 1],
            "one case runs without a draw",
        )

    def test_passes_a_body_that_only_reads_the_random_source(
        self, seat: Collector
    ) -> None:
        """The choices of the random source are inputs."""

        def random(c: Case) -> None:
            c.random()

        outcome = ran(random, Settings(SEED))
        check.equal(
            seat,
            [outcome.kind, outcome.cases],
            ["passed", 100],
            "the choices of the random source are inputs",
        )

    def test_returns_flaky_for_a_body_that_requests_different_choices(
        self, seat: Collector
    ) -> None:
        """The first request diverges."""
        calls = 0

        def shifting(c: Case) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                c.draw(DIGIT, "n")
            else:
                c.draw(BOOLEAN, "n")

        outcome = ran(shifting, Settings(SEED))
        check.equal(
            seat,
            [
                outcome.kind,
                None if outcome.divergence is None else outcome.divergence.index,
            ],
            ["flaky", 0],
            "the first request diverges",
        )

    def test_returns_flaky_for_a_failure_whose_replay_passes(
        self, seat: Collector
    ) -> None:
        """The replay of the failure passes."""
        calls = 0

        def second(c: Case) -> None:
            nonlocal calls
            calls += 1
            c.draw(WIDE, "n")
            if calls == 2:
                c.fail("second")

        outcome = ran(second, Settings(SEED))
        check.equal(
            seat,
            [
                outcome.kind,
                None if outcome.divergence is None else outcome.divergence.what,
            ],
            ["flaky", "verdict"],
            "the outcome is flaky with a verdict divergence",
        )

    def test_returns_flaky_for_a_failure_whose_replay_skips(
        self, seat: Collector
    ) -> None:
        """A replay that skips counts as a replay that passes."""
        failed = False

        def fails_then_skips(c: Case) -> None:
            nonlocal failed
            value = c.draw(BILLION, "value")
            if failed:
                c.skip("after")
            if value > 1000:
                failed = True
                c.fail("once")

        outcome = ran(fails_then_skips, Settings(SEED))
        check.equal(
            seat,
            [outcome.kind, outcome.cases, outcome.divergence],
            ["flaky", 1, Divergence("verdict", 1, "once", None)],
            "the recorded failure against a skip, as against a pass",
        )

    def test_returns_skipped_at_the_simplest_case_of_a_body_that_skips_every_case(
        self, seat: Collector
    ) -> None:
        """The first case skips before any case is valid."""

        def skips(c: Case) -> None:
            c.draw(SMALL, "n")
            c.skip("unsupported")

        outcome = ran(skips, Settings(SEED))
        check.equal(
            seat,
            [outcome.kind, outcome.cases, outcome.reason],
            ["skipped", 0, "unsupported"],
            "the run skips at the simplest case",
        )

    def test_counts_the_valid_cases_before_the_case_that_skips(
        self, seat: Collector
    ) -> None:
        """Three cases pass before a case draws 1000."""
        outcome = ran(skips_at_thousand, Settings(SEED))
        check.equal(
            seat,
            [outcome.kind, outcome.cases, outcome.reason],
            ["skipped", 3, "the largest value"],
            "the run skips after three valid cases",
        )

    def test_skips_at_a_case_that_skips_where_an_earlier_case_made_a_request(
        self, seat: Collector
    ) -> None:
        """A case that skips at the node of an earlier case leaves no leaf."""
        calls = 0

        def zero_again(c: Case) -> None:
            nonlocal calls
            calls += 1
            if c.draw(DIGIT, "first") == 0 and calls > 1:
                c.skip("zero again")
            c.draw(DIGIT, "second")

        outcome = ran(zero_again, Settings(SEED))
        check.equal(
            seat,
            [outcome.kind, outcome.cases, outcome.reason],
            ["skipped", 3, "zero again"],
            "the run skips after three valid cases",
        )

    def test_skips_a_replay_whose_case_skips(self, seat: Collector) -> None:
        """The one case of the replay skips."""
        outcome = ran(skips_at_thousand, Settings(SEED, replay=recorded(1000)))
        check.equal(
            seat,
            [outcome.kind, outcome.cases, outcome.reason],
            ["skipped", 0, "the largest value"],
            "the replay skips",
        )

    def test_passes_a_requirement_that_the_share_meets(self, seat: Collector) -> None:
        """Half the integers are even."""

        def even(c: Case) -> None:
            if c.draw(WIDE, "n") % 2 == 0:
                c.classify("even")

        outcome = ran(even, Settings(SEED, requirements=(Requirement("even", 0.2),)))
        check.equal(
            seat,
            [outcome.kind, outcome.cases],
            ["passed", 100],
            "half the integers are even",
        )

    def test_returns_coverage_unmet_for_a_label_never_counted(
        self, seat: Collector
    ) -> None:
        """The shortfall has the label and its count."""
        outcome = ran(passes, Settings(SEED, requirements=(Requirement("never", 0.5),)))
        shortfall = outcome.shortfall
        check.equal(
            seat,
            [
                outcome.kind,
                None if shortfall is None else shortfall.requirement.label,
                None if shortfall is None else shortfall.counted,
            ],
            ["coverage-unmet", "never", 0],
            "the shortfall has the label and its count",
        )

    def test_compares_the_exact_shares_of_an_exhausted_domain(
        self, seat: Collector
    ) -> None:
        """One of ten digits is 10%."""
        met = ran(sevens, Settings(SEED, requirements=(Requirement("seven", 0.1),)))
        unmet = ran(sevens, Settings(SEED, requirements=(Requirement("seven", 0.2),)))
        check.equal(
            seat,
            [met.kind, unmet.kind, unmet.cases],
            ["passed", "coverage-unmet", 10],
            "one of ten digits meets 10% and misses 20%",
        )

    def test_runs_an_undecided_requirement_up_to_the_last_check(
        self, seat: Collector
    ) -> None:
        """The run makes eight times the cases."""
        outcome = ran(
            tenths,
            Settings(SEED, cases=50, requirements=(Requirement("tenth", 0.1),)),
        )
        check.equal(seat, outcome.cases, 400, "the run makes eight times the cases")

    def test_decides_an_undecided_requirement_by_its_share_at_the_last_check(
        self, seat: Collector
    ) -> None:
        """43 of 400 is below nine tenths of 12%."""
        outcome = ran(
            tenths,
            Settings(SEED, cases=50, requirements=(Requirement("tenth", 0.12),)),
        )
        shortfall = outcome.shortfall
        check.equal(
            seat,
            [
                None if shortfall is None else shortfall.counted,
                None if shortfall is None else shortfall.valid,
                None if shortfall is None else shortfall.verdict,
            ],
            [43, 400, "unmet"],
            "43 of 400 is below nine tenths of 12%",
        )

    def test_runs_the_random_cases_after_the_first_check_as_coverage_cases(
        self, seat: Collector
    ) -> None:
        """50 valid cases before the first coverage case."""
        seen = Seen()
        ran(
            tenths,
            Settings(SEED, cases=50, requirements=(Requirement("tenth", 0.1),)),
            seen,
        )
        first = seen.phases.index("coverage")
        check.equal(
            seat,
            [
                len([s for _, s in seen.calls[:first] if s == "passed"]),
                list(dict.fromkeys(seen.phases[first:])),
            ],
            [50, ["coverage"]],
            "50 valid cases before the first coverage case",
        )

    def test_runs_the_examples_and_the_stored_cases_first(
        self, seat: Collector
    ) -> None:
        """The known cases run first."""
        seen = Seen()
        calls = 0

        def counted(c: Case) -> None:
            nonlocal calls
            calls += 1
            c.draw(WIDE, "n")

        ran(
            counted,
            Settings(
                SEED,
                cases=1,
                examples=(recorded(5),),
                stored=(recorded(3), recorded(4)),
            ),
            seen,
        )
        check.equal(
            seat,
            [seen.phases[:4], len(seen.calls)],
            [["example", "stored", "stored", "simplest"], calls],
            "the known cases run first",
        )

    def test_runs_a_trace_before_the_examples(self, seat: Collector) -> None:
        """The trace runs before the example."""
        seen = Seen()
        values: list[int] = []

        def keeps(c: Case) -> None:
            values.append(c.draw(WIDE, "n"))

        ran(
            keeps,
            Settings(
                SEED,
                cases=1,
                traces=((Draw("n", 5),),),
                examples=(recorded(3),),
            ),
            seen,
        )
        check.equal(
            seat,
            [seen.phases[:3], values[:2]],
            [["example", "example", "simplest"], [5, 3]],
            "the trace runs before the example",
        )

    def test_raises_trace_error_for_a_trace_that_the_body_cannot_follow(
        self, seat: Collector
    ) -> None:
        """No case runs."""
        seen = Seen()
        error = check.raises(
            seat,
            lambda: ran(wide, Settings(SEED, traces=((Draw("m", 5),),)), seen),
            "the trace is refused",
        )
        check.error_as(seat, error, TraceError, "the error is a TraceError")
        check.is_empty(seat, seen.calls, "no case ran")

    def test_follows_a_random_case_by_its_prefix_case(self, seat: Collector) -> None:
        """Prefix case 0 follows random case 0."""
        seen = Seen()

        def two(c: Case) -> None:
            c.draw(WIDE, "n")
            c.draw(WIDE, "m")

        ran(two, Settings(SEED), seen)
        check.equal(
            seat,
            seen.phases[1:3],
            ["random", "prefix"],
            "prefix case 0 follows random case 0",
        )

    def test_shrinks_a_failure_after_its_replay_before_its_explanation(
        self, seat: Collector
    ) -> None:
        """The shrink runs come before the explain runs."""
        seen = Seen()
        outcome = ran(above_million, Settings(SEED), seen)
        replay = seen.phases.index("replay")
        after = seen.phases[replay + 1 :]
        shrinks = after.count("shrink")
        explains = len(after) - shrinks
        check.equal(
            seat,
            [seen.calls[replay - 1][1], after, explains > 0, len(after)],
            [
                "failed",
                ["shrink"] * shrinks + ["explain"] * explains,
                True,
                outcome.runs,
            ],
            "the shrink runs come before the explain runs",
        )

    def test_runs_each_filling_of_a_draw_as_an_explain_run(
        self, seat: Collector
    ) -> None:
        """The draw has four fillings."""
        seen = Seen()

        def always(c: Case) -> None:
            c.draw(WIDE, "n")
            c.fail("always")

        ran(always, Settings(SEED), seen)
        check.equal(
            seat,
            seen.phases,
            [
                "simplest",
                "replay",
                "shrink",
                "explain",
                "explain",
                "explain",
                "explain",
            ],
            "the explain phase runs four fillings",
        )

    def test_ends_the_explain_phase_with_the_step_to_the_nearest_passing_value(
        self, seat: Collector
    ) -> None:
        """The step passes."""
        seen = Seen()
        ten_thousand = Integer(IntegerBounds(0, 10_000))

        def big(c: Case) -> None:
            if c.draw(ten_thousand, "n") > 1000:
                c.fail("big")

        ran(big, Settings(SEED), seen)
        check.equal(seat, seen.calls[-1], ("explain", "passed"), "the step passes")

    def test_does_not_explain_when_the_explanation_is_off(
        self, seat: Collector
    ) -> None:
        """The outcome does not contain an explanation."""
        outcome = ran(above_million, Settings(SEED, explain=False))
        check.equal(
            seat,
            [outcome.kind, outcome.explanation],
            ["counterexample", ()],
            "the outcome does not contain an explanation",
        )

    def test_does_not_replay_without_a_shrink(self, seat: Collector) -> None:
        """The run reports the first failing case with its token."""
        seen = Seen()
        outcome = ran(above_million, Settings(SEED, shrink=0), seen)
        check.equal(
            seat,
            [
                seen.calls[-1][1],
                "replay" in seen.phases,
                outcome.explanation,
                outcome.token is None,
            ],
            ["failed", False, (), False],
            "the run reports the first failing case with its token",
        )

    def test_runs_the_one_case_of_a_replay_under_the_phase_token(
        self, seat: Collector
    ) -> None:
        """The replay runs one case under the phase token."""
        seen = Seen()
        outcome = ran(above_million, Settings(SEED, replay=recorded(MILLION + 1)), seen)
        check.equal(
            seat,
            [seen.calls, outcome.kind, outcome.token is None],
            [[("token", "failed")], "counterexample", False],
            "the replay runs one token case",
        )

    def test_passes_a_replay_that_passes(self, seat: Collector) -> None:
        """1 does not fail."""
        check.equal(
            seat,
            ran(above_million, Settings(SEED, replay=recorded(1))).kind,
            "passed",
            "the replay of 1 passes",
        )

    def test_returns_vacuous_for_a_replay_that_does_not_request_an_input(
        self, seat: Collector
    ) -> None:
        """The body does not draw."""
        check.equal(
            seat,
            ran(requests_nothing, Settings(SEED, replay=())).kind,
            "vacuous",
            "the outcome is vacuous",
        )

    def test_counts_a_passing_example_of_values_as_a_valid_case(
        self, seat: Collector
    ) -> None:
        """The run counts two inputs and the example."""
        outcome = ran(flag, Settings(SEED, examples=(Values((True,)),)))
        check.equal(
            seat,
            [outcome.kind, outcome.cases],
            ["passed", 3],
            "the run counts two inputs and the example",
        )

    def test_reports_a_failing_example_of_values_as_found(
        self, seat: Collector
    ) -> None:
        """The run does not replay, shrink or explain the example."""
        seen = Seen()
        outcome = ran(
            above_million, Settings(SEED, examples=(Values((MILLION + 5,)),)), seen
        )
        failing = outcome.failing
        check.equal(
            seat,
            [
                seen.calls,
                outcome.kind,
                outcome.valued,
                outcome.token,
                outcome.runs,
                outcome.others,
                None if failing is None else failing.case.choices,
                None if failing is None else failing.case.draws[0].value,
            ],
            [
                [("example", "failed")],
                "counterexample",
                True,
                None,
                0,
                (),
                [],
                MILLION + 5,
            ],
            "the run does not replay, shrink or explain the example",
        )

    def test_shrinks_a_failing_example_of_choices(self, seat: Collector) -> None:
        """The example shrinks to the minimal case."""
        outcome = ran(above_million, Settings(SEED, examples=(recorded(MILLION + 5),)))
        failing = outcome.failing
        check.equal(
            seat,
            [
                outcome.valued,
                outcome.token is None,
                None if failing is None else failing.case.draws[0].value,
            ],
            [False, False, MILLION + 1],
            "the example shrinks to the minimal case",
        )

    def test_returns_a_token_that_replays_the_counterexample(
        self, seat: Collector
    ) -> None:
        """The token replays the minimal value."""
        outcome = ran(above_million, Settings(SEED))
        replayed = executed(above_million, decode(outcome.token or ""))
        check.equal(
            seat,
            replayed.case.draws[0].value,
            MILLION + 1,
            "the token replays the minimal value",
        )

    def test_reports_the_other_identities_that_the_shrink_found(
        self, seat: Collector
    ) -> None:
        """The run reports both identities shrunk."""
        small = Integer(IntegerBounds(0, 1000))

        def odd_or_big(c: Case) -> None:
            value = c.draw(small, "x")
            if value % 2 == 1:
                c.fail("odd")
            if value > 50:
                c.fail("big")

        outcome = ran(odd_or_big, Settings(SEED))
        found = {
            one.failure.identity: one.case.draws[0].value
            for one in (outcome.failing, *outcome.others)
            if one is not None and one.failure is not None
        }
        check.equal(
            seat,
            found,
            {"big": 52, "odd": 1},
            "the run reports both identities shrunk",
        )


def report(outcome: Outcome) -> list[Any]:
    """Return what an outcome reports apart from the identity of its cases."""
    failing = outcome.failing
    return [
        outcome.kind,
        outcome.cases,
        outcome.rejected,
        outcome.shortfall,
        outcome.divergence,
        None if failing is None else failing.case.choices,
        [one.case.choices for one in outcome.others],
        outcome.explanation,
        outcome.token,
        outcome.runs,
    ]


SMALL = Integer(IntegerBounds(0, 1000))
TEN_THOUSAND = Integer(IntegerBounds(0, 10_000))
TRUES = Filter(BOOLEAN, lambda b: b)
HIGH = Filter(Integer(IntegerBounds(0, 3)), lambda v: v >= 2)
EVEN_SMALL = Filter(SMALL, lambda v: v % 2 == 0)


def fifths(c: Case) -> None:
    """Reject four cases in five."""
    c.assume(c.draw(SMALL, "n") % 5 == 0)


def digit(c: Case) -> None:
    """Draw a digit and pass."""
    c.draw(DIGIT, "n")


def thirty_one(c: Case) -> None:
    """Draw one of 31 values and pass."""
    c.draw(Integer(IntegerBounds(0, 30)), "n")


def even(c: Case) -> None:
    """Classify the even values."""
    if c.draw(SMALL, "n") % 2 == 0:
        c.classify("even")


def above_thousand(c: Case) -> None:
    """Fail above 1000."""
    if c.draw(TEN_THOUSAND, "n") >= 1001:
        c.fail("big")


def at_least_900(c: Case) -> None:
    """Fail at 900 and above."""
    if c.draw(SMALL, "n") >= 900:
        c.fail("big")


def at_most(c: Case) -> None:
    """Fail at the largest value. An edge case finds it."""
    if c.draw(TEN_THOUSAND, "n") >= 10_000:
        c.fail("big")


def trues(c: Case) -> None:
    """Draw a filtered true."""
    c.draw(TRUES, "b")


def pair(c: Case) -> None:
    """Fail for a high 3 and then a high 2."""
    first, second = c.draw(HIGH, "first"), c.draw(HIGH, "second")
    if first == 3 and second == 2:
        c.fail("pair")


def even_above(c: Case) -> None:
    """Fail for an even value above 500."""
    if c.draw(EVEN_SMALL, "n") >= 501:
        c.fail("big")


class TestRunOnFourWorkers:
    """run on four workers reports the same outcome as a run on one worker."""

    tests: ClassVar[list[tuple[str, Body, dict[str, Any]]]] = [
        ("reports the pass of a body that never fails", passes, {}),
        ("reports the rejection of a body that rejects every case", rejects, {}),
        ("reports the counts of a body that rejects four cases in five", fifths, {}),
        ("reports the rejection of each case past its cap", passes, {"max_choices": 3}),
        ("reports a body that requests no input", requests_nothing, {}),
        ("reports a pass once every input of a domain is tested", digit, {}),
        ("reports a domain whose repeats have prefix cases", thirty_one, {}),
        (
            "reports a met coverage requirement",
            even,
            {"requirements": (Requirement("even", 0.3),)},
        ),
        (
            "reports a requirement that the last check leaves unmet",
            even,
            {"requirements": (Requirement("even", 0.6),)},
        ),
        ("reports the minimal counterexample and its explanation", above_thousand, {}),
        ("reports a failure at the maximum that an edge case finds", overflow, {}),
        (
            "reports a failure of a later stored case",
            at_least_900,
            {"stored": (recorded(100), recorded(950))},
        ),
        (
            "reports the first failing case without a shrink",
            above_thousand,
            {"shrink": 0},
        ),
        (
            "reports a failure of an edge case after the random cases stop",
            at_most,
            {"cases": 2, "shrink": 0},
        ),
        ("reports a filter whose rejected attempts enter the tree", trues, {}),
        (
            "reports the prefix case of a repeat after rejected attempts",
            pair,
            {"seed": 2},
        ),
        ("reports the counterexample of a filter that shrinks", even_above, {}),
    ]

    @pytest.mark.parametrize(
        ("body", "adjust"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_reports_what_one_worker_reports(
        self, seat: Collector, body: Body, adjust: dict[str, Any]
    ) -> None:
        """The outcome and the calls of the body are the same."""
        one, four = Seen(), Seen()
        options: dict[str, Any] = {"seed": SEED, **adjust}
        alone = run(body, Settings(**options), one.observer)
        many = run(body, Settings(**options, workers=4), four.observer)
        check.equal(
            seat,
            [report(many), four.calls],
            [report(alone), one.calls],
            "four workers report the same outcome and calls as one",
        )


class TestRunStored:
    """run_stored runs the stored cases of a run before its other cases."""

    def test_counts_the_stored_cases_that_pass(self, seat: Collector) -> None:
        """Two stored cases pass."""
        outcome = run_stored(
            above_million, Settings(SEED, stored=(recorded(1), recorded(2)))
        )
        check.equal(
            seat,
            [outcome.kind, outcome.cases, len(outcome.stored)],
            ["passed", 2, 2],
            "two stored cases pass",
        )

    def test_reports_the_first_failing_stored_case_as_found_with_its_token(
        self, seat: Collector
    ) -> None:
        """The run does not shrink the stored case."""
        seen = Seen()
        outcome = run_stored(
            above_million,
            Settings(SEED, stored=(recorded(1), recorded(MILLION + 9), recorded(3))),
            seen.observer,
        )
        check.equal(
            seat,
            [outcome.kind, len(outcome.stored), outcome.token is None, seen.phases],
            ["counterexample", 2, False, ["stored", "stored"]],
            "the run does not shrink the stored case",
        )

    def test_skips_at_the_first_stored_case_that_skips(self, seat: Collector) -> None:
        """The second of three stored cases skips."""
        outcome = run_stored(
            skips_at_thousand,
            Settings(SEED, stored=(recorded(1), recorded(1000), recorded(3))),
        )
        check.equal(
            seat,
            [
                outcome.kind,
                outcome.cases,
                outcome.reason,
                len(outcome.stored),
                outcome.token,
            ],
            ["skipped", 1, "the largest value", 2, None],
            "the run skips at the second stored case, without a token",
        )

    def test_runs_neither_a_trace_nor_an_example(self, seat: Collector) -> None:
        """No case runs."""
        seen = Seen()
        run_stored(
            above_million,
            Settings(SEED, examples=(recorded(5),), traces=((Draw("n", 5),),)),
            seen.observer,
        )
        check.is_empty(seat, seen.calls, "no case runs")


class TestConcludeCase:
    """conclude_case concludes a failed case that a run did not find."""

    def test_shrinks_a_failed_case_that_a_run_did_not_find(
        self, seat: Collector
    ) -> None:
        """The failed case shrinks to the minimal case."""
        failing = executed(above_million, integers(MILLION * 5))
        outcome = conclude_case(above_million, Settings(SEED), failing)
        check.equal(
            seat,
            [
                outcome.kind,
                outcome.cases,
                None
                if outcome.failing is None
                else outcome.failing.case.draws[0].value,
            ],
            ["counterexample", 0, MILLION + 1],
            "the failed case shrinks to the minimal case",
        )
