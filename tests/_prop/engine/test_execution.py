"""The spec of _prop/engine/execution.py tests the call of a body and how it ends."""

from __future__ import annotations

from dokimi_assert import check
from dokimi_assert._prop.engine.case import MAX_CHOICES, Case, Place, Replaying
from dokimi_assert._prop.engine.choice import Choice, IntegerBounds
from dokimi_assert._prop.engine.execution import (
    Body,
    Divergence,
    Execution,
    entered,
    execute,
    finish,
    identity_of,
    repeat,
    unobserved,
)
from dokimi_assert._prop.engine.tree import Tree
from dokimi_assert.seat import Collector
from helpers import Decoding, integers

DIGIT = IntegerBounds(0, 9)
BIT = IntegerBounds(0, 1)

#: A generator of one digit.
DIGITS = Decoding(lambda c: c.integer(DIGIT))

#: A generator of one bit.
BITS = Decoding(lambda c: c.integer(BIT))


def draws(c: Case) -> None:
    """Draw a digit and pass."""
    c.draw(DIGITS, "n")


def draws_two(c: Case) -> None:
    """Draw two digits and pass."""
    c.draw(DIGITS, "a")
    c.draw(DIGITS, "b")


def draws_a_bit(c: Case) -> None:
    """Draw a bit and pass."""
    c.draw(BITS, "b")


def repeating(runs: int) -> Body:
    """Return a body that draws a digit and sets the repeats of its case."""

    def body(c: Case) -> None:
        c.draw(DIGITS, "n")
        c.repeat(runs)

    return body


def fails_on_run(failing: int) -> Body:
    """Return a body that sets four repeats and fails on one of its calls.

    The calls of the body count from 1.
    """
    calls = 0

    def body(c: Case) -> None:
        nonlocal calls
        calls += 1
        c.draw(DIGITS, "n")
        c.repeat(4)
        if calls == failing:
            c.fail("broken")

    return body


def run(
    body: Body,
    choices: list[Choice] | None = None,
    tree: Tree | None = None,
    max_choices: int = MAX_CHOICES,
) -> Execution:
    """Return the execution of a body on recorded choices."""
    return execute(body, Replaying(choices or []), max_choices, tree)


class TestDivergence:
    """Divergence is the first difference between two runs of the same choices."""

    def test_defaults_the_label_and_the_step_to_none(self, seat: Collector) -> None:
        """A difference outside every draw and every machine has neither."""
        check.equal(
            seat,
            Divergence("verdict", 3, "a", None),
            Divergence("verdict", 3, "a", None, None, None),
            "the label and the step are None",
        )


class TestExecution:
    """Execution is one call of the body and how it ended."""

    def test_defaults_the_failure_the_divergence_the_overrun_and_the_stop(
        self, seat: Collector
    ) -> None:
        """The defaults describe a case that passed."""
        execution = Execution(Case(Replaying([])), "passed")
        check.equal(
            seat,
            (
                execution.failure,
                execution.divergence,
                execution.overran,
                execution.stopped,
            ),
            (None, None, False, None),
            "the defaults are those of a pass",
        )

    def test_counts_one_run_and_its_case_for_a_case_that_ran_once(
        self, seat: Collector
    ) -> None:
        """An execution without later runs has one case."""
        c = Case(Replaying([]))
        execution = Execution(c, "passed")
        check.equal(
            seat,
            [execution.ran, execution.runs, execution.cases],
            [(), 1, (c,)],
            "the execution has one run of one case",
        )

    def test_counts_each_run_of_a_case_that_ran_more_than_once(
        self, seat: Collector
    ) -> None:
        """An execution of two runs has the cases of both."""
        first = Case(Replaying([]))
        second = Case(Replaying([]))
        execution = Execution(first, "passed", ran=(first, second))
        check.equal(
            seat,
            [execution.runs, execution.cases],
            [2, (first, second)],
            "the execution has two runs",
        )


