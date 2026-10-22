# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The steps of a machine in a case."""

from __future__ import annotations

import functools
import inspect
import threading
from fractions import Fraction
from typing import TYPE_CHECKING, Any, Generic, TypeVar, cast

from dokimi_assert._history.concurrently import concurrently
from dokimi_assert._history.linearizable import LINEARIZABLE, fields_of, whole
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.loop import Loop
from dokimi_assert._prop.case import Case, FaultSignal, on_engine
from dokimi_assert._prop.engine import draw
from dokimi_assert._prop.engine.case import Case as Engine
from dokimi_assert._prop.engine.case import Place, Request, Step
from dokimi_assert._prop.engine.choice import IntegerBounds, Value
from dokimi_assert._prop.engine.collection import Sizes, more
from dokimi_assert._prop.engine.traces import Tracing
from dokimi_assert._stateful.machine import Action, Machine, validate
from dokimi_assert._stateful.option import Config, Option, configure
from dokimi_assert.failure import Failure, call_site

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from dokimi_assert._history.spec import Spec

__all__ = ["steps"]

_S = TypeVar("_S")
_T = TypeVar("_T")

#: The name of the operation. The text of each fault of steps starts with it.
_OP = "stateful.steps"

#: The contract of the check after a step.
_CONTRACT = "the history of the steps of the machine is linearizable"

#: The odds with which the swarm keeps an action, before the draw makes the
#: choices keep one action at least.
_SWARM = Fraction(1, 2)

#: The bounds of a swarm choice that must keep the last action, and of a
#: swarm choice that can drop its action.
_FORCED = IntegerBounds(1, 1)
_FREE = IntegerBounds(0, 1)

#: A step of a concurrent section that the run plans before any step runs.
#: It has the action and the input of the step.
_Planned = tuple[Action[Any], Any]


def steps(case: Case, machine: Machine[_S], *options: Option) -> None:
    """Take the steps of a machine in a case.

    Each decision of the steps is a choice of the case. The steps run in six
    parts:

    1. The swarm makes one choice per action, in order. The choice decides
       whether the case keeps the action. A random case keeps each action
       with the odds 1 in 2, and the draw makes the case keep one action at
       least. Under swarm(False), the case keeps every action.
    2. Setup runs the check of the history, and then the invariant.
    3. The sequential steps run on client 0. Before each step, steps lists
       the kept actions that are enabled in every state that the last check
       left. The steps end when the list is empty. Otherwise a continue flag
       decides, with the mean of mean and the most steps of max_steps. An
       index into the list then chooses the action by weight. The step is a
       span with the name of the action, from its flag to the end of its run.
       Inside the span, the step requests its input and runs the action. The
       check and the invariant run after each step.
    4. A concurrent section runs for clients of 2 or more. The section plans
       every step before any step runs. A planned step is a flag with the
       most steps of concurrent, a client from 0 to the clients, an index
       into the kept actions without enabled, and the input of the step.
       Client 0 runs its steps first. Then the other clients that have a
       step run their steps at the same time. Under tasks, they run as tasks
       of its scheduler, spawned in client order. Otherwise they run on
       threads through history.concurrently, and the case runs up to repeat
       times, because threads do not replay. The check runs after the
       section.
    5. The drain takes steps of the actions with drain set, without a flag.
       It goes on until no drain action is enabled or max_steps steps have
       run. The check and the invariant run after each step.
    6. Settle runs, and then the invariant.

    The check searches the history of the case with the spec of the
    machine, with every call in one partition. The next state is the first
    of the states that the order of the search leaves. A check that does not
    pass ends the case with a record of linearizable. The contract of the
    record is "the history of the steps of the machine is linearizable".

    The case of the draws option follows its trace. The swarm keeps the
    actions that the step entries of the trace name, and each step entry
    becomes the choices of one step. A step entry that steps cannot take at
    its position ends the run with a fault at the entry, before any other
    case runs. steps cannot take a step entry of an action that the list of
    the step does not have, or of a step past the most steps of its part. It
    also cannot take a client outside the clients, a concurrent step of a
    machine with one client, or a drain step after the drain.

    Each request that the case makes while steps runs belongs to the part
    and the step that run. Each fingerprint that the case observes belongs
    to them too, and the divergence of a flaky run reports them. A step has
    its position in its part from 0, and its action once its index has
    chosen it. A swarm choice has the position of its action. Setup, settle
    and the run of the steps of a concurrent section do not have a position.

    The run of an action and settle can return an awaitable. steps runs the
    awaitable to its end on an event loop of its own, and a task of the
    scheduler awaits it. When an event loop already runs in the thread, an
    awaitable ends the run of the property with a fault.

    Args:
        case: The case.
        machine: The machine.
        *options: The settings of the run.

    Raises:
        ValueError: An action has a weight that is not an int of 0 or more,
            or two actions have one name.
        TypeError: The run of an action is not callable.

    Example:
        stateful.steps(c, QueueMachine(Queue(4)), stateful.clients(2))
    """
    validate(machine)
    config = configure(options)
    with Loop(_OP) as loop:
        _Run(case, machine, config, loop).run()


