"""The search for the smallest case that fails in the same way.

A case is smaller than another when its choice sequence is shorter. Of two
sequences of the same length, the smaller has the smaller first choice where
the two differ.

Before the shrink, the failing case replays once from its choices. A replay
that requests another choice, observes another fingerprint or ends in
another way makes the run flaky.

The shrinker runs its passes in rounds over the best case of one failure.
It stops after a round that does not accept a candidate. delete-and-lower
runs only in a round in which no other pass accepted a candidate. A
candidate runs only when it is smaller than the best case and no earlier
candidate had the same choices. The shrinker accepts it when its run fails
with the same identity and the recorded choices of the run are smaller than
those of the best case. A run that fails with another identity becomes a
further failure. The shrinker shrinks the failures one at a time. It starts
with the failure that has the smallest case. All failures share one budget
of runs.

The explain phase then fills each draw of the counterexample with four
random values. When every filling of a draw still fails in the same way,
any value of the draw fails. For an integer draw that matters, the nearest
passing value is one step towards its target, when that step passes.
"""

from __future__ import annotations

import functools
import itertools
import math
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any, cast

from dokimi_assert._prop.engine.case import (
    Case,
    Drawn,
    Failed,
    Generating,
    Rejected,
    Replaying,
    Request,
    Span,
    Where,
)
from dokimi_assert._prop.engine.choice import (
    Bounds,
    Choice,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
    Value,
    choice_of,
)
from dokimi_assert._prop.engine.execution import (
    Body,
    Divergence,
    Execution,
    Observer,
    Phase,
    execute,
    identity_of,
    repeat,
    unobserved,
)
from dokimi_assert._prop.engine.float import INTEGRAL_LIMIT, Key
from dokimi_assert._prop.engine.generator import Deferred, Integer, Mapped
from dokimi_assert._prop.engine.order import choice_key, shortlex
from dokimi_assert._prop.engine.source import MASK, Source
from dokimi_assert._prop.engine.tokens import encode

__all__ = [
    "DEFAULT_BUDGET",
    "Exhausted",
    "Explained",
    "Failure",
    "Node",
    "Shrinker",
    "confirm",
    "explain",
    "explain_seed",
    "nodes_of",
]

#: The number of runs of the body that shrinking every failure of a run can
#: spend.
DEFAULT_BUDGET = 2000

#: The number of random fillings that the explain phase tries for each draw.
_EXPLAIN_FILLINGS = 4

#: The number of probes that _find_integer makes one by one before it starts
#: doubling.
_LINEAR_PROBES = 4

#: The smallest number of siblings that delete-span-chunk deletes at once.
#: delete-span deletes one.
_SMALLEST_CHUNK = 2


class Exhausted(BaseException):
    """The signal that the shrink budget is spent."""

    def __init__(self) -> None:
        """Return the signal."""
        super().__init__("prop: the shrink budget is spent")


@dataclass(frozen=True, slots=True)
class Node:
    """One recorded choice with its request.

    Attributes:
        request: The request.
        choice: The choice.
    """

    request: Request
    choice: Choice


@dataclass(frozen=True, slots=True)
class Failure:
    """The smallest case found so far that fails with one identity.

    Attributes:
        identity: The identity of the failure.
        execution: The run of the case.
        nodes: The choices of the case with their requests.
        keys: The sort keys of the choices.
    """

    identity: str
    execution: Execution
    nodes: tuple[Node, ...]
    keys: tuple[Key, ...]


@dataclass(frozen=True, slots=True)
class Explained:
    """The explanation of one draw of the counterexample.

    Attributes:
        label: The label of the draw.
        value: The value of the draw.
        any_value_fails: True when every filling of the draw fails in the
            same way. It is None when the draw does not make a choice, when
            no filling decodes, or when the budget was spent before the
            fillings.
        nearest: The value one step towards the target in a tuple of one,
            for an integer draw where that value passes. It is None
            otherwise.
    """

    label: str
    value: Any
    any_value_fails: bool | None
    nearest: tuple[object] | None


#: The choices of a case with their requests. The passes edit them.
Nodes = Sequence[Node]


def nodes_of(c: Case) -> list[Node]:
    """Return the choices of a case with their requests.

    Args:
        c: The case.

    Returns:
        The nodes.
    """
    return [
        Node(request, choice)
        for request, choice in zip(c.requests, c.choices, strict=True)
    ]


def _keys_of(nodes: Nodes) -> tuple[Key, ...]:
    """Return the keys of the choices of nodes."""
    return tuple(choice_key(node.request.bounds, node.choice.value) for node in nodes)


def _find_integer(f: Callable[[int], bool]) -> int:
    """Return a k with f(k) true and f(k + 1) false. f(0) must be true.

    It probes 1, 2, 3 and 4, then doubles until f fails, then bisects.
    """
    for k in range(1, _LINEAR_PROBES + 1):
        if not f(k):
            return k - 1
    low = _LINEAR_PROBES
    high = _LINEAR_PROBES + 1
    while f(high):
        low = high
        high *= 2
    while low + 1 < high:
        middle = (low + high) // 2
        if f(middle):
            low = middle
        else:
            high = middle
    return low


