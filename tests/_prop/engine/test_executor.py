# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/executor.py tests the executors of a run.

A run on more than one worker reports the same outcome as a run on one, so
the spec checks each case of Ahead against the same case of Serial.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from dokimi_assert import check
from dokimi_assert._prop.engine.case import Case, Generating, Replaying
from dokimi_assert._prop.engine.choice import IntegerBounds
from dokimi_assert._prop.engine.edge import BOUNDARIES
from dokimi_assert._prop.engine.execution import Execution, execute
from dokimi_assert._prop.engine.executor import Ahead, Generated, Serial
from dokimi_assert._prop.engine.generator import Filter, Integer
from dokimi_assert._prop.engine.source import Source, case_source
from dokimi_assert._prop.engine.tree import Tree
from helpers import integers, refusal

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

SEED = 7
DIGIT = Integer(IntegerBounds(0, 9))
BIT = Integer(IntegerBounds(0, 1))

#: An even value of [0, 3]. The filter removes the odd attempts.
EVEN = Filter(Integer(IntegerBounds(0, 3)), lambda x: x % 2 == 0)

#: The choice cap of the cancellation test.
CAP = 2**18


def filtered(c: Case) -> None:
    """Draw an even value, then a bit when the value is 2.

    The domain is small, so random cases repeat. Many of them repeat after
    the filter has rejected attempts.
    """
    if c.draw(EVEN, "x") == 2:
        c.draw(BIT, "y")


def summary(execution: Execution) -> list[Any]:
    """Return the status of a case, its divergence and the choices of an ended case.

    The tree stops a case that repeats or diverges. The runner reads only
    the status and the divergence of such a case, so the summary leaves out
    its choices.
    """
    stopped = execution.status in ("repeated", "diverged")
    choices = None if stopped else execution.case.choices
    return [execution.status, execution.divergence, choices]


def scripted(executor: Serial | Ahead) -> list[list[Any]]:
    """Return the cases that an executor gives for a run in the order of one worker.

    The simplest case comes first. Each random case follows with its prefix
    case and the next edge case.
    """
    seen = [summary(executor.replay([]))]
    try:
        for index in range(12):
            generated = executor.random(index)
            source = generated.source
            seen.append([*summary(generated.execution), generated.choices])
            seen.append([source.next(), source.next()])
            seen.append(summary(executor.replay(generated.choices[:1])))
            if index < len(BOUNDARIES):
                seen.append(summary(executor.edge(index)))
    finally:
        executor.close()
    return seen


class TestGenerated:
    """Generated is a random case in the form that the runner takes."""

    def test_keeps_its_execution_its_choices_and_its_source(
        self, seat: Collector
    ) -> None:
        """Generated keeps the three fields."""
        execution = execute(filtered, Replaying([]), 8)
        source = Source(1)
        generated = Generated(execution, integers(0), source)
        check.equal(
            seat,
            [generated.execution is execution, generated.choices, generated.source],
            [True, integers(0), source],
            "Generated keeps its execution, its choices and its source",
        )


class TestSerialReplay:
    """Serial.replay runs the case of recorded choices into the tree."""

    def test_runs_the_case_of_the_choices_into_the_tree(self, seat: Collector) -> None:
        """The case ends at a leaf of the tree."""
        tree = Tree()
        execution = Serial(filtered, SEED, 8, tree).replay(integers(2, 1))
        check.equal(
            seat,
            [summary(execution), tree.root.children[2].children[1].ending],
            [["passed", None, integers(2, 1)], "passed"],
            "the case passes at its leaf",
        )


class TestSerialRandom:
    """Serial.random runs a random case of the seed into the tree."""

    def test_returns_the_case_with_its_choices_and_its_source_after_it(
        self, seat: Collector
    ) -> None:
        """The source resumes after the draws of the case."""
        generated = Serial(filtered, SEED, 8, Tree()).random(3)
        source = case_source(SEED, 3)
        twin = Case(Generating(source))
        filtered(twin)
        check.equal(
            seat,
            [generated.choices, generated.source.next()],
            [twin.choices, source.next()],
            "the source resumes after the choices",
        )


class TestSerialEdge:
    """Serial.edge runs the edge case of a boundary into the tree."""

    def test_runs_the_case_of_the_boundary_into_the_tree(self, seat: Collector) -> None:
        """The boundary max gives the largest digit."""

        def digit(c: Case) -> None:
            c.draw(DIGIT, "n")

        execution = Serial(digit, SEED, 8, Tree()).edge(BOUNDARIES.index("max"))
        check.equal(
            seat,
            execution.case.choices,
            integers(9),
            "the case takes the largest digit",
        )


class TestSerialClose:
    """Serial.close ends a run on one worker."""

    def test_returns_at_once(self, seat: Collector) -> None:
        """The executor does not start a thread."""
        check.does_not_raise(
            seat, Serial(filtered, SEED, 8, Tree()).close, "close returns"
        )


class TestAhead:
    """Ahead is the executor of a run on more than one worker."""

    def test_gives_every_case_that_serial_gives(self, seat: Collector) -> None:
        """The cases are the simplest, random, prefix and edge cases."""
        check.equal(
            seat,
            scripted(Ahead(filtered, SEED, 8, Tree(), 4)),
            scripted(Serial(filtered, SEED, 8, Tree())),
            "four workers give the same cases as one",
        )

    def test_raises_the_error_of_a_body_when_the_runner_takes_its_case(
        self, seat: Collector
    ) -> None:
        """The call for the case raises the error that the body raised."""

        def breaks(c: Case) -> None:
            del c
            msg = "the body broke"
            raise TypeError(msg)

        executor = Ahead(breaks, SEED, 8, Tree(), 2)
        try:
            refusal(seat, lambda: executor.random(0), TypeError)
        finally:
            executor.close()

    def test_runs_at_most_workers_cases_at_once(self, seat: Collector) -> None:
        """At most four cases run at once."""
        lock = threading.Lock()
        running = [0, 0]

        def counted(c: Case) -> None:
            with lock:
                running[0] += 1
                running[1] = max(running[1], running[0])
            try:
                c.draw(DIGIT, "n")
            finally:
                with lock:
                    running[0] -= 1

        scripted(Ahead(counted, SEED, 8, Tree(), 4))
        check.in_range(seat, running[1], 1, 4, "at most four cases ran at once")

    def test_ends_each_case_that_the_runner_did_not_take_at_its_next_choice(
        self, seat: Collector
    ) -> None:
        """Every case has ended at close. No case ran to its cap."""
        lock = threading.Lock()
        running = [0]
        longest = [0]

        def endless(c: Case) -> None:
            with lock:
                running[0] += 1
            choices = 0
            try:
                if c.draw(DIGIT, "n") == 0:
                    return
                while True:
                    c.integer(DIGIT.bounds)
                    choices += 1
            finally:
                with lock:
                    running[0] -= 1
                    longest[0] = max(longest[0], choices)

        executor = Ahead(endless, SEED, CAP, Tree(), 4)
        executor.edge(BOUNDARIES.index("min"))
        executor.close()
        check.equal(seat, running[0], 0, "no case runs after close")
        check.is_true(seat, longest[0] < CAP, "a case ends before its cap")
