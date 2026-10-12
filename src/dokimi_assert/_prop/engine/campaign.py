"""The exploration of a property for a span of time instead of a number of cases.

A campaign first runs the traces, the examples and the stored cases in the
same way as a run. It then runs cases one at a time until its budget has
passed.

A valid case joins the pool of the campaign when it shows new behaviour.

- It counts a label that no earlier case counted.
- It records a fingerprint that no earlier case recorded.
- It records a score above the best score of its label.

In a campaign with a pool, three cases in four mutate a member of the pool.
The campaign chooses the member uniformly. The fourth case is the next
random case of the seed. A mutation makes one of four changes to the member
with odds of 1 in 4 each.

- It draws one choice again.
- It deletes a span.
- It repeats a span after itself.
- It replaces a span with a span of the same label from a member of the
  pool.

A mutated case replays its choices. Each request after them draws from the
stream of the campaign. That stream is the stream of the seed at index
2^64 - 1, above the index of every random case.

The definition leaves these odds to each library.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import TypeVar, cast

from dokimi_assert._prop.engine import draw
from dokimi_assert._prop.engine.case import (
    Generating,
    Provider,
    Request,
    Span,
    Valuing,
)
from dokimi_assert._prop.engine.choice import (
    UINT64_MAX,
    Bounds,
    Choice,
    FloatBounds,
    IntegerBounds,
    Value,
    choice_of,
)
from dokimi_assert._prop.engine.execution import (
    Body,
    Execution,
    Observer,
    execute,
    identity_of,
    unobserved,
)
from dokimi_assert._prop.engine.runner import (
    Kind,
    Outcome,
    Settings,
    Tally,
    conclude,
    known_cases,
    shortfall_of,
)
from dokimi_assert._prop.engine.source import Source, case_source

__all__ = ["campaign"]

_T = TypeVar("_T")

#: The odds that a case of a campaign with a pool mutates a member of the
#: pool. They are 3 in 4.
_MUTATE_NUM = 3
_MUTATE_DEN = 4

#: The kinds of mutation of a member and their number. A mutated case
#: chooses a kind uniformly. Kind 3 replaces a span.
_REDRAW = 0
_DELETE = 1
_REPEAT = 2
_KINDS = 4


@dataclass(frozen=True, slots=True)
class _Member:
    """The choices, the bounds of their requests and the spans of a case of the pool."""

    choices: tuple[Choice, ...]
    bounds: tuple[Bounds, ...]
    spans: tuple[Span, ...]


def _pick(source: Source, items: Sequence[_T]) -> _T:
    """Return an element of items that source chooses uniformly."""
    return items[source.below(len(items))]


def _redrawn(bounds: Bounds, source: Source) -> Choice:
    """Return a choice that a request of the bounds would draw from source."""
    if isinstance(bounds, IntegerBounds):
        return choice_of(bounds, draw.integer(source, bounds))
    if isinstance(bounds, FloatBounds):
        return choice_of(bounds, draw.float_value(source, bounds))
    return choice_of(bounds, draw.sequence(source, bounds))


def _redraw_one(member: _Member, source: Source) -> list[Choice]:
    """Return the choices of member with one uniformly chosen choice drawn again."""
    choices = list(member.choices)
    at = source.below(len(choices))
    choices[at] = _redrawn(member.bounds[at], source)
    return choices


def _mutation(pool: Sequence[_Member], source: Source) -> list[Choice]:
    """Return the choices of a mutation of a member of pool.

    A member without spans takes the mutation that draws a choice again. A
    replacement falls back to that mutation when its donor does not have a
    span of the same label. A member without choices does not take a
    mutation.
    """
    member = _pick(source, pool)
    choices = member.choices
    if not choices:
        return []
    drawn = source.below(_KINDS)
    kind = drawn if member.spans else _REDRAW
    if kind == _REDRAW:
        return _redraw_one(member, source)
    span = _pick(source, member.spans)
    before = choices[: span.start]
    after = choices[span.end :]
    if kind == _DELETE:
        return [*before, *after]
    if kind == _REPEAT:
        return [*choices[: span.end], *choices[span.start :]]
    donor = _pick(source, pool)
    same = [other for other in donor.spans if other.label == span.label]
    if not same:
        return _redraw_one(member, source)
    given = _pick(source, same)
    return [*before, *donor.choices[given.start : given.end], *after]


class _Mutating(Provider):
    """A provider that replays the choices of a mutated case.

    It fits each choice to the bounds of its request. It draws each request
    after the choices from the stream of the campaign.
    """

    def __init__(self, choices: list[Choice], source: Source) -> None:
        """Return the provider of the choices of a mutated case."""
        self._choices: list[Choice] = choices
        self._source: Source = source

    def value(self, request: Request, index: int) -> Value:
        """Return the choice at index fitted to the request, or a fresh draw.

        A request after the choices draws from the stream of the campaign.
        """
        if index < len(self._choices):
            return request.bounds.coerce(self._choices[index])
        return request.draw(self._source)


class _Exploration:
    """The state of one campaign."""

    def __init__(
        self,
        body: Body,
        settings: Settings,
        observer: Observer,
        concluded: Callable[[Outcome], None] | None,
    ) -> None:
        """Return the state of a campaign that has not run a case."""
        self._body: Body = body
        self._settings: Settings = settings
        self._observer: Observer = observer
        self._concluded: Callable[[Outcome], None] | None = concluded
        self._tally: Tally = Tally(settings.seed)
        self._source: Source = case_source(settings.seed, UINT64_MAX)
        self._index: int = 0
        self._pool: list[_Member] = []
        self._labels: set[str] = set()
        self._fingerprints: set[int] = set()
        self._best: dict[str, float] = {}
        self._identities: set[str] = set()
        self._found: Outcome | None = None
        self._stored: list[Execution] = []

    def known(self) -> Outcome | None:
        """Run the known cases, and return the outcome when one ends the campaign."""
        for phase, provider in known_cases(self._settings):
            execution = execute(self._body, provider, self._settings.max_choices)
            self._observer(phase, execution)
            if phase == "stored":
                self._stored.append(execution)
            ended = self._take(execution, isinstance(provider, Valuing))
            if ended is not None:
                return ended
        return None

    def next(self) -> Outcome | None:
        """Run the next case, and return the outcome when it ends the campaign."""
        provider: Provider
        if self._pool and self._source.coin(_MUTATE_NUM, _MUTATE_DEN):
            provider = _Mutating(_mutation(self._pool, self._source), self._source)
        else:
            provider = Generating(case_source(self._settings.seed, self._index))
            self._index += 1
        execution = execute(self._body, provider, self._settings.max_choices)
        self._observer("random", execution)
        return self._take(execution, False)

    def _take(self, execution: Execution, valued: bool) -> Outcome | None:
        """Count an execution, conclude a failure, and admit a valid case to the pool.

        The result is the outcome that ends the campaign, or None. When valued
        is True, the case is an example of values.
        """
        self._tally.take(execution)
        if execution.status == "failed":
            return self._fail(execution, valued)
        if execution.status == "passed":
            self._admit(execution)
        return None

    def _fail(self, execution: Execution, valued: bool) -> Outcome | None:
        """Conclude a failing execution whose identity no earlier failure had.

        The result is the flaky outcome of a replay that differs, or None.
        The other failures that the shrink finds join the others of the
        conclusion. The failures of an identity that the campaign concluded
        before are left out.
        """
        identity = cast("str", identity_of(execution))
        if identity in self._identities:
            return None
        found = replace(
            self._tally.outcome("counterexample", failing=execution), valued=valued
        )
        outcome = conclude(self._body, self._settings, found, self._observer)
        if outcome.kind == "flaky":
            flaky = self._tally.outcome(
                "flaky", failing=outcome.failing, divergence=outcome.divergence
            )
            return replace(flaky, stored=tuple(self._stored))
        self._identities.add(identity)
        others: list[Execution] = []
        for other in outcome.others:
            key = cast("str", identity_of(other))
            if key in self._identities:
                continue
            self._identities.add(key)
            others.append(other)
        concluded = replace(outcome, others=tuple(others))
        if self._concluded is not None:
            self._concluded(concluded)
        if self._found is None:
            self._found = concluded
            return None
        failing = cast("Execution", concluded.failing)
        self._found = replace(
            self._found, others=(*self._found.others, failing, *others)
        )
        return None

    def _admit(self, execution: Execution) -> None:
        """Add a valid case to the pool when it shows new behaviour.

        A case shows new behaviour when it counts a new label, records a new
        fingerprint, or scores above the best score of a label.
        """
        c = execution.case
        novel = False
        for label in c.labels:
            novel = novel or label not in self._labels
            self._labels.add(label)
        for fingerprint in c.fingerprints:
            novel = novel or fingerprint not in self._fingerprints
            self._fingerprints.add(fingerprint)
        for label, score in c.targets.items():
            best = self._best.get(label)
            if best is not None and not score > best:
                continue
            self._best[label] = score
            novel = True
        if not novel:
            return
        bounds = tuple(request.bounds for request in c.requests)
        self._pool.append(_Member(tuple(c.choices), bounds, tuple(c.spans)))

    def result(self) -> Outcome:
        """Return the outcome of a campaign whose budget has passed.

        The outcome is the first failure that the campaign concluded. Every
        later failure is among its others. Without a failure, the last check
        of a run decides the outcome over every valid case.
        """
        tally = self._tally
        stored = tuple(self._stored)
        if self._found is not None:
            return replace(
                self._found, cases=tally.valid, rejected=tally.rejected, stored=stored
            )
        missing = tally.failure_without_counterexample()
        if missing is not None:
            return replace(missing, stored=stored)
        shortfall, _ = shortfall_of(tally, self._settings.requirements, True, False)
        kind: Kind = "passed" if shortfall is None else "coverage-unmet"
        return replace(tally.outcome(kind, shortfall=shortfall), stored=stored)


def campaign(
    body: Body,
    settings: Settings,
    budget: float,
    observer: Observer = unobserved,
    concluded: Callable[[Outcome], None] | None = None,
    now: Callable[[], float] | None = None,
) -> Outcome:
    """Run the known cases of a run, then cases until the budget has passed.

    A failing case whose identity no earlier failure had is replayed, shrunk
    and explained in the same way as the failure of a run. concluded receives
    the outcome. The campaign then goes on. A replay that differs ends the
    campaign as flaky.

    When the budget has passed, the campaign returns a counterexample of the
    first failure that it concluded. Every later failure is among its others.
    Without a failure, the last check of a run decides the outcome over every
    valid case of the campaign. The outcome counts the cases of the campaign
    and contains the runs of the stored cases. The random and the mutated
    cases run under the phase random.

    Args:
        body: The body.
        settings: The settings of the run.
        budget: The exploration time in seconds.
        observer: The observer of every call of the body with its phase. The
            calls arrive in the order of the campaign.
        concluded: Called with each failure when the campaign concludes it.
        now: Returns the time in seconds that measures the budget. The
            default is time.monotonic. The campaign resolves the default when
            it starts.

    Returns:
        The outcome.

    Raises:
        TraceError: A trace has an entry that the body cannot follow.
    """
    clock = time.monotonic if now is None else now
    end = clock() + budget
    exploration = _Exploration(body, settings, observer, concluded)
    known = exploration.known()
    if known is not None:
        return known
    while clock() < end:
        ended = exploration.next()
        if ended is not None:
            return ended
    return exploration.result()