def _search(position: int, at: Callable[[int], bool]) -> bool:
    """Try position 0, then bisect towards the smallest position that at accepts.

    at(p) runs the candidate at position p of an order whose position 0 is
    the target. It returns True when the shrinker accepted the candidate.
    position is the current position. The result is True when the shrinker
    accepted any candidate.
    """
    if position == 0:
        return False
    if at(0):
        return True
    low = 0
    high = position
    improved = False
    while high - low > 1:
        middle = (low + high) // 2
        if at(middle):
            high = middle
            improved = True
        else:
            low = middle
    return improved


def explain_seed(seed: int, draw: int, filling: int) -> int:
    """Return the seed of a filling of a draw: seed + (draw + 1) * 2^32 + filling.

    The sum is modulo 2^64.

    Args:
        seed: The seed of the run.
        draw: The position of the draw in the case.
        filling: The position of the filling.

    Returns:
        The seed.
    """
    return (seed + ((draw + 1) << 32) + filling) & MASK


def confirm(
    body: Body,
    failing: Execution,
    max_choices: int,
    observer: Observer = unobserved,
) -> Divergence | None:
    """Replay a failing case once, and return the first difference of the replay.

    The comparison takes the bounds of the requests first, then the observed
    fingerprints, then the way the replay ended. The divergence of a request
    or a fingerprint has the label and the step of the replay at that
    position.

    Args:
        body: The body.
        failing: The failing execution.
        max_choices: The largest number of choices of a case.
        observer: The observer of the replay.

    Returns:
        The divergence, or None when the replay fails in the same way.
    """
    replay = execute(body, Replaying(failing.case.choices), max_choices)
    observer("replay", replay)
    recorded = failing.case.requests
    replayed = replay.case.requests
    for i in range(max(len(recorded), len(replayed))):
        before = recorded[i].bounds if i < len(recorded) else None
        after = replayed[i].bounds if i < len(replayed) else None
        if before != after:
            wheres = replay.case.wheres
            where = wheres[i] if i < len(wheres) else Where()
            return Divergence("request", i, before, after, where.label, where.place)
    fingerprints = failing.case.fingerprints
    observed = replay.case.fingerprints
    for i in range(max(len(fingerprints), len(observed))):
        first = fingerprints[i] if i < len(fingerprints) else None
        second = observed[i] if i < len(observed) else None
        if first != second:
            places = replay.case.observed
            where = places[i] if i < len(places) else Where()
            return Divergence("fingerprint", i, first, second, where.label, where.place)
    if identity_of(replay) != identity_of(failing):
        return Divergence(
            "verdict",
            len(failing.case.choices),
            identity_of(failing),
            identity_of(replay),
        )
    return None


def _replaced(nodes: Nodes, index: int, value: Value) -> list[Node]:
    """Return nodes with the value of one choice replaced."""
    node = nodes[index]
    changed = Node(node.request, choice_of(node.request.bounds, value))
    return [*nodes[:index], changed, *nodes[index + 1 :]]


def _without(nodes: Nodes, start: int, end: int) -> list[Node]:
    """Return nodes without the nodes from start up to end."""
    return [*nodes[:start], *nodes[end:]]


def _at_target(node: Node) -> Node:
    """Return the node with its choice at its target."""
    bounds = node.request.bounds
    return Node(node.request, choice_of(bounds, bounds.target))


def _children(spans: Sequence[Span], parent: int | None) -> list[Span]:
    """Return the children of parent in order."""
    return [span for span in spans if span.parent == parent]


def _parents_of(spans: Sequence[Span]) -> list[int | None]:
    """Return the parent of each group of siblings in descending order.

    The parent of the top level is None, and None comes last.
    """
    parents: list[int | None] = []
    parents.extend(
        sorted({s.parent for s in spans if s.parent is not None}, reverse=True)
    )
    if spans:
        parents.append(None)
    return parents


def _groups_of(spans: Sequence[Span]) -> list[list[Span]]:
    """Return the groups of siblings in the order of _parents_of."""
    return [_children(spans, parent) for parent in _parents_of(spans)]


def _descendants(spans: Sequence[Span], index: int) -> list[Span]:
    """Return the descendants of the span at index in order."""
    inside = {index}
    found: list[Span] = []
    for later in range(index + 1, len(spans)):
        span = spans[later]
        if span.parent is None or span.parent not in inside:
            break
        inside.add(later)
        found.append(span)
    return found


def _latest_first(spans: Sequence[Span]) -> list[Span]:
    """Return the spans in descending order of their start.

    Of two spans with one start, the longer comes first.
    """
    return sorted(spans, key=lambda span: (-span.start, -span.end))


