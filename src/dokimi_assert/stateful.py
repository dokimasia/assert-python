"""The steps of a machine inside the case of a property, and the task scheduler.

A machine has the sequential specification of a subject and its actions. The
actions are in order, with the simpler first. steps takes the steps of a case
and makes each decision a choice of the case. A failing case then shrinks to
the steps that the failure needs, and it replays from its token:

    class Queue:
        def initial(self) -> tuple[int, ...]:
            return ()

        def next(self, state: tuple[int, ...], op: history.Operation) -> list:
            if op.name == "put":
                return [(*state, op.args[0])]
            head = state[0] if state else None
            return [state[1:]] if op.returned(head) else []

    @dataclass
    class QueueMachine:
        queue: BoundedQueue
        spec: Queue = field(default_factory=Queue)

        @property
        def actions(self) -> list[stateful.Action[tuple[int, ...]]]:
            return [
                stateful.Action("put", self.put, input=self.value),
                stateful.Action("get", self.get),
            ]

        def value(self, c: prop.Case, state: tuple[int, ...]) -> int:
            return c.draw(prop.integer(0, 9), "v")

        def put(self, c: prop.Case, client: int, v: int) -> None:
            call = c.history().invoke(client, "put", [v])
            call.ok(self.queue.put(v))

        def get(self, c: prop.Case, client: int, _: object) -> None:
            call = c.history().invoke(client, "get", [])
            call.ok(self.queue.get())

    def test_the_queue_keeps_its_values_in_order(seat):
        def body(c: prop.Case) -> None:
            stateful.steps(c, QueueMachine(BoundedQueue(4)), stateful.clients(2))

        prop.for_all(seat, "the queue keeps its values in order", body)

The clients of a concurrent section run on threads by default, and a case
then runs up to repeat times, because threads do not replay. With the option
tasks, they run as tasks of a Scheduler. The releases of the scheduler are
choices of the case, so a race replays and shrinks. A subject that runs as
tasks awaits a future or asyncio.sleep(0) at each point where another task
can run.
"""

from __future__ import annotations

from dokimi_assert._history.linearizable import LINEARIZABLE
from dokimi_assert._history.sentence import sentence
from dokimi_assert._stateful.machine import Action, Machine
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
from dokimi_assert._stateful.strategy import Strategy, pct, uniform
from dokimi_assert.failure import register_sentence

__all__ = [
    "Action",
    "Machine",
    "Option",
    "Scheduler",
    "Strategy",
    "clients",
    "concurrent",
    "max_steps",
    "mean",
    "pct",
    "repeat",
    "steps",
    "swarm",
    "tasks",
    "uniform",
]

register_sentence(sentence, LINEARIZABLE)
