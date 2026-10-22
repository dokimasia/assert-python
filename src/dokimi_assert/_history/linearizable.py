# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The check that a history is linearizable.

Each partition of a linearizable history has an order of its calls that
respects their real-time order. The spec accepts that order.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from dokimi_assert._history.history import History, recorded
from dokimi_assert._history.option import Option, configure
from dokimi_assert._history.partition import (
    Checked,
    Partition,
    Span,
    calls_of,
    concurrency,
    partitions_of,
    span_json,
)
from dokimi_assert._history.search import (
    Deadline,
    Ending,
    Limit,
    Search,
    SpecError,
    Verdict,
)
from dokimi_assert._matcher.fault import FaultError, of_operation
from dokimi_assert._matcher.seat import Mode, Seat
from dokimi_assert._matcher.verdict import Running
from dokimi_assert._record.literal import detail as literal_of
from dokimi_assert.failure import Failure, call_site

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from dokimi_assert._history.spec import Spec

__all__ = [
    "LINEARIZABLE",
    "Detail",
    "check",
    "detail_json",
    "fields_of",
    "is_linearizable",
    "whole",
]

_S = TypeVar("_S")

#: The id of the assertion of linearizability.
LINEARIZABLE = "linearizable"

#: The name of the assertion. The text of each fault of a check starts with it.
_OP = "history.is_linearizable"


@dataclass(frozen=True, slots=True)
class Detail(Generic[_S]):
    """The detail of the record of a check of linearizability.

    The detail has the ten fields of the definition. A check that passed has
    the outcome, the partitions and the steps. Its fields of a reported
    partition are empty.

    Attributes:
        outcome: The verdict of the check.
        partitions: The number of partitions.
        steps: The steps of each partition up to and including the reported
            one. A check that passed counts the steps of every partition.
        partition: The keys of the reported partition. It is empty for a
            partition of every key.
        calls: The number of calls of the reported partition.
        concurrency: The most calls of the reported partition that are open
            at one event.
        linearized: The order of the calls of the frontier.
        states: The states of the frontier.
        candidates: The calls that the spec rejected at the frontier.
        limit: The limit that stopped an undecided check. It is None for a
            violated check.
    """

    outcome: Verdict
    partitions: int
    steps: int
    partition: tuple[Any, ...]
    calls: int
    concurrency: int
    linearized: tuple[Span, ...]
    states: tuple[_S, ...]
    candidates: tuple[Span, ...]
    limit: Limit | None


def _reported(
    p: Partition, ending: Ending[_S], partitions: int, steps: int
) -> Detail[_S]:
    """Return the detail of a check that reports partition p and its ending."""

    def spans(positions: tuple[int, ...]) -> tuple[Span, ...]:
        return tuple(p.calls[position].span for position in positions)

    return Detail(
        ending.outcome,
        partitions,
        steps,
        p.keys,
        len(p.calls),
        concurrency(p.calls),
        spans(ending.linearized),
        ending.states,
        spans(ending.candidates),
        ending.limit,
    )


def _passed(partitions: int, steps: int) -> Detail[Any]:
    """Return the detail of a passed check from its counts."""
    return Detail("passed", partitions, steps, (), 0, 0, (), (), (), None)


#: The fewest partitions whose searches run on the threads of the workers.
_PARALLEL_PARTITIONS = 2


def _endings(
    partitions: Sequence[Partition],
    workers: int,
    run: Callable[[Sequence[Checked]], Ending[_S]],
) -> tuple[Callable[[int], Ending[_S]], Callable[[], None]]:
    """Return the ending of each partition by position, and the stop of the searches.

    With one worker, the ending of a partition runs its search. With more
    workers, the searches run on that many threads in partition order. The
    ending of a partition then waits for its search. The stop cancels the
    searches that have not started and waits for the others.
    """
    if workers == 1 or len(partitions) < _PARALLEL_PARTITIONS:
        return (lambda i: run(partitions[i].calls)), lambda: None
    pool = ThreadPoolExecutor(min(workers, len(partitions)))
    futures: list[Future[Ending[_S]]] = [pool.submit(run, p.calls) for p in partitions]

    def stop() -> None:
        pool.shutdown(wait=True, cancel_futures=True)

    return (lambda i: futures[i].result()), stop


def check(history: History, spec: Spec[_S], options: Sequence[Option]) -> Detail[_S]:
    """Check history against spec under options.

    The detail reports the first violated partition. When the check does not
    find a violated partition, the detail reports the first undecided
    partition, or else a pass.

    Args:
        history: The history.
        spec: The spec.
        options: The limits and the workers of the check.

    Returns:
        The detail.

    Raises:
        SpecError: A function of the spec raises.
    """
    config = configure(options)
    deadline = Deadline(config.time_limit)
    events, ids = recorded(history)
    partitions = partitions_of(calls_of(events, ids))

    def run(calls: Sequence[Checked]) -> Ending[_S]:
        return Search(calls, spec, config, deadline).run()

    ending_of, stop = _endings(partitions, config.workers, run)
    try:
        steps = 0
        undecided: Detail[_S] | None = None
        for i, p in enumerate(partitions):
            ending = ending_of(i)
            steps += ending.steps
            if ending.outcome == "passed":
                continue
            detail = _reported(p, ending, len(partitions), steps)
            if ending.outcome == "violated":
                return detail
            if undecided is None:
                undecided = detail
        return undecided if undecided is not None else _passed(len(partitions), steps)
    finally:
        deadline.stopped.set()
        stop()


