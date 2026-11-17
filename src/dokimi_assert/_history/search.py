# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The search of one partition for a linearization. The definition fixes the search.

The search is the scan of Wing and Gong. It keeps a memo of the
configurations that it visited. The entries are the invocations of the
calls of the partition and the completions of its known calls. They are in
event order. A call that is not known does not have a completion entry. It
takes effect at some point after its invocation, or never. The candidates
at each point are the calls invoked before the first completion of a call
that the search has not linearized. An accepted call restarts the scan from
the first entry. The search passes when it has linearized every known call.

A configuration is a set of linearized calls and the distinct states that
they leave. The search skips a configuration that the memo covers: a
configuration in the memo with the same states in any order and the same
calls with a completion entry, whose other calls are among the
configuration's. A call without a completion entry need not take effect,
so every order that follows the configuration also follows the one in the
memo. The search stops as
undecided before a step past its budget, before it stores a configuration
past the limit of its memo, and once its time has passed. The memo counts
one bit per call of the partition for each configuration.

The frontier of a search is the first configuration in search order that
has the most linearized calls. The ending of a search has the order of the
frontier, its states and the candidates that the spec rejected there.
"""

from __future__ import annotations

import json
import math
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar, final

from dokimi_assert._history.spec import (
    Operation,
    Spec,
    SubjectSpec,
    same_state,
    state_key,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Sequence

    from dokimi_assert._history.option import Config
    from dokimi_assert._history.partition import Checked, Span

__all__ = ["Deadline", "Ending", "Limit", "Search", "SpecError", "Verdict"]

_S = TypeVar("_S")

#: The verdict of a check or of the search of a partition.
Verdict = Literal["passed", "violated", "undecided"]

#: The limit that stopped an undecided search.
Limit = Literal["steps", "memo", "time"]

#: The number of steps between two readings of the clock.
_CLOCK_STEPS = 1024

#: The entries of the head and the tail of the list of entries of a search.
_HEAD = 0
_TAIL = 1


@dataclass(frozen=True, slots=True)
class Ending(Generic[_S]):
    """The verdict of the search of one partition, and its frontier.

    Attributes:
        outcome: The verdict of the partition.
        steps: The steps that the search spent.
        linearized: The positions of the calls of the frontier in order. It
            is empty for a search that passed.
        states: The states of the frontier. A search that passed has the
            states after the order that it found.
        candidates: The positions of the calls that the spec rejected at
            the frontier.
        limit: The limit that stopped an undecided search. It is None for any
            other search.
    """

    outcome: Verdict
    steps: int
    linearized: tuple[int, ...]
    states: tuple[_S, ...]
    candidates: tuple[int, ...]
    limit: Limit | None


class Deadline:
    """The deadline of a check, and the signal that the check stopped its searches.

    A check on more than one worker stops the searches whose results it
    does not need.

    Attributes:
        stopped: The event that the check sets when it stops its searches.
    """

    def __init__(self, seconds: float) -> None:
        """Return the deadline of a check with a time limit of seconds.

        Args:
            seconds: The time of the check. A value of 0 does not set a
                limit.
        """
        self._end: float = time.monotonic() + seconds if seconds > 0 else math.inf
        self.stopped: threading.Event = threading.Event()

    def passed(self) -> bool:
        """Report whether the time of the check has passed or the check has stopped.

        Returns:
            True when the time has passed or the check has stopped.
        """
        return self.stopped.is_set() or time.monotonic() >= self._end


@final
class SpecError(Exception):
    """The error of a function of a spec that raised during a search.

    Attributes:
        fn: The name of the function. It is initial, next, equal or key.
        call: The call that the search stepped, or None before the first
            step.
    """

    def __init__(self, fn: str, stepped: Span | None, cause: Exception) -> None:
        """Return the error of a function of a spec that raised.

        Args:
            fn: The function.
            stepped: The span of the call that the search stepped, or None.
            cause: The exception of the function.
        """
        on = "" if stepped is None else f" for {json.dumps(stepped.operation.name)}"
        super().__init__(f"the function {fn} of the spec raises{on}")
        self.fn: str = fn
        self.call: int | None = None if stepped is None else stepped.call
        self.__cause__ = cause


class _LimitError(Exception):
    """The signal of a limit that stopped the search."""

    def __init__(self, limit: Limit) -> None:
        """Return the signal of limit."""
        super().__init__(limit)
        self.limit: Limit = limit


class Search(Generic[_S]):
    """The search of one partition.

    The entries are a doubly linked list between a head and a tail, so the
    search takes the entries of a linearized call out of the scan and puts
    them back in constant time. The head and the tail are the first two
    entries, so a search that grows appends the entries of its new calls
    without moving an entry.
    """

    def __init__(
        self,
        calls: Sequence[Checked],
        spec: Spec[_S],
        config: Config,
        deadline: Deadline,
    ) -> None:
        """Lay out the entries of the calls of a partition in event order.

        Args:
            calls: The calls of the partition in event order.
            spec: The spec.
            config: The limits of the check.
            deadline: The deadline of the check.
        """
        self._calls: list[Checked] = []
        self._budget: int = config.budget
        self._memo_limit: int = config.memo_limit
        self._next: list[int] = [_TAIL, _TAIL]
        self._prev: list[int] = [_HEAD, _HEAD]
        self._position: list[int] = [-1, -1]
        self._invokes: list[bool] = [False, False]
        self._invocation: list[int] = []
        self._completion: list[int | None] = []
        self._optional: int = 0
        self._open: int = 0
        self._steps: int = 0
        self._done: int = 0
        self._started: bool = False
        self._states: list[_S] = []
        self._stack: list[tuple[int, list[_S]]] = []
        self._memo: dict[
            tuple[int, frozenset[Hashable]], list[tuple[int, list[_S]]]
        ] = {}
        self._configurations: int = 0
        self._linearized: tuple[int, ...] = ()
        self._frontier: list[_S] = []
        self._candidates: list[int] = []
        self._at_frontier: bool = True
        self._calling: str = "initial"
        self._stepped: int | None = None
        self._use(spec, deadline)
        self._add(calls)

    @property
    def calls(self) -> tuple[Checked, ...]:
        """The calls of the search, in event order.

        Returns:
            The calls.
        """
        return tuple(self._calls)

    def fits(self, calls: int, config: Config) -> bool:
        """Report whether the search continues as a new search when it grows to calls.

        A new search of the calls would take the steps of this search up to the
        order that it found when config states its budget and its memo limit,
        and when the memo contains no more configurations than the memo limit
        lets a search of the calls store.

        Args:
            calls: The number of calls of the grown search.
            config: The limits of the check.

        Returns:
            True when the grown search continues as a new search of its calls.
        """
        return (
            config.budget == self._budget
            and config.memo_limit == self._memo_limit
            and self._configurations * calls <= config.memo_limit
        )

    def grow(
        self, calls: Sequence[Checked], spec: Spec[_S], deadline: Deadline
    ) -> None:
        """Add calls that follow every event that a search that passed read.

        The entries of the calls join the scan before the tail, in event
        order. The search then steps through spec, and reads deadline before
        its next step. A search of every call takes the same steps from the
        order that this search found.

        Args:
            calls: The new calls of the partition in event order.
            spec: The spec of the check that grows the search.
            deadline: The deadline of the check that grows the search.
        """
        self._use(spec, deadline)
        self._add(calls)

    def _use(self, spec: Spec[_S], deadline: Deadline) -> None:
        """Step through spec, and read deadline before the next step."""
        self._spec: Spec[_S] = spec
        stated_equal = getattr(spec, "equal", None)
        self._equal: Callable[[_S, _S], bool] = (
            same_state
            if stated_equal is None
            else lambda a, b: bool(stated_equal(a, b))
        )
        stated_key = getattr(spec, "key", None)
        self._key: Callable[[_S], Hashable] = (
            state_key if stated_key is None else stated_key
        )
        # mypy reads spec as a Spec of any state type, and a SubjectSpec has a
        # state type of its own.
        self._cost: Callable[[Any], int] = (
            spec.cost if isinstance(spec, SubjectSpec) else lambda _: 1  # type: ignore[redundant-expr, unreachable]
        )
        self._deadline: Deadline = deadline
        self._clock_at: int = self._steps

    def _add(self, calls: Sequence[Checked]) -> None:
        """Lay out the entries of calls after the entries of the search, in event order.

        An entry that the search took out of the scan while the tail followed
        it then points at the first new entry. A backtrack puts it back before
        the new entries, as a search of every call does.
        """
        start = len(self._calls)
        entries: list[tuple[int, int, bool]] = []
        for offset, c in enumerate(calls):
            entries.append((c.span.call, start + offset, True))
            completion = c.span.completion
            if c.span.operation.known and completion is not None:
                entries.append((completion, start + offset, False))
            else:
                self._optional |= 1 << (start + offset)
        entries.sort()
        self._calls.extend(calls)
        self._invocation.extend([0] * len(calls))
        self._completion.extend([None] * len(calls))
        if not entries:
            return
        first = len(self._next)
        for entry in range(_TAIL + 1, first):
            if self._next[entry] == _TAIL:
                self._next[entry] = first
        last = self._prev[_TAIL]
        self._next[last] = first
        for offset, (_, position, invokes) in enumerate(entries):
            entry = first + offset
            self._prev.append(entry - 1 if offset else last)
            self._next.append(entry + 1)
            self._position.append(position)
            self._invokes.append(invokes)
            if invokes:
                self._invocation[position] = entry
            else:
                self._completion[position] = entry
                self._open += 1
        self._next[-1] = _TAIL
        self._prev[_TAIL] = len(self._next) - 1

    def run(self) -> Ending[_S]:
        """Search the partition and return its ending.

        A search that grew continues from the order that it found.

        Returns:
            The ending.

        Raises:
            SpecError: A function of the spec raises.
        """
        try:
            if not self._started:
                self._states = [self._spec.initial()]
                self._frontier = self._states
                self._started = True
            if self._search():
                return Ending("passed", self._steps, (), tuple(self._states), (), None)
            return self._ending("violated", None)
        except _LimitError as stopped:
            return self._ending("undecided", stopped.limit)
        except Exception as error:
            stepped = None if self._stepped is None else self._calls[self._stepped]
            raise SpecError(
                self._calling, None if stepped is None else stepped.span, error
            ) from error

    def _ending(self, outcome: Verdict, limit: Limit | None) -> Ending[_S]:
        """Return an ending that has the frontier."""
        return Ending(
            outcome,
            self._steps,
            self._linearized,
            tuple(self._frontier),
            tuple(self._candidates),
            limit,
        )

    def _search(self) -> bool:
        """Scan the entries until every known call is linearized.

        Returns:
            True when one order passes.
        """
        entry = self._next[_HEAD]
        while self._open > 0:
            if not self._invokes[entry]:
                if not self._stack:
                    return False
                entry = self._backtrack()
            elif self._linearize(self._position[entry]):
                entry = self._next[_HEAD]
            else:
                entry = self._next[entry]
        return True

    def _linearize(self, position: int) -> bool:
        """Linearize a candidate when the spec accepts it in a new configuration.

        Returns:
            True when the search linearized the candidate.
        """
        self._stepped = position
        following = self._step(self._calls[position].span.operation)
        if not following:
            if self._at_frontier:
                self._candidates.append(position)
            return False
        done = self._done | (1 << position)
        if not self._remember(done, following):
            return False
        self._stack.append((position, self._states))
        self._done = done
        self._states = following
        self._lift(position)
        self._at_frontier = len(self._stack) > len(self._linearized)
        if self._at_frontier:
            self._linearized = tuple(at for at, _ in self._stack)
            self._frontier = following
            self._candidates = []
        return True

    def _step(self, op: Operation) -> list[_S]:
        """Return the distinct states that op leaves from the current ones."""
        following: list[_S] = []
        for state in self._states:
            self._calling = "next"
            cost = self._cost(state)
            if self._steps + cost > self._budget:
                limit: Limit = "steps"
                raise _LimitError(limit)
            if self._steps >= self._clock_at:
                if self._deadline.passed():
                    limit = "time"
                    raise _LimitError(limit)
                self._clock_at = self._steps + _CLOCK_STEPS
            self._steps += cost
            for after in self._spec.next(state, op):
                self._calling = "equal"
                if not any(self._equal(after, kept) for kept in following):
                    following.append(after)
                self._calling = "next"
        return following

    def _remember(self, done: int, states: list[_S]) -> bool:
        """Store a configuration, and report whether the memo did not cover it.

        A configuration in the memo covers this one when the two have the same
        states and the same calls with a completion entry, and its calls
        without one are among this configuration's.
        """
        self._calling = "key"
        optional = done & self._optional
        name = (done & ~self._optional, frozenset(self._key(state) for state in states))
        bucket = self._memo.setdefault(name, [])
        self._calling = "equal"
        for taken, seen in bucket:
            if (
                taken & ~optional == 0
                and len(seen) == len(states)
                and all(
                    any(self._equal(state, other) for other in seen) for state in states
                )
            ):
                return False
        if (self._configurations + 1) * len(self._calls) > self._memo_limit:
            limit: Limit = "memo"
            raise _LimitError(limit)
        bucket.append((optional, states))
        self._configurations += 1
        return True

    def _backtrack(self) -> int:
        """Undo the last linearized call, and return the entry after its invocation."""
        position, self._states = self._stack.pop()
        self._done &= ~(1 << position)
        self._unlift(position)
        self._at_frontier = False
        return self._next[self._invocation[position]]

    def _lift(self, position: int) -> None:
        """Take the entries of a call out of the scan."""
        self._unlink(self._invocation[position])
        completion = self._completion[position]
        if completion is not None:
            self._unlink(completion)
            self._open -= 1

    def _unlift(self, position: int) -> None:
        """Put the entries of a call back in the reverse order of _lift."""
        completion = self._completion[position]
        if completion is not None:
            self._relink(completion)
            self._open += 1
        self._relink(self._invocation[position])

    def _unlink(self, entry: int) -> None:
        """Take one entry out of the list."""
        before = self._prev[entry]
        after = self._next[entry]
        self._next[before] = after
        self._prev[after] = before

    def _relink(self, entry: int) -> None:
        """Put an entry that _unlink took out back between its old neighbours."""
        self._next[self._prev[entry]] = entry
        self._prev[self._next[entry]] = entry
