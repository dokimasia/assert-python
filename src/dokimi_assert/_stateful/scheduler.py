# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The task scheduler, whose releases of tasks are choices of a case.

The scheduler is an event loop of asyncio, and a task is a coroutine. The
scheduler releases one ready task at a time. The task runs until it awaits
a future that is not done, yields with asyncio.sleep(0), or ends. A task
that awaits a future, an asyncio.Event or an asyncio.sleep of a positive
duration is parked until the future is done. The strategy of the scheduler
takes each release from the choices of the case, so a schedule replays and
shrinks in the same way as the values of the case.

The scheduler implements the members of the event loop that futures, locks,
events, queues and asyncio.sleep call. Its clock is the clock of the event
loop. The clock starts at midnight UTC 2000-01-01, and only advance moves
it, so a sleep does not spend real time. Each other member of the event
loop ends the run of the property with a fault. The members for sockets,
pipes, subprocesses, signals and threads are such members, and so is
create_task.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import heapq
import inspect
import itertools
from asyncio import events
from collections import deque
from collections.abc import Callable, Coroutine, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NoReturn, TypeVarTuple, cast, final

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._override import override
from dokimi_assert._prop.case import Case, FaultSignal, on_engine
from dokimi_assert._prop.engine.case import Case as Engine
from dokimi_assert._prop.engine.case import Request
from dokimi_assert._prop.engine.choice import UINT64_MAX, IntegerBounds

if TYPE_CHECKING:
    from dokimi_assert._stateful.strategy import Strategy
    from dokimi_assert.clock import Clock

__all__ = ["EPOCH", "MAX_RELEASES", "Scheduler", "SchedulerOption", "max_releases"]

_Ts = TypeVarTuple("_Ts")

#: The instant at which the clock of every scheduler starts, midnight UTC
#: 2000-01-01, in nanoseconds since the Unix epoch.
EPOCH = 946_684_800 * 10**9

#: The most tasks that one run or one advance releases by default.
MAX_RELEASES = 1_000_000

#: The nanoseconds of a second.
_SECOND = 10**9

#: The bounds of the priority of a task under PCT, and of the count of a
#: change point.
_UNSIGNED = IntegerBounds(0, UINT64_MAX)

#: The bounds of the presence choice of a change point.
_PRESENCE = IntegerBounds(0, 1)

#: The function of a task. It returns the coroutine of the task.
_Start = Callable[[], Coroutine[Any, Any, object]]


@dataclass(eq=False)
class _Task:
    """A spawned task.

    Attributes:
        start: The function of the task.
        priority: The priority of the task under PCT.
        context: The copy of the context of the spawn, in which the task runs.
        level: 0 until a change point lowers the task. Each lowering gives
            the task a level below every level before.
        coroutine: The coroutine of the task, once a release has started it.
    """

    start: _Start
    priority: int
    context: contextvars.Context
    level: int = 0
    coroutine: Coroutine[Any, Any, object] | None = None


@final
class _Timer(asyncio.TimerHandle):
    """A timer of the scheduler.

    Its cancel marks the timer alone, and a run skips a cancelled timer. The
    cancel of a timer of asyncio also calls a private member of its loop.
    """

    @override
    def cancel(self) -> None:
        """Cancel the timer."""
        asyncio.Handle.cancel(self)


@dataclass(frozen=True, eq=False)
class _Callback:
    """A callback that the scheduler runs, and the handle that cancels it.

    Attributes:
        handle: The handle, which cancels the callback.
        fn: The callback.
        args: The arguments of the callback.
        context: The context in which the callback runs.
    """

    handle: asyncio.Handle
    fn: Callable[..., object]
    args: tuple[Any, ...]
    context: contextvars.Context


@dataclass(frozen=True, slots=True)
class SchedulerOption:
    """An option of a Scheduler, which max_releases returns.

    Attributes:
        max_releases: The most tasks that one run or one advance releases.
    """

    max_releases: int


