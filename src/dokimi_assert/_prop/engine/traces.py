# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""A trace is the list of the draws and the machine steps of a case.

A trace has its entries in request order. A draw entry has a label and a
value. A step entry has an action. It also has its client in a concurrent
section, and the drain mark in the drain. entries returns the trace of a case
in the same form as the counterexample of a machine.

A body runs on a trace through Tracing. Tracing is a provider whose values
come from the entries.

- A draw takes the next entry. The entry must be a draw entry with the label
  of the draw. Its value runs backwards through the generator of the draw,
  and the draw decodes the resulting choices. A draw past the last entry
  takes its targets.
- A machine turns each step entry into the choices of one step. Tracing
  serves those choices as the machine requests them.
- Every other request takes its target.

A trace that the body cannot follow raises TraceError. The error has the
position of the entry, and it is not a failure of the case. It ends the run
before any case runs.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn, TypeGuard, cast

from dokimi_assert._override import override
from dokimi_assert._prop.engine.case import Case, Decoder, Provider, Request, Step
from dokimi_assert._prop.engine.choice import Choice, Value
from dokimi_assert._prop.engine.inverse import inverse_of

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dokimi_assert._prop.engine.generator import Generator

__all__ = ["Draw", "Entry", "TraceError", "Tracing", "entries", "is_step"]


@dataclass(frozen=True, slots=True)
class Draw:
    """A draw entry with the label of a draw and the value that it decoded.

    Attributes:
        label: The label.
        value: The value.
    """

    label: str
    value: Any


#: One entry of a trace. It is a draw entry or a step entry.
Entry = Draw | Step


def is_step(entry: Entry) -> TypeGuard[Step]:
    """Report whether an entry is a step entry.

    Args:
        entry: The entry.

    Returns:
        True for a step entry.
    """
    return isinstance(entry, Step)


class TraceError(ValueError):
    """The refusal of an entry that the body cannot follow.

    Attributes:
        entry: The position of the entry.
        what: The label of the draw for a reason of label or value, and the
            action of the step for a reason of step.
        reason: The reason that the body cannot follow the entry. It is
            label, value or step.
    """

    def __init__(self, entry: int, what: str, reason: str) -> None:
        """Return the error of an entry.

        Args:
            entry: The position of the entry.
            what: The label of the draw or the action of the step.
            reason: The reason. It is label, value or step.
        """
        super().__init__(f"prop: trace entry {entry} ({what}): {reason}")
        self.entry: int = entry
        self.what: str = what
        self.reason: str = reason


def entries(c: Case) -> list[Entry]:
    """Return the draws and the steps of a case as a trace in request order.

    A step comes before the draws that the case recorded after it.

    Args:
        c: The case.

    Returns:
        The trace.
    """
    trace: list[Entry] = []
    steps = c.steps
    following = 0
    for number, drawn in enumerate(c.draws):
        while following < len(steps) and steps[following][0] <= number:
            trace.append(steps[following][1])
            following += 1
        trace.append(Draw(drawn.label, drawn.value))
    trace.extend(taken for _, taken in steps[following:])
    return trace


class Tracing(Provider):
    """A provider that serves the values of the entries of a trace."""

    def __init__(self, trace: Sequence[Entry]) -> None:
        """Return the provider of the entries of a trace from the first entry.

        Args:
            trace: The entries.
        """
        self._entries: tuple[Entry, ...] = tuple(trace)
        self._at: int = 0
        self._queue: deque[Choice] = deque()

    @override
    def value(self, request: Request, index: int) -> Value:
        """Return the next prepared value fitted to the request, or its target.

        Args:
            request: The request.
            index: The number of choices in the record of the case.

        Returns:
            The value.
        """
        del index
        if not self._queue:
            return request.bounds.target
        return request.bounds.coerce(self._queue.popleft())

    @override
    def drawing(self, generator: Decoder[Any], label: str) -> None:
        """Prepare the choices of the next entry for a draw under a label.

        Args:
            generator: The generator of the draw.
            label: The label of the draw.

        Raises:
            TraceError: The next entry is not a draw entry with the label, or
                the generator cannot produce its value.
        """
        if self._at >= len(self._entries):
            return
        entry = self._entries[self._at]
        if not isinstance(entry, Draw) or entry.label != label:
            raise TraceError(self._at, label, "label")
        choices = inverse_of(cast("Generator[Any]", generator), entry.value)
        if choices is None:
            raise TraceError(self._at, label, "value")
        self._queue.extend(choices)
        self._at += 1

    def next_step(self) -> Step | None:
        """Return the next entry when it is a step entry, and None otherwise.

        Returns:
            The step entry, or None.
        """
        if self._at >= len(self._entries):
            return None
        entry = self._entries[self._at]
        return entry if is_step(entry) else None

    def actions(self) -> list[str]:
        """Return the actions of the step entries from the next one on, each once.

        Returns:
            The actions, in the order of their first entries.
        """
        named = [entry.action for entry in self._entries[self._at :] if is_step(entry)]
        return list(dict.fromkeys(named))

    def prepare(self, *values: int) -> None:
        """Serve integer values to the next requests, before any target.

        Args:
            *values: The values.
        """
        self._queue.extend(Choice("integer", value) for value in values)

    def take(self, *values: int) -> None:
        """Take the next step entry, and serve the values of its choices.

        Args:
            *values: The values of the choices of the step.
        """
        self.prepare(*values)
        self._at += 1

    def refuse(self) -> NoReturn:
        """Fail on the next step entry. The machine cannot take its step.

        Raises:
            TraceError: Always.
        """
        step = cast("Step", self.next_step())
        raise TraceError(self._at, step.action, "step")
