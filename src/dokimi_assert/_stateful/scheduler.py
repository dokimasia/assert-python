"""The task scheduler, whose releases of tasks are choices of a case.

The scheduler is an event loop of asyncio, and a task is a coroutine. The
scheduler releases one ready task at a time. The task runs until it awaits
a future that is not done, yields with asyncio.sleep(0), or ends. The
strategy of the scheduler takes each release from the choices of the case,
so a schedule replays and shrinks in the same way as the values of the case.

The scheduler implements the members of the event loop that futures, locks,
events, queues and asyncio.sleep call. Its clock is virtual. The clock
starts at 0, and it moves to the next timer when no task is ready and no
callback is due, so a sleep does not spend real time. Each other member
of the event loop ends the run of the property with a fault. The members
for sockets, pipes, subprocesses, signals and threads are such members, and
so is create_task.
"""

from __future__ import annotations

import asyncio
import contextvars
import heapq
import inspect
import itertools
from asyncio import events
from collections import deque
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any, NoReturn, TypeVarTuple, cast, final

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._prop.case import Case, FaultSignal, on_engine
from dokimi_assert._prop.engine.case import Case as Engine
from dokimi_assert._prop.engine.case import Request
from dokimi_assert._prop.engine.choice import UINT64_MAX, IntegerBounds
from dokimi_assert._stateful.strategy import Strategy

__all__ = ["Scheduler"]

