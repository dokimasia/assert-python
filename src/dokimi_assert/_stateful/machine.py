"""The machines that describe a subject and the actions that steps take on it."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

from dokimi_assert._history.spec import Spec
from dokimi_assert._prop.case import Case

__all__ = ["Action", "Machine", "validate"]

S = TypeVar("S")


@dataclass(frozen=True)
class Action(Generic[S]):
    """One named action of a machine. S is the type of the state of the spec.

    Attributes:
        name: The name of the action in a counterexample and in the step
            entries of a trace.
        run: Calls the subject on a client with the input of the step, and
            records each call in the history of the case. It takes the case,
            the client and the input. A run can return an awaitable. The step
            then runs it to its end.
        weight: The relative frequency with which a random step takes the
            action among the actions that the step lists. A weight of 0
            counts as 1.
        drain: When True, the action takes the steps of the drain. It takes
            them also when the swarm did not keep it.
        enabled: Returns True when a sequential or a drain step can take the
            action in a state. An action without enabled is enabled in every
            state, and only such an action takes the steps of a concurrent
            section. Its result must not depend on results that the subject
            can return differently on a replay of the case.
        input: Requests the input of a step from the case, such as a draw. It
            takes the case and the state. A step of an action without input
            has the input None. The bounds of its requests must not depend
            on results that the subject can return differently on a replay.
    """

    name: str
    run: Callable[[Case, int, Any], object]
    weight: int = 1
    drain: bool = False
    enabled: Callable[[S], bool] | None = None
    input: Callable[[Case, S], Any] | None = None


class Machine(Protocol[S]):
    """The sequential specification of a subject, and the actions that steps take on it.

    S is the type of the state of the spec. A machine can also define two
    methods. steps calls them with the case and the state:

    - invariant(case, state) runs after setup, after every sequential and
      drain step, and after settle.
    - settle(case, state) runs once after the drain. It checks what must be
      true once the subject has recovered, such as that every accepted write
      is readable. A settle can return an awaitable. steps then runs it to
      its end.

    The functions of a machine and of its actions receive a state of the
    spec. It is the first of the states that the last check of the history
    left. A machine without a spec receives None.

    These states follow what the subject returned. A replay of a case
    requests the same choices only when its steps list the same actions and
    its requests have the same bounds. A subject can return other results on
    a replay. An example is a subject that refuses a call when it is full.
    For such a subject, enabled and input must read a state that the
    machine keeps itself instead of the state of the spec. The inputs of the
    steps change that state, and the results of the subject do not.
    Otherwise a replay can take steps that differ from the steps of the
    case, and the run ends as flaky.
    """

    @property
    def spec(self) -> Spec[S] | None:
        """The sequential specification of the subject, or None.

        steps checks the history of the steps against the spec after every
        step, with every call in one partition. A machine without a spec does
        not check the history.
        """
        ...

    @property
    def actions(self) -> Sequence[Action[S]]:
        """The actions that steps can take.

        The actions are in order, with the simpler first. Each has a name of its
        own.
        """
        ...


def validate(machine: Machine[Any]) -> None:
    """Raise for a machine whose actions cannot take steps.

    Args:
        machine: The machine.

    Raises:
        ValueError: An action has a weight that is not an int of 0 or more,
            or two actions have one name.
        TypeError: The run of an action is not callable.
    """
    names: set[str] = set()
    for action in machine.actions:
        name = json.dumps(action.name, ensure_ascii=False)
        if type(action.weight) is not int or action.weight < 0:
            raise ValueError(
                f"stateful: the weight {action.weight!r} of the action {name} is "
                "not an int of 0 or more"
            )
        if not callable(action.run):
            raise TypeError(f"stateful: the run of the action {name} is not callable")
        if action.name in names:
            raise ValueError(
                f"stateful: two actions of the machine have the name {name}"
            )
        names.add(action.name)
