"""The sequential specification of an object, and the operations that it receives.

A check of a history reads the history against a spec.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Callable, Hashable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, TypeVar

from dokimi_assert._matcher.compare import equal as compare
from dokimi_assert._matcher.option import settings

__all__ = [
    "CallOperation",
    "Operation",
    "Spec",
    "SubjectSpec",
    "same_state",
    "spec_from",
    "state_key",
]

_S = TypeVar("_S")

#: The relaxations of the equality of the library without an option.
_STRICT = settings([])

#: The most levels of a state that state_key walks.
_MAX_DEPTH = 100

#: The subject of spec_from. It applies an operation to its arguments and
#: returns the output.
Subject = Callable[[str, Sequence[Any]], Any]


class Operation(Protocol):
    """A call as a spec receives it.

    A call that is not known might have taken effect with any output, so
    returned reports True for every value of such a call.
    """

    @property
    def name(self) -> str:
        """The operation of the call."""
        ...

    @property
    def args(self) -> tuple[Any, ...]:
        """The arguments of the call."""
        ...

    @property
    def known(self) -> bool:
        """True when the call completed as ok.

        A call whose outcome is unknown and a pending call are not known.
        """
        ...

    @property
    def output(self) -> Any:
        """The value that a known call returned. It is None for any other call."""
        ...

    def returned(self, value: Any) -> bool:
        """Report whether the call might have returned value.

        A call that is not known might have returned any value. For a known
        call, returned reports whether output equals value in the same way as
        check.equal without an option.

        Args:
            value: A value of the state of the spec.

        Returns:
            True when the call might have returned value.
        """
        ...


@dataclass(frozen=True, slots=True)
class CallOperation:
    """The operation of a call as a spec receives it.

    Attributes:
        name: The operation of the call.
        args: The arguments of the call.
        known: True when the call completed as ok.
        output: The value that a known call returned. It is None for any
            other call.
    """

    name: str
    args: tuple[Any, ...]
    known: bool
    output: Any = None

    def returned(self, value: Any) -> bool:
        """Report whether the call might have returned value.

        Args:
            value: A value of the state of the spec.

        Returns:
            True for a call that is not known, and whether output equals
            value for a known call.
        """
        return not self.known or compare(self.output, value, _STRICT)


class Spec(Protocol[_S]):
    """The sequential specification of an object.

    The spec has the state before any call, and the states that an operation
    can leave. A spec can also have two more methods:

    - equal(a, b) reports whether two states are interchangeable. Without
      it, two states compare in the same way as in check.equal without an
      option.
    - key(state) returns a hashable value that every state equal to state
      shares. Without it, the key of a state is a value that every equal
      state without a cycle shares.

    equal must be exact. The search merges two configurations whose states
    equal reports equal. An equality that is coarser than the meaning of the
    spec can then turn a linearizable history into a violated one. Two
    states that equal reports equal must have one key. A key that splits two
    equal states costs the search time. It does not change a verdict.

    next, equal and key must not change their arguments.
    """

    def initial(self) -> _S:
        """Return the state before any call."""
        ...

    def next(self, state: _S, op: Operation) -> Sequence[_S]:
        """Return the states that can follow state when op takes effect.

        The search tries the states in the order of the result. The result
        is empty when the spec rejects op in state. For a call whose outcome
        is unknown, the result is the states that the call leaves when it
        takes effect.

        Args:
            state: The state before the call.
            op: The call.

        Returns:
            The states after the call.
        """
        ...


def _key_at(value: object, depth: int, seen: set[int]) -> Hashable:
    """Return the key of value at a depth of the walk.

    seen contains the ids of the values around value.
    """
    if depth > _MAX_DEPTH:
        return "deep"
    kind = type(value)
    if value is None or isinstance(value, (bool, int, str, bytes)):
        return (kind, value)
    if isinstance(value, float):
        return (kind, "nan") if math.isnan(value) else (kind, value)
    if id(value) in seen:
        return "cycle"
    seen.add(id(value))
    try:
        return _composite_key(value, depth + 1, seen)
    finally:
        seen.discard(id(value))


def _composite_key(value: object, depth: int, seen: set[int]) -> Hashable:
    """Return the key of a value that is not a scalar.

    The key has the type of the value and the parts that the equality of the
    library compares. An object of any other type compares with its own ==,
    so its key is its type alone.
    """
    kind = type(value)
    if isinstance(value, (list, tuple)):
        items: Sequence[object] = value
        return (kind, tuple(_key_at(item, depth, seen) for item in items))
    if isinstance(value, Mapping):
        entries: Mapping[object, object] = value
        return (
            kind,
            frozenset(
                (_key_at(k, depth, seen), _key_at(v, depth, seen))
                for k, v in entries.items()
            ),
        )
    if isinstance(value, (set, frozenset)):
        members: set[object] | frozenset[object] = value
        return (kind, frozenset(_key_at(item, depth, seen) for item in members))
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return (
            kind,
            tuple(
                _key_at(getattr(value, f.name), depth, seen)
                for f in dataclasses.fields(value)
            ),
        )
    return (kind,)


def state_key(state: object) -> Hashable:
    """Return the default key of a state.

    Two states without a cycle that check.equal reports equal have the same
    key.

    Args:
        state: The state.

    Returns:
        The key.
    """
    return _key_at(state, 0, set())


def same_state(a: object, b: object) -> bool:
    """Report whether check.equal without an option reports two states equal.

    Args:
        a: A state.
        b: Another state.

    Returns:
        True when they are equal.
    """
    return compare(a, b, _STRICT)


class SubjectSpec:
    """The spec that a subject defines by its sequential behaviour.

    spec_from returns it. Its state is the tuple of the calls that it has
    applied. Each call is an operation that is not known, with its name and
    its arguments.
    """

    def __init__(self, factory: Callable[[], Subject]) -> None:
        """Return the spec of the subjects that factory returns.

        Args:
            factory: Returns a fresh subject.
        """
        self._factory: Callable[[], Subject] = factory

    def initial(self) -> tuple[Operation, ...]:
        """Return the state before any call. It is the empty tuple."""
        return ()

    def next(
        self, state: tuple[Operation, ...], op: Operation
    ) -> list[tuple[Operation, ...]]:
        """Return the state after op when the subject might have returned its output.

        A fresh subject applies the calls of state in order, and then op.

        Args:
            state: The calls applied so far.
            op: The call.

        Returns:
            The calls with op. The list is empty when op could not have
            returned the output of the subject.
        """
        subject = self._factory()
        for applied in state:
            subject(applied.name, applied.args)
        if not op.returned(subject(op.name, op.args)):
            return []
        return [(*state, CallOperation(op.name, tuple(op.args), False))]

    def equal(self, a: tuple[Operation, ...], b: tuple[Operation, ...]) -> bool:
        """Report whether two states have the same calls in the same order."""
        return len(a) == len(b) and all(
            x.name == y.name and same_state(x.args, y.args)
            for x, y in zip(a, b, strict=True)
        )

    def key(self, state: tuple[Operation, ...]) -> Hashable:
        """Return the key of a state from the name and the arguments of each call."""
        return tuple((op.name, state_key(op.args)) for op in state)

    def cost(self, state: tuple[Operation, ...]) -> int:
        """Return the budget steps that a call of next from state costs.

        A step from a state of d calls applies d + 1 calls.
        """
        return len(state) + 1


def spec_from(factory: Callable[[], Subject]) -> SubjectSpec:
    """Return the spec that a subject defines by its sequential behaviour.

    The state of the spec is the tuple of the calls applied so far. next
    builds a subject with factory, applies the calls of the state in order,
    and then applies the operation. It accepts the operation when
    Operation.returned reports that the call might have returned the output of
    the subject. Two states are equal when they have the same calls in the
    same order. A step from a state of d calls applies d + 1 calls. It costs
    d + 1 steps of the budget. A check against the spec finds a call of a
    history that was not atomic.

    The subject must return the same outputs for the same calls. A subject
    with hidden state returns other outputs on a replay. The check then
    reports a violation that did not happen.

    Args:
        factory: Returns a fresh subject. The subject applies an operation
            to its arguments and returns the output.

    Returns:
        The spec.
    """
    return SubjectSpec(factory)