def _position(listed: Sequence[Action[Any]], name: str) -> int | None:
    """Return the index of the action of a name in listed, or None without one."""
    return next((i for i, action in enumerate(listed) if action.name == name), None)


def _resolved(loop: Loop, value: object) -> None:
    """Run an awaitable that an action or settle returned to its end on loop.

    Raises:
        FaultSignal: An event loop already runs in the thread, so loop cannot
            run the awaitable.
    """
    try:
        loop.resolve(value)
    except FaultError as fault:
        raise FaultSignal(fault) from None


class _Run(Generic[_S]):
    """One run of the steps of a machine in one case."""

    def __init__(
        self, c: Case, machine: Machine[_S], config: Config, loop: Loop
    ) -> None:
        """Return the run of the steps of a machine in a case under the settings."""
        self._c: Case = c
        self._e: Engine = on_engine(c, lambda e: e)
        self._machine: Machine[_S] = machine
        self._actions: list[Action[_S]] = list(machine.actions)
        self._spec: Spec[_S] | None = getattr(machine, "spec", None)
        self._config: Config = config
        self._loop: Loop = loop
        provider = self._e.provider
        self._trace: Tracing | None = (
            provider if isinstance(provider, Tracing) else None
        )
        self._states: tuple[_S, ...] = (cast("_S", None),)

    def run(self) -> None:
        """Run the six parts in order, and restore the place of the case at the end."""
        before = self._e.place
        try:
            kept = self._swarm()
            self._at(Place("setup"))
            self._check()
            self._invariant()
            self._sequential(kept)
            self._concurrent(kept)
            self._drain()
            self._at(Place("settle"))
            settle = getattr(self._machine, "settle", None)
            if settle is not None:
                _resolved(self._loop, settle(self._c, self._state()))
            self._invariant()
        finally:
            self._at(before)

    def _on(self, fn: Callable[[Engine], _T]) -> _T:
        """Return what fn returns on the engine case in the same way as a draw."""
        return on_engine(self._c, fn)

    def _choose(self, request: Request) -> Value:
        """Return the value of the case for a request."""
        return self._on(lambda e: e.choose(request))

    def _at(self, place: Place | None) -> None:
        """Make place the place of the case."""
        self._e.place = place

    def _swarm(self) -> list[Action[_S]]:
        """Return the actions that the case keeps, in order.

        A case that follows a trace keeps the actions that the step entries of
        the trace name.
        """
        actions = self._actions
        if not self._config.swarm:
            return list(actions)
        named = set() if self._trace is None else set(self._trace.actions())
        kept: list[Action[_S]] = []
        for position, action in enumerate(actions):
            self._at(Place("swarm", position, action.name))
            if self._trace is not None:
                self._trace.prepare(1 if action.name in named else 0)
            earlier = bool(kept)
            remaining = len(actions) - position
            bounds = _FORCED if not earlier and remaining == 1 else _FREE
            keep = functools.partial(
                draw.keep, p=_SWARM, kept=earlier, remaining=remaining
            )
            if self._choose(Request(bounds, keep, 1)) == 1:
                kept.append(action)
        return kept

    def _sequential(self, kept: Sequence[Action[_S]]) -> None:
        """Take sequential steps until no kept action is enabled or a flag is 0."""
        sizes = Sizes(0, self._config.max_steps)
        count = 0
        while True:
            self._at(Place("sequential", count))
            available = self._available(kept)
            start = len(self._e.choices)
            if self._trace is not None:
                self._follow_sequential(self._trace, available, count)
            if not available or not self._more(count, sizes, self._config.mean):
                return
            self._take(start, available, "sequential", count)
            count += 1

    def _concurrent(self, kept: Sequence[Action[_S]]) -> None:
        """Plan the steps of the concurrent section, run them, and check the history."""
        clients = self._config.clients
        if clients == 1:
            if self._trace is not None:
                self._refuse_concurrent(self._trace)
            return
        eligible = [action for action in kept if action.enabled is None]
        planned: list[list[_Planned]] = [[] for _ in range(clients + 1)]
        sizes = Sizes(0, self._config.concurrent)
        count = 0
        while True:
            self._at(Place("concurrent", count))
            start = len(self._e.choices)
            if self._trace is not None:
                self._follow_concurrent(self._trace, eligible, count)
            if not eligible or not self._more(count, sizes, None):
                break
            client = self._client()
            action = eligible[self._index(eligible)]
            self._at(Place("concurrent", count, action.name))
            planned[client].append((action, self._plan(start, action, client)))
            count += 1
        self._at(Place("concurrent"))
        self._section(planned)
        self._check()

    def _plan(self, start: int, action: Action[_S], client: int) -> Any:
        """Record a concurrent step of an action on a client, and return its input.

        The span of the step starts at its flag and ends after its input.
        """
        close = self._on(lambda e: e.open(action.name, start))
        try:
            self._on(lambda e: e.step(Step(action.name, client)))
            return self._input(action)
        finally:
            close()

    def _section(self, planned: Sequence[Sequence[_Planned]]) -> None:
        """Run the planned steps of client 0, and then those of the other clients.

        The other clients run as tasks of the scheduler, spawned in client
        order, or on threads. For clients on threads, the run sets the runs
        of the case to the option repeat.
        """
        self._run_steps(0, planned[0], self._loop)
        active = [client for client in range(1, len(planned)) if planned[client]]
        scheduler = self._config.scheduler
        if scheduler is not None:
            for client in active:
                scheduler.spawn(functools.partial(self._task, client, planned[client]))
            scheduler.run()
            return
        if not active:
            return
        self._on(lambda e: e.repeat(self._config.repeat))
        concurrently(
            len(active),
            threading.TIMEOUT_MAX,
            lambda i: self._thread(active[i], planned[active[i]]),
        )

    def _run_steps(self, client: int, listed: Sequence[_Planned], loop: Loop) -> None:
        """Run the planned steps of a client in order, and their awaitables on loop."""
        for action, value in listed:
            _resolved(loop, action.run(self._c, client, value))

    def _thread(self, client: int, listed: Sequence[_Planned]) -> None:
        """Run the planned steps of a client on its thread, with its own event loop."""
        with Loop(_OP) as loop:
            self._run_steps(client, listed, loop)

    async def _task(self, client: int, listed: Sequence[_Planned]) -> None:
        """Run the planned steps of a client as a task, and await their awaitables."""
        for action, value in listed:
            result = action.run(self._c, client, value)
            if inspect.isawaitable(result):
                await result

    def _drain(self) -> None:
        """Take drain steps until no drain action is enabled or the most steps ran."""
        drains = [action for action in self._actions if action.drain]
        count = 0
        while True:
            self._at(Place("drain", count))
            enabled = count < self._config.max_steps
            available = self._available(drains) if enabled else []
            if self._trace is not None:
                self._follow_drain(self._trace, available)
            if not available:
                return
            self._take(len(self._e.choices), available, "drain", count)
            count += 1

    def _take(
        self, start: int, listed: Sequence[Action[_S]], part: str, position: int
    ) -> None:
        """Take a sequential or a drain step on client 0.

        The index of the case chooses the action of the step from listed. The
        step is a span with the name of the action from start. Inside the
        span, the case records the step, the step requests its input, and the
        action runs. The check and the invariant run after the step.
        """
        action = listed[self._index(listed)]
        self._at(Place(part, position, action.name))
        taken = Step(action.name, None, part == "drain")
        close = self._on(lambda e: e.open(action.name, start))
        try:
            self._on(lambda e: e.step(taken))
            _resolved(self._loop, action.run(self._c, 0, self._input(action)))
        finally:
            close()
        self._check()
        self._invariant()

    def _available(self, listed: Sequence[Action[_S]]) -> list[Action[_S]]:
        """Return the actions of listed that are enabled in each state of the check.

        Each enabled runs once for each state, also after a state for which it
        returned False.
        """
        available: list[Action[_S]] = []
        for action in listed:
            enabled = action.enabled
            if enabled is None:
                available.append(action)
                continue
            verdicts = [enabled(state) for state in self._states]
            if all(verdicts):
                available.append(action)
        return available

    def _more(self, count: int, sizes: Sizes, average: int | None) -> bool:
        """Return the continue flag of a part after count steps."""
        return self._on(lambda e: more(e, count, sizes, False, average))

    def _index(self, listed: Sequence[Action[_S]]) -> int:
        """Return the choice of the case of an action of listed, by weight."""
        weights = [max(action.weight, 1) for action in listed]
        bounds = IntegerBounds(0, len(listed) - 1)
        request = Request(bounds, lambda source: draw.weighted(source, weights), 0)
        return cast("int", self._choose(request))

    def _client(self) -> int:
        """Return the choice of the case of the client of a concurrent step.

        The choice is uniform over the clients, with the target 0.
        """
        clients = self._config.clients
        bounds = IntegerBounds(0, clients)
        request = Request(bounds, lambda source: source.below(clients + 1), 0)
        return cast("int", self._choose(request))

    def _input(self, action: Action[_S]) -> Any:
        """Return the input that an action requests, or None without an input."""
        return None if action.input is None else action.input(self._c, self._state())

    def _state(self) -> _S:
        """Return the first of the states that the last check left."""
        return self._states[0]

    def _invariant(self) -> None:
        """Run the invariant of the machine, when it has one."""
        invariant = getattr(self._machine, "invariant", None)
        if invariant is not None:
            invariant(self._c, self._state())

    def _check(self) -> None:
        """Check the history of the case against the spec, and keep the states after it.

        Every call of the history is in one partition. A check that does not
        pass ends the case with its record. A machine without a spec does not
        check anything.
        """
        spec = self._spec
        if spec is None:
            return
        detail, states = whole(self._c.history(), spec)
        if detail.outcome != "passed":
            failure = Failure(LINEARIZABLE, _CONTRACT, fields_of(detail), call_site())
            self._c.report(failure, True)
        self._states = states

    def _follow_sequential(
        self, trace: Tracing, available: Sequence[Action[_S]], count: int
    ) -> None:
        """Serve the flag and the index of the next entry of a sequential step.

        The entry is refused past the most steps, and for an action that
        available does not have.
        """

        def follow(_: Engine) -> None:
            step = trace.next_step()
            if step is None or step.client is not None or step.drain:
                return
            index = _position(available, step.action)
            if count == self._config.max_steps or index is None:
                trace.refuse()
            trace.take(1, index)

        self._on(follow)

    def _refuse_concurrent(self, trace: Tracing) -> None:
        """Refuse the next entry of a concurrent step, for a machine with one client."""

        def refuse(_: Engine) -> None:
            step = trace.next_step()
            if step is not None and step.client is not None and not step.drain:
                trace.refuse()

        self._on(refuse)

    def _follow_concurrent(
        self, trace: Tracing, eligible: Sequence[Action[_S]], count: int
    ) -> None:
        """Serve the flag, the client and the index of the next concurrent step entry.

        The entry is refused past the most steps, for a client outside the
        clients, and for an action that eligible does not have.
        """

        def follow(_: Engine) -> None:
            step = trace.next_step()
            if step is None or step.client is None or step.drain:
                return
            index = _position(eligible, step.action)
            outside = step.client < 0 or step.client > self._config.clients
            if count == self._config.concurrent or outside or index is None:
                trace.refuse()
            trace.take(1, step.client, index)

        self._on(follow)

    def _follow_drain(self, trace: Tracing, available: Sequence[Action[_S]]) -> None:
        """Serve the index of the next entry of a drain step.

        The entry is refused for an action that available does not have.
        Once the drain has ended, available is empty.
        """

        def follow(_: Engine) -> None:
            step = trace.next_step()
            if step is None or not step.drain:
                return
            index = _position(available, step.action)
            if index is None:
                trace.refuse()
            trace.take(index)

        self._on(follow)
