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
they leave. Two configurations are the same when their sets are equal and
their states are the same states in any order. The search stops as
undecided before a step past its budget, before it stores a configuration
past the limit of its memo, and once its time has passed. The memo counts
one bit per call of the partition for each configuration.

The frontier of a search is the first configuration in search order that
has the most linearized calls. The ending of a search has the order of the
frontier, its states and the candidates that the spec rejected there.
"""

from __future__ import annotations

import itertools
import json
import math
import threading
import time
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Literal, TypeVar, final

from dokimi_assert._history.option import Config
from dokimi_assert._history.partition import Checked, Span
from dokimi_assert._history.spec import (
    Operation,
    Spec,
    SubjectSpec,
    same_state,
    state_key,
)

__all__ = ["Deadline", "Ending", "Limit", "Search", "SpecError", "Verdict"]

_S = TypeVar("_S")

#: The verdict of a check or of the search of a partition.
Verdict = Literal["passed", "violated", "undecided"]

#: The limit that stopped an undecided search.
Limit = Literal["steps", "memo", "time"]

#: The number of steps between two readings of the clock.
_CLOCK_STEPS = 1024


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
        """Report whether the time of the check has passed or the check has stopped."""
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
    them back in constant time.
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
        self._calls: Sequence[Checked] = calls
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
        self._cost: Callable[[Any], int] = (
            spec.cost if isinstance(spec, SubjectSpec) else lambda _: 1
        )
        self._budget: int = config.budget
        self._memo_limit: int = config.memo_limit
        self._deadline: Deadline = deadline
        self._clock_at: int = 0
        entries: list[tuple[int, int, bool]] = []
        for position, c in enumerate(calls):
            entries.append((c.span.call, position, True))
            completion = c.span.completion
            if c.span.operation.known and completion is not None:
                entries.append((completion, position, False))
        entries.sort()
        self._head: int = len(entries)
        chain = [self._head, *range(len(entries)), self._head + 1]
        self._next: list[int] = [0] * len(chain)
        self._prev: list[int] = [0] * len(chain)
        for before, after in itertools.pairwise(chain):
            self._next[before] = after
            self._prev[after] = before
        self._position: list[int] = [position for _, position, _ in entries]
        self._invokes: list[bool] = [invokes for _, _, invokes in entries]
        self._invocation: list[int] = [0] * len(calls)
        self._completion: list[int | None] = [None] * len(calls)
        for entry, (_, position, invokes) in enumerate(entries):
            if invokes:
                self._invocation[position] = entry
            else:
                self._completion[position] = entry
        self._open: int = sum(1 for c in calls if c.span.operation.known)
        self._steps: int = 0
        self._done: int = 0
        self._states: list[_S] = []
        self._stack: list[tuple[int, list[_S]]] = []
        self._memo: dict[tuple[int, frozenset[Hashable]], list[list[_S]]] = {}
        self._configurations: int = 0
        self._linearized: tuple[int, ...] = ()
        self._frontier: list[_S] = []
        self._candidates: list[int] = []
        self._at_frontier: bool = True
        self._calling: str = "initial"
        self._stepped: int | None = None

    def run(self) -> Ending[_S]:
        """Search the partition and return its ending.

        Returns:
            The ending.

        Raises:
            SpecError: A function of the spec raises.
        """
        try:
            self._states = [self._spec.initial()]
            self._frontier = self._states
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
        entry = self._next[self._head]
        while self._open > 0:
            if not self._invokes[entry]:
                if not self._stack:
                    return False
                entry = self._backtrack()
            elif self._linearize(self._position[entry]):
                entry = self._next[self._head]
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
                raise _LimitError("steps")
            if self._steps >= self._clock_at:
                if self._deadline.passed():
                    raise _LimitError("time")
                self._clock_at = self._steps + _CLOCK_STEPS
            self._steps += cost
            for after in self._spec.next(state, op):
                self._calling = "equal"
                if not any(self._equal(after, kept) for kept in following):
                    following.append(after)
                self._calling = "next"
        return following

    def _remember(self, done: int, states: list[_S]) -> bool:
        """Store a configuration, and report whether the memo did not have it."""
        self._calling = "key"
        name = (done, frozenset(self._key(state) for state in states))
        bucket = self._memo.setdefault(name, [])
        self._calling = "equal"
        for seen in bucket:
            if len(seen) == len(states) and all(
                any(self._equal(state, other) for other in seen) for state in states
            ):
                return False
        if (self._configurations + 1) * len(self._calls) > self._memo_limit:
            raise _LimitError("memo")
        bucket.append(states)
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
