# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/campaign.py tests a run that explores for a span of time.

A campaign keeps the cases that show new behaviour. Every campaign of the
spec but one measures its budget on a clock that advances by one at each
reading. A budget of n + 1 then runs n cases after the known ones.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from dokimi_assert import check
from dokimi_assert._prop.engine.campaign import campaign
from dokimi_assert._prop.engine.case import Case, Generating
from dokimi_assert._prop.engine.choice import (
    Choice,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
)
from dokimi_assert._prop.engine.collection import Sizes
from dokimi_assert._prop.engine.execution import Body, Execution, Phase
from dokimi_assert._prop.engine.generator import Bytes, Float, Integer, List
from dokimi_assert._prop.engine.runner import Outcome, Requirement, Settings, Values
from dokimi_assert._prop.engine.source import case_source
from dokimi_assert._prop.engine.traces import Draw
from helpers import integers

if TYPE_CHECKING:
    from collections.abc import Callable

    from dokimi_assert.seat import Collector

SEED = 7
WIDE = Integer(IntegerBounds(0, 1_000_000_000))
DIGITS = List(Integer(IntegerBounds(0, 9)), Sizes(0, 5))
UNIT = Float(FloatBounds(0.0, 1.0))
BYTES = Bytes(SequenceBounds(256, 0, 4))
HIGH = 900_000_000

#: The phase and the execution of one call of the body.
Call = tuple[Phase, Execution]


def recorded(*values: int) -> tuple[Choice, ...]:
    """Return the integer choices of values in the form of the settings of a run."""
    return tuple(integers(*values))


def ticking() -> Callable[[], float]:
    """Return a clock that advances by one at each reading."""
    reading = 0.0

    def now() -> float:
        nonlocal reading
        reading += 1
        return reading

    return now


def explored(
    body: Body,
    count: int,
    settings: Settings | None = None,
    concluded: Callable[[Outcome], None] | None = None,
) -> tuple[Outcome, list[Call]]:
    """Return the outcome of a campaign that runs count cases after the known ones.

    The result also contains the phase and the execution of every call.
    """
    calls: list[Call] = []
    outcome = campaign(
        body,
        Settings(SEED) if settings is None else settings,
        count + 1,
        lambda phase, execution: calls.append((phase, execution)),
        concluded,
        ticking(),
    )
    return outcome, calls


def firsts(calls: list[Call]) -> list[object]:
    """Return the first value that each random call drew."""
    return [
        execution.case.draws[0].value for phase, execution in calls if phase == "random"
    ]


def repeated_share(values: list[object]) -> float:
    """Return the share of values that equal an earlier value of the list."""
    seen: set[object] = set()
    repeats = 0
    for value in values:
        if value in seen:
            repeats += 1
        seen.add(value)
    return repeats / len(values)


def plain(c: Case) -> None:
    """Draw two wide integers that do not show new behaviour."""
    c.draw(WIDE, "n")
    c.draw(WIDE, "m")


def high(c: Case) -> None:
    """Fail when a wide integer is above HIGH."""
    if c.draw(WIDE, "n") > HIGH:
        c.fail("high")


