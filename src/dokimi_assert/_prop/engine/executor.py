"""The executors of a run on one worker and of a run on more than one.

Serial runs each case on the thread of the runner when the runner calls for
it. The case walks the case tree as it runs.

Ahead runs the cases of a run on more than one worker. Its workers run the
random and edge cases ahead of the runner and outside the case tree. They run
them in the order of one worker: random case 0, edge case 0, random case 1,
edge case 1, and so on. Random cases follow alone after the fourth edge case.
A worker starts a case at most `workers` positions of that order past the
furthest case that the runner called for. A call for a case waits until the
case has ended, and it enters the case into the tree then. A replayed case
runs on the next free worker before any case ahead. The simplest case and a
prefix case are replayed cases. At close, every case that the runner did not
take is cancelled, and it ends at its next choice.

Both executors give the runner the same cases as a run on one worker, so a
run on any number of workers reports the same outcome as a run on one.
"""

from __future__ import annotations

import threading
from collections import deque
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import cast

from dokimi_assert._prop.engine.case import (
    Case,
    Generating,
    Provider,
    Replaying,
    Trailing,
)
from dokimi_assert._prop.engine.choice import Choice
from dokimi_assert._prop.engine.edge import BOUNDARIES, Edge
from dokimi_assert._prop.engine.execution import (
    Body,
    Execution,
    entered,
    execute,
    finish,
)
from dokimi_assert._prop.engine.source import Source, case_source
from dokimi_assert._prop.engine.tree import Tree

__all__ = ["Ahead", "Generated", "Serial"]


@dataclass(frozen=True, slots=True)
class Generated:
    """A random case in the form that the runner takes.

    Attributes:
        execution: The execution of the case in the case tree.
        choices: The choices of the case where a run on one worker stops it.
        source: The source of the case where that run stops it. The cut of
            the prefix case is drawn from it.
    """

    execution: Execution
    choices: list[Choice]
    source: Source


class Serial:
    """The executor of a run on one worker."""

    def __init__(self, body: Body, seed: int, max_choices: int, tree: Tree) -> None:
        """Return the executor of one worker over a case tree.

        Args:
            body: The body.
            seed: The seed of the run.
            max_choices: The largest number of choices of a case.
            tree: The case tree.
        """
        self._body: Body = body
        self._seed: int = seed
        self._max_choices: int = max_choices
        self._tree: Tree = tree

    def replay(self, choices: Sequence[Choice]) -> Execution:
        """Run the case that replays choices into the tree.

        Args:
            choices: The choices.

        Returns:
            The execution.
        """
        provider = Replaying(list(choices))
        return execute(self._body, provider, self._max_choices, self._tree)

    def random(self, index: int) -> Generated:
        """Run random case index of the seed into the tree.

        Args:
            index: The index of the case.

        Returns:
            The case.
        """
        source = case_source(self._seed, index)
        provider = Generating(source)
        execution = execute(self._body, provider, self._max_choices, self._tree)
        return Generated(execution, execution.case.choices, source)

    def edge(self, number: int) -> Execution:
        """Run the edge case of a boundary into the tree.

        Args:
            number: The position of the boundary in BOUNDARIES.

        Returns:
            The execution.
        """
        provider = Edge(BOUNDARIES[number])
        return execute(self._body, provider, self._max_choices, self._tree)

    def close(self) -> None:
        """End the run. The executor of one worker does not start a thread."""


class _Flight:
    """One case that a worker of a run on more than one worker runs.

    Attributes:
        case: The case. It keeps its walk.
        trail: The provider of a random case, and None for any other case.
        done: The event that is set when the case has ended.
    """

    def __init__(
        self, provider: Provider, max_choices: int, trail: Trailing | None = None
    ) -> None:
        """Return a case that has not started and takes its values from a provider."""
        self.case: Case = Case(provider, max_choices, walk=True)
        self.trail: Trailing | None = trail
        self.done: threading.Event = threading.Event()
        self._execution: Execution | None = None
        self._error: BaseException | None = None

    def run(self, body: Body) -> None:
        """Run the body on the case, and keep how the case ended."""
        try:
            self._execution = finish(body, self.case)
        except BaseException as error:
            self._error = error
        self.done.set()

    def result(self) -> Execution:
        """Return the execution of the case, or raise the error of the body.

        The case has ended when this method runs.
        """
        if self._error is not None:
            raise self._error
        return cast("Execution", self._execution)


def _random_position(index: int) -> int:
    """Return the position of random case index in the order of one worker.

    The position is 2 * index while the edge cases alternate with the random
    cases, and index + 4 after the last edge case. The smaller of the two is
    the position at every index.
    """
    return min(2 * index, index + len(BOUNDARIES))


