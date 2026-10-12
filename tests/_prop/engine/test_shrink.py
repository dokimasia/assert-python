"""The spec of _prop/engine/shrink.py tests the replay, the shrink and the explanation.

The reference implementation of the definition computed the pinned results of
this spec on the same bodies and choices. The signal of a spent budget derives
from BaseException. The raises assertion does not catch it, so the spec
catches it with pytest.raises.
"""

from __future__ import annotations

import math
import time
from typing import Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.case import MAX_CHOICES, Case, Place, Replaying
from dokimi_assert._prop.engine.choice import (
    Choice,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
)
from dokimi_assert._prop.engine.collection import Sizes
from dokimi_assert._prop.engine.execution import (
    Body,
    Divergence,
    Execution,
    Phase,
    execute,
    unobserved,
)
from dokimi_assert._prop.engine.generator import (
    Bytes,
    Float,
    Integer,
    Just,
    List,
    Mapped,
    Recursive,
)
from dokimi_assert._prop.engine.shrink import (
    DEFAULT_BUDGET,
    Exhausted,
    Shrinker,
    confirm,
    explain,
    explain_seed,
    nodes_of,
)
from dokimi_assert._prop.engine.value import canonical
from dokimi_assert.seat import Collector
from helpers import Decoding, integers

DIGIT = Integer(IntegerBounds(0, 9))
WIDE = Integer(IntegerBounds(0, 1_000_000_000))
SMALL = Integer(IntegerBounds(0, 1000))
PERCENT = List(Integer(IntegerBounds(0, 100)), Sizes())
UNIT = Float(FloatBounds(0.0, 10.0))
SIGNED = Integer(IntegerBounds(-100, 100))
SIGNED_LIST = List(SIGNED, Sizes())
NESTED = List(List(DIGIT, Sizes()), Sizes())
POSITIVE = Integer(IntegerBounds(1, 1000))
SIGNED_FLOAT = Float(FloatBounds(-10.0, 10.0))
BYTES = Bytes(SequenceBounds(256))
PAIR_BYTES = Bytes(SequenceBounds(256, 2))
JUST = Just(7)
TREE: Recursive[Any] = Recursive(DIGIT, 100, lambda inner: List(inner, Sizes(0, 3)))
WIDE32 = Float(FloatBounds(0.0, 2.0**25, False, 32))
ANY_FLOAT = Float(FloatBounds(-math.inf, math.inf))
NARROW = Float(FloatBounds(2.6, 2.9))

#: The trees for which the body of the run of siblings fails. They are
#: [[9, 5]], [9, 5] and [9].
EXACT = {canonical([[9, 5]]), canonical([9, 5]), canonical([9])}


def seven(c: Case) -> int:
    """Return a digit, and reject the case unless the digit is 7."""
    value = DIGIT.decode(c)
    c.assume(value == 7)
    return value


#: A digit that rejects its case unless it is 7.
SEVEN = Decoding(seven)


def executed(body: Body, choices: list[Choice]) -> Execution:
    """Return the execution of a body on recorded choices."""
    return execute(body, Replaying(choices), MAX_CHOICES)


def shrunk(
    body: Body, choices: list[Choice], budget: int = DEFAULT_BUDGET, workers: int = 1
) -> Shrinker:
    """Return the shrinker of the failing case of choices after its shrink."""
    first = executed(body, choices)
    shrinker = Shrinker(body, first, MAX_CHOICES, budget, workers=workers)
    shrinker.shrink_all()
    return shrinker


#: The numbers of workers of a shrink. A run on four reports the same results
#: as a run on one.
WORKERS = pytest.mark.parametrize("workers", [1, 4], ids=["one worker", "four workers"])


def drawn(execution: Execution) -> list[Any]:
    """Return the values that the case of an execution drew."""
    return [one.value for one in execution.case.draws]


def contains(value: object, wanted: int) -> bool:
    """Report whether a nested list contains wanted anywhere."""
    if isinstance(value, list):
        items: list[object] = value
        return any(contains(item, wanted) for item in items)
    return value == wanted


def above(c: Case) -> None:
    """Fail when a wide integer is above 1000."""
    if c.draw(WIDE, "n") > 1000:
        c.fail("above")


def above_three_times(c: Case) -> None:
    """Set three repeats, and fail when a wide integer is above 1000."""
    c.repeat(3)
    above(c)


def first_above_ten(c: Case) -> None:
    """Fail when the first percentage of a list is above 10."""
    values = c.draw(PERCENT, "xs")
    if values and values[0] > 10:
        c.fail("first")


def sum_of_ten(c: Case) -> None:
    """Fail when a list of percentages sums to 10 or more."""
    if sum(c.draw(PERCENT, "xs")) >= 10:
        c.fail("ten")


def has_fifty(c: Case) -> None:
    """Fail when a list of percentages contains 50."""
    if 50 in c.draw(PERCENT, "xs"):
        c.fail("fifty")


def has_nine(c: Case) -> None:
    """Fail when a tree contains a 9."""
    if contains(c.draw(TREE, "tree"), 9):
        c.fail("nine")


def far(c: Case) -> None:
    """Fail when a signed integer is 2 or more away from 0, except for 2."""
    value = c.draw(SIGNED, "x")
    if (value >= 2 or value <= -2) and value != 2:
        c.fail("far")


