"""The record of the choices and the spans of one call of a body.

A generator never reads the random source itself. It asks the case for a
choice with bounds, and the provider of the case supplies the value.

- A generating provider draws the value from the source.
- A replaying provider reads the value back from recorded choices.
- The edge phase gives the value.
- The fuzz bridge decodes the value from the bytes of a fuzzer.

The case records every value with its request and the spans of the
generators that asked for it. The shrinker edits that record.

Rejected, Failed and the signals of the case tree end the body. They derive
from BaseException, so a body that catches Exception does not catch them.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar, cast

from dokimi_assert._prop.engine import draw as draws
from dokimi_assert._prop.engine.choice import (
    UINT64_MAX,
    Bounds,
    Choice,
    IntegerBounds,
    SequenceBounds,
    Value,
    choice_of,
)
from dokimi_assert._prop.engine.source import Source

__all__ = [
    "MAX_CHOICES",
    "Case",
    "Decoder",
    "Drawn",
    "Failed",
    "Generating",
    "Mark",
    "Observer",
    "Overrun",
    "Place",
    "Provider",
    "Rejected",
    "Replaying",
    "Request",
    "Span",
    "Step",
    "Trailing",
    "Valuing",
    "Walked",
    "Where",
]

#: The largest number of choices that one case can make. A sequence counts as
#: one choice plus one for each element.
MAX_CHOICES = 8192

_T = TypeVar("_T")
_T_co = TypeVar("_T_co", covariant=True)


class Decoder(Protocol[_T_co]):
    """The decoder of the values of a domain."""

    def decode(self, c: Case) -> _T_co:
        """Ask the case for choices, and return the value that they decode to.

        Raises:
            Rejected: The choices do not decode to a value of the domain.
        """
        ...


class Rejected(BaseException):
    """The signal that ends a case without a verdict.

    A rejected case is neither counted nor shrunk.
    """

    def __init__(self) -> None:
        """Return the signal."""
        super().__init__("prop: the case is rejected")


class Overrun(Rejected):
    """The signal of a case that asked for more choices than its cap allows."""


class Failed(BaseException):
    """The failure of a body and the identity under which the shrinker keeps it.

    Two failures are the same failure when their identities are equal.

    Attributes:
        identity: The identity of the failure.
        record: The object of the failure, such as a failure record. The
            report of the run uses it.
    """

    def __init__(self, identity: str, record: object = None) -> None:
        """Return the failure of an identity.

        Args:
            identity: The identity.
            record: The object of the failure, or None.
        """
        super().__init__(f"prop: the case fails as {identity}")
        self.identity: str = identity
        self.record: object = record


@dataclass(frozen=True, slots=True)
class Request:
    """One choice that a generator requests.

    A choice that decides the structure of the value of its generator has an
    edge. The continue flag of a collection and the index of a one-of are
    such choices. The edge is the value that the edge phase gives the
    choice. reuse marks a value choice of the integer and duration
    generators. A generated case can take such a value from an earlier
    choice with the same bounds.

    Attributes:
        bounds: The bounds of the choice.
        draw: Draws the value from a source.
        edge: The value that the edge phase gives a structure choice, or None
            for a value choice.
        reuse: When True, a generated case can take the value of an earlier
            choice with the same bounds.
    """

    bounds: Bounds
    draw: Callable[[Source], Value]
    edge: int | None = None
    reuse: bool = False


class Provider:
    """The provider of the values of a case."""

    def value(self, request: Request, index: int) -> Value:
        """Return the value for the request at an index of the case.

        Args:
            request: The request.
            index: The number of choices in the record of the case.

        Returns:
            The value. A provider without values of its own returns the
            target of the bounds.
        """
        del index
        return request.bounds.target

    def drawing(self, generator: Decoder[Any], label: str) -> None:
        """Prepare the values of the draw of a generator under a label.

        A provider that serves a trace prepares them. Any other provider
        does nothing.

        Args:
            generator: The generator of the draw.
            label: The label of the draw.
        """
        del generator, label

    def valued(self) -> tuple[object] | None:
        """Return the value of the next draw from a provider that gives the values.

        Returns:
            The value in a tuple of one, or None when the provider does not
            give a value.
        """
        return None


class Observer(Protocol):
    """The observer of each choice that the case records. The case tree is one."""

    def step(self, index: int, request: Request, value: Value) -> None:
        """Take the choice at an index, or raise a signal that ends the body."""
        ...


@dataclass(frozen=True, slots=True)
class Step:
    """The action and the place of one step that a machine took.

    Attributes:
        action: The name of the action.
        client: The client of a step of a concurrent section, or None.
        drain: When True, the step is a step of the drain.
    """

    action: str
    client: int | None = None
    drain: bool = False


@dataclass(frozen=True, slots=True)
class Place:
    """The part of the steps of a machine that was running, and its step.

    Attributes:
        part: The part. It is swarm, setup, sequential, concurrent, drain or
            settle.
        position: The position of the step in its part from 0, or None.
        action: The action of the swarm choice or of the step, or None.
    """

    part: str
    position: int | None = None
    action: str | None = None


@dataclass(frozen=True, slots=True)
class Where:
    """The place where a case made a request or observed a fingerprint.

    Attributes:
        label: The label of the innermost draw that was running, or None.
        place: The part and the step of the machine, or None.
    """

    label: str | None = None
    place: Place | None = None


@dataclass(frozen=True, slots=True)
class Walked:
    """One step of the kept walk of a case that runs outside the case tree.

    Attributes:
        index: The number of choices that the record contained before the
            choice of the step.
        request: The request.
        value: The value that the request took.
        where: Where the case made the request.
    """

    index: int
    request: Request
    value: Value
    where: Where


class Generating(Provider):
    """A provider that draws every value from a random source.

    A reuse request first tosses coin(1, 4) when its bounds admit more than
    one value and an earlier reuse request of the same case had the same
    bounds. When the coin comes up, the value is one of the earlier values
    with those bounds. below(their count) chooses it. Otherwise the request
    draws as usual. The earlier values are those of the choices that the
    record of the case still contains, so the next attempt of a filter never
    reuses a rejected value.
    """

    def __init__(self, source: Source) -> None:
        """Return the provider that draws from a source.

        Args:
            source: The source of the case.
        """
        self._source: Source = source
        self._earlier: dict[Bounds, list[tuple[int, Value]]] = {}

    def value(self, request: Request, index: int) -> Value:
        """Return the draw of the request from the source, or an earlier value.

        Args:
            request: The request.
            index: The number of choices in the record of the case.

        Returns:
            The value.
        """
        for kept in self._earlier.values():
            while kept and kept[-1][0] >= index:
                kept.pop()
        bounds = request.bounds
        forced = isinstance(bounds, IntegerBounds) and bounds.lo == bounds.hi
        if not request.reuse or forced:
            return request.draw(self._source)
        earlier = self._earlier.setdefault(bounds, [])
        if earlier and self._source.coin(1, draws.REUSE_ODDS):
            value = earlier[self._source.below(len(earlier))][1]
        else:
            value = request.draw(self._source)
        earlier.append((index, value))
        return value


class Trailing(Generating):
    """A generating provider that keeps the state of its source after each value.

    A run on more than one worker runs a random case outside the case tree.
    It enters the case into the tree afterwards. A run on one worker stops a
    repeated case at its repeat. It then draws the cut of the prefix case
    from the source in the state that the stop left. The kept states let the
    run resume the source at that point.

    Attributes:
        states: The state of the source before the first value and after
            each value in order.
    """

    def __init__(self, source: Source) -> None:
        """Return the provider that draws from a source and keeps its states.

        Args:
            source: The source of the case.
        """
        super().__init__(source)
        self.states: list[Source] = [copy.copy(source)]

    def value(self, request: Request, index: int) -> Value:
        """Return the value that Generating returns, and keep the state.

        Args:
            request: The request.
            index: The number of choices in the record of the case.

        Returns:
            The value.
        """
        value = super().value(request, index)
        self.states.append(copy.copy(self._source))
        return value

    def after(self, n: int) -> Source:
        """Return a copy of the source after its first n values.

        Args:
            n: The number of values.

        Returns:
            The source.
        """
        return copy.copy(self.states[n])


class Replaying(Provider):
    """A provider that reads recorded choices back in order.

    The bounds of a request coerce a recorded choice that does not fit. A
    request past the last recorded choice takes the target of its bounds.
    """

    def __init__(self, choices: list[Choice] | tuple[Choice, ...]) -> None:
        """Return the provider that replays choices.

        Args:
            choices: The recorded choices.
        """
        self._choices: list[Choice] | tuple[Choice, ...] = choices

    def value(self, request: Request, index: int) -> Value:
        """Return the recorded value at an index, fitted to the request.

        Args:
            request: The request.
            index: The number of choices in the record of the case.

        Returns:
            The value.
        """
        if index >= len(self._choices):
            return request.bounds.target
        return request.bounds.coerce(self._choices[index])


class Valuing(Provider):
    """A provider that gives the values of the draws of a case in order.

    A draw takes the next value without a choice. A draw past the last value
    decodes. Every request of that draw takes the target of its bounds. A
    replay that runs out of choices does the same.
    """

    def __init__(self, values: list[object] | tuple[object, ...]) -> None:
        """Return the provider that gives values for the draws.

        Args:
            values: The values of the draws from the first.
        """
        self._values: list[object] | tuple[object, ...] = values
        self._at: int = 0

    def valued(self) -> tuple[object] | None:
        """Return the next given value, or None when none is left."""
        if self._at == len(self._values):
            return None
        self._at += 1
        return (self._values[self._at - 1],)


@dataclass(slots=True)
class Span:
    """The choices [start, end) that one generator, element or entry made.

    Attributes:
        label: The id of the generator, element or entry.
        start: The first choice.
        end: The choice after the last.
        depth: The number of spans that were open when this one opened.
        parent: The index of the span that was open when this one opened, or
            None.
    """

    label: str
    start: int
    end: int
    depth: int
    parent: int | None


@dataclass(frozen=True, slots=True)
class Drawn:
    """One value that a body drew.

    Attributes:
        label: The label of the draw.
        value: The value.
        span: The index of the first span that the generator opened.
        generator: The generator.
    """

    label: str
    value: Any
    span: int
    generator: Decoder[Any]


@dataclass(frozen=True, slots=True)
class Mark:
    """The numbers of choices, spans and draws at a point of a record."""

    choices: int
    spans: int
    draws: int


def _cost(value: Value) -> int:
    """Return the cost of a value. It is 1, plus 1 per element of a sequence."""
    return 1 + len(value) if isinstance(value, tuple) else 1


#: The bounds of the values of random. They cover the whole unsigned 64-bit
#: range.
_RANDOM = IntegerBounds(0, UINT64_MAX)


class Case:
    """The record of one call of a body.

    wheres has the place of each recorded request. observed has the place of
    each observed fingerprint. The steps of a machine set place while they
    run.

    Attributes:
        choices: The recorded choices.
        requests: The request of each recorded choice.
        spans: The spans in the order that they opened.
        draws: The draws in order.
        steps: The steps of a machine. Each step is paired with the number
            of draws recorded before it.
        labels: The labels that classify counted.
        notes: The notes.
        fingerprints: The observed fingerprints.
        targets: The highest score that the case recorded under each label.
        wheres: Where the case made each recorded request.
        observed: Where the case observed each fingerprint.
        place: The part and the step of the machine while its steps run.
        walk: Every choice that the case made for a case that keeps its
            walk, and None otherwise. The walk includes the choices that a
            rewind removed from the record.
        owner: The object of the layer above the engine that runs a body on
            the case, or None. The case of a property is such an object.
    """

    def __init__(
        self,
        provider: Provider,
        max_choices: int = MAX_CHOICES,
        observer: Observer | None = None,
        walk: bool = False,
    ) -> None:
        """Return an empty case whose values come from a provider.

        Args:
            provider: The provider of the values.
            max_choices: The largest number of choices that the case can
                make.
            observer: The observer of every choice after the case records it.
            walk: When True, the case keeps its walk. A run on more than one
                worker enters the walk into the case tree once the case has
                ended.
        """
        self._provider: Provider = provider
        self._max_choices: int = max_choices
        self._observer: Observer | None = observer
        self._cancelled: bool = False
        self._cost: int = 0
        self._open: list[int] = []
        self._drawing: list[str] = []
        self.choices: list[Choice] = []
        self.requests: list[Request] = []
        self.spans: list[Span] = []
        self.draws: list[Drawn] = []
        self.steps: list[tuple[int, Step]] = []
        self.labels: set[str] = set()
        self.notes: list[str] = []
        self.fingerprints: list[int] = []
        self.targets: dict[str, float] = {}
        self.wheres: list[Where] = []
        self.observed: list[Where] = []
        self.place: Place | None = None
        self.walk: list[Walked] | None = [] if walk else None
        self.owner: object = None
        self._repeats: int = 1

    @property
    def provider(self) -> Provider:
        """The provider of the values of the case. The steps of a machine use it."""
        return self._provider

    @property
    def max_choices(self) -> int:
        """The largest number of choices that the case can make."""
        return self._max_choices

    @property
    def repeats(self) -> int:
        """The number of runs of the body on the choices of the case.

        It is 1 until a call of repeat raises it.
        """
        return self._repeats

    def repeat(self, n: int) -> None:
        """Make the execution of the case run the body up to n times on its choices.

        The steps of a machine call repeat when the clients of a concurrent
        section run on threads, because threads do not replay. The case
        keeps the larger of two numbers of runs.

        Args:
            n: The number of runs. It includes the first run.
        """
        self._repeats = max(self._repeats, n)

    def where(self) -> Where:
        """Return the label of the open draw and the place of the machine."""
        return Where(self._drawing[-1] if self._drawing else None, self.place)

    def choose(self, request: Request) -> Value:
        """Return the value for a request, and record it.

        A sequence whose minimum length alone takes the case past its cap
        ends the case before the provider makes its value. A cancelled case
        ends in the same way.

        Args:
            request: The request.

        Returns:
            The value.

        Raises:
            Overrun: The value takes the case past its cap, or the case is
                cancelled.
        """
        bounds = request.bounds
        if self._cancelled or (
            isinstance(bounds, SequenceBounds)
            and self._cost + 1 + bounds.min_size > self._max_choices
        ):
            raise Overrun
        value = self._provider.value(request, len(self.choices))
        self._cost += _cost(value)
        if self._cost > self._max_choices:
            raise Overrun
        self.choices.append(choice_of(bounds, value))
        self.requests.append(request)
        self.wheres.append(self.where())
        if self.walk is not None:
            index = len(self.choices) - 1
            self.walk.append(Walked(index, request, value, self.wheres[index]))
        if self._observer is not None:
            self._observer.step(len(self.choices) - 1, request, value)
        return value

    def integer(
        self, bounds: IntegerBounds, edge: int | None = None, reuse: bool = False
    ) -> int:
        """Return an integer choice inside bounds. draw.integer draws it.

        Args:
            bounds: The bounds.
            edge: The value that the edge phase gives a structure choice.
            reuse: When True, a generated case can take an earlier value.

        Returns:
            The value.

        Raises:
            Overrun: The choice takes the case past its cap.
        """
        request = Request(
            bounds, lambda source: draws.integer(source, bounds), edge, reuse
        )
        return cast("int", self.choose(request))

    def sequence(self, bounds: SequenceBounds) -> tuple[int, ...]:
        """Return a sequence choice inside bounds. draw.sequence draws it.

        Args:
            bounds: The bounds.

        Returns:
            The elements.

        Raises:
            Overrun: The sequence takes the case past its cap.
        """
        request = Request(bounds, lambda source: draws.sequence(source, bounds))
        return cast("tuple[int, ...]", self.choose(request))

    @contextmanager
    def span(self, label: str, start: int | None = None) -> Generator[None, None, None]:
        """Record the choices that the block of a with statement makes as one span.

        The block runs in the frame of its caller, so a decode of a nested
        value does not spend a frame on its spans.

        Args:
            label: The label of the span.
            start: The first choice of the span. It is an index that the case
                recorded before the block, so the span of an element can
                include the continue flag before it. None means the current
                index.

        Yields:
            Nothing. The span closes where the block ends, even when the
            block raises.
        """
        close = self.open(label, start)
        try:
            yield
        finally:
            close()

    def open(self, label: str, start: int | None = None) -> Callable[[], None]:
        """Open a span, and return the function that closes it.

        The steps of a machine open their spans this way around their
        actions. Spans close in the reverse order of their opening.

        Args:
            label: The label of the span.
            start: The first choice of the span. It has the same meaning as
                in span.

        Returns:
            The function that closes the span at the current index.
        """
        parent = self._open[-1] if self._open else None
        index = len(self.spans)
        first = len(self.choices) if start is None else start
        self.spans.append(Span(label, first, first, len(self._open), parent))
        self._open.append(index)

        def close() -> None:
            self._open.pop()
            self.spans[index].end = len(self.choices)

        return close

    def cancel(self) -> None:
        """End the case at its next choice.

        A run on more than one worker cancels the cases that it started ahead
        of the runner and no longer needs.
        """
        self._cancelled = True

    def record_at(self, n: int) -> list[Choice]:
        """Return the choices of the record after the first n steps of the walk.

        The record is the record before the rewinds of the later steps. The
        case has kept its walk.

        Args:
            n: The number of steps.

        Returns:
            The choices.
        """
        record: list[Choice] = []
        for step in cast("list[Walked]", self.walk)[:n]:
            del record[step.index :]
            record.append(choice_of(step.request.bounds, step.value))
        return record

    def mark(self) -> Mark:
        """Return the current point of the record for rewind."""
        return Mark(len(self.choices), len(self.spans), len(self.draws))

    def rewind(self, mark: Mark) -> None:
        """Remove every choice, span and draw recorded after a mark.

        Every span opened after the mark must have closed. The removed
        choices still count towards the cap. An observer keeps them, because
        the case tree walked them and a removal cannot undo a step.

        Args:
            mark: A point of the record.
        """
        del self.choices[mark.choices :]
        del self.requests[mark.choices :]
        del self.wheres[mark.choices :]
        del self.spans[mark.spans :]
        del self.draws[mark.draws :]

    def draw(self, generator: Decoder[_T], label: str) -> _T:
        """Return a value of a generator, and record it under a label.

        The span of the draw is the first span that the generator opens. Two
        draws can share a label. A provider that serves a trace prepares the
        values of the draw first. A provider that gives the values of the
        draws gives the draw its value. Such a draw does not make a choice or
        open a span. Every request of the draw has its label.

        Args:
            generator: The generator.
            label: The label of the draw.

        Returns:
            The value.
        """
        stated = self._provider.valued()
        if stated is not None:
            self.draws.append(Drawn(label, stated[0], len(self.spans), generator))
            return cast("_T", stated[0])
        self._provider.drawing(generator, label)
        span = len(self.spans)
        self._drawing.append(label)
        try:
            value = generator.decode(self)
        finally:
            self._drawing.pop()
        self.draws.append(Drawn(label, value, span, generator))
        return value

    def step(self, taken: Step) -> None:
        """Record a step that a machine took, after every draw recorded so far.

        Args:
            taken: The step.
        """
        self.steps.append((len(self.draws), taken))

    def assume(self, condition: bool) -> None:
        """Reject the case when the condition is false.

        Args:
            condition: The condition.

        Raises:
            Rejected: The condition is false.
        """
        if not condition:
            raise Rejected

    def classify(self, label: str) -> None:
        """Count the case under a label. A label counted twice counts once.

        Args:
            label: The label.
        """
        self.labels.add(label)

    def note(self, message: str) -> None:
        """Attach a message to the case. Only a failing case reports it.

        Args:
            message: The note.
        """
        self.notes.append(message)

    def observe(self, fingerprint: int) -> None:
        """Record a fingerprint of the state of the subject. A replay compares it.

        Args:
            fingerprint: The fingerprint.
        """
        self.fingerprints.append(fingerprint)
        self.observed.append(self.where())

    def target(self, label: str, score: float) -> None:
        """Record a score under a label.

        The case keeps the higher of two scores under one label.

        Args:
            label: The label.
            score: The score.
        """
        best = self.targets.get(label)
        if best is None or score > best:
            self.targets[label] = score

    def random(self) -> int:
        """Return an integer choice over the whole unsigned 64-bit range."""
        return self.integer(_RANDOM)

    def fail(self, identity: str, record: object = None) -> None:
        """Fail the case.

        Args:
            identity: The identity of the failure.
            record: The object of the failure for the report of the run.

        Raises:
            Failed: Always.
        """
        raise Failed(identity, record)
