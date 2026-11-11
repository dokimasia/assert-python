# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The machine subjects of the definition, which a machines vector runs by name.

Every subject records each call of a client in the history of the case,
without keys, and completes the call as ok with its output:

- queue-loses-on-wrap: a bounded queue of a capacity that the case draws
  under the label capacity from 1 to 8. put writes its value at the write
  index and returns True, or returns False when the queue is full. get
  returns the oldest value, or None for an empty queue. A put at the last
  slot writes its value into the first slot, and the write index wraps to
  the first slot. The actions are put, whose input the case draws under the
  label v from 0 to 1000, and get. The spec is a bounded queue of the
  capacity.
- correct-queue: the same machine over a queue that writes every value at
  its write index.
- counter-overflows: a counter whose increment adds one and returns the
  count, and whose reset sets the count to 0 and returns None. An increment
  that takes the count to 3 sets it to 0 and returns 0. The actions are
  increment and reset, and the spec is a counter.
- store-loses-on-crash: a store that puts a value under a key into a
  buffer, moves the buffer into its durable map on flush, and empties the
  buffer on crash. The actions are put, flush and crash. The input of put
  is a key that the case draws under the label key from 0 to 3, and the
  next value of a count from 1. flush is a drain action, enabled while the
  buffer is not empty. The machine does not have a spec. Its settle reads
  the durable value of every key of an acknowledged put, and fails with a
  record of lost-write for a value that is not the last value put.
- racy-counter: a counter whose increment reads the count, awaits
  asyncio.sleep(0), writes the count plus one and returns it. The action is
  increment, the spec is a counter, and the clients run as tasks of a
  scheduler.
- correct-counter: the same machine over an increment that adds one and
  returns the count without an await.
- counter-refuses-every-third: a counter that refuses every third
  increment, counted over every case of the run. A refused increment
  completes as failed with the error refused, and does not change the
  count. Any other increment adds one and returns the count, and read
  returns the count. The actions are increment, enabled while the count of
  the spec is below 3, and read. The spec is a counter.
- register-flushes-in-two-parts: a register of a buffer and a durable
  value. write sets the buffer to its value and returns None. read returns
  the buffer when it is set, and the durable value otherwise. A flusher
  task of the subject awaits an asyncio.Event that write sets. It takes the
  value and clears the buffer and the event, yields, and then sets the
  durable value to the value that it took. The actions are write, whose
  input the case draws under the label v from 0 to 1000, and read. The spec
  is a register, and the clients and the flusher run as tasks of one
  scheduler.
- register-flushes: the same machine over a flusher that sets the durable
  value to the buffer and then clears the buffer, without a yield between.
- ticker-skips-its-first-tick: a ticker task that sleeps 4 ms with
  asyncio.sleep and adds one to its count, four times, and that skips the
  first addition. The actions are advance, which advances the scheduler by
  a number of milliseconds that the case draws under the label ms from 0 to
  10, and read, which returns the count. The spec counts the milliseconds
  of the advances.
- ticker: the same machine over a ticker that adds one at each tick.
- spins-until-a-flag: a subject whose action spin spawns a task that yields
  until a flag is set, and runs the scheduler. No action sets the flag, and
  the machine does not have a spec.

Each run builds its subjects anew, so a subject that counts over the cases
of a run starts each run at 0. A subject that spawns tasks of its own
spawns them on a scheduler of the case with the strategy and the limit of
releases of the setup, and the clients of its concurrent section run on the
same scheduler. Each subject sets keep on the actions that the setup names.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from dokimi_assert import history, prop, stateful
from dokimi_assert._stateful import scheduler as stateful_scheduler
from dokimi_assert.failure import Failure

__all__ = ["SUBJECTS", "Setup", "Subject"]


