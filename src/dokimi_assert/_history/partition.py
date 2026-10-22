# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The calls of a history that a check of linearizability reads, and their partitions.

The check removes every call that failed. Two calls that share a key are in
one partition. A call without keys touches every key, so it puts the whole
history into one partition. The partitions come in the order of their
first invocations.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dokimi_assert._history.event import Completion, Event, Invocation
from dokimi_assert._history.spec import CallOperation
from dokimi_assert._record.literal import detail as literal_of

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "Checked",
    "Partition",
    "Span",
    "calls_of",
    "concurrency",
    "partitions_of",
    "span_json",
]


@dataclass(frozen=True, slots=True)
class Span:
    """A call of a history, from its invocation to its completion.

    The record of a check has each call as a span.

    Attributes:
        call: The index of the invocation event of the call.
        completion: The index of the completion event of the call, or None
            for a pending call.
        process: The process that made the call.
        operation: The operation of the call that the spec receives.
    """

    call: int
    completion: int | None
    process: int
    operation: CallOperation


@dataclass(frozen=True, slots=True)
class Checked:
    """A call that a check reads.

    Attributes:
        span: The span of the call.
        keys: The keys that the call touches. It is empty for a call that
            touches every key.
        ids: The identities of the keys.
    """

    span: Span
    keys: tuple[Any, ...]
    ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Partition:
    """A group of calls that share keys. The check searches each group on its own.

    Attributes:
        keys: The keys of the calls without repeats. They are in the order of
            their first use. A partition of every key has an empty tuple.
        calls: The calls in event order.
    """

    keys: tuple[Any, ...]
    calls: tuple[Checked, ...]


def calls_of(events: Sequence[Event], ids: Sequence[tuple[str, ...]]) -> list[Checked]:
    """Return the calls of a history that did not fail.

    The calls are in event order. A call is known when it completed as ok.

    Args:
        events: The events of the history.
        ids: The identities of the keys of each event.

    Returns:
        The calls.
    """
    completions = {e.call: e for e in events if isinstance(e, Completion)}
    calls: list[Checked] = []
    for event in events:
        if not isinstance(event, Invocation):
            continue
        completion = completions.get(event.index)
        if completion is not None and completion.kind == "fail":
            continue
        known = completion is not None and completion.kind == "ok"
        output = completion.output if completion is not None and known else None
        operation = CallOperation(event.operation, event.args, known, output)
        index = None if completion is None else completion.index
        span = Span(event.index, index, event.process, operation)
        calls.append(Checked(span, event.keys, ids[event.index]))
    return calls


def _root(parent: list[int], position: int) -> int:
    """Return the root of the partition of a call. The search halves the path to it."""
    at = position
    while parent[at] != at:
        parent[at] = parent[parent[at]]
        at = parent[at]
    return at


def _keys_of(calls: Sequence[Checked]) -> tuple[Any, ...]:
    """Return each key of calls once in the order of first use."""
    seen: dict[str, Any] = {}
    for call in calls:
        for identity, key in zip(call.ids, call.keys, strict=True):
            seen.setdefault(identity, key)
    return tuple(seen.values())


def partitions_of(calls: Sequence[Checked]) -> list[Partition]:
    """Return the partitions of calls in the order of their first invocations.

    Args:
        calls: The calls in event order.

    Returns:
        The partitions.
    """
    if not calls:
        return []
    if any(not call.ids for call in calls):
        return [Partition((), tuple(calls))]
    parent = list(range(len(calls)))
    first: dict[str, int] = {}
    for position, call in enumerate(calls):
        for identity in call.ids:
            other = first.setdefault(identity, position)
            parent[_root(parent, position)] = _root(parent, other)
    groups: dict[int, list[Checked]] = {}
    for position, call in enumerate(calls):
        groups.setdefault(_root(parent, position), []).append(call)
    return [Partition(_keys_of(group), tuple(group)) for group in groups.values()]


def concurrency(calls: Sequence[Checked]) -> int:
    """Return the most calls that are open at one event.

    A call is open from its invocation to its completion. A call that is not
    known is open to the end of the history.

    Args:
        calls: The calls.

    Returns:
        The highest number of open calls.
    """
    changes: list[tuple[int, int]] = []
    for call in calls:
        span = call.span
        changes.append((span.call, 1))
        if span.operation.known and span.completion is not None:
            changes.append((span.completion, -1))
    changes.sort()
    return max(itertools.accumulate(change for _, change in changes), default=0)


def span_json(span: Span) -> dict[str, Any]:
    """Return a span in the JSON form of the history.

    The form has the call, the completion, the process, the operation, the
    arguments as typed literals, and the output as a typed literal. A
    pending call does not have a completion. A call that is not known does
    not have an output.

    Args:
        span: The span.

    Returns:
        The JSON value.
    """
    op = span.operation
    stated: dict[str, Any] = {"call": span.call}
    if span.completion is not None:
        stated["completion"] = span.completion
    stated["process"] = span.process
    stated["operation"] = op.name
    stated["args"] = [literal_of(arg) for arg in op.args]
    if op.known:
        stated["output"] = literal_of(op.output)
    return stated