def _random_at(position: int) -> int | None:
    """Return the index of the random case at a position, or None for an edge case.

    An edge case is at each odd position below 2 * 4. The index of a random
    case is position // 2 while the edge cases alternate with the random
    cases, and position - 4 after the last edge case. The larger of the two
    is the index at every position.
    """
    if position % 2 == 1 and position // 2 < len(BOUNDARIES):
        return None
    return max(position // 2, position - len(BOUNDARIES))


class Ahead:
    """The executor of a run on more than one worker."""

    def __init__(
        self, body: Body, seed: int, max_choices: int, tree: Tree, workers: int
    ) -> None:
        """Return the executor of a number of workers. The workers start at once.

        Args:
            body: The body.
            seed: The seed of the run.
            max_choices: The largest number of choices of a case.
            tree: The case tree. Only the thread of the runner reads it.
            workers: The number of workers. It is at least 2.
        """
        self._body: Body = body
        self._seed: int = seed
        self._max_choices: int = max_choices
        self._tree: Tree = tree
        self._workers: int = workers
        self._lock: threading.Condition = threading.Condition()
        self._flights: dict[int, _Flight] = {}
        self._next: int = 0
        self._taken: int = 0
        self._replays: deque[_Flight] = deque()
        self._closed: bool = False
        self._pool: ThreadPoolExecutor = ThreadPoolExecutor(workers)
        for _ in range(workers):
            self._pool.submit(self._work)

    def replay(self, choices: Sequence[Choice]) -> Execution:
        """Run the case that replays choices on the next free worker, into the tree.

        Args:
            choices: The choices.

        Returns:
            The execution.
        """
        flight = _Flight(Replaying(list(choices)), self._max_choices)
        with self._lock:
            self._replays.append(flight)
            self._lock.notify()
        flight.done.wait()
        execution, _ = entered(self._tree, flight.result())
        return execution

    def random(self, index: int) -> Generated:
        """Take random case index of the seed, and enter it into the tree.

        A case that the tree ends as repeated comes with its record and its
        source at the step of the repeat, where a run on one worker stops it.

        Args:
            index: The index of the case.

        Returns:
            The case.
        """
        flight = self._take(_random_position(index))
        execution, steps = entered(self._tree, flight.result())
        trail = cast("Trailing", flight.trail)
        if execution.status == "repeated":
            return Generated(
                execution, execution.case.record_at(steps), trail.after(steps)
            )
        last = len(trail.states) - 1
        return Generated(execution, execution.case.choices, trail.after(last))

    def edge(self, number: int) -> Execution:
        """Take the edge case of a boundary, and enter it into the tree.

        Args:
            number: The position of the boundary in BOUNDARIES.

        Returns:
            The execution.
        """
        execution, _ = entered(self._tree, self._take(2 * number + 1).result())
        return execution

    def close(self) -> None:
        """Cancel the cases that the runner did not take, and wait for the workers."""
        with self._lock:
            self._closed = True
            for flight in self._flights.values():
                flight.case.cancel()
            self._lock.notify_all()
        self._pool.shutdown(wait=True)

    def _take(self, position: int) -> _Flight:
        """Return the case at a position once it has ended.

        The workers can then run up to `workers` positions past it.
        """
        with self._lock:
            flight = self._flight_at(position)
            self._taken = max(self._taken, position + 1)
            self._lock.notify_all()
        flight.done.wait()
        with self._lock:
            del self._flights[position]
        return flight

    def _work(self) -> None:
        """Run cases until the run closes."""
        with self._lock:
            flight = self._claim()
            while flight is not None:
                self._lock.release()
                flight.run(self._body)
                self._lock.acquire()
                flight = self._claim()

    def _claim(self) -> _Flight | None:
        """Return the next case for a worker, or None once the run has closed.

        A replayed case comes first, then the next case ahead while it is at
        most `workers` positions past the runner. The worker waits while
        neither is there. The caller has acquired the lock.
        """
        while not self._closed:
            if self._replays:
                return self._replays.popleft()
            if self._next < self._taken + self._workers:
                flight = self._flight_at(self._next)
                self._next += 1
                return flight
            self._lock.wait()
        return None

    def _flight_at(self, position: int) -> _Flight:
        """Return the case at a position, and make it when it does not exist yet.

        The caller has acquired the lock.
        """
        flight = self._flights.get(position)
        if flight is None:
            index = _random_at(position)
            if index is None:
                flight = _Flight(Edge(BOUNDARIES[position // 2]), self._max_choices)
            else:
                trail = Trailing(case_source(self._seed, index))
                flight = _Flight(trail, self._max_choices, trail)
            self._flights[position] = flight
        return flight