@dataclass(frozen=True, slots=True)
class Setup:
    """The options of the steps of a subject, and the options of its scheduler.

    Attributes:
        steps: The options that every subject takes: mean, max_steps and
            swarm.
        section: The options of a concurrent section: clients, concurrent
            and concurrent_mean.
        strategy: The strategy of the scheduler that a subject with a
            concurrent section or with tasks of its own makes in each case.
        max_releases: The most tasks that one run or one advance of that
            scheduler releases.
        keep: The names of the actions of the subject that every case keeps.
    """

    steps: Sequence[stateful.Option]
    section: Sequence[stateful.Option]
    strategy: stateful.Strategy
    max_releases: int = stateful_scheduler.MAX_RELEASES
    keep: frozenset[str] = frozenset()

    def marked(self, actions: list[stateful.Action[Any]]) -> list[stateful.Action[Any]]:
        """Return the actions with keep set on each action that the setup names.

        Args:
            actions: The actions of a machine.

        Returns:
            The actions in the same order.
        """
        return [
            replace(action, keep=True) if action.name in self.keep else action
            for action in actions
        ]

    def scheduler_in(self, c: prop.Case) -> stateful.Scheduler:
        """Return a scheduler of a case with the strategy and the limit of the setup.

        Args:
            c: The case whose choices decide the releases.

        Returns:
            The scheduler.
        """
        return stateful.Scheduler(
            c, self.strategy, stateful.max_releases(self.max_releases)
        )


#: A subject builds its machine and takes its steps in a case.
Subject = Callable[[prop.Case, Setup], None]

#: The generators of the draws of the subjects.
_CAPACITIES = prop.integer(1, 8)
_VALUES = prop.integer(0, 1000)
_KEYS = prop.integer(0, 3)

#: The count at which counter-overflows sets its count to 0.
_OVERFLOW = 3

#: Every this many increments of a run, counter-refuses-every-third refuses
#: an increment with the error refused.
_REFUSAL = 3
_REFUSED = "refused"

#: The count of the spec below which counter-refuses-every-third enables its
#: increment.
_LIMIT = 3

#: The ticker sleeps _PERIOD seconds before each of its _TICKS ticks. The
#: spec counts the ticks of _PERIOD_MS milliseconds.
_PERIOD = 0.004
_PERIOD_MS = 4
_TICKS = 4

#: The generator of the milliseconds of an advance, and a millisecond in
#: seconds.
_MILLISECONDS = prop.integer(0, 10)
_MILLISECOND = 0.001

#: The assertion and the contract of the record of the settle of
#: store-loses-on-crash.
_LOST = "lost-write"
_DURABLE = "the store keeps every acknowledged put"


@dataclass(slots=True)
class _Machine:
    """A machine of a subject.

    Attributes:
        actions: The actions in order, with the simpler first.
        spec: The spec of the machine, or None.
        settle: The settle of the machine, or None.
    """

    actions: list[stateful.Action[Any]]
    spec: history.Spec[Any] | None = None
    settle: Callable[[prop.Case, Any], None] | None = None


class _Ring:
    """A bounded queue in a ring of slots.

    A ring that loses on wrap writes the value of a put at the last slot into
    the first slot.
    """

    def __init__(self, capacity: int, loses_on_wrap: bool) -> None:
        """Return an empty ring of a capacity."""
        self._slots: list[int | None] = [None] * capacity
        self._loses_on_wrap: bool = loses_on_wrap
        self._head: int = 0
        self._tail: int = 0
        self._size: int = 0

    def put(self, value: int) -> bool:
        """Add value, and report whether the ring had room for it."""
        capacity = len(self._slots)
        if self._size == capacity:
            return False
        last = self._tail == capacity - 1
        self._slots[0 if last and self._loses_on_wrap else self._tail] = value
        self._tail = 0 if last else self._tail + 1
        self._size += 1
        return True

    def get(self) -> int | None:
        """Remove and return the oldest value, or return None for an empty ring."""
        if self._size == 0:
            return None
        value = self._slots[self._head]
        self._head = (self._head + 1) % len(self._slots)
        self._size -= 1
        return value