def max_releases(n: int) -> SchedulerOption:
    """Set the most tasks that one run or one advance of a scheduler releases.

    The default is 1,000,000. A run or an advance that has released n tasks
    while a task is still ready ends every task, and fails the case with the
    message "the task scheduler released n tasks in one run, and a task is
    still ready". Under the uniform strategy each release is a choice of the
    case, so a case passes the option max_choices of prop first unless the
    run raises it. The last max_releases of a scheduler applies.

    Args:
        n: The most releases. It is at least 1.

    Returns:
        The option for Scheduler.

    Raises:
        ValueError: n is not an int of 1 or more.
    """
    if type(n) is not int or n < 1:
        msg = f"stateful: max_releases({n!r}) needs an int of 1 or more"
        raise ValueError(msg)
    return SchedulerOption(n)


def _nanoseconds(seconds: float) -> int:
    """Return a duration in seconds as the nanoseconds of the clock of a scheduler."""
    return round(seconds * _SECOND)


@final
class _Clock:
    """The clock of a scheduler, as the clock of the definition reads it.

    now reads the clock of the scheduler in seconds since the Unix epoch. A
    task sleeps on that clock with asyncio.sleep, because a coroutine parks
    only where it awaits. sleep therefore returns at once for a duration of
    zero or less, and raises RuntimeError for a positive duration.
    """

    def __init__(self, scheduler: Scheduler) -> None:
        """Return the clock of scheduler."""
        self._scheduler: Scheduler = scheduler

    def now(self) -> float:
        """Return the time of the clock of the scheduler.

        Returns:
            The seconds since the Unix epoch.
        """
        return self._scheduler.time()

    def sleep(self, duration: float) -> None:
        """Return at once for a duration of zero or less.

        Args:
            duration: The seconds.

        Raises:
            RuntimeError: The duration is positive. In a task, asyncio.sleep
                parks the task instead. Outside a task, only the body could
                advance the clock that the sleep waits for.
        """
        if duration <= 0:
            return
        if self._scheduler.is_running():
            msg = (
                "stateful: a task sleeps on the clock of its scheduler with "
                "asyncio.sleep"
            )
            raise RuntimeError(msg)
        msg = (
            "stateful: a sleep outside a task waits for a clock that only the body "
            "moves"
        )
        raise RuntimeError(msg)


def _refusing(name: str) -> Any:
    """Return a member of the event loop that the scheduler does not implement.

    The member ends the run of the property with a fault. The text of the
    fault contains the name of the member. The member takes any arguments,
    so its type is Any, which the signature of each member accepts.
    """

    def refuse(*args: object, **kwargs: object) -> NoReturn:
        del args, kwargs
        reason = f"the task scheduler does not implement the event loop member {name}"
        raise FaultSignal(FaultError("", reason))

    return refuse