def whole(history: History, spec: Spec[_S]) -> tuple[Detail[_S], tuple[_S, ...]]:
    """Check every call of history as one partition.

    The calls form one partition whatever keys they have. The check has the
    default limits. A machine of stateful checks the history of its steps
    this way, because its spec has one state for the whole subject. A history
    without calls passes without a partition.

    Args:
        history: The history.
        spec: The spec.

    Returns:
        The detail, and the states after the order that the search found. A
        history without calls has the initial state. The states are empty for
        a check that did not pass.

    Raises:
        SpecError: A function of the spec raises.
    """
    events, ids = recorded(history)
    calls = calls_of(events, ids)
    ending = Search(calls, spec, configure([]), Deadline(0)).run()
    if ending.outcome == "passed":
        return _passed(1 if calls else 0, ending.steps), ending.states
    reported = _reported(Partition((), tuple(calls)), ending, 1, ending.steps)
    return reported, ()


def fields_of(detail: Detail[Any]) -> dict[str, Any]:
    """Return the detail fields of the record of a failing check.

    Each field of the definition has its name and its Python value.

    Args:
        detail: The detail.

    Returns:
        The fields.
    """
    return {
        "outcome": detail.outcome,
        "partitions": detail.partitions,
        "steps": detail.steps,
        "partition": detail.partition,
        "calls": detail.calls,
        "concurrency": detail.concurrency,
        "linearized": detail.linearized,
        "states": detail.states,
        "candidates": detail.candidates,
        "limit": detail.limit,
    }


def detail_json(detail: Detail[Any]) -> dict[str, Any]:
    """Return the detail of a failing check as JSON.

    The call record of the check contains the JSON. The counts are numbers.
    Each key and each state is a typed literal. Each call has the JSON form
    of the history. The limit of a violated check is None.

    Args:
        detail: The detail.

    Returns:
        The JSON value.
    """
    return {
        "outcome": detail.outcome,
        "partitions": detail.partitions,
        "steps": detail.steps,
        "partition": [literal_of(key) for key in detail.partition],
        "calls": detail.calls,
        "concurrency": detail.concurrency,
        "linearized": [span_json(span) for span in detail.linearized],
        "states": [literal_of(state) for state in detail.states],
        "candidates": [span_json(span) for span in detail.candidates],
        "limit": detail.limit,
    }


def _refusal(history: object, spec: object) -> str | None:
    """Return why a check refuses its history and its spec, or None to run the check."""
    if not isinstance(history, History):
        return "the history is not a History"
    if not callable(getattr(spec, "initial", None)) or not callable(
        getattr(spec, "next", None)
    ):
        return "the spec does not have an initial and a next"
    return None


def is_linearizable(
    seat: Seat, history: History, spec: Spec[_S], msg: str, *options: Option
) -> None:
    """Fail when the calls of a partition of history do not have a linearization.

    A linearization is an order of the calls that respects their real-time
    order. spec must accept the order as a sequence. The failure is one
    record of the assertion linearizable. Its contract is msg. Its location
    is the call of is_linearizable.

    The check removes the calls that failed. A call that completed as ok is
    known. It takes effect between its invocation and its completion. A call
    whose outcome is unknown takes effect at some point after its
    invocation, or never. A pending call behaves the same way. Call a
    precedes call b in real time when a completed before b was invoked. Two
    calls that share a key are in one partition. A call without keys puts
    every call into one partition. The check searches each partition from
    the initial state of the spec. The definition fixes the search. The
    check reports the first violated partition in the order of first
    invocation. When it does not find a violated partition, it reports the
    first undecided partition. An undecided check fails in the same way as a
    violated check.

    The detail of the record has the ten fields of the definition. They are
    outcome, partitions, steps, partition, calls, concurrency, linearized,
    states, candidates and limit. linearized and candidates are spans of the
    calls of the history. limit is None for a violated check.

    The call ends with a fault for a history that is not a History, a spec
    without initial or next, and a function of the spec that raises. The
    fault of a function that raises contains the call that the search
    stepped.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        history: The history.
        spec: The sequential specification.
        msg: The contract under test.
        *options: The limits and the workers of the check.

    Example:
        history.is_linearizable(seat, h, Register(), "the register is linearizable")
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat)
    refused = _refusal(history, spec)
    if refused is not None:
        run.faulted(Mode.FATAL, LINEARIZABLE, msg, of_operation(_OP, refused))
        return
    try:
        detail = check(history, spec, options)
    except SpecError as raised:
        at = "" if raised.call is None else f"calls[{raised.call}]"
        cause = raised.__cause__
        fault = FaultError(at, str(raised), cause)
        run.faulted(Mode.FATAL, LINEARIZABLE, msg, of_operation(_OP, fault))
        return
    if detail.outcome == "passed":
        run.passed(Mode.FATAL, LINEARIZABLE, msg)
        return
    failure = Failure(LINEARIZABLE, msg, fields_of(detail), call_site())
    run.failed_run(Mode.FATAL, failure, detail_json(detail))