def _largest_power(count: int) -> int:
    """Return the largest power of two that is count or less, and 0 for 0."""
    return 0 if count == 0 else 1 << (count.bit_length() - 1)


def _floor_shift(n: int, k: int) -> int:
    """Return n * 2^-k rounded down. k is at least 0."""
    return n >> k


def _ceil_shift(n: int, k: int) -> int:
    """Return n * 2^-k rounded up. k is at least 0."""
    return -(-n >> k)


def _rounded_floats(value: float, bounds: FloatBounds) -> Iterator[float]:
    """Yield the roundings of a fraction to each smaller number of fractional bits.

    The roundings to 0 bits come first. At each number of bits, the function
    yields the value rounded towards the target and then the value rounded
    away from it. It yields only the roundings that the bounds admit. An
    integral value, an infinity and NaN do not have a rounding.
    """
    if not math.isfinite(value):
        return
    numerator, denominator = value.as_integer_ratio()
    bits = denominator.bit_length() - 1
    downward = value > bounds.target
    roundings = (_floor_shift, _ceil_shift) if downward else (_ceil_shift, _floor_shift)
    for fraction_bits in range(bits):
        shift = bits - fraction_bits
        for rounding in roundings:
            candidate = float(rounding(numerator, shift)) * 2.0**-fraction_bits
            if bounds.admits(candidate):
                yield candidate


def _stepped_at(nodes: Nodes, index: int) -> list[Node] | None:
    """Return nodes with the integer at index stepped once towards its target.

    The result is None for a choice that is not an integer and for an integer
    at its target.
    """
    node = nodes[index]
    bounds = node.request.bounds
    if not isinstance(bounds, IntegerBounds):
        return None
    value = cast("int", node.choice.value)
    target = bounds.target
    if value == target:
        return None
    return _replaced(nodes, index, value - 1 if value > target else value + 1)


def _sequence_deletions(nodes: Nodes, index: int) -> Iterator[list[Node]]:
    """Yield nodes with 2^k consecutive elements deleted from the sequence at index.

    The largest k comes first. For each k, the last run comes first. No
    deletion takes the sequence below its min_size. A choice of another
    kind does not yield a candidate.
    """
    node = nodes[index]
    bounds = node.request.bounds
    if not isinstance(bounds, SequenceBounds):
        return
    elements = cast("tuple[int, ...]", node.choice.value)
    count = len(elements)
    size = _largest_power(count)
    while size >= 1:
        if count - size >= bounds.min_size:
            for first in range(count - size, -1, -1):
                kept = elements[:first] + elements[first + size :]
                yield _replaced(nodes, index, kept)
        size //= 2


def _element_deletions(nodes: Nodes, index: int) -> Iterator[list[Node]]:
    """Yield nodes with one element deleted from the sequence at index.

    The last element comes first. A sequence that is not longer than its
    min_size does not yield a candidate. A choice of another kind does not
    yield one either.
    """
    node = nodes[index]
    bounds = node.request.bounds
    if not isinstance(bounds, SequenceBounds):
        return
    elements = cast("tuple[int, ...]", node.choice.value)
    if len(elements) <= bounds.min_size:
        return
    for position in range(len(elements) - 1, -1, -1):
        yield _replaced(nodes, index, elements[:position] + elements[position + 1 :])


def _free_structure(node: Node) -> bool:
    """Report whether a choice decides structure and allows two values or more."""
    bounds = node.request.bounds
    return (
        node.request.edge is not None
        and isinstance(bounds, IntegerBounds)
        and bounds.lo < bounds.hi
    )


def _duplicates(nodes: Nodes) -> list[list[int]]:
    """Return the groups of choices that share their bounds and their value.

    A choice at its target does not belong to a group.
    """
    shared: dict[tuple[Bounds, str], list[int]] = {}
    for index, node in enumerate(nodes):
        bounds = node.request.bounds
        if choice_key(bounds, node.choice.value) == choice_key(bounds, bounds.target):
            continue
        shared.setdefault((bounds, encode([node.choice])), []).append(index)
    return [indices for indices in shared.values() if len(indices) > 1]


def _next_with_bounds(nodes: Nodes, index: int) -> int | None:
    """Return the index of the next node with the bounds of the node at index.

    The result is None when no later node has those bounds.
    """
    bounds = nodes[index].request.bounds
    for later in range(index + 1, len(nodes)):
        if nodes[later].request.bounds == bounds:
            return later
    return None


@dataclass(frozen=True, slots=True)
class _Candidate:
    """The choices and the token of a candidate of a pass."""

    choices: list[Choice]
    token: str