def not_its_reverse(c: Case) -> None:
    """Fail when a list of signed integers differs from its reverse."""
    values = c.draw(SIGNED_LIST, "xs")
    if values != values[::-1]:
        c.fail("reverse")


def mixed(c: Case) -> None:
    """Fail when the lists of a list contain two different digits."""
    if len({value for values in c.draw(NESTED, "xss") for value in values}) >= 2:
        c.fail("mixed")


def one_apart(c: Case) -> None:
    """Fail when two positive integers one apart start at 10 or more."""
    x = c.draw(POSITIVE, "x")
    y = c.draw(POSITIVE, "y")
    if x >= 10 and abs(x - y) == 1:
        c.fail("one")


def spread(c: Case) -> None:
    """Fail when the second signed integer is 7 or more above the first."""
    x = c.draw(SIGNED, "x")
    if c.draw(SIGNED, "y") - x >= 7:
        c.fail("spread")


def float_then_above(c: Case) -> None:
    """Draw an unrelated float, then fail in the same way as above."""
    c.draw(UNIT, "v")
    if c.draw(WIDE, "n") > 1000:
        c.fail("above")


def high_byte(c: Case) -> None:
    """Fail when a byte string contains a byte above 200."""
    if any(byte > 200 for byte in c.draw(BYTES, "b")):
        c.fail("high")


def count_with_items(c: Case) -> None:
    """Fail when a count of 2 or more draws items that end in 9."""
    count = c.draw(DIGIT, "count")
    items = [c.draw(DIGIT, "item") for _ in range(count)]
    if count >= 2 and items[-1] == 9:
        c.fail("nine")


def count_with_list(c: Case) -> None:
    """Fail when the list that a count sizes contains 9."""
    count = c.draw(DIGIT, "count")
    if 9 in c.draw(List(DIGIT, Sizes(count, count)), "xs"):
        c.fail("nine")


def indexed(c: Case) -> None:
    """Fail when the percentage at an index drawn after the list is above 50."""
    values = c.draw(PERCENT, "xs")
    index = c.draw(DIGIT, "i")
    if index < len(values) and values[index] > 50:
        c.fail("indexed")


def byte_indexed(c: Case) -> None:
    """Fail when the byte at an index drawn after the bytes is above 200."""
    value = c.draw(BYTES, "b")
    index = c.draw(DIGIT, "i")
    if index < len(value) and value[index] > 200:
        c.fail("high")


def pair_byte_indexed(c: Case) -> None:
    """Fail in the same way as byte_indexed over bytes of at least two."""
    value = c.draw(PAIR_BYTES, "b")
    index = c.draw(DIGIT, "i")
    if index < len(value) and value[index] > 200:
        c.fail("high")


def just_then_above(c: Case) -> None:
    """Fail when an integer drawn after a just is above 50."""
    c.draw(JUST, "j")
    if c.draw(SMALL, "n") > 50:
        c.fail("above")


def both(c: Case) -> None:
    """Fail when a list of percentages contains 3 and 5."""
    values = c.draw(PERCENT, "xs")
    if 3 in values and 5 in values:
        c.fail("both")


def sum_above(c: Case) -> None:
    """Fail when the sum of two integers is above 500."""
    if c.draw(SMALL, "x") + c.draw(SMALL, "y") > 500:
        c.fail("sum")


def equal(c: Case) -> None:
    """Fail when two integers are equal and above 0."""
    x = c.draw(SMALL, "x")
    if x == c.draw(SMALL, "y") and x > 0:
        c.fail("equal")


def equal_beside_another(c: Case) -> None:
    """Fail in the same way as equal with an unrelated third integer."""
    x = c.draw(SMALL, "x")
    y = c.draw(SMALL, "y")
    c.draw(SMALL, "z")
    if x == y and x > 0:
        c.fail("equal")


def fraction(c: Case) -> None:
    """Fail when a float above 2.5 is not an integer."""
    value = c.draw(UNIT, "v")
    if value > 2.5 and not value.is_integer():
        c.fail("fraction")


def bigger(c: Case) -> None:
    """Fail when a float is above 2.5."""
    if c.draw(UNIT, "v") > 2.5:
        c.fail("bigger")


def large(c: Case) -> None:
    """Fail when a signed float is 3 or more away from 0."""
    if abs(c.draw(SIGNED_FLOAT, "v")) >= 3:
        c.fail("large")


def big32(c: Case) -> None:
    """Fail when a float of width 32 is 2^24 + 2 or more."""
    if c.draw(WIDE32, "v") >= 2**24 + 2:
        c.fail("big")


def same_floats(c: Case) -> None:
    """Fail when two floats are equal and above 1."""
    x = c.draw(UNIT, "x")
    if x == c.draw(UNIT, "y") and x > 1:
        c.fail("same")


def same_bytes(c: Case) -> None:
    """Fail when two byte strings are equal and not empty."""
    x = c.draw(BYTES, "x")
    y = c.draw(BYTES, "y")
    if len(x) > 0 and x == y:
        c.fail("same")