class TestCampaign:
    """campaign explores a body until its budget has passed."""

    def test_runs_cases_until_its_budget_has_passed(self, seat: Collector) -> None:
        """The campaign runs 25 valid cases."""
        outcome, calls = explored(plain, 25)
        check.equal(
            seat,
            [outcome.kind, outcome.cases, len(calls)],
            ["passed", 25, 25],
            "the campaign runs 25 valid cases",
        )

    def test_runs_the_random_cases_of_the_seed_while_its_pool_is_empty(
        self, seat: Collector
    ) -> None:
        """The cases are the random cases of seed 7."""
        _, calls = explored(plain, 10)
        want = [WIDE.decode(Case(Generating(case_source(SEED, i)))) for i in range(10)]
        check.equal(
            seat, firsts(calls), want, "the cases are the random cases of seed 7"
        )

    def test_measures_its_budget_on_the_platform_clock_by_default(
        self, seat: Collector
    ) -> None:
        """A budget of 0 seconds does not run a case."""
        calls: list[Call] = []
        outcome = campaign(
            plain,
            Settings(SEED),
            0,
            lambda phase, execution: calls.append((phase, execution)),
        )
        check.equal(
            seat,
            [outcome.kind, len(calls)],
            ["vacuous", 0],
            "a budget of 0 seconds does not run a case",
        )

    def test_repeats_the_first_value_of_a_pool_member_in_many_mutated_cases(
        self, seat: Collector
    ) -> None:
        """More than 30% of the first values repeat."""

        def labelled(c: Case) -> None:
            n = c.draw(WIDE, "n")
            c.draw(WIDE, "m")
            c.classify(str(n))

        outcome, calls = explored(labelled, 400)
        check.equal(
            seat,
            [outcome.kind, repeated_share(firsts(calls)) > 0.3],
            ["passed", True],
            "more than 30% of the first values repeat",
        )

    def test_admits_a_case_that_records_a_new_fingerprint(
        self, seat: Collector
    ) -> None:
        """Mutated cases repeat the first value of a member."""

        def observing(c: Case) -> None:
            c.observe(c.draw(WIDE, "n") % 7)
            c.draw(WIDE, "m")

        _, calls = explored(observing, 200)
        check.is_true(
            seat,
            repeated_share(firsts(calls)) > 0,
            "mutated cases repeat the first value of a member",
        )

    def test_admits_a_case_that_records_a_score_above_the_best_of_its_label(
        self, seat: Collector
    ) -> None:
        """Mutated cases repeat the first value of a member."""

        def scoring(c: Case) -> None:
            c.target("size", float(c.draw(WIDE, "n") % 100))
            c.draw(WIDE, "m")

        _, calls = explored(scoring, 200)
        check.is_true(
            seat,
            repeated_share(firsts(calls)) > 0,
            "mutated cases repeat the first value of a member",
        )

    def test_mutates_every_kind_of_pool_member_into_a_valid_case(
        self, seat: Collector
    ) -> None:
        """Every case is valid."""
        generators = (DIGITS, UNIT, BYTES)
        calls = 0

        def mixed(c: Case) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                c.classify("nothing drawn")
                return
            n = c.random()
            c.classify(f"n{n % 1000}")
            index = n % 4
            if index < len(generators):
                c.draw(generators[index], "x")

        outcome, _ = explored(mixed, 2000)
        check.equal(
            seat,
            [outcome.kind, outcome.cases, outcome.rejected],
            ["passed", 2000, 0],
            "every case is valid",
        )

    def test_runs_the_known_cases_first(self, seat: Collector) -> None:
        """Four known cases run before two random cases."""
        outcome, calls = explored(
            plain,
            2,
            Settings(
                SEED,
                traces=((Draw("n", 1),),),
                examples=(recorded(5, 6), Values((7, 8))),
                stored=(recorded(3, 4),),
            ),
        )
        check.equal(
            seat,
            [[phase for phase, _ in calls], len(outcome.stored), outcome.cases],
            [["example", "example", "example", "stored", "random", "random"], 1, 6],
            "four known cases run before two random cases",
        )

    def test_goes_on_past_a_concluded_failure_until_its_budget_has_passed(
        self, seat: Collector
    ) -> None:
        """The campaign concludes one failure and runs 100 cases."""
        concluded: list[Outcome] = []
        outcome, calls = explored(high, 100, concluded=concluded.append)
        failing = outcome.failing
        check.equal(
            seat,
            [
                outcome.kind,
                None if failing is None else failing.case.draws[0].value,
                len(concluded),
                len([phase for phase, _ in calls if phase == "random"]),
            ],
            ["counterexample", HIGH + 1, 1, 100],
            "the campaign concludes one failure and runs 100 cases",
        )

    def test_reports_each_later_failure_of_another_identity_among_the_others(
        self, seat: Collector
    ) -> None:
        """The campaign concludes each identity once."""
        concluded: list[Outcome] = []

        def three(c: Case) -> None:
            n = c.draw(WIDE, "n")
            m = c.draw(WIDE, "m")
            if n > HIGH:
                c.fail("high n")
            if n == 0:
                c.fail("zero n")
            if m > HIGH:
                c.fail("high m")

        outcome, _ = explored(three, 300, concluded=concluded.append)
        identities = [
            execution.failure.identity
            for one in concluded
            for execution in (one.failing, *one.others)
            if execution is not None and execution.failure is not None
        ]
        reported = [
            execution.failure.identity
            for execution in (outcome.failing, *outcome.others)
            if execution is not None and execution.failure is not None
        ]
        check.equal(
            seat,
            [len(set(identities)) == len(identities), sorted(reported)],
            [True, ["high m", "high n", "zero n"]],
            "each identity is concluded once",
        )

    def test_returns_flaky_for_a_failure_whose_replay_passes(
        self, seat: Collector
    ) -> None:
        """The replay of the stored failure passes."""
        calls = 0

        def first(c: Case) -> None:
            nonlocal calls
            calls += 1
            c.draw(WIDE, "n")
            if calls == 1:
                c.fail("first")

        outcome, _ = explored(first, 10, Settings(SEED, stored=(recorded(5),)))
        divergence = outcome.divergence
        check.equal(
            seat,
            [
                outcome.kind,
                None if divergence is None else divergence.what,
                len(outcome.stored),
            ],
            ["flaky", "verdict", 1],
            "the outcome is flaky with a verdict divergence",
        )

    def test_returns_flaky_for_a_random_failure_whose_replay_passes(
        self, seat: Collector
    ) -> None:
        """Two valid cases run before the failure."""
        calls = 0

        def third(c: Case) -> None:
            nonlocal calls
            calls += 1
            c.draw(WIDE, "n")
            if calls == 3:
                c.fail("third")

        outcome, _ = explored(third, 10)
        check.equal(
            seat,
            [outcome.kind, outcome.cases],
            ["flaky", 2],
            "two valid cases run before the failure",
        )

    def test_reports_a_failing_example_of_values_as_found(
        self, seat: Collector
    ) -> None:
        """The counterexample is the value of the example."""
        outcome, _ = explored(high, 5, Settings(SEED, examples=(Values((HIGH + 9,)),)))
        failing = outcome.failing
        check.equal(
            seat,
            [
                outcome.kind,
                outcome.valued,
                None if failing is None else failing.case.draws[0].value,
            ],
            ["counterexample", True, HIGH + 9],
            "the counterexample is the value of the example",
        )

    def test_returns_rejected_for_a_campaign_that_rejects_every_case(
        self, seat: Collector
    ) -> None:
        """The body rejects every case."""

        def rejects(c: Case) -> None:
            c.draw(WIDE, "n")
            c.assume(False)

        outcome, _ = explored(rejects, 5)
        check.equal(seat, outcome.kind, "rejected", "the outcome is rejected")

    def test_returns_coverage_unmet_for_a_label_that_no_case_counted(
        self, seat: Collector
    ) -> None:
        """The shortfall has the label."""
        outcome, _ = explored(
            plain, 5, Settings(SEED, requirements=(Requirement("never", 0.5),))
        )
        shortfall = outcome.shortfall
        check.equal(
            seat,
            [
                outcome.kind,
                None if shortfall is None else shortfall.requirement.label,
            ],
            ["coverage-unmet", "never"],
            "the shortfall has the label",
        )

    def test_passes_a_requirement_that_every_case_meets(self, seat: Collector) -> None:
        """Every case counts the label."""

        def always(c: Case) -> None:
            c.draw(WIDE, "n")
            c.classify("always")

        outcome, _ = explored(
            always, 50, Settings(SEED, requirements=(Requirement("always", 0.5),))
        )
        check.equal(seat, outcome.kind, "passed", "every case counts the label")