class TestExecute:
    """execute calls a body on a case."""

    def test_passes_a_body_that_returns(self, seat: Collector) -> None:
        """The case passes with its draw."""
        execution = run(draws, integers(4))
        check.equal(
            seat,
            [execution.status, execution.case.draws[0].value, identity_of(execution)],
            ["passed", 4, None],
            "the case passes with its draw",
        )

    def test_fails_a_body_that_fails_its_case_with_the_identity_of_the_failure(
        self, seat: Collector
    ) -> None:
        """The failure keeps its record."""
        execution = run(lambda c: c.fail("broken", "why"))
        failure = execution.failure
        check.equal(
            seat,
            [
                execution.status,
                identity_of(execution),
                None if failure is None else failure.record,
            ],
            ["failed", "broken", "why"],
            "the case fails with its identity and its record",
        )

    def test_rejects_a_body_that_assumes_false(self, seat: Collector) -> None:
        """A false assumption rejects the case."""
        execution = run(lambda c: c.assume(False))
        check.equal(seat, execution.status, "rejected", "the case is rejected")

    def test_rejects_a_case_past_its_cap_as_overran(self, seat: Collector) -> None:
        """Two draws exceed one choice."""
        execution = run(draws_two, max_choices=1)
        check.equal(
            seat,
            [execution.status, execution.overran],
            ["rejected", True],
            "the case overran its cap",
        )

    def test_rejects_a_case_past_its_cap_without_a_leaf(self, seat: Collector) -> None:
        """The first choice has a node, and no case ended there."""
        tree = Tree()
        run(draws_two, integers(5), tree, 1)
        check.is_none(seat, tree.root.children[5].ending, "the node is not a leaf")

    def test_raises_an_error_of_the_body_that_is_not_a_signal(
        self, seat: Collector
    ) -> None:
        """The caller receives the error of the body."""

        def breaks(_: Case) -> None:
            raise TypeError("the body broke")

        error = check.raises(seat, lambda: run(breaks), "the error propagates")
        check.error_as(seat, error, TypeError, "the error is the TypeError of the body")

    def test_stops_a_case_that_repeats_a_leaf_as_repeated(
        self, seat: Collector
    ) -> None:
        """The second case of the digit 4 repeats the first."""
        tree = Tree()
        run(draws, integers(4), tree)
        check.equal(
            seat,
            run(draws, integers(4), tree).status,
            "repeated",
            "the second case is repeated",
        )

    def test_stops_a_case_that_requests_other_bounds_as_diverged(
        self, seat: Collector
    ) -> None:
        """The first case draws a digit, and the second draws a bit."""
        tree = Tree()
        run(draws, [], tree)
        other = run(draws_a_bit, [], tree)
        check.equal(
            seat,
            [other.status, other.divergence],
            ["diverged", Divergence("request", 0, DIGIT, BIT, "b", None)],
            "the case diverges at the request",
        )

    def test_records_the_place_of_a_diverging_request(self, seat: Collector) -> None:
        """The divergence has the step of the machine that was running."""
        tree = Tree()
        run(draws, [], tree)

        def placed(c: Case) -> None:
            c.place = Place("sequential", 3)
            c.draw(BITS, "b")

        check.equal(
            seat,
            run(placed, [], tree).divergence,
            Divergence("request", 0, DIGIT, BIT, "b", Place("sequential", 3)),
            "the divergence has the step",
        )

    def test_stops_a_case_that_ends_where_another_drew_as_diverged(
        self, seat: Collector
    ) -> None:
        """The first case draws a digit, and the second ends without a choice."""
        tree = Tree()
        run(draws, [], tree)
        other = run(lambda _: None, [], tree)
        check.equal(
            seat,
            [other.status, other.divergence],
            ["diverged", Divergence("request", 0, DIGIT, None, None, None)],
            "the case diverges at its end",
        )

    def test_marks_the_leaf_of_a_case_with_how_it_ended(self, seat: Collector) -> None:
        """The leaf of a rejected case is rejected."""
        tree = Tree()

        def rejects(c: Case) -> None:
            c.draw(DIGITS, "n")
            c.assume(False)

        run(rejects, integers(3), tree)
        check.equal(
            seat, tree.root.children[3].ending, "rejected", "the leaf is rejected"
        )

    def test_runs_a_case_as_often_as_its_repeats(self, seat: Collector) -> None:
        """A case of three repeats runs three times."""
        execution = run(repeating(3), integers(4))
        check.equal(
            seat,
            [execution.runs, [c.draws[0].value for c in execution.cases]],
            [3, [4, 4, 4]],
            "each of the three runs replays the digit 4",
        )

    def test_runs_a_case_once_under_a_limit_of_one_run(self, seat: Collector) -> None:
        """A case of three repeats runs once."""
        execution = execute(repeating(3), Replaying(integers(4)), MAX_CHOICES, limit=1)
        check.equal(seat, execution.runs, 1, "the case runs once")