def infinite(c: Case) -> None:
    """Fail when a float is positive infinity."""
    if c.draw(ANY_FLOAT, "v") == math.inf:
        c.fail("infinite")


def negative_fraction(c: Case) -> None:
    """Fail when a float below -2.5 is not an integer."""
    value = c.draw(SIGNED_FLOAT, "v")
    if value < -2.5 and not value.is_integer():
        c.fail("fraction")


def narrow(c: Case) -> None:
    """Fail when a float in [2.6, 2.9] is above 2.8."""
    if c.draw(NARROW, "v") > 2.8:
        c.fail("narrow")


def two_justs_then_above(c: Case) -> None:
    """Fail when an integer drawn after two justs is above 50."""
    c.draw(JUST, "j")
    c.draw(JUST, "k")
    if c.draw(SMALL, "n") > 50:
        c.fail("above")


def negative_one_apart(c: Case) -> None:
    """Fail when two signed integers one apart start at -10 or less."""
    x = c.draw(SIGNED, "x")
    y = c.draw(SIGNED, "y")
    if x <= -10 and abs(x - y) == 1:
        c.fail("one")


def exact(c: Case) -> None:
    """Fail for the trees [[9, 5]], [9, 5] and [9]."""
    if canonical(c.draw(TREE, "tree")) in EXACT:
        c.fail("exact")


def bytes_then_above(c: Case) -> None:
    """Draw a byte string, then fail in the same way as above."""
    c.draw(BYTES, "b")
    if c.draw(WIDE, "n") > 1000:
        c.fail("above")


def capped_sum(c: Case) -> None:
    """Fail when the sum of two integers is above 500 and the second is 400 or less."""
    x = c.draw(SMALL, "x")
    y = c.draw(SMALL, "y")
    if x + y > 500 and y <= 400:
        c.fail("sum")


def length_after_bytes(c: Case) -> None:
    """Fail when a digit after bytes that are not empty equals their length."""
    value = c.draw(BYTES, "b")
    if len(value) >= 1 and c.draw(DIGIT, "i") == len(value):
        c.fail("length")


def any_bigger(c: Case) -> None:
    """Fail when a float of any value is above 2.5."""
    if c.draw(ANY_FLOAT, "v") > 2.5:
        c.fail("bigger")


def noisy(c: Case) -> None:
    """Fail in the same way as above with an unrelated second wide integer."""
    value = c.draw(WIDE, "n")
    c.draw(WIDE, "noise")
    if value > 1000:
        c.fail("above")


def always_seven(c: Case) -> None:
    """Draw a seven and fail."""
    c.draw(SEVEN, "seven")
    c.fail("always")


class TestDefaultBudget:
    """DEFAULT_BUDGET is the number of runs that a shrink can spend."""

    def test_allows_2000_runs(self, seat: Collector) -> None:
        """The definition sets a budget of 2000 runs."""
        check.equal(seat, DEFAULT_BUDGET, 2000, "the budget is 2000 runs")


class TestExhausted:
    """Exhausted is the signal of a spent budget."""

    def test_returns_the_signal_of_a_spent_budget(self, seat: Collector) -> None:
        """A body that catches Exception does not catch the signal."""
        signal = Exhausted()
        check.equal(
            seat,
            str(signal),
            "prop: the shrink budget is spent",
            "the signal has its text",
        )
        check.is_false(
            seat, isinstance(signal, Exception), "the signal is not an Exception"
        )


class TestNodesOf:
    """nodes_of returns the choices of a case with their requests."""

    def test_returns_each_choice_of_a_case_with_its_request(
        self, seat: Collector
    ) -> None:
        """The case has one node."""
        execution = executed(above, integers(2000))
        node = nodes_of(execution.case)[0]
        check.equal(
            seat,
            [node.choice, node.request is execution.case.requests[0]],
            [Choice("integer", 2000), True],
            "the node has the choice and its request",
        )


class TestExplainSeed:
    """explain_seed returns the seed of a filling of a draw."""

    def test_returns_the_seed_plus_the_shifted_draw_plus_the_filling_modulo_2_64(
        self, seat: Collector
    ) -> None:
        """The last of three seeds wraps past 2^64."""
        check.equal(
            seat,
            [
                explain_seed(7, 0, 0),
                explain_seed(7, 2, 3),
                explain_seed(2**64 - 1, 0, 1),
            ],
            [7 + 2**32, 7 + 3 * 2**32 + 3, 2**32],
            "the seeds follow the formula",
        )


