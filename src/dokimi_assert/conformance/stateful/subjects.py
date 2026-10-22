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

Each run builds its subjects anew, so a subject that counts over the cases
of a run starts each run at 0.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from dokimi_assert import history, prop, stateful
from dokimi_assert.failure import Failure

__all__ = ["SUBJECTS", "Setup", "Subject"]


@dataclass(frozen=True, slots=True)
class Setup:
    """The options of the steps of a subject and the strategy of its scheduler.

    Attributes:
        steps: The options that every subject takes: mean, max_steps and
            swarm.
        section: The options of a concurrent section: clients and
            concurrent.
        strategy: The strategy of the scheduler that a subject with a
            concurrent section makes in each case.
    """

    steps: Sequence[stateful.Option]
    section: Sequence[stateful.Option]
    strategy: stateful.Strategy


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
    stateful.steps(c, _Machine(actions, _BoundedQueue(capacity)), *setup.steps)


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
    stateful.steps(c, _Machine(actions, _Counter()), *setup.steps)


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
    stateful.steps(c, _Machine(actions, settle=settle), *setup.steps)


def _shared_counter(c: prop.Case, setup: Setup, racy: bool) -> None:
    """Run the counter machine on clients that run as tasks of a scheduler.

    The increment of a racy counter awaits between its read and its write.
    """
    scheduler = stateful.Scheduler(c, setup.strategy)
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
        _Machine(actions, _Counter()),
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
        stateful.steps(c, _Machine(actions, _Counter()), *setup.steps)

    return subject


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
}