class TestFinish:
    """finish calls a body on a case that exists."""

    def test_runs_the_body_on_the_case_that_it_receives(self, seat: Collector) -> None:
        """The execution has the case that finish received."""
        c = Case(Replaying(integers(4)))
        execution = finish(draws, c)
        check.equal(
            seat,
            [execution.case is c, execution.status, c.draws[0].value],
            [True, "passed", 4],
            "the execution has the case and its draw",
        )

    def test_runs_the_body_again_for_a_case_of_two_repeats(
        self, seat: Collector
    ) -> None:
        """A case of two repeats runs twice."""
        c = Case(Replaying(integers(4)))
        execution = finish(repeating(2), c)
        check.equal(
            seat,
            [execution.runs, execution.cases[0] is c],
            [2, True],
            "the first of the two runs is the case",
        )


class TestRepeat:
    """repeat runs the body again on the choices of a case of more than one repeat."""

    def test_keeps_the_case_of_every_run_of_a_case_that_passes(
        self, seat: Collector
    ) -> None:
        """A case of four repeats passes four times."""
        first = execute(repeating(4), Replaying(integers(4)), MAX_CHOICES, limit=1)
        execution = repeat(first, repeating(4))
        check.equal(
            seat,
            [execution.status, execution.runs, execution.case is first.case],
            ["passed", 4, True],
            "the execution is the first run with the cases of four runs",
        )

    def test_ends_the_case_at_the_first_later_run_that_fails(
        self, seat: Collector
    ) -> None:
        """The second of four runs fails."""
        body = fails_on_run(2)
        first = execute(body, Replaying(integers(4)), MAX_CHOICES, limit=1)
        execution = repeat(first, body)
        check.equal(
            seat,
            [
                execution.status,
                identity_of(execution),
                execution.runs,
                execution.case is execution.cases[1],
            ],
            ["failed", "broken", 2, True],
            "the case ends at the second run with its record",
        )

    def test_does_not_run_a_failing_case_again(self, seat: Collector) -> None:
        """The first run fails."""
        body = fails_on_run(1)
        first = execute(body, Replaying(integers(4)), MAX_CHOICES, limit=1)
        check.is_true(seat, repeat(first, body) is first, "the execution is the run")

    def test_runs_at_most_the_limit(self, seat: Collector) -> None:
        """A case of four repeats has a limit of two."""
        first = execute(repeating(4), Replaying(integers(4)), MAX_CHOICES, limit=1)
        check.equal(seat, repeat(first, repeating(4), 2).runs, 2, "the case runs twice")


def ahead(
    body: Body, choices: list[Choice], max_choices: int = MAX_CHOICES
) -> Execution:
    """Return the execution of a body that runs outside the tree and keeps its walk."""
    return finish(body, Case(Replaying(choices), max_choices, walk=True))


def rejected_attempt(c: Case) -> None:
    """Draw a digit, remove it from the record, and draw another."""
    start = c.mark()
    c.draw(DIGITS, "attempt")
    c.rewind(start)
    c.draw(DIGITS, "kept")


