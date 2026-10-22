# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _history/spec.py tests the sequential specifications that a check reads.

The reference implementation of the definition takes the same steps for the
spec of a subject.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._history.spec import (
    CallOperation,
    Operation,
    same_state,
    spec_from,
    state_key,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from dokimi_assert.seat import Collector


@dataclass(frozen=True)
class Point:
    """A dataclass. The equality of the library compares it by its fields."""

    x: int


class Opaque:
    """A class that compares its instances with the == of object."""


def known(name: str, args: tuple[Any, ...], output: Any) -> Operation:
    """Return a known call of name with args and output."""
    return CallOperation(name, args, True, output)


def unknown(name: str, args: tuple[Any, ...]) -> Operation:
    """Return a call of name with args whose outcome is unknown."""
    return CallOperation(name, args, False)


@dataclass
class Counted:
    """The builds of the counter subject, and the calls that they applied."""

    built: int = 0
    applied: int = 0


def counters() -> tuple[Callable[[], Callable[[str, Sequence[Any]], Any]], Counted]:
    """Return a factory of counters, and the counts of its use.

    The add of a counter adds its argument and returns the new total.
    """
    counted = Counted()

    def factory() -> Callable[[str, Sequence[Any]], Any]:
        counted.built += 1
        total = [0]

        def apply(_: str, args: Sequence[Any]) -> int:
            counted.applied += 1
            total[0] += args[0]
            return total[0]

        return apply

    return factory, counted


def nested(leaf: int) -> object:
    """Return leaf inside 101 lists."""
    value: object = leaf
    for _ in range(101):
        value = [value]
    return value


class TestCallOperation:
    """CallOperation is the operation of a call as a spec receives it."""

    def test_keeps_the_fields_of_a_call(self, seat: Collector) -> None:
        """The write of 1 is known and returned None."""
        op = CallOperation("write", (1,), True, None)
        check.equal(
            seat,
            [op.name, op.args, op.known, op.output],
            ["write", (1,), True, None],
            "the operation keeps its fields",
        )

    def test_does_not_have_an_output_for_a_call_that_is_not_known(
        self, seat: Collector
    ) -> None:
        """A read that is not known does not set an output."""
        check.is_none(
            seat, CallOperation("read", (), False).output, "the output is None"
        )


class TestCallOperationReturned:
    """CallOperation.returned reports whether a call might have returned a value."""

    tests: ClassVar[list[tuple[str, Operation, Any, bool]]] = [
        ("the value of a known call", known("read", (), 3), 3, True),
        ("another value of a known call", known("read", (), 3), 4, False),
        (
            "an equal structure of a known call",
            known("read", (), {"a": [1]}),
            {"a": [1]},
            True,
        ),
        ("a value of another type", known("read", (), 3), 3.0, False),
        ("NaN of a known call", known("read", (), math.nan), math.nan, False),
        ("a value of a call that is not known", unknown("read", ()), 4, True),
    ]

    @pytest.mark.parametrize(
        ("op", "value", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_reports_whether_the_call_may_have_returned(
        self, seat: Collector, op: Operation, value: Any, want: bool
    ) -> None:
        """The method compares the value with the output of a known call."""
        check.equal(
            seat, op.returned(value), want, "returned gives the expected verdict"
        )


class TestStateKey:
    """state_key returns the default key of a state."""

    tests: ClassVar[list[tuple[str, object, object, bool]]] = [
        ("-0.0 and 0.0", -0.0, 0.0, True),
        ("NaN and NaN", math.nan, math.nan, True),
        (
            "two dicts of the same entries in another order",
            {1: "a", 2: "b"},
            {2: "b", 1: "a"},
            True,
        ),
        ("two sets of the same values in another order", {1, 2}, {2, 1}, True),
        ("two dataclasses of the same field", Point(1), Point(1), True),
        ("two objects that compare with their own ==", Opaque(), Opaque(), True),
        ("two values that differ below a depth of 100", nested(1), nested(2), True),
        ("an int and a str", 1, "1", False),
        ("an int and a float", 1, 1.0, False),
        ("a bool and an int", True, 1, False),
        ("None and False", None, False, False),
        ("two lists of other items", [1], [2], False),
        ("a list and a tuple", [1], (1,), False),
        ("a dataclass and a dict of its fields", Point(1), {"x": 1}, False),
        ("two dataclasses of other fields", Point(1), Point(2), False),
    ]

    @pytest.mark.parametrize(
        ("a", "b", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_compares_the_keys_of(
        self, seat: Collector, a: object, b: object, want: bool
    ) -> None:
        """The keys of two states are equal when the states are equal."""
        check.equal(
            seat,
            state_key(a) == state_key(b),
            want,
            "the keys are equal exactly for equal states",
        )

    def test_returns_a_key_of_a_state_that_contains_itself(
        self, seat: Collector
    ) -> None:
        """The cycle ends the walk."""
        cyclic: list[object] = []
        cyclic.append(cyclic)
        check.equal(
            seat, state_key(cyclic), (list, ("cycle",)), "the key marks the cycle"
        )


class TestSameState:
    """same_state compares two states as check.equal does without an option."""

    tests: ClassVar[list[tuple[str, object, object, bool]]] = [
        ("two equal structures", {"a": [1, 2]}, {"a": [1, 2]}, True),
        ("two structures of other values", {"a": [1]}, {"a": [2]}, False),
        ("NaN and NaN", math.nan, math.nan, False),
        ("-0.0 and 0.0", -0.0, 0.0, True),
    ]

    @pytest.mark.parametrize(
        ("a", "b", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_comparison_of(
        self, seat: Collector, a: object, b: object, want: bool
    ) -> None:
        """same_state returns True for equal states."""
        check.equal(
            seat, same_state(a, b), want, "same_state gives the expected verdict"
        )


class TestSpecFrom:
    """spec_from returns the spec of the sequential behaviour of a subject."""

    def test_starts_without_an_applied_call(self, seat: Collector) -> None:
        """The initial state is the empty tuple."""
        factory, _ = counters()
        check.equal(
            seat,
            spec_from(factory).initial(),
            (),
            "the initial state does not have a call",
        )

    def test_steps_a_state_by_a_replay_of_its_calls_on_a_fresh_subject(
        self, seat: Collector
    ) -> None:
        """A fresh counter replays two adds before the third."""
        factory, counted = counters()
        state = (unknown("add", (1,)), unknown("add", (2,)))
        following = spec_from(factory).next(state, known("add", (4,), 7))
        check.equal(
            seat,
            [following, counted],
            [[(*state, CallOperation("add", (4,), False))], Counted(1, 3)],
            "next builds one subject and applies three calls",
        )

    def test_rejects_a_call_whose_output_the_subject_does_not_return(
        self, seat: Collector
    ) -> None:
        """add(1) returns 1 on a fresh counter. The call returned 2."""
        factory, _ = counters()
        check.is_empty(
            seat,
            spec_from(factory).next((), known("add", (1,), 2)),
            "next rejects the output 2",
        )

    def test_accepts_a_call_whose_outcome_is_unknown(self, seat: Collector) -> None:
        """The call is applied and listed."""
        factory, counted = counters()
        following = spec_from(factory).next((), unknown("add", (1,)))
        check.equal(
            seat,
            [following, counted.applied],
            [[(CallOperation("add", (1,), False),)], 1],
            "the call is applied and listed",
        )

    def test_compares_states_by_their_calls_in_order(self, seat: Collector) -> None:
        """Two states are equal when they list the same calls in the same order."""
        factory, _ = counters()
        spec = spec_from(factory)
        a = unknown("add", (1,))
        b = unknown("add", (2,))
        check.equal(
            seat,
            [
                spec.equal((a, b), (unknown("add", (1,)), b)),
                spec.equal((a, b), (b, a)),
                spec.equal((a,), (a, b)),
                spec.equal((a,), (unknown("sub", (1,)),)),
            ],
            [True, False, False, False],
            "equal compares the calls in order",
        )

    def test_gives_two_equal_states_one_key(self, seat: Collector) -> None:
        """The two states list the same call."""
        factory, _ = counters()
        spec = spec_from(factory)
        check.equal(
            seat,
            spec.key((unknown("add", (1,)),)),
            spec.key((unknown("add", (1,)),)),
            "the two states have one key",
        )

    def test_counts_a_step_as_the_depth_of_its_state_plus_one(
        self, seat: Collector
    ) -> None:
        """A step from the empty state costs 1. A step from two calls costs 3."""
        factory, _ = counters()
        spec = spec_from(factory)
        check.equal(
            seat,
            [spec.cost(()), spec.cost((unknown("add", (1,)), unknown("add", (2,))))],
            [1, 3],
            "the costs are 1 and 3",
        )