class Shrinker:
    """The shrink of every failure of one run within one budget.

    Attributes:
        budget: The number of runs of the body that the shrink can spend.
        runs: The number of runs spent.
        workers: The number of candidates and fillings that run at once.
        failures: The smallest case of each identity in the order of
            discovery.
    """

    def __init__(
        self,
        body: Body,
        first: Execution,
        max_choices: int,
        budget: int,
        observer: Observer = unobserved,
        seconds: float = 0.0,
        workers: int = 1,
    ) -> None:
        """Return the shrinker that starts from the first failing case.

        Args:
            body: The body.
            first: The first failing execution.
            max_choices: The largest number of choices of a case.
            budget: The number of runs that the shrink can spend.
            observer: The observer of every run.
            seconds: The seconds that the shrink can take on the platform
                clock. 0 means no limit.
            workers: The number of candidates and fillings that run at once.
                It is at least 1.
        """
        self._body: Body = body
        self._max_choices: int = max_choices
        self._observer: Observer = observer
        self._deadline: float = time.monotonic() + seconds if seconds > 0 else math.inf
        self.budget: int = budget
        self.runs: int = 0
        self.workers: int = workers
        self.failures: dict[str, Failure] = {}
        self._sizes: dict[str, int] = {
            encode(first.case.choices): len(first.case.choices)
        }
        self._target: str = cast("str", identity_of(first))
        self._record(first)

    @property
    def best(self) -> Failure:
        """The failure that is being shrunk.

        Returns:
            The smallest failing case so far.
        """
        return self.failures[self._target]

    @property
    def nodes(self) -> tuple[Node, ...]:
        """The choices of the best case.

        Returns:
            The nodes of the choices, in order.
        """
        return self.best.nodes

    @property
    def spans(self) -> list[Span]:
        """The spans of the best case.

        Returns:
            The spans, in the order of their starts.
        """
        return self.best.execution.case.spans

    def _record(self, execution: Execution) -> None:
        """Keep a failing run when it is the first or the smallest of its identity."""
        identity = cast("str", identity_of(execution))
        nodes = tuple(nodes_of(execution.case))
        keys = _keys_of(nodes)
        known = self.failures.get(identity)
        if known is None or shortlex(keys) < shortlex(known.keys):
            self.failures[identity] = Failure(identity, execution, nodes, keys)

    def _room(self) -> int:
        """Return the number of runs that the budget has left.

        Raises:
            Exhausted: The budget or the time is spent.
        """
        if self.runs >= self.budget or time.monotonic() > self._deadline:
            raise Exhausted
        return self.budget - self.runs

    def _run_all(self, batch: Sequence[Sequence[Choice]]) -> list[Execution]:
        """Run the body once on each choice sequence of a batch at once.

        The first sequence runs on the calling thread. Each other sequence
        runs on a thread of its own. The runs come back in the order of the
        batch.
        """
        if len(batch) == 1:
            return [self._replay(batch[0])]
        with ThreadPoolExecutor(len(batch) - 1) as pool:
            later = [pool.submit(self._replay, choices) for choices in batch[1:]]
            first = self._replay(batch[0])
            return [first, *(future.result() for future in later)]

    def _replay(self, choices: Sequence[Choice]) -> Execution:
        """Run the body once on choices outside the case tree, without a later run."""
        return execute(self._body, Replaying(list(choices)), self._max_choices, limit=1)

    def run_each(
        self, batch: Sequence[Sequence[Choice]], phase: Phase = "shrink"
    ) -> Iterator[Execution]:
        """Run the body on each choice sequence of a batch at once, and yield the runs.

        The runs come in the order of the batch, in the same way as on one
        worker. A case with more than one repeat runs again before the
        iteration yields it. The repeats stop when the budget does not have
        room left. The iteration counts the runs of a case against the
        budget when it yields the case. The runs after an early stop then do
        not count. The batch runs only as far as the room of the budget
        allows.

        Args:
            batch: The choice sequences.
            phase: The phase of the runs.

        Yields:
            The executions.

        Raises:
            Exhausted: The budget or the time is spent before the batch ends.
        """
        room = self._room()
        taken = 0
        for once in self._run_all(batch[:room]):
            if room == 0:
                break
            execution = repeat(once, self._body, room)
            room -= execution.runs
            self.runs += execution.runs
            taken += 1
            self._observer(phase, execution)
            yield execution
        if taken < len(batch):
            raise Exhausted

    def run(self, choices: Sequence[Choice], phase: Phase = "shrink") -> Execution:
        """Run the body once on choices, and count the run against the budget.

        Args:
            choices: The choices.
            phase: The phase of the run.

        Returns:
            The execution.

        Raises:
            Exhausted: The budget or the time is spent.
        """
        return next(self.run_each([choices], phase))

    def _fresh(self, nodes: Nodes, batch: list[_Candidate]) -> _Candidate | None:
        """Return nodes as a candidate when they are smaller than the best case and new.

        A candidate is new when neither a run nor a candidate of the batch had
        the same choices.
        """
        if shortlex(_keys_of(nodes)) >= shortlex(self.best.keys):
            return None
        choices = [node.choice for node in nodes]
        token = encode(choices)
        if token in self._sizes or any(one.token == token for one in batch):
            return None
        return _Candidate(choices, token)

    def _settle(self, batch: list[_Candidate]) -> bool:
        """Run the candidates of a batch at once, and take their runs in order.

        The method stops at the first run that became the best case. Each run
        that it takes counts against the budget, records its size and keeps
        its failure.

        Returns:
            True when a run became the best case.

        Raises:
            Exhausted: The budget or the time is spent before the batch ends.
        """
        runs = self.run_each([candidate.choices for candidate in batch])
        for index, execution in enumerate(runs):
            self._sizes[batch[index].token] = len(execution.case.choices)
            if execution.failure is None:
                continue
            before = self.best
            self._record(execution)
            if self.best is not before:
                return True
        return False

    def _first(self, candidates: Iterable[Nodes]) -> bool:
        """Run candidates in order, up to workers of them at once.

        Returns:
            True when a candidate became the best case. The pass stops at
            that candidate.
        """
        batch: list[_Candidate] = []
        for nodes in candidates:
            candidate = self._fresh(nodes, batch)
            if candidate is None:
                continue
            batch.append(candidate)
            if len(batch) < self.workers:
                continue
            if self._settle(batch):
                return True
            batch = []
        return bool(batch) and self._settle(batch)

    def _consider(self, nodes: Nodes) -> bool:
        """Run a smaller new candidate, and report whether it became the best case."""
        return self._first([nodes])

    def shrink_all(self) -> None:
        """Shrink the failures one at a time from the failure with the smallest case.

        Shrinking stops when every failure is done or the budget is spent.
        Two failures of a body that is a function of its choices never have
        cases of equal keys, because equal keys are equal choices.
        """
        done: set[str] = set()
        try:
            while True:
                pending = [f for f in self.failures.values() if f.identity not in done]
                if not pending:
                    return
                target = min(pending, key=lambda failure: shortlex(failure.keys))
                self._shrink(target.identity)
                done.add(target.identity)
        except Exhausted:
            return

    def _shrink(self, identity: str) -> None:
        """Run rounds of every pass on one failure until a round accepts nothing."""
        self._target = identity
        passes: list[Callable[[], bool]] = [
            self._delete_span_chunk,
            self._delete_span,
            self._lift_descendant,
            self._delete_span_run,
            self._sequence_delete,
            self._delete_structure_pair,
            self._target_span,
            self._minimize_choice,
            self._sequence_lower,
            self._lower_and_delete,
            self._sort_siblings,
            self._redistribute,
            self._lower_together,
            self._minimize_duplicates,
            self._float_simplify,
        ]
        while True:
            improved = False
            for shrink_pass in passes:
                if shrink_pass():
                    improved = True
            if not improved and not self._delete_and_lower():
                return

    def _sweep(self, candidates: Callable[[], Iterator[list[Node]]]) -> bool:
        """Try the candidates in order, and start over after each acceptance.

        Each start takes the candidates of the new best case.
        """
        improved = False
        while self._first(candidates()):
            improved = True
        return improved

    def _delete_span_chunk(self) -> bool:
        """Delete 2^k consecutive siblings for k from the largest down to 1.

        For each k, the last chunk comes first.
        """

        def candidates() -> Iterator[list[Node]]:
            nodes = self.nodes
            for group in _groups_of(self.spans):
                count = len(group)
                size = _largest_power(count)
                while size >= _SMALLEST_CHUNK:
                    for first in range(count - size, -1, -1):
                        start = group[first].start
                        end = group[first + size - 1].end
                        if start < end:
                            yield _without(nodes, start, end)
                    size //= 2

        return self._sweep(candidates)

    def _delete_span(self) -> bool:
        """Delete one span in the order of _latest_first."""

        def candidates() -> Iterator[list[Node]]:
            nodes = self.nodes
            for span in _latest_first(self.spans):
                if span.start < span.end:
                    yield _without(nodes, span.start, span.end)

        return self._sweep(candidates)

    def _lift_descendant(self) -> bool:
        """Replace a span by a shorter descendant with the same label."""

        def candidates() -> Iterator[list[Node]]:
            nodes = self.nodes
            spans = self.spans
            for index, span in enumerate(spans):
                for inner in _descendants(spans, index):
                    shorter = inner.end - inner.start < span.end - span.start
                    if inner.label == span.label and shorter:
                        yield [
                            *nodes[: span.start],
                            *nodes[inner.start : inner.end],
                            *nodes[span.end :],
                        ]

        return self._sweep(candidates)

    def _delete_span_run(self) -> bool:
        """Delete the longest run of siblings that _find_integer finds at each start.

        The groups come in the order of _parents_of. Within a group, the runs
        start at the first sibling and move to the last.
        """
        improved = False
        for parent in _parents_of(self.spans):
            first = 0
            while first < len(_children(self.spans, parent)):
                group = _children(self.spans, parent)
                deleted = functools.partial(self._delete_run, self.nodes, group, first)
                if _find_integer(deleted) > 0:
                    improved = True
                first += 1
        return improved

    def _delete_run(
        self, original: Nodes, group: list[Span], first: int, count: int
    ) -> bool:
        """Consider original without count siblings of group from first."""
        if first + count > len(group):
            return False
        start = group[first].start
        end = group[first + count - 1].end
        return self._consider(_without(original, start, end))

    def _sequence_delete(self) -> bool:
        """Delete 2^k consecutive elements of each sequence.

        The candidates come in the order of _sequence_deletions.
        """

        def candidates() -> Iterator[list[Node]]:
            nodes = self.nodes
            for index in range(len(nodes)):
                yield from _sequence_deletions(nodes, index)

        return self._sweep(candidates)

    def _delete_structure_pair(self) -> bool:
        """Delete two adjacent free structure choices.

        The pairs come from the last to the first.
        """

        def candidates() -> Iterator[list[Node]]:
            nodes = self.nodes
            for first in range(len(nodes) - 2, -1, -1):
                if _free_structure(nodes[first]) and _free_structure(nodes[first + 1]):
                    yield _without(nodes, first, first + 2)

        return self._sweep(candidates)

    def _target_span(self) -> bool:
        """Set the choices of one span at a time to their targets."""

        def candidates() -> Iterator[list[Node]]:
            nodes = self.nodes
            for span in self.spans:
                yield [
                    *nodes[: span.start],
                    *map(_at_target, nodes[span.start : span.end]),
                    *nodes[span.end :],
                ]

        return self._sweep(candidates)

    def _lower(self, indices: list[int]) -> bool:
        """Move integer choices of one value together towards their target.

        The target comes first, then a binary search over the position of
        the value in the key order of its bounds.
        """
        nodes = self.nodes
        node = nodes[indices[0]]
        bounds = cast("IntegerBounds", node.request.bounds)
        value = cast("int", node.choice.value)

        def at(rank: int) -> bool:
            moved: Nodes = nodes
            for index in indices:
                moved = _replaced(moved, index, bounds.at_rank(rank))
            return self._consider(moved)

        return _search(bounds.rank(value), at)

    def _minimize_choice(self) -> bool:
        """Move the choices towards their targets one at a time."""
        improved = False
        index = 0
        while index < len(self.nodes):
            node = self.nodes[index]
            bounds = node.request.bounds
            if isinstance(bounds, IntegerBounds):
                accepted = self._lower([index])
            else:
                accepted = self._consider(_replaced(self.nodes, index, bounds.target))
            improved = accepted or improved
            index += 1
        return improved

    def _sequence_lower(self) -> bool:
        """Move each element of each sequence towards 0.

        The search tries 0 first, then bisects.
        """
        improved = False
        index = 0
        while index < len(self.nodes):
            position = 0
            while index < len(self.nodes) and position < self._length(index):
                improved = self._lower_element(index, position) or improved
                position += 1
            index += 1
        return improved

    def _length(self, index: int) -> int:
        """Return the length of the sequence at index, or 0 for another kind."""
        value = self.nodes[index].choice.value
        return len(value) if isinstance(value, tuple) else 0

    def _lower_element(self, index: int, position: int) -> bool:
        """Move one element of a sequence towards 0."""
        nodes = self.nodes
        elements = cast("tuple[int, ...]", nodes[index].choice.value)

        def at(element: int) -> bool:
            changed = (*elements[:position], element, *elements[position + 1 :])
            return self._consider(_replaced(nodes, index, changed))

        return _search(elements[position], at)

    def _lower_and_delete(self) -> bool:
        """Step each integer towards its target, and delete a later span with the step.

        After a step with a deletion, the pass tries the same integer again.
        After a step alone, it moves to the next integer.
        """
        improved = False
        index = 0
        while index < len(self.nodes):
            before = self.best
            deleted = self._step_and_delete(index)
            improved = improved or self.best is not before
            if not deleted:
                index += 1
        return improved

    def _step_and_delete(self, index: int) -> bool:
        """Step the integer at index by one, alone and then with a later span deleted.

        The result is True when the shrinker accepted a step with a deletion.
        The pass tries the deletions only when the step alone makes the run
        record another number of choices. Each candidate deletes one span
        that starts after the integer. The span that starts last comes first.
        A step that the shrinker did not accept has an entry in the sizes of
        the runs, because _consider ran it now or earlier.
        """
        nodes = self.nodes
        stepped = _stepped_at(nodes, index)
        if stepped is None or self._consider(stepped):
            return False
        if self._sizes[encode([node.choice for node in stepped])] == len(nodes):
            return False
        later = [span for span in self.spans if index < span.start < span.end]
        for span in _latest_first(later):
            if self._consider(_without(stepped, span.start, span.end)):
                return True
        return False

    def _delete_and_lower(self) -> bool:
        """Step each integer towards its target with earlier choices deleted.

        The first candidates of an integer delete one span that is not empty
        and ends at or before the integer. The span that starts last comes
        first. The next candidates delete one element of an earlier
        sequence, from the last element of the last sequence.
        """

        def candidates() -> Iterator[list[Node]]:
            nodes = self.nodes
            spans = self.spans
            for index in range(len(nodes)):
                stepped = _stepped_at(nodes, index)
                if stepped is None:
                    continue
                earlier = [span for span in spans if span.start < span.end <= index]
                for span in _latest_first(earlier):
                    yield _without(stepped, span.start, span.end)
                for at in range(index - 1, -1, -1):
                    yield from _element_deletions(stepped, at)

        return self._sweep(candidates)

    def _sort_siblings(self) -> bool:
        """Swap adjacent siblings with one label when the later one is smaller."""

        def candidates() -> Iterator[list[Node]]:
            nodes = self.nodes
            for group in _groups_of(self.spans):
                for left, right in itertools.pairwise(group):
                    first = nodes[left.start : left.end]
                    second = nodes[right.start : right.end]
                    smaller = shortlex(_keys_of(second)) < shortlex(_keys_of(first))
                    if left.label == right.label and smaller:
                        yield [
                            *nodes[: left.start],
                            *second,
                            *nodes[left.end : right.start],
                            *first,
                            *nodes[right.end :],
                        ]

        return self._sweep(candidates)

    def _redistribute(self) -> bool:
        """Move value from each integer to the next one with its bounds.

        A move does not change the sum of the two values.
        """
        improved = False
        index = 0
        while index < len(self.nodes):
            improved = self._move(index) or improved
            index += 1
        return improved

    def _move(self, index: int) -> bool:
        """Move value from the integer at index to the next one with its bounds.

        The whole distance comes first, then a binary search.
        """
        nodes = self.nodes
        node = nodes[index]
        bounds = node.request.bounds
        later = _next_with_bounds(nodes, index)
        if not isinstance(bounds, IntegerBounds) or later is None:
            return False
        value = cast("int", node.choice.value)
        target = bounds.target
        if value == target:
            return False
        other = cast("int", nodes[later].choice.value)
        sign = 1 if value > target else -1

        def tried(amount: int) -> bool:
            raised = other + sign * amount
            if not bounds.admits(raised):
                return False
            moved = _replaced(nodes, index, value - sign * amount)
            return self._consider(_replaced(moved, later, raised))

        distance = abs(value - target)
        if tried(distance):
            return True
        low = 0
        high = distance
        improved = False
        while high - low > 1:
            middle = (low + high) // 2
            if tried(middle):
                low = middle
                improved = True
            else:
                high = middle
        return improved

    def _lower_together(self) -> bool:
        """Move each integer and the next one with its bounds by one amount.

        Both move towards their target.
        """
        improved = False
        index = 0
        while index < len(self.nodes):
            improved = self._lower_pair(index) or improved
            index += 1
        return improved

    def _lower_pair(self, index: int) -> bool:
        """Move the integer at index and the next one with its bounds by one amount.

        Both must be on one side of the target.
        """
        nodes = self.nodes
        node = nodes[index]
        bounds = node.request.bounds
        later = _next_with_bounds(nodes, index)
        if not isinstance(bounds, IntegerBounds) or later is None:
            return False
        value = cast("int", node.choice.value)
        other = cast("int", nodes[later].choice.value)
        target = bounds.target
        if (value > target) != (other > target) or target in (value, other):
            return False
        step = -1 if value > target else 1
        room = min(abs(value - target), abs(other - target))

        def moved(amount: int) -> bool:
            if amount > room:
                return False
            lowered = _replaced(nodes, index, value + step * amount)
            return self._consider(_replaced(lowered, later, other + step * amount))

        return _find_integer(moved) > 0

    def _minimize_duplicates(self) -> bool:
        """Move the choices of each group of duplicates towards the target together."""
        improved = False
        group = 0
        while True:
            groups = _duplicates(self.nodes)
            if group >= len(groups):
                return improved
            indices = groups[group]
            if isinstance(self.nodes[indices[0]].request.bounds, IntegerBounds):
                improved = self._lower(indices) or improved
            else:
                moved = list(self.nodes)
                for index in indices:
                    moved[index] = _at_target(moved[index])
                improved = self._consider(moved) or improved
            group += 1

    def _float_simplify(self) -> bool:
        """Simplify the floats one at a time.

        A float first takes fewer fractional bits, then a smaller integral
        value.
        """
        improved = False
        index = 0
        while index < len(self.nodes):
            node = self.nodes[index]
            bounds = node.request.bounds
            if isinstance(bounds, FloatBounds):
                value = cast("float", node.choice.value)
                rounded = (
                    _replaced(self.nodes, index, candidate)
                    for candidate in _rounded_floats(value, bounds)
                )
                improved = self._first(rounded) or improved
                improved = self._lower_float(index) or improved
            index += 1
        return improved

    def _lower_float(self, index: int) -> bool:
        """Move an integral float as an integer towards an integral target.

        The search runs over the integers of the bounds below 2^53 in
        magnitude in their key order. It skips an integer that is not a value
        of the width of the float.
        """
        nodes = self.nodes
        node = nodes[index]
        bounds = cast("FloatBounds", node.request.bounds)
        value = cast("float", node.choice.value)
        target = bounds.target
        integral = (
            value.is_integer()
            and target.is_integer()
            and abs(value) < INTEGRAL_LIMIT
            and abs(target) < INTEGRAL_LIMIT
        )
        if not integral:
            return False
        limit = INTEGRAL_LIMIT - 1
        lo = -limit if bounds.lo < -limit else math.ceil(bounds.lo)
        hi = limit if bounds.hi > limit else math.floor(bounds.hi)
        integers = IntegerBounds(lo, hi)

        def tried(rank: int) -> bool:
            candidate = float(integers.at_rank(rank))
            if not bounds.admits(candidate):
                return False
            return self._consider(_replaced(nodes, index, candidate))

        return _search(integers.rank(int(value)), tried)


