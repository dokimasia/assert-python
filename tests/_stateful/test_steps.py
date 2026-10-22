# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _stateful/steps.py tests the steps of a machine in a case.

The spec covers the swarm, the steps of each part, the checks, the traces
and the places. The choices, the steps and the refusals of a port of a
TypeScript case are those of the reference implementation of the
definition on the same machine and values.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._history.spec import Operation, Spec
from dokimi_assert._prop.case import Case, Failing, FaultSignal
from dokimi_assert._prop.engine.case import Case as Engine
from dokimi_assert._prop.engine.case import (
    Failed,
    Generating,
    Place,
    Span,
    Step,
    Where,
)
from dokimi_assert._prop.engine.choice import IntegerBounds
from dokimi_assert._prop.engine.generator import Integer
from dokimi_assert._prop.engine.source import Source
from dokimi_assert._prop.engine.traces import Draw, Entry, TraceError, Tracing
from dokimi_assert._stateful.machine import Action
from dokimi_assert._stateful.option import (
    Option,
    clients,
    concurrent,
    max_steps,
    mean,
    repeat,
    swarm,
    tasks,
)
from dokimi_assert._stateful.scheduler import Scheduler
from dokimi_assert._stateful.steps import steps
from dokimi_assert._stateful.strategy import uniform
from helpers import body_case, refusal, replaying

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

#: The generator of the inputs of the actions.
DIGIT = Integer(IntegerBounds(0, 9))

#: The bounds of a choice between two values, and of a choice of one value.
BINARY = IntegerBounds(0, 1)
ONE = IntegerBounds(0, 0)


@dataclass
class Plain:
    """A machine of fields. A function of None is absent."""

    actions: list[Action[Any]]
    spec: Spec[Any] | None = None
    invariant: Callable[[Case, Any], object] | None = None
    settle: Callable[[Case, Any], object] | None = None


@dataclass
class Counting:
    """A spec whose state counts the calls, or whose next state is the one of step."""

    step: Callable[[int, Operation], list[int]] | None = None

    def initial(self) -> int:
        """Return the count before any call."""
        return 0

    def next(self, state: int, op: Operation) -> list[int]:
        """Return the count after one more call, or the states of step."""
        return [state + 1] if self.step is None else self.step(state, op)


#: A spec whose call leaves the count plus one, or the count.
LOSSY = Counting(lambda state, _: [state + 1, state])


class Log:
    """The inputs and the runs of the actions of a case, in order."""

    def __init__(self) -> None:
        """Return an empty log."""
        self.events: list[list[object]] = []

    def action(
        self,
        name: str,
        weight: int = 1,
        drain: bool = False,
        enabled: Callable[[Any], bool] | None = None,
        draws: bool = False,
    ) -> Action[Any]:
        """Return an action that records its call and logs its input and its run."""

        def input_of(c: Case, state: object) -> object:
            self.events.append(["input", name, state])
            return c.draw(DIGIT, "v") if draws else None

        def run(c: Case, client: int, value: object) -> None:
            c.history().invoke(client, name, [] if value is None else [value]).ok(None)
            self.events.append([name, client, value])

        return Action(name, run, weight, drain, enabled, input_of)

    def runs(self, name: str) -> list[list[object]]:
        """Return the runs of the action of a name, as their clients and inputs."""
        return [event for event in self.events if event[0] == name]


def replayed(machine: Plain, values: list[int], *options: Option) -> Engine:
    """Return the engine case of the steps of a machine on a replay of values."""
    c, engine = body_case(replaying(*values))
    steps(c, machine, *options)
    return engine


def section(c: Case, *more: Option) -> list[Option]:
    """Return the options of a concurrent section of two clients as tasks of c.

    The section has no sequential step and no swarm.
    """
    return [
        max_steps(0),
        swarm(False),
        clients(2),
        tasks(Scheduler(c, uniform())),
        *more,
    ]


def mean_steps(twin: Source, most: int) -> list[object]:
    """Return the steps of a mean of 3 on the coins of twin, and the last bounds.

    The last bounds are those of the flag that stops the steps. The flag is
    forced at the most steps, and free before them.
    """
    taken = 0
    while taken < most and twin.coin(3, 4):
        taken += 1
    return [taken, ONE if taken == most else BINARY]


def draining(log: Log, pending: list[int]) -> Plain:
    """Return a machine of an action a that adds a message and a drain action d.

    The action d delivers a message. The invariant of the machine logs the
    count of the spec.
    """

    def adds(c: Case, client: int, _: object) -> None:
        c.history().invoke(client, "a", []).ok(None)
        pending[0] += 1

    def delivers(c: Case, client: int, _: object) -> None:
        c.history().invoke(client, "d", []).ok(None)
        pending[0] -= 1

    return Plain(
        [
            Action("a", adds),
            Action("d", delivers, drain=True, enabled=lambda _: pending[0] > 0),
        ],
        Counting(),
        invariant=lambda _, state: log.events.append(["invariant", state]),
    )


