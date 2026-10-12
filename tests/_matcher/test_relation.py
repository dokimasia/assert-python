"""The spec of _matcher/relation.py tests the relations of a subject across calls.

The corpus has one passing and one failing case of each relation. This spec
adds the exceptions of the callables, the coroutines and the faults of the
event loop. It checks its verdicts with the assert statement of pytest.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator, Callable
from typing import Any

from dokimi_assert._matcher import relation
from dokimi_assert._matcher.option import Relaxations, equate_empty
from dokimi_assert._matcher.seat import Mode
from dokimi_assert.seat import Recorder


class BoomError(Exception):
    """The error that boom raises."""


def boom(*_: Any) -> Any:
    """Raise BoomError."""
    raise BoomError("boom")


async def doubled(x: int) -> int:
    """Return 2 * x from a coroutine."""
    return 2 * x


def run(drive: Callable[[Recorder], None]) -> Recorder:
    """Call drive on a new recorder, and return the recorder."""
    seat = Recorder()
    drive(seat)
    return seat


def faulted(drive: Callable[[Recorder], None]) -> str:
    """Call drive inside a running event loop, and return the message of the seat."""
    seat = Recorder()

    async def test() -> None:
        drive(seat)

    asyncio.run(test())
    assert seat.failures == []
    return seat.message


async def never() -> None:
    """Return from a coroutine without an await."""


class TestRepetitions:
    """REPETITIONS is the number of runs of a subject whose results can vary."""

    def test_is_32(self) -> None:
        """A subject runs 32 times."""
        assert relation.REPETITIONS == 32


class TestIsIdempotent:
    """is_idempotent checks that a second call does not change what observe returns."""

    def test_fails_with_the_error_of_the_first_step(self) -> None:
        """The exception of the first step is in first, and second is None."""
        seat = run(
            lambda s: relation.is_idempotent(s, Mode.SOFT, boom, 1, lambda: 0, "c")
        )
        assert isinstance(seat.failures[0].detail["first"], BoomError)
        assert seat.failures[0].detail["second"] is None

    def test_fails_with_the_error_of_the_second_step(self) -> None:
        """The exception of the second step is in second, and first is None."""
        calls = [0]

        def second_fails(_: Any) -> None:
            calls[0] += 1
            if calls[0] == 2:
                raise BoomError("second")

        seat = run(
            lambda s: relation.is_idempotent(
                s, Mode.SOFT, second_fails, 1, lambda: 0, "c"
            )
        )
        assert seat.failures[0].detail["first"] is None
        assert isinstance(seat.failures[0].detail["second"], BoomError)

    def test_awaits_a_coroutine_function(self) -> None:
        """The subject can be a coroutine function."""
        seat = run(
            lambda s: relation.is_idempotent(s, Mode.FATAL, doubled, 1, lambda: 0, "c")
        )
        assert not seat.failed

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine."""
        message = faulted(
            lambda s: relation.is_idempotent(s, Mode.FATAL, doubled, 1, lambda: 0, "c")
        )
        assert message.startswith("idempotent runs a coroutine")


class TestAccumulates:
    """accumulates checks that each call changes a number by the same amount."""

    def test_fails_a_first_call_that_does_not_change_the_number(self) -> None:
        """A first call that does not change the number fails with both changes."""
        seat = run(
            lambda s: relation.accumulates(
                s, Mode.FATAL, lambda _: None, 1, lambda: 5, "c"
            )
        )
        assert dict(seat.failures[0].detail) == {"first": 0, "second": 0}

    def test_fails_with_the_error_of_the_first_call(self) -> None:
        """The exception of the first call is in first."""
        seat = run(
            lambda s: relation.accumulates(s, Mode.SOFT, boom, 1, lambda: 0, "c")
        )
        assert isinstance(seat.failures[0].detail["first"], BoomError)

    def test_fails_with_the_error_of_the_second_call(self) -> None:
        """The exception of the second call is in second."""
        count = [0]

        def call(_: Any) -> None:
            count[0] += 1
            if count[0] == 2:
                raise BoomError("second")

        seat = run(
            lambda s: relation.accumulates(s, Mode.SOFT, call, 1, lambda: count[0], "c")
        )
        assert isinstance(seat.failures[0].detail["second"], BoomError)

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine."""
        message = faulted(
            lambda s: relation.accumulates(s, Mode.FATAL, doubled, 1, lambda: 0, "c")
        )
        assert message.startswith("accumulates runs a coroutine")


class TestIsDeterministic:
    """is_deterministic checks that a call returns the same result each time."""

    def test_fails_with_the_error_of_a_later_call(self) -> None:
        """The exception of a later call is in second, and first is None."""
        calls = [0]

        def flaky(_: Any) -> int:
            calls[0] += 1
            if calls[0] == 5:
                raise BoomError("fifth")
            return 1

        seat = run(lambda s: relation.is_deterministic(s, Mode.FATAL, flaky, 1, "c"))
        assert seat.failures[0].detail["first"] is None
        assert isinstance(seat.failures[0].detail["second"], BoomError)

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine."""
        message = faulted(
            lambda s: relation.is_deterministic(s, Mode.FATAL, doubled, 1, "c")
        )
        assert message.startswith("deterministic runs a coroutine")