def _filled(
    nodes: Nodes, span: Span, drawn: Drawn, source: Source
) -> list[Choice] | None:
    """Return the choices with the span of one draw replaced by a filling from source.

    A decode that rejects the case, passes the cap on choices or fails does
    not return a value. Such a decode does not give a filling, and the result
    is None.
    """
    fresh = Case(Generating(source))
    try:
        drawn.generator.decode(fresh)
    except (Rejected, Failed):
        return None
    before = [node.choice for node in nodes[: span.start]]
    after = [node.choice for node in nodes[span.end :]]
    return [*before, *fresh.choices, *after]


def _relevance(
    shrinker: Shrinker,
    failure: Failure,
    span: Span,
    drawn: Drawn,
    seeds: list[int],
) -> bool | None:
    """Run the fillings of one draw from seeds, and report whether any value fails.

    The result is True when every filling that decoded fails in the same
    way. It is False at the first filling that does not, and None when no
    filling decoded. A filling whose decode does not return a value does not
    cost a run. Up to workers fillings run at once, and their runs count in
    order.
    """
    relevance: bool | None = None
    pending = deque(seeds)
    while pending:
        batch: list[list[Choice]] = []
        while pending and len(batch) < shrinker.workers:
            choices = _filled(failure.nodes, span, drawn, Source(pending.popleft()))
            if choices is not None:
                batch.append(choices)
        if not batch:
            break
        for execution in shrinker.run_each(batch, "explain"):
            if identity_of(execution) != failure.identity:
                return False
        relevance = True
    return relevance