def requests_of(engine: Engine) -> list[tuple[object, int | None]]:
    """Return the bounds and the edge of each request of an engine case."""
    return [(request.bounds, request.edge) for request in engine.requests]


def actions_of(engine: Engine) -> list[str]:
    """Return the action of each step of an engine case."""
    return [taken.action for _, taken in engine.steps]


def failing_of(run: Callable[[], object]) -> Failing:
    """Return the record with which run fails its case."""
    with pytest.raises(Failed) as raised:
        run()
    return cast("Failing", raised.value.record)


def refused(seat: Collector, run: Callable[[], object]) -> TraceError:
    """Return the TraceError with which run refuses an entry of a trace."""
    error = check.raises(seat, run, "steps refuses an entry of the trace")
    traced = check.error_as(seat, error, TraceError, "the refusal is a TraceError")
    return cast("TraceError", traced)


def traced(trace: list[Entry]) -> tuple[Case, Engine]:
    """Return a case that follows a trace, and its engine case."""
    return body_case(Tracing(trace))


class TestSteps:
    """steps takes the steps of a machine in a case."""

    def test_makes_one_swarm_choice_per_action_in_order_with_edge_1(
        self, seat: Collector
    ) -> None:
        """Three actions make three choices of two values."""
        log = Log()
        engine = replayed(
            Plain([log.action(name) for name in "abc"]), [1, 1, 1], max_steps(0)
        )
        check.equal(
            seat,
            requests_of(engine)[:3],
            [(BINARY, 1), (BINARY, 1), (BINARY, 1)],
            "each action has a choice of two values with edge 1",
        )

    def test_takes_the_swarm_choices_of_two_actions_from_a_random_source(
        self, seat: Collector
    ) -> None:
        """Seeds 0 to 19 keep both actions or one of them."""
        got: list[list[object]] = []
        for seed in range(20):
            c, engine = body_case(Generating(Source(seed)))
            log = Log()
            steps(c, Plain([log.action("a"), log.action("b")]), max_steps(0))
            got.append([choice.value for choice in engine.choices])
        check.equal(
            seat,
            got,
            [
                [1, 1, 0],
                [1, 1, 0],
                [1, 1, 0],
                [0, 1, 0],
                [1, 0, 0],
                [0, 1, 0],
                [1, 1, 0],
                [1, 0, 0],
                [1, 1, 0],
                [0, 1, 0],
                [1, 0, 0],
                [1, 1, 0],
                [1, 0, 0],
                [1, 1, 0],
                [1, 1, 0],
                [0, 1, 0],
                [1, 1, 0],
                [1, 1, 0],
                [1, 0, 0],
                [1, 1, 0],
            ],
            "the choices of seeds 0 to 19 are those of the reference",
        )

    def test_keeps_the_last_action_when_the_swarm_kept_no_earlier_one(
        self, seat: Collector
    ) -> None:
        """The swarm drops a and b, so c takes the step."""
        log = Log()
        engine = replayed(
            Plain([log.action(name) for name in "abc"]), [0, 0, 0, 1, 0], max_steps(1)
        )
        check.equal(
            seat,
            [engine.requests[2].bounds, engine.steps],
            [IntegerBounds(1, 1), [(0, Step("c"))]],
            "the choice of c is forced, and c takes the step",
        )

    def test_takes_no_sequential_step_of_an_action_that_the_swarm_dropped(
        self, seat: Collector
    ) -> None:
        """The swarm drops b, so the index of the step lists a alone."""
        log = Log()
        engine = replayed(Plain([log.action("a"), log.action("b")]), [1, 0, 1, 0, 0])
        check.equal(
            seat,
            [engine.requests[3].bounds, actions_of(engine)],
            [ONE, ["a"]],
            "the list of the step contains a alone",
        )

    def test_keeps_every_action_without_a_choice_when_the_swarm_is_off(
        self, seat: Collector
    ) -> None:
        """The first request is the flag of the first step."""
        log = Log()
        engine = replayed(
            Plain([log.action("a"), log.action("b")]), [1, 1, 0], swarm(False)
        )
        check.equal(
            seat,
            [engine.requests[0].edge, engine.requests[1].bounds, actions_of(engine)],
            [1, BINARY, ["b"]],
            "the flag comes first, and the index lists both actions",
        )

    def test_drains_a_drain_action_that_the_swarm_dropped(
        self, seat: Collector
    ) -> None:
        """The swarm drops d, and the drain takes one step of d."""
        log = Log()
        pending = [1]
        deliver = log.action("d", drain=True, enabled=lambda _: pending[0] > 0)

        def delivers(c: Case, client: int, value: object) -> None:
            deliver.run(c, client, value)
            pending[0] = 0

        machine = Plain(
            [log.action("a"), Action("d", delivers, 1, True, deliver.enabled)]
        )
        engine = replayed(machine, [1, 0, 0])
        check.equal(
            seat,
            engine.steps,
            [(0, Step("d", None, True))],
            "the drain takes one step of d",
        )

    def test_records_a_sequential_step_as_a_flag_and_an_index_in_a_span_of_its_action(
        self, seat: Collector
    ) -> None:
        """The step of b covers its flag, its index and its draw."""
        log = Log()
        engine = replayed(
            Plain([log.action("a"), log.action("b", draws=True)]),
            [1, 1, 7, 0],
            swarm(False),
        )
        check.equal(
            seat,
            [engine.spans, engine.steps, log.events, engine.requests[1].edge],
            [
                [Span("b", 0, 3, 0, None), Span("integer", 2, 3, 1, 0)],
                [(0, Step("b"))],
                [["input", "b", None], ["b", 0, 7]],
                0,
            ],
            "the span of b starts at its flag and ends after its draw",
        )

    def test_lists_the_actions_that_are_enabled_in_every_state(
        self, seat: Collector
    ) -> None:
        """The function enabled runs once for each state that the last check left."""
        seen: list[object] = []
        log = Log()

        def zero(state: object) -> bool:
            seen.append(state)
            return state == 0

        engine = replayed(
            Plain([log.action("a"), log.action("b", enabled=zero)], LOSSY),
            [1, 0, 1, 0],
            swarm(False),
            max_steps(2),
        )
        check.equal(
            seat,
            [[bounds for bounds, _ in requests_of(engine)], seen],
            [[BINARY, BINARY, BINARY, ONE, ONE], [0, 1, 0, 2, 1, 0]],
            "enabled runs once for each state",
        )

    def test_ends_the_sequential_steps_without_a_flag_when_no_action_is_enabled(
        self, seat: Collector
    ) -> None:
        """The one action is never enabled."""
        log = Log()
        engine = replayed(
            Plain([log.action("a", enabled=lambda _: False)]), [], swarm(False)
        )
        check.is_empty(seat, engine.requests, "the steps make no request")

    def test_continues_by_the_mean_up_to_the_most_steps(self, seat: Collector) -> None:
        """Each flag of a mean of 3 is a coin of 3 in 4."""
        got: list[list[object]] = []
        want: list[list[object]] = []
        for seed in range(40):
            c, engine = body_case(Generating(Source(seed)))
            twin = Source(seed)
            steps(c, Plain([Log().action("a")]), mean(3), max_steps(5), swarm(False))
            got.append([len(engine.steps), engine.requests[-1].bounds])
            want.append(mean_steps(twin, 5))
        check.equal(seat, got, want, "each step takes a coin of 3 in 4")

    def test_chooses_the_action_of_a_step_by_weight(self, seat: Collector) -> None:
        """The weights 1 and 3 split below(4)."""
        got: list[list[str]] = []
        want: list[list[str]] = []
        for seed in range(20):
            c, engine = body_case(Generating(Source(seed)))
            twin = Source(seed)
            log = Log()
            machine = Plain([log.action("a"), log.action("b", 3)])
            steps(c, machine, mean(1000), max_steps(20), swarm(False))
            names: list[str] = []
            while len(names) < 20 and twin.coin(1000, 1001):
                names.append("a" if twin.below(4) < 1 else "b")
            got.append(actions_of(engine))
            want.append(names)
        check.equal(seat, got, want, "the weights 1 and 3 split below(4)")

    def test_fails_the_case_with_the_record_of_linearizable_for_a_violated_check(
        self, seat: Collector
    ) -> None:
        """The spec does not accept a call."""
        c, _ = body_case(replaying(1, 0))
        machine = Plain([Log().action("a")], Counting(lambda _, __: []))
        failing = failing_of(lambda: steps(c, machine, swarm(False)))
        check.equal(
            seat,
            [
                failing.failure.assertion,
                failing.failure.contract,
                failing.failure.detail["outcome"],
            ],
            [
                "linearizable",
                "the history of the steps of the machine is linearizable",
                "violated",
            ],
            "the case fails with the record of the check",
        )

    def test_gives_input_the_first_state_after_the_order_that_the_check_found(
        self, seat: Collector
    ) -> None:
        """The states after one call are 1 and 0."""
        log = Log()
        replayed(Plain([log.action("a")], LOSSY), [1, 0, 1, 0, 0], swarm(False))
        check.equal(
            seat,
            log.events,
            [["input", "a", 0], ["a", 0, None], ["input", "a", 1], ["a", 0, None]],
            "the second input receives the state 1",
        )

    def test_runs_the_invariant_after_setup_after_each_step_and_after_settle(
        self, seat: Collector
    ) -> None:
        """The machine takes two steps."""
        seen: list[list[object]] = []
        replayed(
            Plain(
                [Log().action("a")],
                Counting(),
                invariant=lambda _, state: seen.append(["invariant", state]),
                settle=lambda _, state: seen.append(["settle", state]),
            ),
            [1, 0, 1, 0, 0],
            swarm(False),
        )
        check.equal(
            seat,
            seen,
            [
                ["invariant", 0],
                ["invariant", 1],
                ["invariant", 2],
                ["settle", 2],
                ["invariant", 2],
            ],
            "the invariant runs four times and settle once",
        )

    def test_gives_the_functions_of_a_machine_without_a_spec_the_state_none(
        self, seat: Collector
    ) -> None:
        """enabled, the invariant and settle receive None six times."""
        seen: list[object] = []
        log = Log()

        def enabled(state: object) -> bool:
            seen.append(state)
            return True

        replayed(
            Plain(
                [log.action("a", enabled=enabled)],
                invariant=lambda _, state: seen.append(state),
                settle=lambda _, state: seen.append(state),
            ),
            [1, 0],
            swarm(False),
        )
        check.equal(
            seat,
            [seen, log.events[0]],
            [[None] * 6, ["input", "a", None]],
            "every function receives None",
        )

    def test_runs_the_awaitable_of_a_run_before_the_next_step(
        self, seat: Collector
    ) -> None:
        """The run of a is a coroutine that yields between its two parts."""
        events: list[str] = []

        async def run(c: Case, client: int, value: object) -> None:
            del c, value
            events.append(f"start {client}")
            await asyncio.sleep(0)
            events.append("end")

        replayed(Plain([Action("a", run)]), [1, 0, 1, 0, 0], swarm(False))
        check.equal(
            seat,
            events,
            ["start 0", "end", "start 0", "end"],
            "each step runs to its end before the next step",
        )

    def test_runs_the_awaitable_of_settle(self, seat: Collector) -> None:
        """The settle of the machine is a coroutine."""
        events: list[str] = []

        async def settle(c: Case, state: object) -> None:
            del c, state
            await asyncio.sleep(0)
            events.append("settled")

        replayed(Plain([Log().action("a")], settle=settle), [0], swarm(False))
        check.equal(seat, events, ["settled"], "settle runs to its end")

    def test_ends_the_run_with_a_fault_for_an_awaitable_inside_a_running_loop(
        self, seat: Collector
    ) -> None:
        """The body is a coroutine, and the run of the step is a coroutine."""
        c, _ = body_case(replaying(1, 0))

        async def run(c: Case, client: int, value: object) -> None:
            del c, client, value

        async def body() -> None:
            steps(c, Plain([Action("a", run)]), swarm(False))

        with pytest.raises(FaultSignal) as raised:
            asyncio.run(body())
        check.equal(
            seat,
            str(raised.value.fault),
            "stateful.steps runs a coroutine on an event loop of its own, and an "
            "event loop already runs in this thread",
            "the fault states the loop that already runs",
        )

    def test_lists_a_concurrent_step_as_a_flag_a_client_and_an_index(
        self, seat: Collector
    ) -> None:
        """The section lists one step of b on client 2."""
        log = Log()
        c, engine = body_case(replaying(0, 1, 2, 1, 0))
        steps(c, Plain([log.action("a"), log.action("b")]), *section(c))
        check.equal(
            seat,
            [requests_of(engine)[1:4], engine.steps, engine.spans[0]],
            [
                [(BINARY, 1), (IntegerBounds(0, 2), 0), (BINARY, 0)],
                [(0, Step("b", 2))],
                Span("b", 1, 4, 0, None),
            ],
            "the step of b on client 2 is a span of its flag, client and index",
        )

    def test_requests_every_input_of_a_section_before_any_step_runs(
        self, seat: Collector
    ) -> None:
        """Both inputs receive the state after the sequential steps."""
        log = Log()
        c, _ = body_case(replaying(0, 1, 2, 0, 1, 1, 0, 0))
        steps(c, Plain([log.action("a")], Counting()), *section(c))
        check.equal(
            seat,
            log.events,
            [["input", "a", 0], ["input", "a", 0], ["a", 1, None], ["a", 2, None]],
            "the inputs come before the runs",
        )

    def test_runs_the_steps_of_client_0_before_the_other_clients_start(
        self, seat: Collector
    ) -> None:
        """The step of client 1 is listed first and runs last."""
        log = Log()
        c, _ = body_case(replaying(0, 1, 1, 0, 1, 0, 0, 0))
        steps(c, Plain([log.action("a")]), *section(c))
        check.equal(
            seat,
            log.runs("a"),
            [["a", 0, None], ["a", 1, None]],
            "client 0 runs first",
        )

    def test_runs_each_other_client_as_a_task_spawned_in_client_order(
        self, seat: Collector
    ) -> None:
        """The release of index 1 runs the task of client 2 first."""
        log = Log()
        c, _ = body_case(replaying(0, 1, 1, 0, 1, 2, 0, 0, 1))
        steps(c, Plain([log.action("a")]), *section(c))
        check.equal(
            seat,
            log.runs("a"),
            [["a", 2, None], ["a", 1, None]],
            "the task of client 2 runs first",
        )

    def test_awaits_the_awaitable_of_a_run_in_a_task(self, seat: Collector) -> None:
        """The run of a is a coroutine that yields in its task."""
        events: list[str] = []

        async def run(c: Case, client: int, value: object) -> None:
            del c, value
            events.append(f"start {client}")
            await asyncio.sleep(0)
            events.append(f"end {client}")

        c, _ = body_case(replaying(0, 1, 1, 0, 1, 2, 0, 0))
        steps(c, Plain([Action("a", run)]), *section(c))
        check.equal(
            seat,
            events,
            ["start 1", "start 2", "end 1", "end 2"],
            "the tasks of the clients alternate at the yield",
        )

    def test_lets_only_the_actions_without_enabled_join_a_section(
        self, seat: Collector
    ) -> None:
        """The index of the concurrent step lists a alone."""
        log = Log()
        c, engine = body_case(replaying(0, 1, 1, 0, 0))
        machine = Plain([log.action("a"), log.action("b", enabled=lambda _: True)])
        steps(c, machine, *section(c))
        check.equal(seat, engine.requests[3].bounds, ONE, "the index lists a alone")

    def test_records_no_flag_of_a_section_without_an_eligible_action(
        self, seat: Collector
    ) -> None:
        """The one action has enabled."""
        c, engine = body_case(replaying(0))
        steps(c, Plain([Log().action("a", enabled=lambda _: True)]), *section(c))
        check.length(seat, engine.requests, 1, "the sequential flag is the one request")

    def test_chooses_the_client_of_a_concurrent_step_uniformly(
        self, seat: Collector
    ) -> None:
        """Each client is below(3) after a coin of 5 in 6."""
        got: list[list[int | None]] = []
        want: list[list[int | None]] = []
        for seed in range(20):
            c, engine = body_case(Generating(Source(seed)))
            twin = Source(seed)
            steps(c, Plain([Log().action("a")]), *section(c))
            listed: list[int | None] = []
            while len(listed) < 16 and twin.coin(5, 6):
                listed.append(twin.below(3))
            got.append([taken.client for _, taken in engine.steps])
            want.append(listed)
        check.equal(seat, got, want, "each client is below(3) after a coin of 5 in 6")

    def test_checks_the_history_once_every_task_of_a_section_ends(
        self, seat: Collector
    ) -> None:
        """The machine settles at the count of the three calls of the section."""
        seen: list[object] = []
        c, _ = body_case(replaying(0, 1, 1, 0, 1, 2, 0, 1, 0, 0))
        machine = Plain(
            [Log().action("a")], Counting(), settle=lambda _, state: seen.append(state)
        )
        steps(c, machine, *section(c))
        check.equal(seat, seen, [3], "the check counts every call of the section")

    def test_starts_the_drain_from_the_state_after_the_section(
        self, seat: Collector
    ) -> None:
        """The drain action d is enabled once the check counts the two calls."""
        log = Log()
        c, engine = body_case(replaying(0, 1, 1, 0, 1, 2, 0, 0, 0, 0))
        machine = Plain(
            [
                log.action("a"),
                log.action("d", drain=True, enabled=lambda state: state == 2),
            ],
            Counting(),
        )
        steps(c, machine, *section(c, max_steps(1)))
        check.equal(
            seat,
            engine.steps[-1],
            (0, Step("d", None, True)),
            "the drain takes a step of d",
        )

    def test_ends_a_section_that_fails_its_check_before_the_drain(
        self, seat: Collector
    ) -> None:
        """The spec refuses the second call."""
        log = Log()
        c, _ = body_case(replaying(0, 1, 1, 0, 1, 2, 0, 0, 0, 0))
        machine = Plain(
            [log.action("a"), log.action("d", drain=True, enabled=lambda _: True)],
            Counting(lambda state, _: [] if state == 1 else [state + 1]),
        )
        failing_of(lambda: steps(c, machine, *section(c)))
        check.equal(seat, log.runs("d"), [], "the drain does not run")

    def test_runs_the_other_clients_on_threads_without_a_scheduler(
        self, seat: Collector
    ) -> None:
        """Clients 1 and 2 each run a step on a thread of their own."""
        log = Log()
        c, engine = body_case(replaying(0, 1, 1, 0, 1, 2, 0, 0))
        steps(c, Plain([log.action("a")]), max_steps(0), swarm(False), clients(2))
        check.equal(
            seat,
            [sorted(cast("int", event[1]) for event in log.runs("a")), engine.repeats],
            [[1, 2], 4],
            "both clients run, and the case has 4 repeats",
        )

    def test_sets_the_repeats_of_the_case_to_the_option_repeat(
        self, seat: Collector
    ) -> None:
        """A section on threads under repeat(2) sets 2 repeats."""
        c, engine = body_case(replaying(0, 1, 1, 0, 0))
        steps(
            c,
            Plain([Log().action("a")]),
            max_steps(0),
            swarm(False),
            clients(2),
            repeat(2),
        )
        check.equal(seat, engine.repeats, 2, "the case has 2 repeats")

    def test_leaves_one_run_for_a_section_whose_steps_are_all_on_client_0(
        self, seat: Collector
    ) -> None:
        """The one step of the section is on client 0."""
        c, engine = body_case(replaying(0, 1, 0, 0, 0))
        steps(c, Plain([Log().action("a")]), max_steps(0), swarm(False), clients(2))
        check.equal(seat, engine.repeats, 1, "the case has one run")

    def test_runs_the_awaitable_of_a_run_on_a_thread(self, seat: Collector) -> None:
        """The run of a is a coroutine on client 1."""
        events: list[str] = []

        async def run(c: Case, client: int, value: object) -> None:
            del c, value
            await asyncio.sleep(0)
            events.append(f"ran {client}")

        c, _ = body_case(replaying(0, 1, 1, 0, 0))
        steps(c, Plain([Action("a", run)]), max_steps(0), swarm(False), clients(2))
        check.equal(seat, events, ["ran 1"], "the coroutine of client 1 runs")

    def test_raises_value_error_for_an_action_of_a_negative_weight(
        self, seat: Collector
    ) -> None:
        """The steps validate the machine before any choice."""
        c, _ = body_case(replaying())
        check.equal(
            seat,
            refusal(seat, lambda: steps(c, Plain([Log().action("a", -1)]))),
            'stateful: the weight -1 of the action "a" is not an int of 0 or more',
            "the text of the refusal contains the weight",
        )

    def test_takes_drain_steps_until_no_drain_action_is_enabled(
        self, seat: Collector
    ) -> None:
        """Two sends are followed by two deliveries without a flag."""
        engine = replayed(draining(Log(), [0]), [1, 0, 1, 0, 0], swarm(False))
        check.equal(
            seat,
            [
                [taken for _, taken in engine.steps],
                len(engine.requests),
                engine.requests[-1].bounds,
                engine.spans[-1],
            ],
            [
                [Step("a"), Step("a"), Step("d", None, True), Step("d", None, True)],
                7,
                ONE,
                Span("d", 6, 7, 0, None),
            ],
            "the drain delivers both messages",
        )

    def test_runs_the_check_and_the_invariant_after_each_drain_step(
        self, seat: Collector
    ) -> None:
        """The invariant counts every call."""
        log = Log()
        replayed(draining(log, [0]), [1, 0, 1, 0, 0], swarm(False))
        check.equal(
            seat,
            [event[1] for event in log.events if event[0] == "invariant"],
            [0, 1, 2, 3, 4, 4],
            "the invariant counts every call",
        )

    def test_stops_the_drain_after_the_most_steps(self, seat: Collector) -> None:
        """A drain action without enabled takes three steps under max_steps(3)."""
        engine = replayed(
            Plain([Log().action("d", drain=True)]), [0], swarm(False), max_steps(3)
        )
        check.equal(
            seat,
            engine.steps,
            [(0, Step("d", None, True))] * 3,
            "the drain takes three steps",
        )

    def test_keeps_the_actions_that_the_step_entries_of_a_trace_name(
        self, seat: Collector
    ) -> None:
        """The swarm drops a and c."""
        log = Log()
        c, engine = traced([Step("b")])
        steps(c, Plain([log.action(name) for name in "abc"]))
        check.equal(
            seat,
            [[choice.value for choice in engine.choices], engine.steps],
            [[0, 1, 0, 1, 0, 0], [(0, Step("b"))]],
            "the swarm keeps b alone",
        )

    def test_decodes_the_draws_of_each_step_from_a_trace(self, seat: Collector) -> None:
        """Each draw entry gives its step its input."""
        log = Log()
        c, _ = traced([Step("a"), Draw("v", 4), Step("a"), Draw("v", 6)])
        steps(c, Plain([log.action("a", draws=True)]))
        check.equal(
            seat,
            [event[2] for event in log.runs("a")],
            [4, 6],
            "the inputs are the values of the entries",
        )

    def test_raises_trace_error_for_a_step_entry_whose_action_is_not_enabled(
        self, seat: Collector
    ) -> None:
        """The one action is never enabled."""
        c, _ = traced([Step("a")])
        machine = Plain([Log().action("a", enabled=lambda _: False)])
        error = refused(seat, lambda: steps(c, machine))
        check.equal(
            seat,
            [error.entry, error.what, error.reason],
            [0, "a", "step"],
            "steps refuses entry 0",
        )

    def test_raises_trace_error_for_a_step_entry_past_the_most_steps(
        self, seat: Collector
    ) -> None:
        """The second entry is past max_steps(1)."""
        c, _ = traced([Step("a"), Step("a")])
        error = refused(
            seat, lambda: steps(c, Plain([Log().action("a")]), max_steps(1))
        )
        check.equal(seat, error.entry, 1, "steps refuses the second entry")

    def test_takes_the_client_of_a_concurrent_step_entry(self, seat: Collector) -> None:
        """Client 2 is listed first, and client 1 runs first."""
        log = Log()
        c, engine = traced([Step("a", 2), Step("a", 1)])
        steps(c, Plain([log.action("a")]), clients(2), tasks(Scheduler(c, uniform())))
        check.equal(
            seat,
            [engine.steps, [event[1] for event in log.runs("a")]],
            [[(0, Step("a", 2)), (0, Step("a", 1))], [1, 2]],
            "the steps have the clients of the entries",
        )

    tests: ClassVar[list[tuple[str, int]]] = [
        ("a client outside the clients", 3),
        ("a client below 0", -1),
    ]

    @pytest.mark.parametrize("client", [t[1] for t in tests], ids=[t[0] for t in tests])
    def test_raises_trace_error_for_a_concurrent_step_entry_of(
        self, seat: Collector, client: int
    ) -> None:
        """The steps refuse the entry at its step."""
        c, _ = traced([Step("a", client)])
        error = refused(
            seat,
            lambda: steps(
                c,
                Plain([Log().action("a")]),
                clients(2),
                tasks(Scheduler(c, uniform())),
            ),
        )
        check.equal(
            seat, [error.entry, error.reason], [0, "step"], "steps refuses entry 0"
        )

    def test_raises_trace_error_for_a_concurrent_step_entry_past_the_most_steps(
        self, seat: Collector
    ) -> None:
        """The second entry is past concurrent(1)."""
        c, _ = traced([Step("a", 1), Step("a", 1)])
        error = refused(
            seat,
            lambda: steps(
                c,
                Plain([Log().action("a")]),
                clients(2),
                concurrent(1),
                tasks(Scheduler(c, uniform())),
            ),
        )
        check.equal(seat, error.entry, 1, "steps refuses the second entry")

    def test_raises_trace_error_for_a_concurrent_step_entry_where_no_section_runs(
        self, seat: Collector
    ) -> None:
        """A machine of one client does not run a section."""
        c, _ = traced([Step("a", 1)])
        error = refused(seat, lambda: steps(c, Plain([Log().action("a")])))
        check.equal(seat, error.entry, 0, "steps refuses entry 0")

    def test_chooses_the_action_of_a_drain_step_entry_among_the_drain_actions(
        self, seat: Collector
    ) -> None:
        """The drain delivers e, and then d."""
        delivered: list[str] = []
        pending = [0]

        def adds(c: Case, client: int, value: object) -> None:
            del c, client, value
            pending[0] += 2

        def deliver(name: str) -> Action[Any]:
            def delivers(c: Case, client: int, value: object) -> None:
                del c, client, value
                delivered.append(name)
                pending[0] -= 1

            return Action(name, delivers, drain=True, enabled=lambda _: pending[0] > 0)

        c, _ = traced([Step("a"), Step("e", None, True), Step("d", None, True)])
        steps(c, Plain([Action("a", adds), deliver("d"), deliver("e")]))
        check.equal(seat, delivered, ["e", "d"], "the drain takes the entries in order")

    def test_raises_trace_error_for_a_drain_step_entry_after_the_drain(
        self, seat: Collector
    ) -> None:
        """The drain ends after one delivery."""
        pending = [0]

        def adds(c: Case, client: int, value: object) -> None:
            del c, client, value
            pending[0] += 1

        def delivers(c: Case, client: int, value: object) -> None:
            del c, client, value
            pending[0] -= 1

        machine = Plain(
            [
                Action("a", adds),
                Action("d", delivers, drain=True, enabled=lambda _: pending[0] > 0),
            ]
        )
        c, _ = traced([Step("a"), Step("d", None, True), Step("d", None, True)])
        error = refused(seat, lambda: steps(c, machine))
        check.equal(
            seat, [error.entry, error.what], [2, "d"], "steps refuses the second drain"
        )

    def test_states_the_position_and_the_action_of_each_swarm_choice(
        self, seat: Collector
    ) -> None:
        """Each swarm choice is at its action."""
        log = Log()
        engine = replayed(
            Plain([log.action("a"), log.action("b")]), [1, 1], max_steps(0)
        )
        check.equal(
            seat,
            [where.place for where in engine.wheres[:2]],
            [Place("swarm", 0, "a"), Place("swarm", 1, "b")],
            "each choice is at the position of its action",
        )

    def test_states_the_position_of_a_sequential_step_and_then_its_action(
        self, seat: Collector
    ) -> None:
        """The flag and the index are at the step, and the input at its action."""
        log = Log()
        engine = replayed(
            Plain([log.action("a", draws=True), log.action("b", draws=True)]),
            [1, 1, 7, 1, 0, 3, 0],
            swarm(False),
        )
        first = Place("sequential", 0)
        second = Place("sequential", 1)
        check.equal(
            seat,
            engine.wheres,
            [
                Where(None, first),
                Where(None, first),
                Where("v", Place("sequential", 0, "b")),
                Where(None, second),
                Where(None, second),
                Where("v", Place("sequential", 1, "a")),
                Where(None, Place("sequential", 2)),
            ],
            "the input of each step is at its action",
        )

    def test_states_the_position_of_a_drain_step_and_then_its_action(
        self, seat: Collector
    ) -> None:
        """The index is at the step, and the draw of the run at its action."""
        pending = [1]

        def delivers(c: Case, client: int, value: object) -> None:
            del client, value
            c.draw(DIGIT, "w")
            pending[0] = 0

        engine = replayed(
            Plain(
                [Action("d", delivers, drain=True, enabled=lambda _: pending[0] > 0)]
            ),
            [0, 0, 4],
            swarm(False),
        )
        check.equal(
            seat,
            engine.wheres,
            [
                Where(None, Place("sequential", 0)),
                Where(None, Place("drain", 0)),
                Where("w", Place("drain", 0, "d")),
            ],
            "the draw of the run is at its action",
        )

    def test_states_the_position_of_a_concurrent_step_and_none_while_the_steps_run(
        self, seat: Collector
    ) -> None:
        """The release of the section has no position."""

        def observes(c: Case, client: int, value: object) -> None:
            del client, value
            c.observe(9)

        c, engine = body_case(replaying(0, 1, 1, 0, 0, 0))
        steps(c, Plain([Action("a", observes)]), *section(c))
        listed = Where(None, Place("concurrent", 0))
        check.equal(
            seat,
            [engine.wheres, engine.observed],
            [
                [
                    Where(None, Place("sequential", 0)),
                    listed,
                    listed,
                    listed,
                    Where(None, Place("concurrent", 1)),
                    Where(None, Place("concurrent")),
                ],
                [Where(None, Place("concurrent"))],
            ],
            "the release and the run have no position",
        )

    def test_states_the_parts_of_setup_and_settle(self, seat: Collector) -> None:
        """The invariant observes in setup, and settle and the invariant in settle."""
        engine = replayed(
            Plain(
                [Log().action("a")],
                invariant=lambda c, _: c.observe(0),
                settle=lambda c, _: c.observe(1),
            ),
            [0],
            swarm(False),
        )
        check.equal(
            seat,
            [where.place for where in engine.observed],
            [Place("setup"), Place("settle"), Place("settle")],
            "each observation is at its part",
        )

    def test_restores_the_place_of_the_case_when_the_steps_end(
        self, seat: Collector
    ) -> None:
        """The case was at an outer place before the steps."""
        c, engine = body_case(replaying(0))
        engine.place = Place("outer")
        steps(c, Plain([Log().action("a")]), swarm(False))
        check.equal(seat, engine.place, Place("outer"), "the place is the one before")