class TestIsCommutative:
    """is_commutative checks that the order of the operands does not matter."""

    def test_passes_a_commutative_coroutine_function(self) -> None:
        """The operation can be a coroutine function."""

        async def add(a: int, b: int) -> int:
            return a + b

        seat = run(lambda s: relation.is_commutative(s, Mode.FATAL, add, 2, 3, "c"))
        assert not seat.failed

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine."""

        async def add(a: int, b: int) -> int:
            return a + b

        message = faulted(
            lambda s: relation.is_commutative(s, Mode.FATAL, add, 2, 3, "c")
        )
        assert message.startswith("commutative runs a coroutine")


class TestIsAssociative:
    """is_associative checks that the grouping does not change the result."""

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine."""

        async def add(a: int, b: int) -> int:
            return a + b

        message = faulted(
            lambda s: relation.is_associative(s, Mode.FATAL, add, 2, 3, 5, "c")
        )
        assert message.startswith("associative runs a coroutine")


class TestRoundTrip:
    """round_trip checks that inverse returns the value that forward received."""

    def test_fails_a_conversion_that_raises(self) -> None:
        """When a conversion raises, want is None and got is the error."""
        seat = run(lambda s: relation.round_trip(s, Mode.FATAL, boom, str, 1, "c"))
        assert seat.failures[0].detail["want"] is None
        assert isinstance(seat.failures[0].detail["got"], BoomError)

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine."""
        message = faulted(
            lambda s: relation.round_trip(s, Mode.FATAL, doubled, str, 1, "c")
        )
        assert message.startswith("round-trip runs a coroutine")


async def counting() -> AsyncIterator[int]:
    """Yield 1, 2 and 3 asynchronously."""
    for item in (1, 2, 3):
        yield item


class TestHasStableOrder:
    """has_stable_order checks that each iteration yields the same sequence."""

    def test_reads_an_asynchronous_iterable(self) -> None:
        """A sequence can be an asynchronous iterable."""
        seat = run(lambda s: relation.has_stable_order(s, Mode.FATAL, counting, "c"))
        assert not seat.failed

    def test_reads_an_absent_sequence_as_none(self) -> None:
        """A subject that returns None each time passes."""
        seat = run(
            lambda s: relation.has_stable_order(s, Mode.FATAL, lambda: None, "c")
        )
        assert not seat.failed

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot drain an asynchronous iterable."""
        message = faulted(
            lambda s: relation.has_stable_order(s, Mode.FATAL, counting, "c")
        )
        assert message.startswith("stable-order runs a coroutine")


class TestNoDuplicates:
    """no_duplicates checks that an iteration does not yield two equal elements."""

    def test_fails_an_iteration_that_raises(self) -> None:
        """When the iteration raises, got is the error and index is None."""
        seat = run(lambda s: relation.no_duplicates(s, Mode.FATAL, boom, "c"))
        assert seat.failures[0].detail["index"] is None
        assert isinstance(seat.failures[0].detail["got"], BoomError)

    def test_passes_an_absent_sequence(self) -> None:
        """An absent sequence does not have a duplicate."""
        seat = run(lambda s: relation.no_duplicates(s, Mode.FATAL, lambda: None, "c"))
        assert not seat.failed

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot drain an asynchronous iterable."""
        message = faulted(
            lambda s: relation.no_duplicates(s, Mode.FATAL, counting, "c")
        )
        assert message.startswith("no-duplicates runs a coroutine")


class TestIsMonotonic:
    """is_monotonic checks that the readings of observe never fall."""

    def test_fails_a_first_reading_that_is_nan(self) -> None:
        """A first reading that is NaN fails at index 0."""
        seat = run(
            lambda s: relation.is_monotonic(
                s, Mode.FATAL, lambda: math.nan, lambda: None, 3, "c"
            )
        )
        assert seat.failures[0].detail["index"] == 0
        assert seat.failures[0].detail["first"] is None

    def test_fails_a_later_reading_that_is_nan(self) -> None:
        """A reading that is NaN after a step fails at its index."""
        readings = iter([1.0, math.nan])
        seat = run(
            lambda s: relation.is_monotonic(
                s, Mode.FATAL, lambda: next(readings), lambda: None, 3, "c"
            )
        )
        assert seat.failures[0].detail["index"] == 1

    def test_fails_with_the_error_of_the_first_reading(self) -> None:
        """The exception of the first reading is in second."""
        seat = run(
            lambda s: relation.is_monotonic(s, Mode.FATAL, boom, lambda: None, 3, "c")
        )
        assert isinstance(seat.failures[0].detail["second"], BoomError)

    def test_fails_with_the_error_of_a_step(self) -> None:
        """The exception of advance is in second, and index is None."""
        seat = run(
            lambda s: relation.is_monotonic(s, Mode.FATAL, lambda: 1, boom, 3, "c")
        )
        assert isinstance(seat.failures[0].detail["second"], BoomError)
        assert seat.failures[0].detail["index"] is None

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine."""

        async def reading() -> int:
            return 1

        message = faulted(
            lambda s: relation.is_monotonic(
                s, Mode.FATAL, reading, lambda: None, 3, "c"
            )
        )
        assert message.startswith("monotonic runs a coroutine")