class TestConfirm:
    """confirm replays a failing case before its shrink."""

    def test_returns_none_for_a_replay_that_fails_in_the_same_way(
        self, seat: Collector
    ) -> None:
        """2000 fails each time."""
        failing = executed(above, integers(2000))
        check.is_none(
            seat, confirm(above, failing, MAX_CHOICES), "the replay does not diverge"
        )

    def test_returns_a_verdict_divergence_for_a_replay_that_passes(
        self, seat: Collector
    ) -> None:
        """The divergence compares the identity with a pass."""
        calls = 0

        def once(c: Case) -> None:
            nonlocal calls
            calls += 1
            c.place = Place("settle")
            c.draw(WIDE, "n")
            if calls == 1:
                c.fail("once")

        check.equal(
            seat,
            confirm(once, executed(once, integers(5)), MAX_CHOICES),
            Divergence("verdict", 1, "once", None),
            "the divergence compares the identity with a pass",
        )

    def test_returns_a_request_divergence_with_the_label_and_the_step_of_the_replay(
        self, seat: Collector
    ) -> None:
        """The first request diverges."""
        calls = 0

        def shifting(c: Case) -> None:
            nonlocal calls
            calls += 1
            c.place = Place("sequential", 1, "put")
            c.draw(WIDE if calls == 1 else SMALL, "n")
            c.fail("always")

        check.equal(
            seat,
            confirm(shifting, executed(shifting, integers(5)), MAX_CHOICES),
            Divergence(
                "request",
                0,
                WIDE.bounds,
                SMALL.bounds,
                "n",
                Place("sequential", 1, "put"),
            ),
            "the first request diverges",
        )

    def test_returns_a_request_divergence_without_a_label_for_a_replay_that_ends_first(
        self, seat: Collector
    ) -> None:
        """The replay does not make a request at the position."""
        calls = 0

        def shortening(c: Case) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                c.draw(WIDE, "n")
            c.fail("always")

        check.equal(
            seat,
            confirm(shortening, executed(shortening, integers(5)), MAX_CHOICES),
            Divergence("request", 0, WIDE.bounds, None, None, None),
            "the replay does not make a request at the position",
        )

    def test_returns_a_fingerprint_divergence_with_the_step_of_the_replay(
        self, seat: Collector
    ) -> None:
        """The fingerprints 1 and 2 differ."""
        calls = 0

        def observing(c: Case) -> None:
            nonlocal calls
            calls += 1
            c.draw(WIDE, "n")
            c.place = Place("drain", 0, "flush")
            c.observe(calls)
            c.fail("always")

        check.equal(
            seat,
            confirm(observing, executed(observing, integers(5)), MAX_CHOICES),
            Divergence("fingerprint", 0, 1, 2, None, Place("drain", 0, "flush")),
            "the fingerprints 1 and 2 differ",
        )

    def test_returns_a_fingerprint_divergence_without_a_step_for_a_missing_fingerprint(
        self, seat: Collector
    ) -> None:
        """The replay does not observe a fingerprint."""
        calls = 0

        def once(c: Case) -> None:
            nonlocal calls
            calls += 1
            c.draw(WIDE, "n")
            if calls == 1:
                c.observe(1)
            c.fail("always")

        check.equal(
            seat,
            confirm(once, executed(once, integers(5)), MAX_CHOICES),
            Divergence("fingerprint", 0, 1, None, None, None),
            "the replay does not observe the fingerprint",
        )

    def test_returns_none_for_a_replay_that_observes_the_same_fingerprints(
        self, seat: Collector
    ) -> None:
        """Each run observes two fingerprints."""

        def observing(c: Case) -> None:
            c.observe(c.draw(WIDE, "n") % 7)
            c.observe(3)
            c.fail("always")

        failing = executed(observing, integers(5))
        check.is_none(
            seat,
            confirm(observing, failing, MAX_CHOICES),
            "the replay does not diverge",
        )

    def test_passes_the_replay_to_the_observer_under_the_phase_replay(
        self, seat: Collector
    ) -> None:
        """The observer receives one replay."""
        phases: list[Phase] = []
        confirm(
            above,
            executed(above, integers(2000)),
            MAX_CHOICES,
            lambda phase, _: phases.append(phase),
        )
        check.equal(seat, phases, ["replay"], "the observer receives one replay")

    def test_runs_the_replay_up_to_the_repeats_of_the_case(
        self, seat: Collector
    ) -> None:
        """Every third run of the body fails, and the case has three repeats."""
        calls = 0
        replays: list[Execution] = []

        def third(c: Case) -> None:
            nonlocal calls
            calls += 1
            c.repeat(3)
            c.draw(WIDE, "n")
            if calls % 3 == 0:
                c.fail("third")

        failing = executed(third, integers(5))
        divergence = confirm(
            third, failing, MAX_CHOICES, lambda _, replay: replays.append(replay)
        )
        check.equal(
            seat,
            [divergence, replays[0].runs],
            [None, 3],
            "the third run of the replay fails in the same way",
        )


