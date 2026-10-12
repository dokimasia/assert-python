"""The invocations and the completions of the calls to one object in recording order.

Each client starts on a process of its own. The history numbers the
processes in the order of their first invocations. A call that completes
as unknown can still be in progress inside the subject, so its client
continues on a new process. Every process has at most one open call.
Clients can record from any thread. A lock orders their events, so the
recording order is the order in which the clients record.
"""

from __future__ import annotations

import threading
import weakref
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

from dokimi_assert._history.event import Completion, Event, Invocation
from dokimi_assert._record.literal import encode, json, quoted

__all__ = ["Call", "History", "identity_of", "recorded"]

#: The kind of a completion.
_Ending = Literal["ok", "fail", "unknown"]


def _normalized(literal: dict[str, Any]) -> dict[str, Any]:
    """Return a typed literal with the entries of every map sorted by their JSON."""
    kind = literal["type"]
    if kind == "map":
        pairs = [[_normalized(k), _normalized(v)] for k, v in literal["entries"]]
        return {**literal, "entries": sorted(pairs, key=json)}
    if kind == "list" and "items" in literal:
        return {**literal, "items": [_normalized(item) for item in literal["items"]]}
    if kind == "record":
        fields = [[name, _normalized(value)] for name, value in literal["fields"]]
        return {**literal, "fields": fields}
    return literal


def identity_of(value: object) -> str | None:
    """Return the identity of a key or a value.

    The identity is the JSON text of the typed literal of the value. The
    entries of each map in it are in the order of their JSON. Two values
    have one identity when their typed literals are equal in any order of
    the entries of their maps.

    Args:
        value: The value.

    Returns:
        The identity, or None for a value without a typed literal.
    """
    literal = encode(value)
    return None if literal is None else json(_normalized(literal))


@dataclass(eq=False, slots=True)
class _State:
    """The state of a history. The checks read it.

    Attributes:
        events: The events in recording order.
        ids: The identities of the keys of each event. A completion has an
            empty tuple.
        open: The index of the invocation of the open call of each client
            that has one.
        process: The process of each client.
        processes: The number of processes so far.
        lock: The lock that orders the events.
    """

    events: list[Event] = field(default_factory=list)
    ids: list[tuple[str, ...]] = field(default_factory=list)
    open: dict[int, int] = field(default_factory=dict)
    process: dict[int, int] = field(default_factory=dict)
    processes: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock)


#: The state of each history.
_STATES: weakref.WeakKeyDictionary[History, _State] = weakref.WeakKeyDictionary()


class Call:
    """An open call of a History. Its client records the completion through it.

    A second completion of one call is a usage error.
    """

    def __init__(self, complete: Callable[[_Ending, Any], None]) -> None:
        """Return the call whose completions call complete.

        History.invoke constructs each call.

        Args:
            complete: The function that records a completion of the call.
        """
        self._complete: Callable[[_Ending, Any], None] = complete

    def ok(self, output: Any) -> None:
        """Record that the call returned output and took effect.

        Args:
            output: The value that the call returned.

        Raises:
            RuntimeError: The call has completed already.
        """
        self._complete("ok", output)

    def fail(self, error: Any) -> None:
        """Record that the call did not take effect.

        A refused connection ends a call this way. When the error describes
        what the subject observed, record it as an output with ok instead.
        For example, a compare-and-set that refuses because the value differs
        returns False.

        Args:
            error: The error of the call.

        Raises:
            RuntimeError: The call has completed already.
        """
        self._complete("fail", error)

    def unknown(self, error: Any) -> None:
        """Record that the call ended without an outcome.

        A timeout, a lost reply and a crash end a call this way. The call can
        still take effect, so the next invocation of its client starts on a
        new process.

        Args:
            error: The error of the call.

        Raises:
            RuntimeError: The call has completed already.
        """
        self._complete("unknown", error)


class History:
    """The events of one history in recording order.

    The history keeps the values that it receives and does not copy them.
    A caller records a copy of a value that the subject or the test changes
    later. The methods of History are safe for concurrent use.
    """

    def __init__(self) -> None:
        """Return an empty history."""
        _STATES[self] = _State()

    def invoke(
        self, client: int, operation: str, args: Sequence[Any], *keys: Any
    ) -> Call:
        """Record an invocation of operation with args by client.

        keys lists the keys that the call touches. A call without keys
        touches every key. Two keys are one key when their typed literals are
        equal, so two maps of equal entries are one key in any order of their
        entries.

        Args:
            client: The client that makes the call.
            operation: The operation of the call.
            args: The arguments of the call.
            *keys: The keys that the call touches.

        Returns:
            The call, through which the client records its completion.

        Raises:
            RuntimeError: client has a call open.
            TypeError: A key does not have a typed literal.
        """
        state = _STATES[self]
        with state.lock:
            open_call = state.open.get(client)
            if open_call is not None:
                raise RuntimeError(
                    f"history: invoke({client}, {quoted(operation)}) while call "
                    f"{open_call} of client {client} is open"
                )
            ids: list[str] = []
            for key in keys:
                identity = identity_of(key)
                if identity is None:
                    raise TypeError(
                        f"history: the key {key!r} of invoke({client}, "
                        f"{quoted(operation)}) does not have a typed literal"
                    )
                ids.append(identity)
            process = state.process.get(client)
            if process is None:
                process = state.processes
                state.processes += 1
                state.process[client] = process
            index = len(state.events)
            state.events.append(
                Invocation(index, index, client, process, operation, tuple(args), keys)
            )
            state.ids.append(tuple(ids))
            state.open[client] = index
        return Call(lambda kind, value: _complete(state, index, kind, value))

    def events(self) -> list[Event]:
        """Return the recorded events in recording order.

        The copy contains the events with the indices 0 to n - 1. n is the
        number of events that the history recorded before the call.

        Returns:
            A copy of the events.
        """
        state = _STATES[self]
        with state.lock:
            return list(state.events)


def _complete(state: _State, call: int, kind: _Ending, value: Any) -> None:
    """Record a completion of the call whose invocation is at index call.

    Raises:
        RuntimeError: The call has completed already.
    """
    with state.lock:
        invocation = state.events[call]
        if state.open.get(invocation.client) != call:
            raise RuntimeError(f"history: call {call} completes a second time")
        del state.open[invocation.client]
        if kind == "unknown":
            del state.process[invocation.client]
        output, error = (value, None) if kind == "ok" else (None, value)
        state.events.append(
            Completion(
                len(state.events),
                kind,
                call,
                invocation.client,
                invocation.process,
                output,
                error,
            )
        )
        state.ids.append(())


def recorded(history: History) -> tuple[list[Event], list[tuple[str, ...]]]:
    """Return the events of a history and the identities of the keys of each event.

    A check of a history reads both copies.

    Args:
        history: The history.

    Returns:
        A copy of the events, and a copy of the identities of the keys of
        each event.
    """
    state = _STATES[history]
    with state.lock:
        return list(state.events), list(state.ids)
