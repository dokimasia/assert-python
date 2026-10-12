"""The spec of _history/event.py tests the events of a history and their JSON form."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._history.event import Completion, Event, Invocation, event_json
from dokimi_assert.seat import Collector

#: The fields of the events of call 0 by client 0 on process 0.
HEAD = {"call": 0, "client": 0, "process": 0}


def integer(value: int) -> dict[str, Any]:
    """Return the typed literal of an int."""
    return {"type": "int", "value": value}


class Probe:
    """A value without a typed literal and with a fixed repr."""

    def __repr__(self) -> str:
        """Return the text that the opaque literal contains."""
        return "Probe()"


class TestInvocation:
    """Invocation is the event that starts a call."""

    def test_has_the_kind_invoke(self, seat: Collector) -> None:
        """Every invocation has the kind invoke."""
        event = Invocation(0, 0, 0, 0, "read", (), ())
        check.equal(seat, event.kind, "invoke", "the kind of the event is invoke")


class TestCompletion:
    """Completion is the event that ends a call."""

    def test_leaves_its_values_at_none_by_default(self, seat: Collector) -> None:
        """The ok completion of call 0 sets neither the output nor the error."""
        event = Completion(1, "ok", 0, 0, 0)
        check.equal(
            seat,
            [event.output, event.error],
            [None, None],
            "the output and the error are None",
        )


class TestEventJson:
    """event_json returns the JSON form of an event."""

    tests: ClassVar[list[tuple[str, Event, dict[str, Any]]]] = [
        (
            "an invocation",
            Invocation(0, 0, 0, 0, "write", (1,), ("x",)),
            {
                "index": 0,
                "kind": "invoke",
                **HEAD,
                "operation": "write",
                "args": [integer(1)],
                "keys": [{"type": "string", "value": "x"}],
            },
        ),
        (
            "an ok completion",
            Completion(1, "ok", 0, 0, 0, output=1),
            {"index": 1, "kind": "ok", **HEAD, "output": integer(1)},
        ),
        (
            "a fail completion",
            Completion(1, "fail", 0, 0, 0, error=ValueError("refused")),
            {"index": 1, "kind": "fail", **HEAD, "error": "refused"},
        ),
        (
            "an unknown completion",
            Completion(1, "unknown", 0, 0, 0, error="the reply was lost"),
            {"index": 1, "kind": "unknown", **HEAD, "error": "the reply was lost"},
        ),
        (
            "an argument without a typed literal",
            Invocation(0, 0, 0, 0, "call", (Probe(),), ()),
            {
                "index": 0,
                "kind": "invoke",
                **HEAD,
                "operation": "call",
                "args": [{"type": "opaque", "text": "Probe()"}],
                "keys": [],
            },
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_json_of(
        self, seat: Collector, give: Event, want: dict[str, Any]
    ) -> None:
        """The JSON has the head fields and the fields of the kind."""
        check.equal(seat, event_json(give), want, "the JSON of the event")
