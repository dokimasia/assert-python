# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The named specs of the definition.

A history vector has the name of a named spec in place of a spec of its
own. A state is a decoded value. The state of the register is its value, the
state of the key-value map is a dict with its keys in the order of their
first put, and the state of the queue and of the set is a tuple of the
values in order. Two values compare by their canonical texts.

Every spec accepts a call whose outcome is unknown in every state. It does
not check the output of a write, a put, an append, an enqueue or an add. It
raises ValueError for an operation that it does not define, and the check
reports the error as a fault. The key-value map and the set compare two
states whose entries are equal in any order.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dokimi_assert.conformance.literal import canonical
from dokimi_assert.history import Operation

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["SPECS", "NamedSpec"]

#: The value of a key that the key-value map does not have.
_EMPTY = ""


def _same(a: object, b: object) -> bool:
    """Report whether two decoded values have one canonical text."""
    return canonical(a) == canonical(b)


def _undefined(name: str, op: Operation) -> ValueError:
    """Return the error of an operation that the spec of a name does not define."""
    return ValueError(
        f"conformance: the {name} spec does not have the operation "
        f"{json.dumps(op.name)}"
    )


def _read(state: Any, op: Operation, name: str) -> list[Any]:
    """Step the read of a register. A read returns the state and does not change it.

    Raises:
        ValueError: The operation is not a read.
    """
    if op.name != "read":
        raise _undefined(name, op)
    return [state] if not op.known or _same(op.output, state) else []


def _register(state: Any, op: Operation) -> list[Any]:
    """Step the register. A write stores its value, and a read returns it."""
    if op.name == "write":
        return [op.args[0]]
    return _read(state, op, "register")


def _cas_register(state: Any, op: Operation) -> list[Any]:
    """Step the register with compare-and-set.

    cas(from, to) returns whether the state equals from, and stores to when
    it does. A cas whose outcome is unknown takes effect when the state
    equals from, and does not change the state otherwise.
    """
    if op.name == "write":
        return _register(state, op)
    if op.name != "cas":
        return _read(state, op, "cas-register")
    matches = _same(state, op.args[0])
    if op.known and op.output is not matches:
        return []
    return [op.args[1] if matches else state]


def _lossy_register(state: Any, op: Operation) -> list[Any]:
    """Step the register whose write can be lost.

    A write leaves the new value or the old value.
    """
    if op.name == "write":
        return [op.args[0], state]
    return _read(state, op, "lossy-register")


def _lookup(state: dict[Any, Any], key: object) -> Any:
    """Return the value of a key in a key-value state, or the empty value."""
    return next(
        (value for stored, value in state.items() if _same(stored, key)), _EMPTY
    )


def _with_value(state: dict[Any, Any], key: object, value: Any) -> dict[Any, Any]:
    """Return a key-value state with value under key.

    The entry of a stored key keeps its place, and a new key comes last. The
    state does not have an empty value, so two states are equal exactly when
    every key has the same value in both.
    """
    entries = list(state.items())
    at = next((i for i, (stored, _) in enumerate(entries) if _same(stored, key)), None)
    if at is None:
        if value != _EMPTY:
            entries.append((key, value))
    elif value == _EMPTY:
        del entries[at]
    else:
        entries[at] = (key, value)
    return dict(entries)


def _key_value(state: dict[Any, Any], op: Operation) -> list[Any]:
    """Step the map from keys to strings.

    get returns the value of a key, put stores a value under a key, and
    append extends the value of a key.

    Raises:
        ValueError: The operation is not get, put or append.
    """
    key = op.args[0] if op.args else None
    current = _lookup(state, key)
    if op.name == "get":
        return [state] if not op.known or _same(op.output, current) else []
    if op.name == "put":
        return [_with_value(state, key, op.args[1])]
    if op.name == "append":
        return [_with_value(state, key, f"{current}{op.args[1]}")]
    name = "key-value"
    raise _undefined(name, op)


def _queue(state: tuple[Any, ...], op: Operation) -> list[Any]:
    """Step the queue.

    enqueue adds a value at the tail. dequeue returns the head and removes
    it, or returns None for an empty queue.

    Raises:
        ValueError: The operation is not enqueue or dequeue.
    """
    if op.name == "enqueue":
        return [(*state, op.args[0])]
    if op.name != "dequeue":
        name = "queue"
        raise _undefined(name, op)
    if not state:
        return [state] if not op.known or op.output is None else []
    return [state[1:]] if not op.known or _same(op.output, state[0]) else []


def _set(state: tuple[Any, ...], op: Operation) -> list[Any]:
    """Step the set, which has its values in the order of their addition.

    add adds a value that the set does not have. remove and contains return
    whether the set has a value. A remove whose outcome is unknown removes
    the value when the set has it.

    Raises:
        ValueError: The operation is not add, remove or contains.
    """
    value = op.args[0] if op.args else None
    present = any(_same(item, value) for item in state)
    if op.name == "add":
        return [state if present else (*state, value)]
    if op.name == "contains":
        return [state] if not op.known or op.output is present else []
    if op.name != "remove":
        name = "set"
        raise _undefined(name, op)
    if op.known and op.output is not present:
        return []
    return [tuple(item for item in state if not _same(item, value))]


def _unordered(state: Sequence[Any]) -> str:
    """Return the sorted canonical texts of the items of a state, joined.

    Two states of equal items share the text in any order.
    """
    return ",".join(sorted(canonical(item) for item in state))


@dataclass(frozen=True, slots=True)
class NamedSpec:
    """A named spec of the definition.

    Attributes:
        start: Returns the state before any call.
        step: Returns the states that an operation can leave.
        text: Returns a text that two equal states share and two other
            states do not.
    """

    start: Callable[[], Any]
    step: Callable[[Any, Operation], list[Any]]
    text: Callable[[Any], str] = canonical

    def initial(self) -> Any:
        """Return the state before any call.

        Returns:
            The state.
        """
        return self.start()

    def next(self, state: Any, op: Operation) -> list[Any]:
        """Return the states that op can leave after state.

        Args:
            state: The state before the call.
            op: The operation of the call.

        Returns:
            The states. A call that the spec does not accept leaves none.

        Raises:
            ValueError: The spec does not define the operation of op.
        """
        return self.step(state, op)

    def equal(self, a: Any, b: Any) -> bool:
        """Report whether two states have one text.

        Args:
            a: A state.
            b: Another state.

        Returns:
            True for two states of one text.
        """
        return self.text(a) == self.text(b)

    def key(self, state: Any) -> str:
        """Return the text of a state.

        Args:
            state: The state.

        Returns:
            The text. Two equal states share it.
        """
        return self.text(state)


#: The named specs of the definition, by name.
SPECS: dict[str, NamedSpec] = {
    "register": NamedSpec(lambda: None, _register),
    "cas-register": NamedSpec(lambda: None, _cas_register),
    "key-value": NamedSpec(
        dict, _key_value, lambda state: _unordered(list(state.items()))
    ),
    "queue": NamedSpec(tuple, _queue),
    "set": NamedSpec(tuple, _set, _unordered),
    "lossy-register": NamedSpec(lambda: None, _lossy_register),
}
