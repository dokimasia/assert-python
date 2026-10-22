# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The phases, the counts and the outcome of a run.

The runner calls a body once per case in four phases. It stops at the first
failing case.

1. The traces, the examples and the stored cases run first. The traces of
   cases whose draws and steps the caller gives come first. The examples of
   cases whose values the caller gives follow in order. The stored choice
   sequences come last. An example is a choice sequence, or the values of
   its draws when its generator does not have an inverse. These cases do
   not enter the case tree. A trace that the body cannot follow raises
   TraceError. The error ends the run before any other case runs.
2. The simplest case runs next. Each of its choices is the target of its
   request.
3. The random cases follow. Random case i of the seed runs for i = 0, 1, 2
   and so on. The random cases stop when `cases` valid cases have run, when
   the domain is exhausted, or after ten times `cases` random cases. That
   count includes repeats. A prefix case follows each random case while at
   most min(cases // 10, 50) cases are valid and the random case made at
   least two choices. The next edge case follows too, until all four have
   run. The edge cases that are left when the random cases stop run after
   them.
4. The coverage cases run last. When a requirement is undecided at a check,
   further random cases run up to the next check. The checks are at 2, 4
   and 8 times `cases`.

A valid case passed and did not repeat an earlier case. The valid cases of
every earlier phase count towards `cases`.

A run on more than one worker runs the cases of the last three phases on
the workers of an executor. It takes them in the order of one worker, and it
reports the same outcome as a run on one worker.

A failing case is replayed, shrunk and explained. The run then ends as a
counterexample, or as flaky when the replay differs. A diverging body ends
the run as flaky. A shrink budget of 0 skips the replay, the shrink and the
explanation. The run then reports the first failing case as found. A failing
example of values does not record a choice. The run reports it as found and
skips the replay and the explanation. Its outcome does not have a token.

A run that did not find a failing case still fails when it rejected more
than ten times as many cases as were valid. It also fails when no case
requested an input, or when a coverage requirement is refuted or unmet. The
checks run in that order.

A campaign shares the counts, the known cases and the conclusion of a
failure with a run. This module exports them for the campaign.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import Literal, cast

from dokimi_assert._prop.engine import coverage
from dokimi_assert._prop.engine.case import (
    MAX_CHOICES,
    Provider,
    Replaying,
    Valuing,
)
from dokimi_assert._prop.engine.choice import Choice
from dokimi_assert._prop.engine.edge import BOUNDARIES
from dokimi_assert._prop.engine.execution import (
    Body,
    Divergence,
    Execution,
    Observer,
    Phase,
    execute,
    identity_of,
    unobserved,
)
from dokimi_assert._prop.engine.executor import Ahead, Serial
from dokimi_assert._prop.engine.shrink import (
    DEFAULT_BUDGET,
    Explained,
    Shrinker,
    confirm,
    explain,
)
from dokimi_assert._prop.engine.tokens import encode
from dokimi_assert._prop.engine.traces import Entry, Tracing
from dokimi_assert._prop.engine.tree import Tree

__all__ = [
    "DEFAULT_CASES",
    "Kind",
    "Outcome",
    "Requirement",
    "Settings",
    "Shortfall",
    "Tally",
    "Values",
    "conclude",
    "conclude_case",
    "known_cases",
    "run",
    "run_stored",
    "shortfall_of",
]

#: The number of valid cases that a run aims for when the caller does not
#: give one.
DEFAULT_CASES = 100

#: A run that rejects more than this many cases for every valid one ends as
#: rejected.
_MAX_REJECTIONS = 10

#: A phase generates at most this many times as many random cases as the
#: valid cases that it aims for.
_GENERATION_FACTOR = 10

#: A run tries prefix cases while at most cases // _PREFIX_DIVISOR of its
#: cases are valid. That limit is at most _MAX_PREFIX_CASES.
_PREFIX_DIVISOR = 10
_MAX_PREFIX_CASES = 50

#: A random case has a prefix case only when it made at least this many
#: choices.
_MIN_PREFIXED_CHOICES = 2

#: How a run ended. Every kind but passed fails the test.
Kind = Literal[
    "passed", "counterexample", "flaky", "rejected", "coverage-unmet", "vacuous"
]


@dataclass(frozen=True, slots=True)
class Requirement:
    """A label and the smallest share of the valid cases that must count it.

    Attributes:
        label: The label.
        share: The share from 0 to 1.
    """

    label: str
    share: float


@dataclass(frozen=True, slots=True)
class Values:
    """An example that gives the values of the draws of a generator without an inverse.

    Attributes:
        values: The values of the draws in order.
    """

    values: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class Settings:
    """The settings of a run.

    Attributes:
        seed: The seed of the run.
        cases: The number of valid cases that the run aims for.
        max_choices: The largest number of choices of a case.
        requirements: The coverage requirements in order.
        traces: The cases whose draws and machine steps the caller gives.
            They run first.
        examples: The cases whose values the caller gives. They run next.
            Each example is the choice sequence that decodes to its values,
            or its Values.
        stored: The stored choice sequences from the oldest.
        shrink: The number of runs that shrinking and explaining every
            failure can spend. A budget of 0 turns both off.
        shrink_time: The seconds that shrinking and explaining can take on
            the platform clock. 0 means no limit.
        explain: When True, the run explains a counterexample.
        workers: The number of cases, shrink candidates and explain fillings
            that run at once on threads. A run on more than one worker
            reports the same outcome as a run on one.
        replay: The one case that the run tries, or None for a full run.
    """

    seed: int
    cases: int = DEFAULT_CASES
    max_choices: int = MAX_CHOICES
    requirements: tuple[Requirement, ...] = ()
    traces: tuple[tuple[Entry, ...], ...] = ()
    examples: tuple[tuple[Choice, ...] | Values, ...] = ()
    stored: tuple[tuple[Choice, ...], ...] = ()
    shrink: int = DEFAULT_BUDGET
    shrink_time: float = 0.0
    explain: bool = True
    workers: int = 1
    replay: tuple[Choice, ...] | None = None

    def __post_init__(self) -> None:
        """Refuse a run of fewer than one case, and a run on fewer than one worker.

        Raises:
            ValueError: cases or workers is below 1.
        """
        if self.cases < 1:
            msg = f"prop: a run of {self.cases} cases does not test anything"
            raise ValueError(msg)
        if self.workers < 1:
            msg = f"prop: a run on {self.workers} workers does not run anything"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Shortfall:
    """The counts of a requirement that a run refuted or left unmet.

    Attributes:
        requirement: The requirement.
        counted: The number of valid cases that counted its label.
        valid: The number of valid cases.
        verdict: The verdict. It is refuted or unmet.
    """

    requirement: Requirement
    counted: int
    valid: int
    verdict: coverage.Verdict


@dataclass(frozen=True, slots=True)
class Outcome:
    """The outcome of a run.

    Attributes:
        kind: How the run ended.
        cases: The number of valid cases.
        rejected: The number of rejected cases.
        seed: The seed of the run.
        failing: The minimal failing execution of a counterexample, or the
            case that a flaky replay contradicted.
        divergence: The difference that made a run flaky.
        shortfall: The requirement that a coverage-unmet run missed.
        others: The minimal executions of the other failures in the order of
            discovery.
        explanation: The explanation of each draw of the counterexample.
        token: The replay token of failing.
        runs: The number of runs that shrinking and explaining spent.
        valued: When True, an example of values found the counterexample.
            Such a counterexample does not have a token.
        stored: The runs of the stored cases in order. They end at the
            stored case that ended the run.
    """

    kind: Kind
    cases: int
    rejected: int
    seed: int
    failing: Execution | None = None
    divergence: Divergence | None = None
    shortfall: Shortfall | None = None
    others: tuple[Execution, ...] = ()
    explanation: tuple[Explained, ...] = ()
    token: str | None = None
    runs: int = 0
    valued: bool = False
    stored: tuple[Execution, ...] = ()


class Tally:
    """The counts of a run so far. Every outcome takes its counts from the tally.

    Attributes:
        seed: The seed of the run.
        valid: The number of valid cases.
        rejected: The number of rejected cases.
        requested: When True, a case requested an input.
        labels: The number of valid cases that counted each label.
    """

    def __init__(self, seed: int) -> None:
        """Return the counts of a run of seed that has not run a case.

        Args:
            seed: The seed of the run.
        """
        self.seed: int = seed
        self.valid: int = 0
        self.rejected: int = 0
        self.requested: bool = False
        self.labels: Counter[str] = Counter()

    def take(self, execution: Execution) -> Outcome | None:
        """Count one execution, and return the outcome when it ends the run.

        A failed case ends the run with a counterexample. A diverged case
        ends it as flaky. A case that repeated an earlier case does not
        count.

        Args:
            execution: The execution.

        Returns:
            The outcome, or None for a case that does not end the run.
        """
        c = execution.case
        self.requested = self.requested or bool(c.draws) or bool(c.choices)
        if execution.status == "failed":
            return self.outcome("counterexample", failing=execution)
        if execution.status == "diverged":
            return self.outcome("flaky", divergence=execution.divergence)
        if execution.status == "rejected":
            self.rejected += 1
        elif execution.status == "passed":
            self.valid += 1
            self.labels.update(c.labels)
        return None

    def outcome(
        self,
        kind: Kind,
        failing: Execution | None = None,
        divergence: Divergence | None = None,
        shortfall: Shortfall | None = None,
    ) -> Outcome:
        """Return an outcome of a kind with the counts so far.

        The other failures, the explanation and the stored runs of the
        outcome are empty.

        Args:
            kind: How the run ended.
            failing: The failing case.
            divergence: The divergence.
            shortfall: The shortfall.

        Returns:
            The outcome.
        """
        return Outcome(
            kind, self.valid, self.rejected, self.seed, failing, divergence, shortfall
        )

    def failure_without_counterexample(self) -> Outcome | None:
        """Return the outcome of too many rejections or of no input.

        More than ten rejected cases for every valid one end the run as
        rejected. Then a run in which no case requested an input ends as
        vacuous.

        Returns:
            The outcome, or None when neither ends the run.
        """
        if self.rejected > _MAX_REJECTIONS * self.valid:
            return self.outcome("rejected")
        if not self.requested:
            return self.outcome("vacuous")
        return None


def _prefix_cases(cases: int) -> int:
    """Return the largest number of valid cases at which a run tries a prefix case."""
    return min(cases // _PREFIX_DIVISOR, _MAX_PREFIX_CASES)


def shortfall_of(
    tally: Tally, requirements: tuple[Requirement, ...], last: bool, exact: bool
) -> tuple[Shortfall | None, bool]:
    """Return the first requirement that the counts refute or leave unmet.

    Args:
        tally: The counts.
        requirements: The requirements in order.
        last: When True, the check is the last. The last check decides every
            requirement.
        exact: When True, the run tested every input of the domain.

    Returns:
        The shortfall or None, and True when the counts meet every
        requirement.
    """
    met = True
    for requirement in requirements:
        counted = tally.labels[requirement.label]
        found = coverage.verdict(counted, tally.valid, requirement.share, last, exact)
        if found in ("refuted", "unmet"):
            return Shortfall(requirement, counted, tally.valid, found), False
        met = met and found == "met"
    return None, met


def conclude(
    body: Body, settings: Settings, outcome: Outcome, observer: Observer
) -> Outcome:
    """Replay, shrink and explain the failing case of a counterexample.

    The concluded outcome has the minimal case, the other failures that the
    shrink found and the replay token. A shrink budget of 0 adds the token
    alone. A replay that differs makes the outcome flaky. The function
    returns any other outcome and a counterexample of values unchanged. A
    counterexample of values does not record a choice.

    Args:
        body: The body.
        settings: The settings of the run.
        outcome: The outcome that the run ended with.
        observer: The observer of every call of the body with its phase.

    Returns:
        The concluded outcome.
    """
    if outcome.kind != "counterexample" or outcome.valued:
        return outcome
    failing = cast("Execution", outcome.failing)
    if settings.shrink == 0:
        return replace(outcome, token=encode(failing.case.choices))
    divergence = confirm(body, failing, settings.max_choices, observer)
    if divergence is not None:
        return replace(outcome, kind="flaky", divergence=divergence)
    shrinker = Shrinker(
        body,
        failing,
        settings.max_choices,
        settings.shrink,
        observer,
        settings.shrink_time,
        settings.workers,
    )
    shrinker.shrink_all()
    identity = cast("str", identity_of(failing))
    first = shrinker.failures[identity]
    others = tuple(
        found.execution
        for found in shrinker.failures.values()
        if found.identity != identity
    )
    explanation = (
        tuple(explain(shrinker, first, settings.seed)) if settings.explain else ()
    )
    return replace(
        outcome,
        failing=first.execution,
        others=others,
        explanation=explanation,
        token=encode(first.execution.case.choices),
        runs=shrinker.runs,
    )


class _Phases:
    """The cases of a run after its known cases in the order of one worker.

    The simplest case comes first. The prefix case and the next edge case
    follow each random case. The edge cases that are left when the random
    cases stop run after them. phase is the phase of the random cases. It is
    random up to the first check and coverage after it. The executor runs
    the cases on the workers of the settings.
    """

    def __init__(
        self, body: Body, settings: Settings, tally: Tally, observer: Observer
    ) -> None:
        """Return the phases of a run that has run its known cases."""
        self.settings: Settings = settings
        self.tally: Tally = tally
        self._observer: Observer = observer
        self.tree: Tree = Tree()
        seed, max_choices, workers = (
            settings.seed,
            settings.max_choices,
            settings.workers,
        )
        self._executor: Serial | Ahead = (
            Serial(body, seed, max_choices, self.tree)
            if workers == 1
            else Ahead(body, seed, max_choices, self.tree, workers)
        )
        self._edges: int = 0
        self._index: int = 0
        self.phase: Phase = "random"

    def close(self) -> None:
        """End the run, and stop the workers of the executor."""
        self._executor.close()

    def _seen(self, phase: Phase, execution: Execution) -> Outcome | None:
        """Pass one case of a phase to the observer, and count it.

        The result is the outcome when the case ends the run, and None
        otherwise.
        """
        self._observer(phase, execution)
        return self.tally.take(execution)

    def simplest(self) -> Outcome | None:
        """Run the simplest case. Each of its choices is the target of its request."""
        return self._seen("simplest", self._executor.replay([]))

    def _random(self) -> Outcome | None:
        """Run the next random case, then its prefix case and the next edge case."""
        generated = self._executor.random(self._index)
        self._index += 1
        outcome = self._seen(self.phase, generated.execution)
        if outcome is not None:
            return outcome
        choices = generated.choices
        prefixed = (
            self.tally.valid <= _prefix_cases(self.settings.cases)
            and len(choices) >= _MIN_PREFIXED_CHOICES
            and not self.tree.exhausted
        )
        if prefixed:
            cut = 1 + generated.source.below(len(choices) - 1)
            prefix = self._seen("prefix", self._executor.replay(choices[:cut]))
            if prefix is not None:
                return prefix
        return self._next_edge()

    def _next_edge(self) -> Outcome | None:
        """Run the next edge case, unless none is left or the domain is exhausted."""
        if self._edges == len(BOUNDARIES) or self.tree.exhausted:
            return None
        execution = self._executor.edge(self._edges)
        self._edges += 1
        return self._seen("edge", execution)

    def run_to(self, target: int) -> Outcome | None:
        """Run random cases until target cases are valid, then the edge cases left.

        The random cases also stop when the domain is exhausted, and after
        ten times target random cases. That count includes repeats.
        """
        while (
            self.tally.valid < target
            and not self.tree.exhausted
            and self._index < _GENERATION_FACTOR * target
        ):
            outcome = self._random()
            if outcome is not None:
                return outcome
        while self._edges < len(BOUNDARIES) and not self.tree.exhausted:
            outcome = self._next_edge()
            if outcome is not None:
                return outcome
        return None


def _example_provider(example: tuple[Choice, ...] | Values) -> Provider:
    """Return the provider of the values or the choices of an example."""
    if isinstance(example, Values):
        return Valuing(example.values)
    return Replaying(example)


def known_cases(settings: Settings) -> list[tuple[Phase, Provider]]:
    """Return the cases that a run tries before it generates any.

    The traces and the examples run in order under the phase example. The
    stored cases then run under the phase stored.

    Args:
        settings: The settings of the run.

    Returns:
        The phase and the provider of each case.
    """
    known: list[tuple[Phase, Provider]] = [
        ("example", Tracing(trace)) for trace in settings.traces
    ]
    known.extend(("example", _example_provider(one)) for one in settings.examples)
    known.extend(("stored", Replaying(choices)) for choices in settings.stored)
    return known


def _try_known(
    body: Body,
    settings: Settings,
    tally: Tally,
    observer: Observer,
    stored: list[Execution],
) -> Outcome | None:
    """Run the known cases outside the case tree until one ends the run.

    The result is the outcome of that case, or None. stored receives the
    run of each stored case. A known case runs outside the tree, so it
    cannot diverge. The outcome is therefore a counterexample.
    """
    for phase, provider in known_cases(settings):
        execution = execute(body, provider, settings.max_choices)
        observer(phase, execution)
        if phase == "stored":
            stored.append(execution)
        outcome = tally.take(execution)
        if outcome is not None:
            valued = isinstance(provider, Valuing)
            return replace(outcome, valued=valued, stored=tuple(stored))
    return None


def _checks(phases: _Phases) -> Outcome | None:
    """Run the random phase to each check, and return the outcome that ends the run.

    The result is None when the run passes. The random cases after the
    first check belong to the coverage phase. A run without requirements
    meets them all at the first check. The last check decides every
    requirement. The checks therefore end with a pass or an outcome.
    """
    settings = phases.settings
    tally = phases.tally
    multiples = coverage.CHECKS if settings.requirements else coverage.CHECKS[:1]
    position = 0
    while True:
        phases.phase = "random" if position == 0 else "coverage"
        outcome = phases.run_to(multiples[position] * settings.cases)
        if outcome is None:
            outcome = tally.failure_without_counterexample()
        if outcome is not None:
            return outcome
        last = position == len(multiples) - 1
        shortfall, met = shortfall_of(
            tally, settings.requirements, last, phases.tree.exhausted
        )
        if shortfall is not None:
            return tally.outcome("coverage-unmet", shortfall=shortfall)
        if met:
            return None
        position += 1


def _explore(body: Body, settings: Settings, observer: Observer) -> Outcome:
    """Run the phases until the run ends, without the conclusion of a counterexample."""
    tally = Tally(settings.seed)
    stored: list[Execution] = []
    known = _try_known(body, settings, tally, observer, stored)
    if known is not None:
        return known
    phases = _Phases(body, settings, tally, observer)
    try:
        outcome = phases.simplest()
        if outcome is None:
            outcome = _checks(phases)
    finally:
        phases.close()
    if outcome is None:
        outcome = tally.outcome("passed")
    return replace(outcome, stored=tuple(stored))


def _replay_only(
    body: Body, settings: Settings, choices: tuple[Choice, ...], observer: Observer
) -> Outcome:
    """Run the one case that choices record, and report it as found.

    The case runs outside a case tree, so it cannot diverge. When it ends
    the run, the outcome is a counterexample.
    """
    tally = Tally(settings.seed)
    execution = execute(body, Replaying(choices), settings.max_choices)
    observer("token", execution)
    outcome = tally.take(execution)
    if outcome is not None:
        return replace(outcome, token=encode(execution.case.choices))
    without = tally.failure_without_counterexample()
    return tally.outcome("passed") if without is None else without


def run(body: Body, settings: Settings, observer: Observer = unobserved) -> Outcome:
    """Run the phases, and return the outcome.

    A run with replay set runs that one case instead, and it neither shrinks
    nor explains the case.

    Args:
        body: The body.
        settings: The settings of the run.
        observer: The observer of every call of the body with its phase. The
            calls arrive in the order of the run.

    Returns:
        The outcome.

    Raises:
        TraceError: A trace has an entry that the body cannot follow.
    """
    if settings.replay is not None:
        return _replay_only(body, settings, settings.replay, observer)
    return conclude(body, settings, _explore(body, settings, observer), observer)


def run_stored(
    body: Body, settings: Settings, observer: Observer = unobserved
) -> Outcome:
    """Run the stored cases of settings from the oldest in the same way as run.

    The result is a pass that counts them, or the outcome of the first
    stored case that does not pass. A failing stored case is reported as
    found with its token. The run does not shrink or explain it. The outcome
    contains the runs of the stored cases up to the case that ended the run.
    The traces and the examples of the settings do not run. A stored case
    runs outside a case tree, so it cannot diverge.

    Args:
        body: The body.
        settings: The settings of the run.
        observer: The observer of every call of the body with its phase.

    Returns:
        The outcome.
    """
    only = replace(settings, traces=(), examples=())
    tally = Tally(only.seed)
    stored: list[Execution] = []
    outcome = _try_known(body, only, tally, observer, stored)
    if outcome is None:
        return replace(tally.outcome("passed"), stored=tuple(stored))
    failing = cast("Execution", outcome.failing)
    return replace(outcome, token=encode(failing.case.choices))


def conclude_case(
    body: Body, settings: Settings, failing: Execution, observer: Observer = unobserved
) -> Outcome:
    """Replay, shrink and explain a failed case that the body ran outside a run.

    The fuzz bridge decodes such a case from the input of a fuzzer. The
    result is a counterexample with 0 valid cases, or a flaky outcome when
    the replay of failing differs from it.

    Args:
        body: The body.
        settings: The settings of the run.
        failing: The failed execution.
        observer: The observer of every call of the body with its phase.

    Returns:
        The outcome.
    """
    found = Tally(settings.seed).outcome("counterexample", failing=failing)
    return conclude(body, settings, found, observer)