def _nearest(
    shrinker: Shrinker, nodes: Nodes, span: Span, drawn: Drawn
) -> tuple[object] | None:
    """Return the value one step from an integer draw towards its target.

    The result is None unless the case passes with that value. A map of an
    integer is an integer draw too. Its integer is its choice, and its
    nearest passing value is what the map returns for the step. A deferred
    generator is the generator that it picks.
    """
    generator: object = drawn.generator
    maps: list[Mapped[Any, Any]] = []
    with ExitStack() as picks:
        while isinstance(generator, (Mapped, Deferred)):
            if isinstance(generator, Deferred):
                deferred: Deferred[Any] = generator
                generator = picks.enter_context(deferred.picked())
                continue
            mapped: Mapped[Any, Any] = generator
            maps.append(mapped)
            generator = mapped.of
    value = nodes[span.start].choice.value if maps else drawn.value
    if not isinstance(generator, Integer) or not isinstance(value, int):
        return None
    target = generator.bounds.target
    if value == target:
        return None
    stepped = value - 1 if value > target else value + 1
    choices = [node.choice for node in _replaced(nodes, span.start, stepped)]
    if shrinker.run(choices, "explain").status != "passed":
        return None
    found: object = stepped
    for mapped in reversed(maps):
        found = mapped.f(found)
    return (found,)


def explain(shrinker: Shrinker, failure: Failure, seed: int) -> list[Explained]:
    """Explain each draw of the case of a failure.

    The runs spend the rest of the budget of the shrinker. Filling j of draw
    d decodes from the stream of seed + (d + 1) * 2^32 + j.

    Args:
        shrinker: The shrinker. The runs spend its budget.
        failure: The failure.
        seed: The seed of the run.

    Returns:
        The explanation of each draw.
    """
    c = failure.execution.case
    explained: list[Explained] = []
    for number, drawn in enumerate(c.draws):
        span = c.spans[drawn.span]
        unexplained = Explained(drawn.label, drawn.value, None, None)
        if span.start == span.end:
            explained.append(unexplained)
            continue
        seeds = [explain_seed(seed, number, j) for j in range(_EXPLAIN_FILLINGS)]
        try:
            any_value = _relevance(shrinker, failure, span, drawn, seeds)
            near = None
            if any_value is False:
                near = _nearest(shrinker, failure.nodes, span, drawn)
            explained.append(Explained(drawn.label, drawn.value, any_value, near))
        except Exhausted:
            explained.append(unexplained)
    return explained
