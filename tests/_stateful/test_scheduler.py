# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _stateful/scheduler.py tests the releases of the task scheduler.

Each order and each choice of a port of a TypeScript case is the order and
the choice of the reference implementation of the definition on the same
tasks and values.
"""

from __future__ import annotations

import asyncio
import contextvars
import types
from collections.abc import Callable, Coroutine, Generator
from typing import TYPE_CHECKING, Any, ClassVar, NoReturn, cast

import pytest

from dokimi_assert import check
from dokimi_assert._prop.case import FaultSignal
from dokimi_assert._prop.engine.case import Case as Engine
from dokimi_assert._prop.engine.case import Generating
from dokimi_assert._prop.engine.choice import UINT64_MAX, IntegerBounds
from dokimi_assert._prop.engine.source import Source
from dokimi_assert._stateful.scheduler import Scheduler
from dokimi_assert._stateful.strategy import Strategy, pct, uniform
from helpers import body_case, replaying

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

#: The bounds of a choice between two values, and of a choice of one value.
BINARY = IntegerBounds(0, 1)
ONE = IntegerBounds(0, 0)

#: The bounds of a priority under PCT and of the count of a change point.
WIDE = IntegerBounds(0, UINT64_MAX)

#: The members of the event loop that the scheduler implements.
IMPLEMENTED = {
    "call_at",
    "call_exception_handler",
    "call_later",
    "call_soon",
    "create_future",
    "get_debug",
    "is_closed",
    "is_running",
    "time",
}

#: The public members of the event loop that the scheduler does not implement.
REFUSED = sorted(
    name
    for name, member in vars(asyncio.AbstractEventLoop).items()
    if callable(member) and not name.startswith("_") and name not in IMPLEMENTED
)

#: The function of a task, which returns the coroutine of the task.
Task = Callable[[], Coroutine[Any, Any, None]]


def started(strategy: Strategy, *values: int) -> tuple[Scheduler, Engine, list[str]]:
    """Return a scheduler on a case that replays values, its engine case and a log."""
    c, engine = body_case(replaying(*values))
    return Scheduler(c, strategy), engine, []


def task(log: list[str], name: str, parts: int) -> Task:
    """Return a task that logs each of its parts, and yields between two parts."""

    async def run() -> None:
        for part in range(1, parts + 1):
            log.append(f"{name}{part}")
            if part < parts:
                await asyncio.sleep(0)

    return run


def requests_of(engine: Engine) -> list[tuple[object, int | None]]:
    """Return the bounds and the edge of each request of an engine case."""
    return [(request.bounds, request.edge) for request in engine.requests]


def raised_by(seat: Collector, scheduler: Scheduler) -> BaseException:
    """Return the error with which the run of a scheduler ends."""
    return cast("BaseException", check.raises(seat, scheduler.run, "the run raises"))


@types.coroutine
def yielding(value: object) -> Generator[object, None, None]:
    """Yield value to the event loop of the task, as no await of a future does."""
    yield value


class TestScheduler:
    """Scheduler is the event loop of the tasks of a case."""

    def test_runs_without_a_release_when_no_task_is_ready(
        self, seat: Collector
    ) -> None:
        """A scheduler without a task does not make a request."""
        scheduler, engine, _ = started(uniform())
        scheduler.run()
        check.is_empty(seat, engine.requests, "the run makes no request")

    def test_is_the_running_event_loop_of_a_task(self, seat: Collector) -> None:
        """A task finds the scheduler as its running loop, and the test finds none."""
        scheduler, _, _ = started(uniform())
        seen: list[object] = []

        async def looks() -> None:
            seen.append(asyncio.get_running_loop())

        scheduler.spawn(looks)
        scheduler.run()
        # asyncio.get_running_loop raises where no loop runs, and
        # _get_running_loop returns None.
        check.equal(
            seat,
            [seen[0] is scheduler, asyncio.events._get_running_loop()],  # noqa: SLF001
            [True, None],
            "the task runs on the scheduler, and the test runs on no loop",
        )


class TestSchedulerSpawn:
    """Scheduler.spawn makes a task ready after the ready tasks."""

    def test_makes_a_task_that_a_task_spawns_ready_behind_the_ready_tasks(
        self, seat: Collector
    ) -> None:
        """Task c runs before task p resumes."""
        scheduler, _, log = started(uniform())

        async def parent() -> None:
            log.append("p1")
            scheduler.spawn(task(log, "c", 1))
            await asyncio.sleep(0)
            log.append("p2")

        scheduler.spawn(parent)
        scheduler.spawn(task(log, "b", 1))
        scheduler.run()
        check.equal(seat, log, ["p1", "b1", "c1", "p2"], "c runs before p resumes")

    def test_requests_a_priority_under_pct_for_each_task(self, seat: Collector) -> None:
        """Two spawns under PCT request two priorities."""
        scheduler, engine, log = started(pct(3))
        scheduler.spawn(task(log, "a", 1))
        scheduler.spawn(task(log, "b", 1))
        check.equal(
            seat,
            requests_of(engine),
            [(WIDE, None), (WIDE, None)],
            "each spawn requests a priority over the whole unsigned range",
        )

    def test_runs_each_task_in_a_copy_of_the_context_of_its_spawn(
        self, seat: Collector
    ) -> None:
        """A task sets a variable, and the next task reads the value of the spawn."""
        scheduler, _, _ = started(uniform())
        variable: contextvars.ContextVar[str] = contextvars.ContextVar("variable")
        seen: list[str] = []

        async def sets() -> None:
            variable.set("changed")

        async def reads() -> None:
            seen.append(variable.get())

        token = variable.set("spawned")
        try:
            scheduler.spawn(sets)
            scheduler.spawn(reads)
        finally:
            variable.reset(token)
        scheduler.run()
        check.equal(seat, seen, ["spawned"], "the second task reads its own copy")


class TestSchedulerRun:
    """Scheduler.run releases one ready task at a time until every task has ended."""

    def test_makes_a_task_that_yields_wait_behind_the_ready_tasks(
        self, seat: Collector
    ) -> None:
        """Tasks a and b alternate."""
        scheduler, _, log = started(uniform())
        scheduler.spawn(task(log, "a", 3))
        scheduler.spawn(task(log, "b", 2))
        scheduler.run()
        check.equal(seat, log, ["a1", "b1", "a2", "b2", "a3"], "a and b alternate")

    def test_releases_the_task_at_the_index_that_each_release_chooses(
        self, seat: Collector
    ) -> None:
        """The values 1, 0 and 0 release b first, and then a behind it."""
        scheduler, _, log = started(uniform(), 1, 0, 0)
        scheduler.spawn(task(log, "a", 2))
        scheduler.spawn(task(log, "b", 2))
        scheduler.run()
        check.equal(seat, log, ["b1", "a1", "b2", "a2"], "b runs first")

    def test_records_the_uniform_choice_of_a_release_with_one_ready_task(
        self, seat: Collector
    ) -> None:
        """Each of three releases makes a choice."""
        scheduler, engine, log = started(uniform())
        scheduler.spawn(task(log, "a", 1))
        scheduler.spawn(task(log, "b", 2))
        scheduler.run()
        check.equal(
            seat,
            requests_of(engine),
            [(BINARY, 0), (ONE, 0), (ONE, 0)],
            "a choice of two, then two choices of one",
        )

    def test_takes_a_uniform_release_below_the_number_of_ready_tasks(
        self, seat: Collector
    ) -> None:
        """Seeds 0 to 19 take below(3), then below(2), and then no value."""
        got: list[list[object]] = []
        want: list[list[object]] = []
        for seed in range(20):
            c, engine = body_case(Generating(Source(seed)))
            twin = Source(seed)
            scheduler = Scheduler(c, uniform())
            for name in ("a", "b", "c"):
                scheduler.spawn(task([], name, 1))
            scheduler.run()
            got.append([choice.value for choice in engine.choices])
            want.append([twin.below(3), twin.below(2), 0])
        check.equal(seat, got, want, "each release is below the number of ready tasks")

    def test_raises_runtime_error_for_a_task_that_calls_run(
        self, seat: Collector
    ) -> None:
        """A task calls run of its own scheduler."""
        scheduler, _, _ = started(uniform())

        async def nested() -> None:
            scheduler.run()

        scheduler.spawn(nested)
        error = raised_by(seat, scheduler)
        check.equal(
            seat,
            [type(error), str(error)],
            [RuntimeError, "stateful: a task called run of its own scheduler"],
            "the nested run raises a RuntimeError",
        )

    def test_raises_the_error_of_a_task_and_releases_no_other_task(
        self, seat: Collector
    ) -> None:
        """Task b never runs."""
        scheduler, _, log = started(uniform())
        broken = ValueError("broken")

        async def raises() -> None:
            raise broken

        scheduler.spawn(raises)
        scheduler.spawn(task(log, "b", 1))
        check.equal(
            seat,
            [raised_by(seat, scheduler) is broken, log],
            [True, []],
            "the run ends with the error before b runs",
        )

    def test_raises_the_error_of_a_task_function_that_raises_as_it_starts(
        self, seat: Collector
    ) -> None:
        """The function of the task raises before it returns a coroutine."""
        scheduler, _, _ = started(uniform())
        broken = ValueError("broken")

        def starts() -> NoReturn:
            raise broken

        scheduler.spawn(starts)
        check.is_true(
            seat, raised_by(seat, scheduler) is broken, "the run ends with the error"
        )

    def test_runs_the_tasks_spawned_after_a_run_that_a_task_ended(
        self, seat: Collector
    ) -> None:
        """A second run releases a task that the test spawns after the first."""
        scheduler, _, log = started(uniform())

        async def raises() -> None:
            msg = "broken"
            raise ValueError(msg)

        scheduler.spawn(raises)
        raised_by(seat, scheduler)
        scheduler.spawn(task(log, "a", 1))
        scheduler.run()
        check.equal(seat, log, ["a1"], "the second run releases a")

    def test_closes_the_coroutine_of_every_task_when_a_task_raises(
        self, seat: Collector
    ) -> None:
        """Task a waits at a yield when task b raises."""
        scheduler, _, log = started(uniform())

        async def waits() -> None:
            try:
                await asyncio.sleep(0)
            finally:
                log.append("closed")

        async def raises() -> None:
            msg = "broken"
            raise ValueError(msg)

        scheduler.spawn(waits)
        scheduler.spawn(raises)
        raised_by(seat, scheduler)
        check.equal(seat, log, ["closed"], "the run closes the coroutine of a")

    def test_runs_the_task_of_the_highest_pct_priority_through_its_yields(
        self, seat: Collector
    ) -> None:
        """Task b has the priority 5, and task a the priority 1."""
        scheduler, _, log = started(pct(1), 1, 5)
        scheduler.spawn(task(log, "a", 2))
        scheduler.spawn(task(log, "b", 3))
        scheduler.run()
        check.equal(seat, log, ["b1", "b2", "b3", "a1", "a2"], "b runs to its end")

    def test_runs_the_earliest_ready_task_first_among_equal_pct_priorities(
        self, seat: Collector
    ) -> None:
        """Tasks a and b have the priority 0."""
        scheduler, _, log = started(pct(1))
        scheduler.spawn(task(log, "a", 2))
        scheduler.spawn(task(log, "b", 2))
        scheduler.run()
        check.equal(seat, log, ["a1", "b1", "a2", "b2"], "a and b alternate")

    def test_requests_a_presence_and_a_count_for_each_pct_change_point(
        self, seat: Collector
    ) -> None:
        """The first change point is present at release 9, and the second is absent."""
        scheduler, engine, log = started(pct(3), 0, 0, 1, 9, 0)
        scheduler.spawn(task(log, "a", 1))
        scheduler.spawn(task(log, "b", 1))
        scheduler.run()
        check.equal(
            seat,
            requests_of(engine),
            [(WIDE, None), (WIDE, None), (BINARY, 1), (WIDE, None), (BINARY, 1)],
            "two priorities, a present change point and an absent one",
        )

    def test_drops_the_task_of_a_change_point_below_every_other_task(
        self, seat: Collector
    ) -> None:
        """Task a drops at release 0."""
        scheduler, _, log = started(pct(2), 5, 1, 1, 0)
        scheduler.spawn(task(log, "a", 2))
        scheduler.spawn(task(log, "b", 2))
        scheduler.run()
        check.equal(seat, log, ["a1", "b1", "b2", "a2"], "b runs before a resumes")

    def test_drops_the_task_of_a_later_change_point_lower_still(
        self, seat: Collector
    ) -> None:
        """Task a drops at release 0, and task b at release 1."""
        scheduler, _, log = started(pct(3), 9, 8, 7, 1, 0, 1, 1)
        for name in ("a", "b", "c"):
            scheduler.spawn(task(log, name, 2))
        scheduler.run()
        check.equal(
            seat,
            log,
            ["a1", "b1", "c1", "c2", "a2", "b2"],
            "c ends first, and b resumes last",
        )

    def test_drops_a_spawned_task_of_a_higher_priority_below_the_task_before_it(
        self, seat: Collector
    ) -> None:
        """Task d has the priority 9 and drops at release 1."""
        scheduler, _, log = started(pct(3), 5, 1, 1, 0, 1, 1, 9)

        async def parent() -> None:
            log.append("a1")
            scheduler.spawn(task(log, "d", 2))
            await asyncio.sleep(0)
            log.append("a2")

        scheduler.spawn(parent)
        scheduler.spawn(task(log, "c", 1))
        scheduler.run()
        check.equal(seat, log, ["a1", "d1", "c1", "a2", "d2"], "d resumes last")

    def test_makes_no_choice_for_a_pct_release(self, seat: Collector) -> None:
        """Two tasks under PCT of depth 1 request their priorities alone."""
        scheduler, engine, log = started(pct(1))
        scheduler.spawn(task(log, "a", 1))
        scheduler.spawn(task(log, "b", 1))
        scheduler.run()
        check.equal(
            seat,
            [len(engine.requests), log],
            [2, ["a1", "b1"]],
            "the run requests the two priorities alone",
        )

    def test_makes_a_task_that_awaits_a_future_ready_once_the_future_is_done(
        self, seat: Collector
    ) -> None:
        """Task a waits on an event that task b sets."""
        scheduler, _, log = started(uniform())
        event = asyncio.Event()

        async def waits() -> None:
            log.append("a waits")
            await event.wait()
            log.append("a resumes")

        async def sets() -> None:
            log.append("b sets")
            event.set()

        scheduler.spawn(waits)
        scheduler.spawn(sets)
        scheduler.run()
        check.equal(
            seat,
            log,
            ["a waits", "b sets", "a resumes"],
            "a resumes after b sets the event",
        )

    def test_moves_the_clock_to_the_next_timer_when_no_task_is_ready(
        self, seat: Collector
    ) -> None:
        """Task a sleeps 2 seconds and task b 1 second."""
        scheduler, _, log = started(uniform())

        async def sleeps(name: str, seconds: float) -> None:
            await asyncio.sleep(seconds)
            log.append(f"{name} at {scheduler.time()}")

        scheduler.spawn(lambda: sleeps("a", 2))
        scheduler.spawn(lambda: sleeps("b", 1))
        scheduler.run()
        check.equal(
            seat,
            log,
            ["b at 1.0", "a at 2.0"],
            "b wakes at 1 second and a at 2 seconds",
        )

    def test_skips_a_timer_that_its_caller_cancelled(self, seat: Collector) -> None:
        """The task cancels a timer of 1 second and sleeps 2 seconds."""
        scheduler, _, log = started(uniform())

        async def cancels() -> None:
            scheduler.call_later(1, log.append, "timer").cancel()
            await asyncio.sleep(2)
            log.append(f"awake at {scheduler.time()}")

        scheduler.spawn(cancels)
        scheduler.run()
        check.equal(seat, log, ["awake at 2.0"], "the cancelled timer does not run")

    def test_calls_the_due_callbacks_in_order_before_the_next_release(
        self, seat: Collector
    ) -> None:
        """Task a schedules two callbacks and yields to task b."""
        scheduler, _, log = started(uniform())

        async def schedules() -> None:
            scheduler.call_soon(log.append, "first")
            scheduler.call_soon(log.append, "second")
            await asyncio.sleep(0)

        scheduler.spawn(schedules)
        scheduler.spawn(task(log, "b", 1))
        scheduler.run()
        check.equal(seat, log, ["first", "second", "b1"], "both callbacks run before b")

    def test_calls_a_callback_that_a_callback_schedules_while_no_task_is_ready(
        self, seat: Collector
    ) -> None:
        """The second callback resolves the future that the task awaits."""
        scheduler, _, log = started(uniform())
        future = scheduler.create_future()

        def first() -> None:
            log.append("first")
            scheduler.call_soon(future.set_result, "done")

        async def awaits() -> None:
            scheduler.call_soon(first)
            log.append(await future)

        scheduler.spawn(awaits)
        scheduler.run()
        check.equal(seat, log, ["first", "done"], "the task resumes with the result")

    def test_skips_a_callback_that_its_caller_cancelled(self, seat: Collector) -> None:
        """The task cancels a callback before it yields."""
        scheduler, _, log = started(uniform())

        async def cancels() -> None:
            scheduler.call_soon(log.append, "callback").cancel()
            await asyncio.sleep(0)
            log.append("resumed")

        scheduler.spawn(cancels)
        scheduler.run()
        check.equal(seat, log, ["resumed"], "the cancelled callback does not run")

    def test_raises_the_error_of_a_callback(self, seat: Collector) -> None:
        """A callback of the task raises."""
        scheduler, _, _ = started(uniform())
        broken = ValueError("broken")

        def raises() -> NoReturn:
            raise broken

        async def schedules() -> None:
            scheduler.call_soon(raises)
            await asyncio.sleep(0)

        scheduler.spawn(schedules)
        check.is_true(
            seat, raised_by(seat, scheduler) is broken, "the run ends with the error"
        )

    def test_ends_a_task_that_ends_with_cancelled_error_and_goes_on(
        self, seat: Collector
    ) -> None:
        """Task b cancels the future that task a awaits."""
        scheduler, _, log = started(uniform())
        future = scheduler.create_future()

        async def awaits() -> None:
            log.append("a waits")
            await future

        async def cancels() -> None:
            future.cancel()
            await asyncio.sleep(0)
            log.append("b resumes")

        scheduler.spawn(awaits)
        scheduler.spawn(cancels)
        scheduler.run()
        check.equal(seat, log, ["a waits", "b resumes"], "the run goes on after a")

    def test_raises_runtime_error_when_every_task_waits_and_nothing_is_left(
        self, seat: Collector
    ) -> None:
        """The task awaits a future that nobody resolves."""
        scheduler, _, _ = started(uniform())

        async def waits() -> None:
            await scheduler.create_future()

        scheduler.spawn(waits)
        error = raised_by(seat, scheduler)
        check.equal(
            seat,
            [type(error), str(error)],
            [
                RuntimeError,
                (
                    "stateful: every task that has not ended waits on a future, and no "
                    "callback or timer is left"
                ),
            ],
            "the run ends at the deadlock",
        )

    def test_raises_runtime_error_for_a_future_of_another_event_loop(
        self, seat: Collector
    ) -> None:
        """The task awaits a future of a second scheduler."""
        scheduler, _, _ = started(uniform())
        other, _, _ = started(uniform())

        async def awaits() -> None:
            await other.create_future()

        scheduler.spawn(awaits)
        error = raised_by(seat, scheduler)
        check.equal(
            seat,
            [type(error), str(error)],
            [RuntimeError, "stateful: a task awaited a future of another event loop"],
            "the run refuses the future",
        )

    def test_raises_runtime_error_for_a_yield_of_a_value_that_is_not_a_future(
        self, seat: Collector
    ) -> None:
        """The task yields 3 to its event loop."""
        scheduler, _, _ = started(uniform())

        async def yields() -> None:
            await yielding(3)

        scheduler.spawn(yields)
        error = raised_by(seat, scheduler)
        check.equal(
            seat,
            [type(error), str(error)],
            [RuntimeError, "stateful: a task yielded 3 instead of a future"],
            "the run refuses the value",
        )

    def test_raises_type_error_for_a_task_function_that_does_not_return_a_coroutine(
        self, seat: Collector
    ) -> None:
        """The function of the task returns 3."""
        scheduler, _, _ = started(uniform())
        scheduler.spawn(cast("Task", lambda: 3))
        error = raised_by(seat, scheduler)
        check.equal(
            seat,
            [type(error), str(error)],
            [TypeError, "stateful: the task returned 3 instead of a coroutine"],
            "the run refuses the value",
        )


class TestSchedulerMembers:
    """The members of the event loop that futures, locks, events and sleeps call."""

    def test_starts_the_clock_at_0(self, seat: Collector) -> None:
        """A new scheduler is at the time 0."""
        scheduler, _, _ = started(uniform())
        check.equal(seat, scheduler.time(), 0.0, "the clock starts at 0")

    def test_creates_a_future_of_the_scheduler(self, seat: Collector) -> None:
        """create_future returns a future whose loop is the scheduler."""
        scheduler, _, _ = started(uniform())
        check.is_true(
            seat,
            scheduler.create_future().get_loop() is scheduler,
            "the future belongs to the scheduler",
        )

    def test_reports_that_it_runs_while_it_releases_a_task(
        self, seat: Collector
    ) -> None:
        """A task reads is_running, and the test reads it after the run."""
        scheduler, _, _ = started(uniform())
        seen: list[bool] = []

        async def reads() -> None:
            seen.append(scheduler.is_running())

        scheduler.spawn(reads)
        scheduler.run()
        check.equal(
            seat,
            [seen, scheduler.is_running()],
            [[True], False],
            "the scheduler runs only while it releases tasks",
        )

    def test_reports_that_it_is_not_closed_and_not_in_debug_mode(
        self, seat: Collector
    ) -> None:
        """A scheduler is not closed, and it does not run in debug mode."""
        scheduler, _, _ = started(uniform())
        check.equal(
            seat,
            [scheduler.is_closed(), scheduler.get_debug()],
            [False, False],
            "the scheduler is open and not in debug mode",
        )

    def test_ignores_an_error_that_asyncio_reports_outside_a_task(
        self, seat: Collector
    ) -> None:
        """call_exception_handler takes a report of an error."""
        scheduler, _, _ = started(uniform())
        check.does_not_raise(
            seat,
            lambda: scheduler.call_exception_handler({"message": "lost"}),
            "the report is ignored",
        )

    tests: ClassVar[list[str]] = REFUSED

    @pytest.mark.parametrize("name", tests)
    def test_ends_the_run_with_a_fault_for_the_member(
        self, seat: Collector, name: str
    ) -> None:
        """The text of the fault contains the name of the member."""
        scheduler, _, _ = started(uniform())
        member: Callable[[], object] = getattr(scheduler, name)
        with pytest.raises(FaultSignal) as raised:
            member()
        check.equal(
            seat,
            str(raised.value.fault),
            f"the task scheduler does not implement the event loop member {name}",
            "the text of the fault contains the name of the member",
        )