@dataclass(frozen=True, slots=True)
class _BoundedQueue:
    """The spec of a queue of at most capacity values.

    put appends its value while the queue has room. get returns the oldest
    value and removes it. A get of an empty queue returns None and does not
    change the queue. A put returns whether the queue had room.
    """

    capacity: int

    def initial(self) -> tuple[int, ...]:
        """Return the empty queue."""
        return ()

    def next(self, state: tuple[int, ...], op: history.Operation) -> list[Any]:
        """Return the state after a put or a get."""
        if op.name == "put":
            return [state if len(state) == self.capacity else (*state, op.args[0])]
        if not state:
            return [state]
        return [state[1:]] if op.returned(state[0]) else []


class _Counter:
    """The spec of a counter.

    increment returns the new count, reset sets the count to 0, and read
    returns the count.
    """

    def initial(self) -> int:
        """Return the count 0."""
        return 0

    def next(self, state: int, op: history.Operation) -> list[int]:
        """Return the count after an increment, a reset or a read."""
        if op.name == "reset":
            return [0]
        after = state if op.name == "read" else state + 1
        return [after] if op.returned(after) else []


class _Register:
    """The spec of a register: write leaves its value, and read returns it."""

    def initial(self) -> object:
        """Return the initial value None."""
        return None

    def next(self, state: object, op: history.Operation) -> list[object]:
        """Return the value after a write or a read."""
        if op.name == "write":
            return [op.args[0]]
        return [state] if op.returned(state) else []


