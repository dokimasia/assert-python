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
- A draw of a composite takes no entry when it starts, and its own draws
  take theirs. Once it decodes, it takes the next entry by its label and
  does not read the value. A case records a composite after its draws.
- A draw through a composite, whose generator has a composite inside a
  one-of, an optional, a list, a dict, a filter, a map with an inverse or a
  recursive, takes the first draw entry with its label up to the next step
  entry. When the value runs backwards through a composite, the draws of the
  composite take the entries before it, and the draw takes it once it
  decodes.
- The choices of a draw serve the requests of its own generator. A draw
  inside it serves its own, and the outer requests continue after it.
- A machine turns each step entry into the choices of one step. Tracing
  serves those choices as the machine requests them.
- Every other request takes its target.

A trace that the body cannot follow raises TraceError. The error has the
position of the entry, and it is not a failure of the case. It ends the run
before any case runs.

The counterexample of a stored case is a trace too. Its draw entry has the
value UNSTATED where the entry of the store does not record a typed literal
of the value. The body refuses such an entry.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, NoReturn, TypeGuard, cast, final

from dokimi_assert._override import override
from dokimi_assert._prop.engine.case import Case, Decoder, Provider, Request, Step
from dokimi_assert._prop.engine.choice import Choice, Value
from dokimi_assert._prop.engine.generator import Composite
from dokimi_assert._prop.engine.inverse import (
    CannotInvertError,
    invert_through,
    through_composite,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from dokimi_assert._prop.engine.generator import Generator

__all__ = [
    "UNSTATED",
    "Draw",
    "Entry",
    "TraceError",
    "Tracing",
    "entries",
    "is_step",
]


@final
class _Unstated:
    """The value of a draw entry that does not record a value."""

    @override
    def __repr__(self) -> str:
        """Return the name of the value.

        Returns:
            UNSTATED.
        """
        return "UNSTATED"


#: The value of a draw entry that does not record a value.
UNSTATED: Final = _Unstated()


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


@dataclass(slots=True)
class _Open:
    """A draw in progress: the choices of its requests, and how it ends.

    Attributes:
        queue: The choices of the draw that no request has taken.
        end: The position of the entry that a draw through a composite takes
            once it decodes. It is None for every other draw.
        by_label: True for a composite, which takes the next entry by its
            label alone once it decodes.
    """

    queue: deque[Choice] = field(default_factory=deque)
    end: int | None = None
    by_label: bool = False


class Tracing(Provider):
    """A provider that serves the values of the entries of a trace."""

    def __init__(self, trace: Sequence[Entry]) -> None:
        """Return the provider of the entries of a trace from the first entry.

        The first open draw stands for the requests outside every draw, such
        as the steps of a machine.

        Args:
            trace: The entries.
        """
        self._entries: tuple[Entry, ...] = tuple(trace)
        self._at: int = 0
        self._open: list[_Open] = [_Open()]

    @override
    def value(self, request: Request, index: int) -> Value:
        """Return the next value of the innermost open draw, or the target.

        Args:
            request: The request.
            index: The number of choices in the record of the case.

        Returns:
            The value.
        """
        del index
        queue = self._open[-1].queue
        if not queue:
            return request.bounds.target
        return request.bounds.coerce(queue.popleft())

    @override
    def drawing(self, generator: Decoder[Any], label: str) -> None:
        """Prepare the choices of the entry of a draw under a label.

        A composite takes no entry here. Its draws take theirs, and it takes
        its own entry once it decodes. A draw through a composite takes the
        first entry with its label up to the next step entry. Every other draw
        takes the next entry.

        Args:
            generator: The generator of the draw.
            label: The label of the draw.

        Raises:
            TraceError: The entry is not a draw entry with the label, it does
                not record a value, or the generator cannot produce its value.
        """
        if isinstance(generator, Composite):
            self._open.append(_Open(by_label=True))
            return
        if self._at >= len(self._entries):
            self._open.append(_Open())
            return
        drawn = cast("Generator[Any]", generator)
        at = self._find(label) if through_composite(drawn) else self._at
        entry = self._entries[at]
        if not isinstance(entry, Draw) or entry.label != label:
            raise TraceError(self._at, label, "label")
        if entry.value is UNSTATED:
            raise TraceError(at, label, "value")
        try:
            choices, composite = invert_through(drawn, entry.value)
        except CannotInvertError as bad:
            raise TraceError(at, label, "value") from bad
        if composite:
            self._open.append(_Open(deque(choices), end=at))
            return
        if at != self._at:
            raise TraceError(self._at, label, "label")
        self._at += 1
        self._open.append(_Open(deque(choices)))

    @override
    def drawn(self, generator: Decoder[Any], label: str) -> None:
        """End the draw under a label, and take its entry once it decodes.

        A composite takes the next entry by its label alone. A draw through a
        composite takes its entry, which must be the next one, once the draws
        of its composites have taken the entries before it. Every other draw
        took its entry before it decoded.

        Args:
            generator: The generator of the draw.
            label: The label of the draw.

        Raises:
            TraceError: The next entry is not a draw entry with the label, or it
                is not the entry of the draw. When a draw inside took the entry
                of the draw, the error is at that entry.
        """
        del generator
        ended = self._open.pop()
        if ended.by_label and self._at < len(self._entries):
            self._take(label)
        if ended.end is not None:
            if self._at != ended.end:
                raise TraceError(min(self._at, ended.end), label, "label")
            self._take(label)

    def _find(self, label: str) -> int:
        """Return the position of the first draw entry with the label before a step.

        The position of the next entry is returned when there is no such entry,
        so the draw refuses that entry.
        """
        for at in range(self._at, len(self._entries)):
            entry = self._entries[at]
            if not isinstance(entry, Draw):
                break
            if entry.label == label:
                return at
        return self._at

    def _take(self, label: str) -> Draw:
        """Take the next entry, a draw entry with the label.

        Raises:
            TraceError: The next entry is not a draw entry with the label.
        """
        entry = self._entries[self._at]
        if not isinstance(entry, Draw) or entry.label != label:
            raise TraceError(self._at, label, "label")
        self._at += 1
        return entry

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

    @property
    def taken(self) -> int:
        """The number of entries that the draws and the steps took.

        Returns:
            The number. It is the position of the next entry.
        """
        return self._at

    def prepare(self, *values: int) -> None:
        """Serve integer values to the next requests, before any target.

        Args:
            *values: The values.
        """
        self._open[-1].queue.extend(Choice("integer", value) for value in values)

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
