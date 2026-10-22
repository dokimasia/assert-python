# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""A history of calls that a log recorded with a start and an end on one clock."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from dokimi_assert._history.history import Call, History, identity_of

__all__ = ["Interval", "IntervalError", "from_intervals"]

#: The kinds that complete a call.
_COMPLETIONS = frozenset({"ok", "fail", "unknown"})

#: A moment of an entry. It has the time, the phase and the position of the
#: entry. The phase is 0 for the invocation and 1 for the completion.
_Moment = tuple[float, int, int]


@dataclass(frozen=True, slots=True)
class Interval:
    """A call that a system log recorded with a start and an end on one clock.

    A pending call does not have an end or a kind.

    Attributes:
        client: The client that made the call.
        operation: The operation of the call.
        args: The arguments of the call.
        keys: The keys that the call touches. A call without keys touches
            every key.
        start: The time at which the call started.
        end: The time at which the call completed, or None for a pending
            call.
        kind: The kind of the completion, or None for a pending call.
        output: The value that an ok call returned.
        error: The error of a call that completed as fail or unknown.
    """

    client: int
    operation: str
    args: Sequence[Any]
    keys: Sequence[Any]
    start: float
    end: float | None = None
    kind: Literal["ok", "fail", "unknown"] | None = None
    output: Any = None
    error: Any = None


class IntervalError(ValueError):
    """The error for an entry that from_intervals refuses.

    Attributes:
        entry: The position of the entry.
    """

    def __init__(self, entry: int, reason: str) -> None:
        """Return the error for the entry at a position and the rule that it breaks.

        Args:
            entry: The position of the entry.
            reason: The rule that the entry breaks.
        """
        super().__init__(f"history: entry {entry} {reason}")
        self.entry: int = entry


def _overlap(a: Interval, b: Interval) -> bool:
    """Report whether two closed intervals share an instant.

    A pending interval does not have an end.
    """
    return (a.end is None or b.start <= a.end) and (b.end is None or a.start <= b.end)


def _refusal(entry: Interval, earlier: Sequence[tuple[int, Interval]]) -> str | None:
    """Return the rule that entry breaks against the earlier entries of its client.

    The result is None when the entry does not break a rule.
    """
    if entry.kind is not None and entry.kind not in _COMPLETIONS:
        return f"has the kind {entry.kind!r} instead of ok, fail or unknown"
    if (entry.kind is None) != (entry.end is None):
        return "has a kind without an end, or an end without a kind"
    if entry.end is not None and entry.end < entry.start:
        return f"ends at {entry.end} before it starts at {entry.start}"
    for key in entry.keys:
        if identity_of(key) is None:
            return f"has the key {key!r} without a typed literal"
    for position, before in earlier:
        if _overlap(before, entry):
            return f"overlaps entry {position} of client {entry.client}"
    return None


def from_intervals(entries: Sequence[Interval]) -> History:
    """Return the history of calls with a start and an end on one clock.

    The events are in time order. At one time, an invocation comes before a
    completion. The invocations at one time keep the order of their
    entries. The completions at one time keep it too. Each interval is
    closed, so two entries that share an instant overlap. A pending entry
    overlaps every later entry of its client. The times are compared and
    never subtracted, so they can be ints or floats.

    Args:
        entries: The calls.

    Returns:
        The history.

    Raises:
        IntervalError: An entry has a kind other than ok, fail and unknown,
            an end without a kind or a kind without an end, an end before its
            start, a key without a typed literal, or an interval that
            overlaps an earlier entry of its client. The error is for the
            first such entry in the order given.
    """
    earlier: dict[int, list[tuple[int, Interval]]] = {}
    for position, entry in enumerate(entries):
        own = earlier.setdefault(entry.client, [])
        reason = _refusal(entry, own)
        if reason is not None:
            raise IntervalError(position, reason)
        own.append((position, entry))
    moments: list[_Moment] = []
    for position, entry in enumerate(entries):
        moments.append((entry.start, 0, position))
        if entry.end is not None:
            moments.append((entry.end, 1, position))
    moments.sort()
    history = History()
    calls: dict[int, Call] = {}
    for _, phase, position in moments:
        entry = entries[position]
        if phase == 0:
            calls[position] = history.invoke(
                entry.client, entry.operation, entry.args, *entry.keys
            )
        elif entry.kind == "ok":
            calls[position].ok(entry.output)
        elif entry.kind == "fail":
            calls[position].fail(entry.error)
        else:
            calls[position].unknown(entry.error)
    return history