@final
class Scheduler(asyncio.AbstractEventLoop):
    """The event loop of the tasks of a case, whose releases are choices of the case.

    spawn makes a task ready, and run releases the ready tasks one at a time
    until no task is ready. A task that awaits a future that is not done is
    parked, and run returns while it waits. advance releases tasks in the
    same way and moves the clock of the scheduler from deadline to deadline.
    The steps of a machine run the clients of a concurrent section as tasks
    of a scheduler under the option tasks. A test can also spawn tasks of
    its own.

    The scheduler is the running event loop of its thread while run or
    advance releases a task, so asyncio.get_running_loop returns it. A task
    can create futures, locks, events, queues and conditions, and it sleeps
    on the clock of the scheduler with asyncio.sleep. A task is not an
    asyncio.Task. asyncio.current_task then returns None in a task, and
    asyncio.timeout and asyncio.wait_for raise RuntimeError there.
    asyncio.gather and asyncio.create_task end the run with a fault, because
    the scheduler does not create an asyncio.Task. A test spawns each task
    through spawn instead.

    When its case ends, the scheduler closes the coroutine of every task that
    has not ended, so a parked task does not return from its wait.
    """

    def __init__(
        self, case: Case, strategy: Strategy, *options: SchedulerOption
    ) -> None:
        """Return a scheduler that releases the tasks of a case by a strategy.

        Args:
            case: The case whose choices decide the releases.
            strategy: The way in which the scheduler chooses the task to
                release.
            *options: The options of the scheduler, such as max_releases.
                The last option of a setting applies.
        """
        self._case: Case = case
        self._strategy: Strategy = strategy
        self._max_releases: int = MAX_RELEASES
        for option in options:
            self._max_releases = option.max_releases
        self._tasks: list[_Task] = []
        self._ready: list[_Task] = []
        self._callbacks: deque[_Callback] = deque()
        self._timers: list[tuple[int, int, _Callback]] = []
        self._order: itertools.count[int] = itertools.count()
        self._now: int = EPOCH
        self._lowest: int = 0
        self._running: bool = False
        case.cleanup(self._drop)

    def spawn(self, task: Callable[[], Coroutine[Any, Any, object]]) -> None:
        """Make a task ready after every ready task.

        Under PCT, the task first receives its priority, a choice of the
        case. The task does not run until a release starts it, and it runs in
        a copy of the context of the spawn. A task can spawn other tasks while
        it runs.

        Args:
            task: The function of the task. It returns the coroutine of the
                task, as an async def does.
        """
        priority = 0
        if self._strategy.depth > 0:
            priority = on_engine(self._case, lambda e: e.integer(_UNSIGNED))
        spawned = _Task(task, priority, contextvars.copy_context())
        self._tasks.append(spawned)
        self._ready.append(spawned)

    def run(self) -> None:
        """Release one ready task at a time until no task is ready.

        Under PCT, the run first makes its change points. Before each
        release, the run calls each callback and each timer that is due, in
        the order of the calls that scheduled them. The task of the release
        runs until it awaits a future that is not done, yields, or ends. A
        task that yields becomes ready again after every ready task. A task
        that awaits a future becomes ready after every ready task when the
        future is done. A task that ends with CancelledError ends in the same
        way as a cancelled task. The run does not move the clock, so a task
        that sleeps stays parked until an advance.

        A task that raises ends the run. The run then closes the coroutine of
        every task that has not ended, drops every task, callback and timer,
        and raises the error again. A callback that raises ends the run in the
        same way. A run that has released the most tasks of max_releases
        while a task is still ready ends every task in the same way, and
        fails the case. A task can spawn more tasks after a run has ended,
        and a later run releases them.

        Raises:
            RuntimeError: A task called run of its own scheduler, awaited a
                future of another event loop, or yielded a value that is not
                a future.
            TypeError: The function of a task returned a value that is not a
                coroutine.
        """
        with self._releasing("run"):
            self._release_all(on_engine(self._case, self._change_points), 0)

    def advance(self, duration: float) -> None:
        """Release tasks, and move the clock by duration, deadline by deadline.

        The advance releases one ready task at a time as run does, until no
        task is ready. It then moves the clock to the earliest due time of a
        timer, such as the end of an asyncio.sleep, or to its end time when no
        timer is due before it. The timers of that time wake their tasks, and
        the advance releases tasks again. It returns when the clock reads its
        end time and no task is ready. A task that a timer wakes reads the time
        of its timer, so a task that sleeps again measures its next deadline
        from there. A duration of zero or less moves the clock by nothing.
        Under PCT, the change points count the releases of every step of the
        advance from 0. The advance ends every task at an error and at the
        limit of releases as run does.

        Args:
            duration: The seconds by which the clock moves.

        Raises:
            RuntimeError: A task called advance of its own scheduler, or a
                task failed in a way that run raises for.
            TypeError: The function of a task returned a value that is not a
                coroutine.
        """
        with self._releasing("advance"):
            end = self._now + max(_nanoseconds(duration), 0)
            points = on_engine(self._case, self._change_points)
            release = 0
            while True:
                release = self._release_all(points, release)
                self._now = min(self._due(end), end)
                self._settle()
                if not self._ready and self._now == end:
                    return

    def clock(self) -> Clock:
        """Return the clock of the scheduler.

        The clock reads the time of the scheduler in seconds since the Unix
        epoch, midnight UTC 2000-01-01 until advance moves it. A task sleeps
        on the clock with asyncio.sleep. The sleep of the clock returns at
        once for a duration of zero or less, and raises RuntimeError for a
        positive duration.

        Returns:
            The clock.
        """
        return _Clock(self)

    @contextlib.contextmanager
    def _releasing(self, call: str) -> Iterator[None]:
        """Make the scheduler the running event loop while run or advance releases.

        An error ends every task, and passes through.

        Raises:
            RuntimeError: A task called run or advance of its own scheduler.
        """
        if self._running:
            msg = f"stateful: a task called {call} of its own scheduler"
            raise RuntimeError(msg)
        self._running = True
        # asyncio provides these two functions for the implementations of an
        # event loop.
        previous = events._get_running_loop()  # noqa: SLF001
        events._set_running_loop(self)  # noqa: SLF001
        try:
            yield
        except BaseException:
            self._drop()
            raise
        finally:
            events._set_running_loop(previous)  # noqa: SLF001
            self._running = False

    def _release_all(self, points: list[int], release: int) -> int:
        """Release one ready task at a time until none is ready, counting from release.

        Returns:
            The count of the releases after the last one.
        """
        while True:
            self._settle()
            if not self._ready:
                return release
            if release == self._max_releases:
                self._case.fail(
                    f"the task scheduler released {release} tasks in one run, and a "
                    "task is still ready"
                )
            task = self._next()
            for point in points:
                if point == release:
                    self._lowest -= 1
                    task.level = self._lowest
            self._release(task)
            release += 1

    def _due(self, end: int) -> int:
        """Return the due time of the earliest timer that nobody cancelled, or end."""
        while self._timers and self._timers[0][2].handle.cancelled():
            heapq.heappop(self._timers)
        return self._timers[0][0] if self._timers else end

    @override
    def call_soon(
        self,
        callback: Callable[[*_Ts], object],
        *args: *_Ts,
        context: contextvars.Context | None = None,
    ) -> asyncio.Handle:
        """Schedule a callback before the next release.

        Args:
            callback: The callback.
            *args: The arguments of the callback.
            context: The context in which the callback runs, or None for a
                copy of the current context.

        Returns:
            The handle, which cancels the callback.
        """
        within = contextvars.copy_context() if context is None else context
        handle = asyncio.Handle(callback, args, self, within)
        self._callbacks.append(_Callback(handle, callback, args, within))
        return handle

    @override
    def call_later(
        self,
        delay: float,
        callback: Callable[[*_Ts], object],
        *args: *_Ts,
        context: contextvars.Context | None = None,
    ) -> asyncio.TimerHandle:
        """Schedule a callback for a delay on the clock of the scheduler.

        The clock counts whole nanoseconds, so the due time is the time of the
        clock plus the delay rounded to a nanosecond.

        Args:
            delay: The delay in seconds.
            callback: The callback.
            *args: The arguments of the callback.
            context: The context in which the callback runs, or None for a
                copy of the current context.

        Returns:
            The handle, which cancels the callback.
        """
        return self._timer(self._now + _nanoseconds(delay), callback, args, context)

    @override
    def call_at(
        self,
        when: float,
        callback: Callable[[*_Ts], object],
        *args: *_Ts,
        context: contextvars.Context | None = None,
    ) -> asyncio.TimerHandle:
        """Schedule a callback for a time on the clock of the scheduler.

        The callback is due once the clock is at the time, rounded to a
        nanosecond. Of two callbacks for one time, the one scheduled first
        runs first.

        Args:
            when: The time in seconds since the Unix epoch.
            callback: The callback.
            *args: The arguments of the callback.
            context: The context in which the callback runs, or None for a
                copy of the current context.

        Returns:
            The handle, which cancels the callback.
        """
        return self._timer(_nanoseconds(when), callback, args, context)

    def _timer(
        self,
        due: int,
        callback: Callable[..., object],
        args: tuple[Any, ...],
        context: contextvars.Context | None,
    ) -> asyncio.TimerHandle:
        """Schedule a callback for a due time in nanoseconds, and return its handle."""
        within = contextvars.copy_context() if context is None else context
        handle = _Timer(due / _SECOND, callback, args, self, within)
        timer = _Callback(handle, callback, args, within)
        heapq.heappush(self._timers, (due, next(self._order), timer))
        return handle

    @override
    def time(self) -> float:
        """Return the time on the clock of the scheduler.

        Returns:
            The seconds since the Unix epoch.
        """
        return self._now / _SECOND

    @override
    def create_future(self) -> asyncio.Future[Any]:
        """Return a future of this event loop.

        Returns:
            The future.
        """
        return asyncio.Future(loop=self)

    @override
    def is_running(self) -> bool:
        """Report whether run is releasing tasks.

        Returns:
            True while run releases tasks.
        """
        return self._running

    @override
    def is_closed(self) -> bool:
        """Report whether the event loop is closed. A scheduler is never closed.

        Returns:
            False.
        """
        return False

    @override
    def get_debug(self) -> bool:
        """Report whether the event loop runs in debug mode. A scheduler never does.

        Returns:
            False.
        """
        return False

    @override
    def call_exception_handler(self, context: dict[str, Any]) -> None:
        """Ignore an error that asyncio reports outside a task.

        A future reports an exception that nobody retrieved this way when it
        is collected. An error of a task or of a callback ends the run
        instead.

        Args:
            context: The report.
        """
        del context

    # The members that the scheduler does not implement. Each ends the run of
    # the property with a fault.
    add_reader = _refusing("add_reader")
    add_signal_handler = _refusing("add_signal_handler")
    add_writer = _refusing("add_writer")
    call_soon_threadsafe = _refusing("call_soon_threadsafe")
    close = _refusing("close")
    connect_accepted_socket = _refusing("connect_accepted_socket")
    connect_read_pipe = _refusing("connect_read_pipe")
    connect_write_pipe = _refusing("connect_write_pipe")
    create_connection = _refusing("create_connection")
    create_datagram_endpoint = _refusing("create_datagram_endpoint")
    create_server = _refusing("create_server")
    create_task = _refusing("create_task")
    create_unix_connection = _refusing("create_unix_connection")
    create_unix_server = _refusing("create_unix_server")
    default_exception_handler = _refusing("default_exception_handler")
    get_exception_handler = _refusing("get_exception_handler")
    get_task_factory = _refusing("get_task_factory")
    getaddrinfo = _refusing("getaddrinfo")
    getnameinfo = _refusing("getnameinfo")
    remove_reader = _refusing("remove_reader")
    remove_signal_handler = _refusing("remove_signal_handler")
    remove_writer = _refusing("remove_writer")
    run_forever = _refusing("run_forever")
    run_in_executor = _refusing("run_in_executor")
    run_until_complete = _refusing("run_until_complete")
    sendfile = _refusing("sendfile")
    set_debug = _refusing("set_debug")
    set_default_executor = _refusing("set_default_executor")
    set_exception_handler = _refusing("set_exception_handler")
    set_task_factory = _refusing("set_task_factory")
    shutdown_asyncgens = _refusing("shutdown_asyncgens")
    shutdown_default_executor = _refusing("shutdown_default_executor")
    sock_accept = _refusing("sock_accept")
    sock_connect = _refusing("sock_connect")
    sock_recv = _refusing("sock_recv")
    sock_recv_into = _refusing("sock_recv_into")
    sock_recvfrom = _refusing("sock_recvfrom")
    sock_recvfrom_into = _refusing("sock_recvfrom_into")
    sock_sendall = _refusing("sock_sendall")
    sock_sendfile = _refusing("sock_sendfile")
    sock_sendto = _refusing("sock_sendto")
    start_tls = _refusing("start_tls")
    stop = _refusing("stop")
    subprocess_exec = _refusing("subprocess_exec")
    subprocess_shell = _refusing("subprocess_shell")

    def _change_points(self, e: Engine) -> list[int]:
        """Return the release counts of the change points of a run.

        Under PCT, the run makes depth - 1 presence choices with the edge 1,
        and a count of releases after each presence of 1. The uniform
        strategy makes none.
        """
        return [
            e.integer(_UNSIGNED)
            for _ in range(1, self._strategy.depth)
            if e.integer(_PRESENCE, 1) == 1
        ]

    def _settle(self) -> None:
        """Call the due callbacks and timers until a task is ready or none is due.

        The timers that are due at the time of the clock run in the order of
        their due times, and those of one time in the order of their calls.
        The callbacks that a callback schedules are due after the callbacks
        that were due before it ran. The clock does not move.
        """
        while True:
            while self._timers and self._timers[0][0] <= self._now:
                self._callbacks.append(heapq.heappop(self._timers)[2])
            for _ in range(len(self._callbacks)):
                self._call(self._callbacks.popleft())
            if self._ready or not self._callbacks:
                return

    def _next(self) -> _Task:
        """Remove the task to release from the ready tasks, and return it.

        Under PCT, the task has the highest level and then the highest
        priority. Of equal tasks, it is the earliest ready one. Under the
        uniform strategy, the task is the choice of the case among the ready
        tasks.
        """
        ready = self._ready
        if self._strategy.depth > 0:
            index = max(
                range(len(ready)), key=lambda i: (ready[i].level, ready[i].priority)
            )
        else:
            count = len(ready)
            request = Request(
                IntegerBounds(0, count - 1), lambda source: source.below(count), 0
            )
            index = cast("int", on_engine(self._case, lambda e: e.choose(request)))
        return ready.pop(index)

    def _release(self, task: _Task) -> None:
        """Run a task until it awaits a future that is not done, yields, or ends.

        Raises:
            RuntimeError: The task awaited a future of another event loop, or
                it yielded a value that is not a future.
        """
        try:
            yielded = task.context.run(self._step, task)
        except (StopIteration, asyncio.CancelledError):
            self._tasks.remove(task)
            return
        if yielded is None:
            self._ready.append(task)
            return
        if not asyncio.isfuture(yielded):
            msg = f"stateful: a task yielded {yielded!r} instead of a future"
            raise RuntimeError(msg)
        future = cast("asyncio.Future[object]", yielded)
        if future.get_loop() is not self:
            msg = "stateful: a task awaited a future of another event loop"
            raise RuntimeError(msg)
        future.add_done_callback(lambda _: self._ready.append(task))

    def _step(self, task: _Task) -> object:
        """Start a task at its first release, and send its coroutine the next value.

        Raises:
            TypeError: The function of the task returned a value that is not
                a coroutine.
        """
        coroutine = task.coroutine
        if coroutine is None:
            started = task.start()
            if not inspect.iscoroutine(started):
                msg = f"stateful: the task returned {started!r} instead of a coroutine"
                raise TypeError(msg)
            coroutine = task.coroutine = started
        return coroutine.send(None)

    def _call(self, callback: _Callback) -> None:
        """Run a callback in its context, unless its caller cancelled it."""
        if not callback.handle.cancelled():
            callback.context.run(callback.fn, *callback.args)

    def _drop(self) -> None:
        """Close the coroutine of every task that has not ended, and drop the rest.

        The scheduler then has no task, callback or timer left. An error of a
        run and the end of the case of the scheduler call it.
        """
        tasks = self._tasks
        self._tasks = []
        self._ready.clear()
        self._callbacks.clear()
        self._timers.clear()
        for task in tasks:
            if task.coroutine is not None:
                task.context.run(task.coroutine.close)