_Ts = TypeVarTuple("_Ts")

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
    until every task has ended. The steps of a machine run the clients of a
    concurrent section as tasks of a scheduler under the option tasks. A
    test can also spawn tasks of its own.

    The scheduler is the running event loop of its thread while run
    releases a task, so asyncio.get_running_loop returns it. A task can
    create futures, locks, events, queues and conditions, and it can sleep.
    A task is not an asyncio.Task. asyncio.current_task then returns None in
    a task, and asyncio.timeout and asyncio.wait_for raise RuntimeError
    there. asyncio.gather and asyncio.create_task end the run with a fault,
    because the scheduler does not create an asyncio.Task. A test spawns
    each task through spawn instead.
    """

    def __init__(self, case: Case, strategy: Strategy) -> None:
        """Return a scheduler that releases the tasks of a case by a strategy.

        Args:
            case: The case whose choices decide the releases.
            strategy: The way in which the scheduler chooses the task to
                release.
        """
        self._case: Case = case
        self._strategy: Strategy = strategy
        self._tasks: list[_Task] = []
        self._ready: list[_Task] = []
        self._callbacks: deque[_Callback] = deque()
        self._timers: list[tuple[float, int, _Callback]] = []
        self._order: itertools.count[int] = itertools.count()
        self._now: float = 0.0
        self._lowest: int = 0
        self._running: bool = False

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
        """Release one ready task at a time until every task has ended.

        Under PCT, the run first makes its change points. Before each
        release, the run calls each callback that is due, in the order of the
        calls that scheduled them. When no task is ready and no callback is
        due, the clock moves to the next timer. The task of the release runs
        until it awaits a future that is not done, yields, or ends. A task
        that awaits a future becomes ready when the future is done. A task
        that ends with CancelledError ends in the same way as a cancelled
        task.

        A task that raises ends the run. The run then closes the coroutine of
        every task that has not ended, drops every task, callback and timer,
        and raises the error again. A callback that raises ends the run in the
        same way. A task can spawn more tasks after a run has ended, and a
        later run releases them.

        Raises:
            RuntimeError: A task called run of its own scheduler, awaited a
                future of another event loop, or yielded a value that is not
                a future. The run also raises it when every task that has not
                ended waits, and no callback or timer is left.
            TypeError: The function of a task returned a value that is not a
                coroutine.
        """
        if self._running:
            raise RuntimeError("stateful: a task called run of its own scheduler")
        self._running = True
        previous = events._get_running_loop()
        events._set_running_loop(self)
        try:
            points = on_engine(self._case, self._change_points)
            release = 0
            while self._tasks:
                self._settle()
                task = self._next()
                for point in points:
                    if point == release:
                        self._lowest -= 1
                        task.level = self._lowest
                self._release(task)
                release += 1
        except BaseException:
            self._drop()
            raise
        finally:
            events._set_running_loop(previous)
            self._running = False

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

    def call_later(
        self,
        delay: float,
        callback: Callable[[*_Ts], object],
        *args: *_Ts,
        context: contextvars.Context | None = None,
    ) -> asyncio.TimerHandle:
        """Schedule a callback for a delay on the clock of the scheduler.

        Args:
            delay: The delay in seconds.
            callback: The callback.
            *args: The arguments of the callback.
            context: The context in which the callback runs, or None for a
                copy of the current context.

        Returns:
            The handle, which cancels the callback.
        """
        return self.call_at(self._now + delay, callback, *args, context=context)

    def call_at(
        self,
        when: float,
        callback: Callable[[*_Ts], object],
        *args: *_Ts,
        context: contextvars.Context | None = None,
    ) -> asyncio.TimerHandle:
        """Schedule a callback for a time on the clock of the scheduler.

        The callback is due once the clock is at the time. Of two callbacks
        for one time, the one scheduled first runs first.

        Args:
            when: The time in seconds.
            callback: The callback.
            *args: The arguments of the callback.
            context: The context in which the callback runs, or None for a
                copy of the current context.

        Returns:
            The handle, which cancels the callback.
        """
        within = contextvars.copy_context() if context is None else context
        handle = _Timer(when, callback, args, self, within)
        timer = _Callback(handle, callback, args, within)
        heapq.heappush(self._timers, (when, next(self._order), timer))
        return handle

    def time(self) -> float:
        """Return the time on the clock of the scheduler, in seconds from 0.

        Returns:
            The time.
        """
        return self._now

    def create_future(self) -> asyncio.Future[Any]:
        """Return a future of this event loop.

        Returns:
            The future.
        """
        return asyncio.Future(loop=self)

    def is_running(self) -> bool:
        """Report whether run is releasing tasks.

        Returns:
            True while run releases tasks.
        """
        return self._running

    def is_closed(self) -> bool:
        """Report whether the event loop is closed. A scheduler is never closed.

        Returns:
            False.
        """
        return False

    def get_debug(self) -> bool:
        """Report whether the event loop runs in debug mode. A scheduler never does.

        Returns:
            False.
        """
        return False

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
        points: list[int] = []
        for _ in range(1, self._strategy.depth):
            if e.integer(_PRESENCE, 1) == 1:
                points.append(e.integer(_UNSIGNED))
        return points

    def _settle(self) -> None:
        """Call the due callbacks and timers until a task is ready.

        The clock moves to the next timer while no task is ready and no
        callback is due. The callbacks that a callback schedules are due
        after the callbacks that were due before it ran.

        Raises:
            RuntimeError: No task is ready, and no callback or timer is left.
        """
        while True:
            while self._timers and self._timers[0][0] <= self._now:
                self._callbacks.append(heapq.heappop(self._timers)[2])
            for _ in range(len(self._callbacks)):
                self._call(self._callbacks.popleft())
            if self._ready:
                return
            if not self._callbacks:
                self._advance()

    def _advance(self) -> None:
        """Move the clock to the next timer that nobody cancelled.

        Raises:
            RuntimeError: No such timer is left.
        """
        while self._timers and self._timers[0][2].handle.cancelled():
            heapq.heappop(self._timers)
        if not self._timers:
            raise RuntimeError(
                "stateful: every task that has not ended waits on a future, and "
                "no callback or timer is left"
            )
        self._now = self._timers[0][0]

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
            raise RuntimeError(
                f"stateful: a task yielded {yielded!r} instead of a future"
            )
        future = cast("asyncio.Future[object]", yielded)
        if future.get_loop() is not self:
            raise RuntimeError(
                "stateful: a task awaited a future of another event loop"
            )
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
                raise TypeError(
                    f"stateful: the task returned {started!r} instead of a coroutine"
                )
            coroutine = task.coroutine = started
        return coroutine.send(None)

    def _call(self, callback: _Callback) -> None:
        """Run a callback in its context, unless its caller cancelled it."""
        if not callback.handle.cancelled():
            callback.context.run(callback.fn, *callback.args)

    def _drop(self) -> None:
        """Close the coroutine of every task that has not ended, and drop the rest.

        The scheduler then has no task, callback or timer left.
        """
        tasks = self._tasks
        self._tasks = []
        self._ready.clear()
        self._callbacks.clear()
        self._timers.clear()
        for task in tasks:
            if task.coroutine is not None:
                task.context.run(task.coroutine.close)