class TestShrinkerRun:
    """Shrinker.run runs the body once and counts the run against the budget."""

    def test_passes_each_run_of_the_budget_to_the_observer(
        self, seat: Collector
    ) -> None:
        """The observer receives one run under its phase."""
        phases: list[Phase] = []
        shrinker = Shrinker(
            above,
            executed(above, integers(2000)),
            MAX_CHOICES,
            1,
            lambda phase, _: phases.append(phase),
        )
        execution = shrinker.run(integers(5), "explain")
        check.equal(
            seat,
            [execution.status, shrinker.runs, phases],
            ["passed", 1, ["explain"]],
            "the observer receives one run under its phase",
        )

    def test_raises_exhausted_once_the_budget_is_spent(self, seat: Collector) -> None:
        """No run is left."""
        shrinker = Shrinker(above, executed(above, integers(2000)), MAX_CHOICES, 0)
        with pytest.raises(Exhausted):
            shrinker.run(integers(5))
        check.equal(seat, shrinker.runs, 0, "the shrinker did not run")

    def test_raises_exhausted_once_the_time_is_spent(self, seat: Collector) -> None:
        """The deadline is the smallest float after the start."""
        shrinker = Shrinker(
            above,
            executed(above, integers(2000)),
            MAX_CHOICES,
            10,
            unobserved,
            math.ulp(0.0),
        )
        start = time.monotonic()
        moved = False
        while not moved:
            moved = time.monotonic() > start
        with pytest.raises(Exhausted):
            shrinker.run(integers(5))
        check.equal(seat, shrinker.runs, 0, "the shrinker did not run")

    def test_runs_the_repeats_of_a_case_and_counts_each_run(
        self, seat: Collector
    ) -> None:
        """A case of three repeats passes."""
        phases: list[Phase] = []
        shrinker = Shrinker(
            above_three_times,
            executed(above_three_times, integers(2000)),
            MAX_CHOICES,
            10,
            lambda phase, _: phases.append(phase),
        )
        execution = shrinker.run(integers(5))
        check.equal(
            seat,
            [execution.runs, shrinker.runs, phases],
            [3, 3, ["shrink"]],
            "the shrinker counts three runs and passes the case to the observer once",
        )

    def test_runs_at_most_the_room_of_the_budget(self, seat: Collector) -> None:
        """A case of three repeats has room for two runs."""
        shrinker = Shrinker(
            above_three_times,
            executed(above_three_times, integers(2000)),
            MAX_CHOICES,
            2,
        )
        execution = shrinker.run(integers(5))
        check.equal(
            seat,
            [execution.runs, shrinker.runs],
            [2, 2],
            "the run stops at the end of the budget",
        )


class TestShrinkerRunEach:
    """Shrinker.run_each runs the body on each choice sequence of a batch."""

    def test_raises_exhausted_when_the_runs_of_a_case_spend_the_room_of_the_batch(
        self, seat: Collector
    ) -> None:
        """The first case of a batch of two takes the three runs of the budget."""
        shrinker = Shrinker(
            above_three_times,
            executed(above_three_times, integers(2000)),
            MAX_CHOICES,
            3,
        )
        taken: list[Execution] = []
        with pytest.raises(Exhausted):
            taken.extend(shrinker.run_each([integers(5), integers(6)]))
        check.equal(
            seat,
            [len(taken), shrinker.runs],
            [1, 3],
            "the batch yields the first case alone",
        )