class TestIsTotal:
    """is_total checks that a call returns for each element of a domain."""

    def test_passes_an_empty_domain(self) -> None:
        """An empty domain passes, because it does not have an element."""
        seat = run(lambda s: relation.is_total(s, Mode.FATAL, boom, [], "c"))
        assert not seat.failed

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine."""
        message = faulted(lambda s: relation.is_total(s, Mode.FATAL, doubled, [1], "c"))
        assert message.startswith("total runs a coroutine")


class TestIsNotPure:
    """is_not_pure checks that a call changes what observe returns."""

    def test_fails_an_observation_that_raises(self) -> None:
        """When observe raises, got is the error."""
        seat = run(
            lambda s: relation.is_not_pure(s, Mode.FATAL, boom, lambda: None, "c")
        )
        assert isinstance(seat.failures[0].detail["got"], BoomError)

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine."""
        message = faulted(
            lambda s: relation.is_not_pure(s, Mode.FATAL, never, lambda: None, "c")
        )
        assert message.startswith("not-pure runs a coroutine")


class TestFailsAfterClose:
    """fails_after_close checks that a call raises the sentinel after close."""

    def test_fails_a_close_that_raises(self) -> None:
        """When close raises, want is None and got is the error."""
        seat = run(
            lambda s: relation.fails_after_close(
                s, Mode.FATAL, boom, lambda: None, BoomError, "c"
            )
        )
        assert seat.failures[0].detail["want"] is None

    def test_fails_a_call_that_raises_another_error(self) -> None:
        """A call that raises another error fails.

        The failure has the error as got.
        """

        def other() -> None:
            raise KeyError("other")

        seat = run(
            lambda s: relation.fails_after_close(
                s, Mode.FATAL, lambda: None, other, BoomError, "c"
            )
        )
        assert isinstance(seat.failures[0].detail["got"], KeyError)

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine."""
        message = faulted(
            lambda s: relation.fails_after_close(
                s, Mode.FATAL, never, lambda: None, BoomError, "c"
            )
        )
        assert message.startswith("after-close runs a coroutine")


class TestIsPoisoned:
    """is_poisoned checks that every reading raises after induce."""

    def test_fails_an_induce_that_raises(self) -> None:
        """When induce raises, index is None."""
        seat = run(lambda s: relation.is_poisoned(s, Mode.FATAL, boom, boom, "c"))
        assert seat.failures[0].detail["index"] is None

    def test_ends_with_a_fault_inside_a_running_event_loop(self) -> None:
        """The call ends with a fault when it cannot run a coroutine."""
        message = faulted(
            lambda s: relation.is_poisoned(s, Mode.FATAL, never, boom, "c")
        )
        assert message.startswith("poisoned runs a coroutine")


class TestMatched:
    """matched finds the bipartite matching of is_permutation."""

    def test_matches_where_a_greedy_match_fails(self) -> None:
        """Under equate-empty, None equals both [] and {}, and those two differ."""
        relax = Relaxations(equate_empty=True)
        assert relation.matched([None, []], [[], {}], relax)

    def test_does_not_match_sequences_of_different_lengths(self) -> None:
        """Two sides of different lengths do not match."""
        assert not relation.matched([1], [1, 1], Relaxations())


class TestIsPermutation:
    """is_permutation checks that two sequences have the same elements in any order."""

    def test_compares_values_that_are_not_sequences_by_the_rules_of_equal(self) -> None:
        """None is a permutation of an empty list under equate-empty."""
        seat = run(
            lambda s: relation.is_permutation(
                s, Mode.FATAL, None, [], "c", equate_empty()
            )
        )
        assert not seat.failed