class TestEntered:
    """entered walks a case that ran outside the case tree into the tree."""

    def test_enters_a_passing_case_as_a_leaf(self, seat: Collector) -> None:
        """The case takes one step and ends at its leaf."""
        tree = Tree()
        execution = ahead(draws, integers(4))
        got, steps = entered(tree, execution)
        check.equal(
            seat,
            [got is execution, steps, got.stopped, tree.root.children[4].ending],
            [True, 1, None, "passed"],
            "the case ends at its leaf",
        )

    def test_walks_a_choice_that_a_rewind_removed_from_the_record(
        self, seat: Collector
    ) -> None:
        """The case takes two steps for one recorded choice."""
        tree = Tree()
        _, steps = entered(tree, ahead(rejected_attempt, integers(4)))
        check.equal(
            seat,
            [steps, tree.root.children[4].children[4].ending],
            [2, "passed"],
            "the leaf is below both steps",
        )

    def test_stops_a_case_that_repeats_a_tested_case_at_its_step(
        self, seat: Collector
    ) -> None:
        """The first step arrives at a leaf."""
        tree = Tree()
        run(draws, integers(4), tree)
        got, steps = entered(tree, ahead(draws_two, integers(4, 5)))
        check.equal(
            seat,
            [got.status, steps, got.stopped],
            ["repeated", 1, 1],
            "the repeat stops the case at its first step",
        )

    def test_stops_a_case_at_a_request_that_differs_with_the_where_of_its_step(
        self, seat: Collector
    ) -> None:
        """The first case draws a digit, and the second draws a bit."""
        tree = Tree()
        run(draws, [], tree)
        got, steps = entered(tree, ahead(draws_a_bit, []))
        check.equal(
            seat,
            [got.status, got.divergence, steps, got.stopped],
            ["diverged", Divergence("request", 0, DIGIT, BIT, "b", None), 1, 1],
            "the case diverges at the request",
        )

    def test_diverges_a_case_that_ends_where_an_earlier_case_made_a_request(
        self, seat: Collector
    ) -> None:
        """The first case draws a digit, and the second ends without a choice."""
        tree = Tree()
        run(draws, [], tree)
        got, steps = entered(tree, ahead(lambda _: None, []))
        check.equal(
            seat,
            [got.status, got.divergence, steps, got.stopped],
            ["diverged", Divergence("request", 0, DIGIT, None, None, None), 0, None],
            "the case diverges at its end",
        )

    def test_does_not_add_a_leaf_for_a_case_past_its_cap(self, seat: Collector) -> None:
        """The first choice has a node, and no case ended there."""
        tree = Tree()
        got, steps = entered(tree, ahead(draws_two, integers(5), 1))
        check.equal(
            seat,
            [got.overran, steps, tree.root.children[5].ending],
            [True, 1, None],
            "the node is not a leaf",
        )

    def test_walks_the_first_run_of_a_case_whose_later_run_failed(
        self, seat: Collector
    ) -> None:
        """The first run passes, and the second run fails."""
        tree = Tree()
        execution = ahead(fails_on_run(2), integers(4))
        got, steps = entered(tree, execution)
        check.equal(
            seat,
            [got is execution, steps, tree.root.children[4].ending],
            [True, 1, "passed"],
            "the leaf of the first run is a pass",
        )

    def test_drops_the_later_runs_of_a_case_that_the_walk_stops(
        self, seat: Collector
    ) -> None:
        """The first step of a case of three runs arrives at a leaf."""
        tree = Tree()
        run(draws, integers(4), tree)
        got, _ = entered(tree, ahead(repeating(3), integers(4)))
        check.equal(
            seat,
            [got.status, got.ran],
            ["repeated", ()],
            "the stopped case does not keep its later runs",
        )


class TestIdentityOf:
    """identity_of returns the identity of the failure of an execution."""

    def test_returns_none_for_a_case_that_did_not_fail(self, seat: Collector) -> None:
        """A pass does not have an identity."""
        check.is_none(seat, identity_of(run(draws)), "the identity is None")


class TestUnobserved:
    """unobserved is the observer of a run that nobody records."""

    def test_accepts_any_call(self, seat: Collector) -> None:
        """The observer ignores the call."""
        execution = run(draws)
        check.does_not_raise(
            seat, lambda: unobserved("random", execution), "the call is accepted"
        )