class TestShrinkerShrinkAll:
    """Shrinker.shrink_all finds the smallest case of every failure of a run."""

    tests: ClassVar[list[tuple[str, Body, list[Choice], list[Any], int]]] = [
        ("an integer to the boundary by bisection", above, integers(2000), [1001], 21),
        (
            "a list to its first element when only that element matters",
            first_above_ten,
            integers(1, 50, *[1, 3] * 7, 0),
            [[11]],
            21,
        ),
        (
            "a list to the smallest sum of 10",
            sum_of_ten,
            integers(1, 9, 1, 1, 1, 2, 1, 9, 0),
            [[10]],
            38,
        ),
        (
            "a list to the one element that fails",
            has_fifty,
            integers(1, 3, 1, 50, 0),
            [[50]],
            18,
        ),
        (
            "a tree to the subtree that contains a 9",
            has_nine,
            integers(1, 1, 0, 9, 0),
            [9],
            12,
        ),
        (
            "an integer across its target to a nearer value",
            far,
            integers(3),
            [-2],
            5,
        ),
        (
            "a list that is not its reverse to [0, 1]",
            not_its_reverse,
            integers(1, 0, 1, -1, 0),
            [[0, 1]],
            24,
        ),
        (
            "two lists to one list of two values",
            mixed,
            integers(1, 1, 1, 0, 1, 1, 2, 0, 0),
            [[[0, 1]]],
            36,
        ),
        (
            "two integers one apart to the smallest pair",
            one_apart,
            integers(36, 37),
            [10, 9],
            56,
        ),
        (
            "values on both sides of the target to themselves",
            spread,
            integers(-3, 4),
            [-3, 4],
            14,
        ),
        (
            "an unrelated float to its target",
            float_then_above,
            [Choice("float", 3.75), Choice("integer", 2000)],
            [0.0, 1001],
            27,
        ),
        (
            "a byte string to its one high byte",
            high_byte,
            [Choice("sequence", (1, 250, 3, 4))],
            [bytes([201])],
            20,
        ),
        (
            "a count with its items",
            count_with_items,
            integers(3, 0, 0, 9),
            [2, 0, 9],
            32,
        ),
        (
            "a count with the list that it sizes",
            count_with_list,
            integers(3, 1, 0, 1, 0, 1, 9, 0),
            [1, [9]],
            41,
        ),
        (
            "an index into an earlier list",
            indexed,
            integers(1, 0, 1, 60, 0, 1),
            [[51], 0],
            62,
        ),
        (
            "an index into earlier bytes",
            byte_indexed,
            [Choice("sequence", (1, 250)), Choice("integer", 1)],
            [bytes([201]), 0],
            40,
        ),
        (
            "an index into earlier bytes of at least two",
            pair_byte_indexed,
            [Choice("sequence", (1, 250)), Choice("integer", 1)],
            [bytes([0, 201]), 1],
            23,
        ),
        (
            "an integer after a just",
            just_then_above,
            integers(60),
            [7, 51],
            13,
        ),
        (
            "the elements of a multiset in sorted order",
            both,
            integers(1, 5, 1, 3, 0),
            [[3, 5]],
            47,
        ),
        (
            "a sum of two integers onto the second",
            sum_above,
            integers(300, 300),
            [0, 501],
            37,
        ),
        (
            "two equal integers together",
            equal,
            integers(400, 400),
            [1, 1],
            55,
        ),
        (
            "two equal integers together beside an unrelated one",
            equal_beside_another,
            integers(400, 400, 7),
            [1, 1, 0],
            70,
        ),
        (
            "a fraction to fewer fractional bits",
            fraction,
            [Choice("float", 2.875)],
            [2.75],
            6,
        ),
        (
            "a fraction away from its target to an integer",
            bigger,
            [Choice("float", 2.875)],
            [3.0],
            5,
        ),
        (
            "an integral float as an integer",
            bigger,
            [Choice("float", 9.0)],
            [3.0],
            6,
        ),
        (
            "an integral float in infinite bounds as an integer",
            any_bigger,
            [Choice("float", 9.0)],
            [3.0],
            11,
        ),
        (
            "a negative integral float above zero",
            large,
            [Choice("float", -9.0)],
            [3.0],
            8,
        ),
        (
            "a float of width 32 past the integers that are not values of the width",
            big32,
            [Choice("float", 2.0**25)],
            [2.0**24 + 2],
            49,
        ),
        (
            "two equal floats that must remain equal to themselves",
            same_floats,
            [Choice("float", 5.5), Choice("float", 5.5)],
            [5.5, 5.5],
            9,
        ),
        (
            "two equal byte strings that must remain equal to themselves",
            same_bytes,
            [Choice("sequence", (7, 9)), Choice("sequence", (7, 9))],
            [bytes([7, 9]), bytes([7, 9])],
            27,
        ),
        (
            "an infinite float to itself",
            infinite,
            [Choice("float", math.inf)],
            [math.inf],
            2,
        ),
        (
            "a negative fraction to fewer fractional bits",
            negative_fraction,
            [Choice("float", -2.875)],
            [-2.75],
            6,
        ),
        (
            "a fraction whose roundings leave its bounds to itself",
            narrow,
            [Choice("float", 2.875)],
            [2.875],
            2,
        ),
        (
            "an integer after two empty spans",
            two_justs_then_above,
            integers(60),
            [7, 7, 51],
            13,
        ),
        (
            "two negative integers one apart towards their target together",
            negative_one_apart,
            integers(-36, -37),
            [-10, -11],
            54,
        ),
        (
            "a tree to its one leaf of 9 by deleting a run of siblings",
            exact,
            integers(1, 1, 1, 1, 0, 9, 1, 0, 5, 0, 0),
            [[9]],
            41,
        ),
        (
            "an integer after an empty byte string",
            bytes_then_above,
            [Choice("sequence", ()), Choice("integer", 2000)],
            [b"", 1001],
            25,
        ),
        (
            "a sum of two integers onto the second up to its cap",
            capped_sum,
            integers(300, 300),
            [101, 400],
            53,
        ),
        (
            "bytes and a digit that equals their length to one zero byte",
            length_after_bytes,
            [Choice("sequence", (3, 4)), Choice("integer", 2)],
            [bytes([0]), 1],
            21,
        ),
    ]

    @WORKERS
    @pytest.mark.parametrize(
        ("body", "choices", "want", "runs"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_shrinks(
        self,
        seat: Collector,
        body: Body,
        choices: list[Choice],
        want: list[Any],
        runs: int,
        workers: int,
    ) -> None:
        """The smallest case and its runs are the same on one worker and on four."""
        shrinker = shrunk(body, choices, workers=workers)
        check.equal(
            seat,
            [drawn(shrinker.best.execution), shrinker.runs],
            [want, runs],
            "the smallest case and its runs",
        )

    def test_shrinks_the_choices_of_a_body_that_draws_through_the_random_source_alone(
        self, seat: Collector
    ) -> None:
        """The shrink finds 1001 in 22 runs."""

        def random_above(c: Case) -> None:
            if c.random() > 1000:
                c.fail("above")

        shrinker = shrunk(random_above, integers(5000))
        check.equal(
            seat,
            [shrinker.best.execution.case.choices, shrinker.runs],
            [integers(1001), 22],
            "the shrink finds 1001 in 22 runs",
        )

    def test_shrinks_the_failure_with_the_smallest_case_first(
        self, seat: Collector
    ) -> None:
        """The shrinker shrinks each of three identities."""

        def three(c: Case) -> None:
            x = c.draw(SMALL, "x")
            y = c.draw(SMALL, "y")
            if y == 0 and x >= 100:
                c.fail("p")
            if x == 75:
                c.fail("q")
            if x >= 100 and y >= 100:
                c.fail("a")

        shrinker = shrunk(three, integers(150, 150))
        check.equal(
            seat,
            [
                [[i, drawn(f.execution)] for i, f in shrinker.failures.items()],
                shrinker.runs,
            ],
            [[["a", [100, 100]], ["p", [100, 0]], ["q", [75, 0]]], 76],
            "each identity is shrunk",
        )

    def test_shrinks_the_first_found_failure_first_when_its_case_is_the_smallest(
        self, seat: Collector
    ) -> None:
        """The budget ends before the shrink of half."""

        def spots(c: Case) -> None:
            x = c.draw(SMALL, "x")
            y = c.draw(SMALL, "y")
            if x > 800 and y > 300:
                c.fail("big")
            if x == 0 and y >= 1:
                c.fail("zero")
            if x == 450:
                c.fail("half")

        shrinker = shrunk(spots, integers(900, 500), 68)
        check.equal(
            seat,
            [[i, drawn(f.execution)] for i, f in shrinker.failures.items()],
            [["big", [801, 301]], ["zero", [0, 1]], ["half", [450, 500]]],
            "the budget ends before the shrink of half",
        )

    def test_keeps_a_failure_of_another_identity_that_a_candidate_finds(
        self, seat: Collector
    ) -> None:
        """The shrinker shrinks both identities."""

        def two(c: Case) -> None:
            value = c.draw(SMALL, "x")
            if value % 2 == 1:
                c.fail("odd")
            if value > 50:
                c.fail("big")

        shrinker = shrunk(two, integers(78))
        check.equal(
            seat,
            [
                list(shrinker.failures),
                drawn(shrinker.failures["big"].execution),
                drawn(shrinker.failures["odd"].execution),
            ],
            [["big", "odd"], [52], [1]],
            "both identities are shrunk",
        )

    def test_stops_at_a_spent_budget_with_the_smallest_case_found(
        self, seat: Collector
    ) -> None:
        """The shrink stops after ten runs at a case above the minimum."""
        shrinker = shrunk(above, integers(2000), 10)
        check.equal(
            seat,
            [shrinker.runs, drawn(shrinker.best.execution)[0] > 1001],
            [10, True],
            "the shrink stops after ten runs above the minimum",
        )

    budgets: ClassVar[list[tuple[str, int]]] = [
        ("spends a budget of 1 run in the same way as one worker", 1),
        ("spends a budget of 3 runs in the same way as one worker", 3),
        ("spends a budget of 6 runs in the same way as one worker", 6),
        ("spends a budget of 13 runs in the same way as one worker", 13),
    ]

    @pytest.mark.parametrize(
        "budget", [t[1] for t in budgets], ids=[t[0] for t in budgets]
    )
    def test_spends_on_four_workers_the_runs_of_one_worker(
        self, seat: Collector, budget: int
    ) -> None:
        """A batch past the budget stops where one worker stops."""
        choices = integers(1, 50, *[1, 3] * 7, 0)
        one = shrunk(first_above_ten, choices, budget)
        four = shrunk(first_above_ten, choices, budget, 4)
        check.equal(
            seat,
            [four.runs, drawn(four.best.execution)],
            [one.runs, drawn(one.best.execution)],
            "four workers spend the same runs and find the same case as one",
        )

    def test_raises_an_error_of_the_body_that_is_not_a_signal(
        self, seat: Collector
    ) -> None:
        """The error of the body propagates."""
        calls = 0

        def breaking(c: Case) -> None:
            nonlocal calls
            calls += 1
            if calls > 1:
                raise TypeError("the body broke")
            c.draw(WIDE, "n")
            c.fail("first")

        shrinker = Shrinker(breaking, executed(breaking, integers(5)), MAX_CHOICES, 10)
        error = check.raises(seat, shrinker.shrink_all, "the body raises")
        check.error_as(seat, error, TypeError, "the error is the TypeError of the body")


def explained(
    body: Body,
    choices: list[Choice],
    seed: int,
    budget: int = DEFAULT_BUDGET,
    workers: int = 1,
) -> tuple[list[list[Any]], int]:
    """Return the explanation of the failing case of choices from seed, and its runs."""
    first = executed(body, choices)
    shrinker = Shrinker(body, first, MAX_CHOICES, budget, workers=workers)
    explanation = explain(shrinker, shrinker.best, seed)
    return (
        [
            [one.label, one.value, one.any_value_fails, one.nearest]
            for one in explanation
        ],
        shrinker.runs,
    )


class TestExplain:
    """explain finds the draws of a counterexample that matter."""

    tests: ClassVar[list[tuple[str, Body, list[Choice], int, int]]] = [
        (
            "explains each draw of a failing case",
            noisy,
            integers(1001, 3),
            7,
            DEFAULT_BUDGET,
        ),
        (
            "explains a draw from the fillings that decode",
            always_seven,
            integers(7),
            11,
            DEFAULT_BUDGET,
        ),
        (
            "leaves a draw unexplained when no filling decodes",
            always_seven,
            integers(7),
            7,
            DEFAULT_BUDGET,
        ),
        (
            "leaves a draw unexplained when the budget ends in its fillings",
            noisy,
            integers(1001, 3),
            7,
            2,
        ),
    ]

    @pytest.mark.parametrize(
        ("body", "choices", "seed", "budget"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_explains_on_four_workers_what_one_worker_explains(
        self,
        seat: Collector,
        body: Body,
        choices: list[Choice],
        seed: int,
        budget: int,
    ) -> None:
        """The explanation and its runs are the same."""
        check.equal(
            seat,
            explained(body, choices, seed, budget, 4),
            explained(body, choices, seed, budget),
            "four workers explain the same as one",
        )

    def test_explains_each_draw_of_a_failing_case(self, seat: Collector) -> None:
        """The nearest passing value of n is 1000."""
        check.equal(
            seat,
            explained(noisy, integers(1001, 3), 7),
            ([["n", 1001, False, (1000,)], ["noise", 3, True, None]], 7),
            "the nearest passing value of n is 1000",
        )

    def test_does_not_report_a_nearest_value_when_the_step_fails_in_another_way(
        self, seat: Collector
    ) -> None:
        """1000 fails too."""

        def limit(c: Case) -> None:
            value = c.draw(WIDE, "n")
            if value > 1000:
                c.fail("above")
            if value == 1000:
                c.fail("limit")

        check.equal(
            seat,
            explained(limit, integers(1001), 7),
            ([["n", 1001, False, None]], 3),
            "1000 fails too",
        )

    def test_does_not_report_a_nearest_value_for_a_draw_at_its_target(
        self, seat: Collector
    ) -> None:
        """0 does not have a step towards 0."""

        def zero(c: Case) -> None:
            if c.draw(SIGNED, "v") == 0:
                c.fail("zero")

        check.equal(
            seat,
            explained(zero, integers(0), 7),
            ([["v", 0, False, None]], 1),
            "0 does not have a step towards 0",
        )

    def test_reports_the_nearest_value_above_a_draw_below_its_target(
        self, seat: Collector
    ) -> None:
        """-4 passes."""

        def low(c: Case) -> None:
            if c.draw(SIGNED, "v") < -4:
                c.fail("low")

        check.equal(
            seat,
            explained(low, integers(-5), 7),
            ([["v", -5, False, (-4,)]], 3),
            "-4 passes",
        )

    def test_leaves_a_draw_unexplained_when_no_filling_decodes(
        self, seat: Collector
    ) -> None:
        """The explanation does not run the body."""
        check.equal(
            seat,
            explained(always_seven, integers(7), 7),
            ([["seven", 7, None, None]], 0),
            "the explanation does not run the body",
        )

    def test_explains_a_draw_from_the_fillings_that_decode(
        self, seat: Collector
    ) -> None:
        """One filling decodes."""
        check.equal(
            seat,
            explained(always_seven, integers(7), 11),
            ([["seven", 7, True, None]], 1),
            "one filling decodes",
        )

    def test_leaves_a_draw_unexplained_when_it_does_not_make_a_choice(
        self, seat: Collector
    ) -> None:
        """The just is unexplained."""

        def after_just(c: Case) -> None:
            c.draw(JUST, "j")
            if c.draw(WIDE, "n") > 1000:
                c.fail("above")

        check.equal(
            seat,
            explained(after_just, integers(1001), 7),
            ([["j", 7, None, None], ["n", 1001, False, (1000,)]], 4),
            "the just is unexplained",
        )

    def test_reports_the_map_of_the_nearest_integer_for_a_map_of_an_integer(
        self, seat: Collector
    ) -> None:
        """The map wraps the step in a and b."""
        wrapped = Mapped(WIDE, lambda value: f"a{value}b")

        def above_wrapped(c: Case) -> None:
            if int(c.draw(wrapped, "n")[1:-1]) > 1000:
                c.fail("above")

        explanation, _ = explained(above_wrapped, integers(1001), 7)
        check.equal(
            seat,
            explanation[0][1:],
            ["a1001b", False, ("a1000b",)],
            "the map wraps the step in a and b",
        )

    def test_does_not_report_a_nearest_value_for_a_draw_that_is_not_an_integer(
        self, seat: Collector
    ) -> None:
        """A float does not have a step."""
        explanation, _ = explained(bigger, [Choice("float", 3.0)], 7)
        check.is_none(seat, explanation[0][3], "a float does not have a nearest value")

    def test_leaves_the_draws_unexplained_once_the_budget_is_spent(
        self, seat: Collector
    ) -> None:
        """No run is left."""
        check.equal(
            seat,
            explained(noisy, integers(1001, 3), 7, 0),
            ([["n", 1001, None, None], ["noise", 3, None, None]], 0),
            "no run is left",
        )

    def test_raises_an_error_of_the_decode_of_a_filling_that_is_not_a_signal(
        self, seat: Collector
    ) -> None:
        """The error of the map propagates."""
        decodes = 0

        def brittle(value: int) -> int:
            nonlocal decodes
            decodes += 1
            if decodes > 1:
                raise TypeError("the decode broke")
            return value

        mapped = Mapped(WIDE, brittle)

        def once(c: Case) -> None:
            c.draw(mapped, "n")
            c.fail("always")

        shrinker = Shrinker(once, executed(once, integers(5)), MAX_CHOICES, 10)
        error = check.raises(
            seat, lambda: explain(shrinker, shrinker.best, 7), "the filling raises"
        )
        check.error_as(seat, error, TypeError, "the error is the TypeError of the map")
