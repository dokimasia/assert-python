"""The events of a history, and their JSON form in a record.

Each event has its index in recording order, its kind, its call, the client
that made the call and the process of the client. An invocation also has
the operation, the arguments and the keys of the call. An ok completion has
the output of the call. A fail or an unknown completion has its error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from dokimi_assert._matcher.verdict import fault_text
from dokimi_assert._record.literal import detail

__all__ = ["Completion", "Event", "Invocation", "Kind", "event_json"]

#: The kind of an event. An invocation starts a call. The kinds ok, fail and
#: unknown complete it.
Kind = Literal["invoke", "ok", "fail", "unknown"]


@dataclass(frozen=True, slots=True)
class Invocation:
    """The event that starts a call.

    Attributes:
        index: The position of the event in recording order, from 0.
        call: The index of the invocation of the call. It is the index of the
            event itself.
        client: The client that made the call.
        process: The process that made the call.
        operation: The operation of the call.
        args: The arguments of the call.
        keys: The keys that the call touches. A call without keys touches
            every key.
        kind: The kind of the event.
    """

    index: int
    call: int
    client: int
    process: int
    operation: str
    args: tuple[Any, ...]
    keys: tuple[Any, ...]
    kind: Literal["invoke"] = "invoke"


@dataclass(frozen=True, slots=True)
class Completion:
    """The event that completes a call as ok, fail or unknown.

    Attributes:
        index: The position of the event in recording order, from 0.
        kind: The kind of the event.
        call: The index of the invocation of the call.
        client: The client that made the call.
        process: The process that made the call.
        output: The value that the call returned. It is None for a completion
            that is not ok.
        error: The error of the call. It is None for an ok completion.
    """

    index: int
    kind: Literal["ok", "fail", "unknown"]
    call: int
    client: int
    process: int
    output: Any = None
    error: Any = None


#: An event of a history is the invocation of a call or its completion.
Event = Invocation | Completion


def event_json(event: Event) -> dict[str, Any]:
    """Return the JSON form of an event.

    Every event has the index, the kind, the call, the client and the
    process. An invocation adds the operation, the args and the keys. An ok
    completion adds the output. A fail or an unknown completion adds the text
    of the error. The args, the keys and the output are typed literals.
    A value without a typed literal has the opaque literal of its repr.

    Args:
        event: The event.

    Returns:
        The JSON value.
    """
    head: dict[str, Any] = {
        "index": event.index,
        "kind": event.kind,
        "call": event.call,
        "client": event.client,
        "process": event.process,
    }
    if isinstance(event, Invocation):
        return {
            **head,
            "operation": event.operation,
            "args": [detail(arg) for arg in event.args],
            "keys": [detail(key) for key in event.keys],
        }
    if event.kind == "ok":
        return {**head, "output": detail(event.output)}
    return {**head, "error": fault_text(event.error)}