class _Ticks:
    """The spec of the ticker: the milliseconds that the advances add.

    read returns the milliseconds divided by the period, at most the number
    of ticks.
    """

    def initial(self) -> int:
        """Return 0 milliseconds."""
        return 0

    def next(self, state: int, op: history.Operation) -> list[int]:
        """Return the milliseconds after an advance or a read."""
        if op.name == "advance":
            return [state + op.args[0]]
        return [state] if op.returned(min(_TICKS, state // _PERIOD_MS)) else []


def _queue(c: prop.Case, setup: Setup, loses_on_wrap: bool) -> None:
    """Run the queue machine over a ring of a capacity that the case draws."""
    capacity = c.draw(_CAPACITIES, "capacity")
    ring = _Ring(capacity, loses_on_wrap)

    def put(c: prop.Case, client: int, value: int) -> None:
        call = c.history().invoke(client, "put", [value])
        call.ok(ring.put(value))

    def get(c: prop.Case, client: int, _: object) -> None:
        call = c.history().invoke(client, "get", [])
        call.ok(ring.get())

    actions: list[stateful.Action[Any]] = [
        stateful.Action("put", put, input=lambda c, _: c.draw(_VALUES, "v")),
        stateful.Action("get", get),
    ]
    stateful.steps(
        c, _Machine(setup.marked(actions), _BoundedQueue(capacity)), *setup.steps
    )


def _counter_overflows(c: prop.Case, setup: Setup) -> None:
    """Run the counter machine over a counter that overflows at 3."""
    count = [0]

    def increment(c: prop.Case, client: int, _: object) -> None:
        call = c.history().invoke(client, "increment", [])
        count[0] = (count[0] + 1) % _OVERFLOW
        call.ok(count[0])

    def reset(c: prop.Case, client: int, _: object) -> None:
        call = c.history().invoke(client, "reset", [])
        count[0] = 0
        call.ok(None)

    actions: list[stateful.Action[Any]] = [
        stateful.Action("increment", increment),
        stateful.Action("reset", reset),
    ]
    stateful.steps(c, _Machine(setup.marked(actions), _Counter()), *setup.steps)


@dataclass(slots=True)
class _Store:
    """The state of store-loses-on-crash in one case.

    Attributes:
        durable: The values that a flush moved into the durable map, by key.
        buffer: The values that a put wrote since the last flush or crash.
        acknowledged: The last value of each key whose put returned.
        written: The number of puts so far. The value of a put is the next
            number.
    """

    durable: dict[int, int] = field(default_factory=dict)
    buffer: dict[int, int] = field(default_factory=dict)
    acknowledged: dict[int, int] = field(default_factory=dict)
    written: int = 0


def _store_loses_on_crash(c: prop.Case, setup: Setup) -> None:
    """Run the store machine, whose settle reads every acknowledged put."""
    store = _Store()

    def entry(c: prop.Case, _: object) -> tuple[int, int]:
        key = c.draw(_KEYS, "key")
        store.written += 1
        return key, store.written

    def put(c: prop.Case, client: int, given: tuple[int, int]) -> None:
        key, value = given
        call = c.history().invoke(client, "put", [key, value])
        store.buffer[key] = value
        call.ok(None)
        store.acknowledged[key] = value

    def flush(_c: prop.Case, _client: int, _: object) -> None:
        store.durable.update(store.buffer)
        store.buffer.clear()

    def crash(_c: prop.Case, _client: int, _: object) -> None:
        store.buffer.clear()

    def settle(c: prop.Case, _: object) -> None:
        for key, value in store.acknowledged.items():
            if store.durable.get(key) != value:
                lost = Failure(_LOST, _DURABLE, {"key": key, "lost": value})
                c.report(lost, True)

    actions: list[stateful.Action[Any]] = [
        stateful.Action("put", put, input=entry),
        stateful.Action(
            "flush", flush, drain=True, enabled=lambda _: bool(store.buffer)
        ),
        stateful.Action("crash", crash),
    ]
    stateful.steps(c, _Machine(setup.marked(actions), settle=settle), *setup.steps)


def _shared_counter(c: prop.Case, setup: Setup, racy: bool) -> None:
    """Run the counter machine on clients that run as tasks of a scheduler.

    The increment of a racy counter awaits between its read and its write.
    """
    scheduler = setup.scheduler_in(c)
    count = [0]

    async def increment(c: prop.Case, client: int, _: object) -> None:
        call = c.history().invoke(client, "increment", [])
        read = count[0]
        if racy:
            await asyncio.sleep(0)
        count[0] = read + 1
        call.ok(count[0])

    actions: list[stateful.Action[Any]] = [stateful.Action("increment", increment)]
    stateful.steps(
        c,
        _Machine(setup.marked(actions), _Counter()),
        *setup.steps,
        *setup.section,
        stateful.tasks(scheduler),
    )


def _refusing_counter() -> Subject:
    """Return counter-refuses-every-third before its first increment."""
    increments = [0]

    def subject(c: prop.Case, setup: Setup) -> None:
        count = [0]

        def increment(c: prop.Case, client: int, _: object) -> None:
            call = c.history().invoke(client, "increment", [])
            increments[0] += 1
            if increments[0] % _REFUSAL == 0:
                call.fail(_REFUSED)
                return
            count[0] += 1
            call.ok(count[0])

        def read(c: prop.Case, client: int, _: object) -> None:
            c.history().invoke(client, "read", []).ok(count[0])

        actions: list[stateful.Action[Any]] = [
            stateful.Action(
                "increment", increment, enabled=lambda state: state < _LIMIT
            ),
            stateful.Action("read", read),
        ]
        stateful.steps(c, _Machine(setup.marked(actions), _Counter()), *setup.steps)

    return subject


def _flushed_register(c: prop.Case, setup: Setup, in_two_parts: bool) -> None:
    """Run the register machine on clients, over a buffer that a flusher moves."""
    scheduler = setup.scheduler_in(c)
    buffer: list[object] = [None]
    durable: list[object] = [None]
    filled = asyncio.Event()

    async def flusher() -> None:
        while True:
            await filled.wait()
            taken = buffer[0]
            buffer[0] = None
            filled.clear()
            if in_two_parts:
                await asyncio.sleep(0)
            durable[0] = taken

    def write(c: prop.Case, client: int, value: int) -> None:
        call = c.history().invoke(client, "write", [value])
        buffer[0] = value
        filled.set()
        call.ok(None)

    def read(c: prop.Case, client: int, _: object) -> None:
        call = c.history().invoke(client, "read", [])
        call.ok(durable[0] if buffer[0] is None else buffer[0])

    scheduler.spawn(flusher)
    actions: list[stateful.Action[Any]] = [
        stateful.Action("write", write, input=lambda c, _: c.draw(_VALUES, "v")),
        stateful.Action("read", read),
    ]
    stateful.steps(
        c,
        _Machine(setup.marked(actions), _Register()),
        *setup.steps,
        *setup.section,
        stateful.tasks(scheduler),
    )


def _ticker(c: prop.Case, setup: Setup, skips_first: bool) -> None:
    """Run the ticker machine, whose advance moves the clock of the scheduler."""
    scheduler = setup.scheduler_in(c)
    count = [0]

    async def ticking() -> None:
        for tick in range(_TICKS):
            await asyncio.sleep(_PERIOD)
            if tick > 0 or not skips_first:
                count[0] += 1

    def advance(c: prop.Case, client: int, milliseconds: int) -> None:
        call = c.history().invoke(client, "advance", [milliseconds])
        scheduler.advance(milliseconds * _MILLISECOND)
        call.ok(None)

    def read(c: prop.Case, client: int, _: object) -> None:
        c.history().invoke(client, "read", []).ok(count[0])

    scheduler.spawn(ticking)
    actions: list[stateful.Action[Any]] = [
        stateful.Action(
            "advance", advance, input=lambda c, _: c.draw(_MILLISECONDS, "ms")
        ),
        stateful.Action("read", read),
    ]
    stateful.steps(c, _Machine(setup.marked(actions), _Ticks()), *setup.steps)


def _spinner(c: prop.Case, setup: Setup) -> None:
    """Run the machine whose one action spawns a task that yields without an end.

    The task yields until a flag that no action sets, so it yields on every
    release and the run reaches its limit of releases.
    """
    scheduler = setup.scheduler_in(c)

    async def spinning() -> None:
        # The spin is the behaviour of the subject: the task stays ready.
        while True:  # noqa: ASYNC110
            await asyncio.sleep(0)

    def spin(_c: prop.Case, _client: int, _: object) -> None:
        scheduler.spawn(spinning)
        scheduler.run()

    actions: list[stateful.Action[Any]] = [stateful.Action("spin", spin)]
    stateful.steps(c, _Machine(setup.marked(actions)), *setup.steps)


#: The subjects of the definition, by name. Each entry returns the subject of
#: one run.
SUBJECTS: dict[str, Callable[[], Subject]] = {
    "queue-loses-on-wrap": lambda: lambda c, setup: _queue(c, setup, True),
    "correct-queue": lambda: lambda c, setup: _queue(c, setup, False),
    "counter-overflows": lambda: _counter_overflows,
    "store-loses-on-crash": lambda: _store_loses_on_crash,
    "racy-counter": lambda: lambda c, setup: _shared_counter(c, setup, True),
    "correct-counter": lambda: lambda c, setup: _shared_counter(c, setup, False),
    "counter-refuses-every-third": _refusing_counter,
    "register-flushes-in-two-parts": lambda: (
        lambda c, setup: _flushed_register(c, setup, True)
    ),
    "register-flushes": lambda: lambda c, setup: _flushed_register(c, setup, False),
    "ticker-skips-its-first-tick": lambda: lambda c, setup: _ticker(c, setup, True),
    "ticker": lambda: lambda c, setup: _ticker(c, setup, False),
    "spins-until-a-flag": lambda: _spinner,
}
