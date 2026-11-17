# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The searches that a check of linearizability keeps for the next check of its history.

A check with a checkpoint reads the events that the history recorded since
the check before it. A completion of a call that the kept check read as
pending makes the partition of the call search again from its first call,
and a call that fails leaves its partition. Each new call joins the
partitions of its keys, and a call without keys joins every partition. A
call that joins two or more partitions joins them into one, which searches
again from its first call. Each other partition grows its kept search by
its new calls, when the search fits the limits of the check.
"""

from __future__ import annotations

import bisect
import weakref
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from dokimi_assert._history.history import History, recorded
from dokimi_assert._history.partition import (
    Checked,
    Partition,
    Span,
    calls_from,
    partitions_of,
)
from dokimi_assert._history.search import Search
from dokimi_assert._history.spec import CallOperation

if TYPE_CHECKING:
    from dokimi_assert._history.event import Completion
    from dokimi_assert._history.option import Config
    from dokimi_assert._history.search import Deadline
    from dokimi_assert._history.spec import Spec

__all__ = ["Checkpoint", "forget", "resumed"]

_S = TypeVar("_S")


class Checkpoint(Generic[_S]):
    """The searches of the last check of a history that passed with it.

    history.resume passes a checkpoint to a check of linearizability. The
    check continues the search of each partition that the checkpoint keeps
    over the calls that the history recorded since, and keeps its own
    searches in the checkpoint when it passes. A check that does not pass
    leaves the checkpoint without a search. A continued search takes the
    steps that a search of every call takes after the order that the kept
    search found, so the check reports what a check of every call reports.

    Every check that passes one checkpoint passes the same spec, because the
    kept searches contain the states of that spec. A checkpoint is safe for
    one check at a time.

        h = history.History()
        checkpoint = history.Checkpoint()
        for value in range(100):
            h.invoke(0, "write", [value], "x").ok(None)
            history.is_linearizable(
                seat, h, Register(), "the register is linearizable",
                history.resume(checkpoint),
            )
    """

    def __init__(self) -> None:
        """Return a checkpoint that does not keep a search."""
        _STATES[self] = _State()


@dataclass(eq=False)
class _Part:
    """A partition of a checkpoint, and the kept search of its first calls.

    Attributes:
        keys: The keys of the calls in the order of their first use. A
            partition of every key has no key.
        calls: The calls of the partition in event order.
        search: The search of the first calls of the partition, or None for a
            partition that searches from its first call.
    """

    keys: list[Any]
    calls: list[Checked]
    search: Search[Any] | None = None


@dataclass(eq=False)
class _State:
    """The kept searches of a checkpoint, and the partitions of their history.

    Attributes:
        history: The history of the kept searches, or None for a checkpoint
            that keeps no search.
        whole: True when the kept check searched every call as one partition.
        events: The number of events that the kept check read.
        parts: The partitions.
        every: The partition that every new call joins, or None. It is the one
            partition of a check of whole, and of a history with a call
            without keys.
        key_of: The partition of the identity of each key.
        pending: The partition of each call that the kept check read as
            pending, by the index of its invocation.
    """

    history: History | None = None
    whole: bool = False
    events: int = 0
    parts: list[_Part] = field(default_factory=list)
    every: _Part | None = None
    key_of: dict[str, _Part] = field(default_factory=dict)
    pending: dict[int, _Part] = field(default_factory=dict)

    def complete(self, completion: Completion) -> None:
        """Record the completion of a call that the kept check read as pending.

        The partition of the call searches again from its first call. A call
        that failed leaves its partition. The other calls of the partition then
        form the partitions of a check of every call.
        """
        part = self.pending.pop(completion.call)
        part.search = None
        at = bisect.bisect_left(part.calls, completion.call, key=lambda c: c.span.call)
        call = part.calls[at]
        if completion.kind != "fail":
            known = completion.kind == "ok"
            op = call.span.operation
            output = completion.output if known else None
            operation = CallOperation(op.name, op.args, known, output)
            span = Span(call.span.call, completion.index, call.span.process, operation)
            part.calls[at] = Checked(span, call.keys, call.ids)
            return
        del part.calls[at]
        if self.whole:
            return
        for identity in call.ids:
            self.key_of.pop(identity, None)
        self.replace([part])

    def join(self, call: Checked) -> None:
        """Add a new call to the partitions that it joins.

        A call joins the partition of every key when there is one, every
        partition when it has no key, and the partitions of its keys
        otherwise.
        """
        if self.every is not None:
            self.extend(self.every, call)
        elif call.ids:
            self.join_keys(call)
        elif len(self.parts) == 1:
            self.extend(self.parts[0], call)
        else:
            self.replace(list(self.parts), call)

    def join_keys(self, call: Checked) -> None:
        """Add a new call with keys to the partition of its keys.

        A call whose keys belong to no partition starts one. A call whose keys
        belong to two or more partitions joins them into one.
        """
        found: _Part | None = None
        for identity in call.ids:
            part = self.key_of.get(identity)
            if part is None or part is found:
                continue
            if found is not None:
                joined: list[_Part] = []
                for other in call.ids:
                    kept = self.key_of.get(other)
                    if kept is not None and all(kept is not p for p in joined):
                        joined.append(kept)
                self.replace(joined, call)
                return
            found = part
        if found is None:
            found = _Part([], [])
            self.parts.append(found)
        self.extend(found, call)

    def extend(self, part: _Part, call: Checked) -> None:
        """Add a new call to part, and map its keys and a pending call to part."""
        part.calls.append(call)
        if call.span.completion is None:
            self.pending[call.span.call] = part
        if self.whole:
            return
        if not call.ids:
            part.keys = []
            self.every = part
        for identity, key in zip(call.ids, call.keys, strict=True):
            if self.key_of.get(identity) is part:
                continue
            self.key_of[identity] = part
            if part is not self.every:
                part.keys.append(key)

    def replace(self, old: list[_Part], *more: Checked) -> None:
        """Replace the partitions old with the partitions of their calls and of more.

        more are new calls, which follow every call of old. Each new partition
        searches from its first call.
        """
        calls = sorted((c for p in old for c in p.calls), key=lambda c: c.span.call)
        self.every = None
        self.parts = [p for p in self.parts if all(p is not q for q in old)]
        for partition in partitions_of([*calls, *more]):
            part = _Part(list(partition.keys), list(partition.calls))
            self.parts.append(part)
            if not part.keys:
                self.every = part
            for c in part.calls:
                for identity in c.ids:
                    self.key_of[identity] = part
                if c.span.completion is None:
                    self.pending[c.span.call] = part


#: The kept searches of each checkpoint.
_STATES: weakref.WeakKeyDictionary[Checkpoint[Any], _State] = (
    weakref.WeakKeyDictionary()
)


def resumed(
    checkpoint: Checkpoint[_S],
    history: History,
    spec: Spec[_S],
    config: Config,
    deadline: Deadline,
    *,
    whole: bool,
) -> list[tuple[Partition, Search[_S]]]:
    """Return the partitions of a check of history with checkpoint, and their searches.

    The partitions are in the order of their first invocation. A check of
    whole has one partition of every call. The search of a partition is its
    kept search grown by its new calls when the kept search fits the limits
    of config, and a new search otherwise. The searches step through spec
    and read deadline.

    Args:
        checkpoint: The checkpoint of the check.
        history: The history of the check.
        spec: The spec of the check.
        config: The limits of the check.
        deadline: The deadline of the check.
        whole: True for a check of every call as one partition.

    Returns:
        The partitions and their searches.
    """
    state = _STATES[checkpoint]
    if state.history is not history or state.whole != whole:
        state = _State(history, whole)
        if whole:
            state.every = _Part([], [])
            state.parts = [state.every]
        _STATES[checkpoint] = state
    events, ids = recorded(history, state.events)
    calls, earlier = calls_from(events, ids, state.events)
    state.events += len(events)
    for completion in earlier:
        state.complete(completion)
    for call in calls:
        state.join(call)
    if not whole:
        state.parts.sort(key=lambda part: part.calls[0].span.call)
    searched: list[tuple[Partition, Search[_S]]] = []
    for part in state.parts:
        search = part.search
        if search is None or not search.fits(len(part.calls), config):
            search = Search(part.calls, spec, config, deadline)
        else:
            search.grow(part.calls[len(search.calls) :], spec, deadline)
        part.search = search
        searched.append((Partition(tuple(part.keys), tuple(part.calls)), search))
    return searched


def forget(checkpoint: Checkpoint[Any]) -> None:
    """Leave checkpoint without a search, after a check that did not pass.

    Args:
        checkpoint: The checkpoint.
    """
    _STATES[checkpoint] = _State()
