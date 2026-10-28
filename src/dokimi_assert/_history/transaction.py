# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The transactions of a history of list appends or of registers.

The isolation checks read them. A transaction is one call of the operation
txn. Its arguments are its micro-operations in the order in which it ran
them. An append is ["append", key, value], a write to a register is
["write", key, value], and a read is ["read", key, None]. A history whose
micro-operations write is a register history, and every other history is a
list-append history. An ok completion commits the transaction. Its output
repeats the micro-operations. Each read in the output of a list-append
history has its list, or None for an empty list. Each read in the output of
a register history has its value, or None for the initial value. A fail
completion aborts the transaction. A value can be appended or written to its
key only once, so a value identifies the micro-operation that produced it.
Keys and values compare by their typed literals.

A read of a register is a read of the list of its one value, or of the
empty list for the initial value, so the checks read both workloads alike.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal

from dokimi_assert._history.event import Completion, Event, Invocation
from dokimi_assert._history.history import identity_of
from dokimi_assert._record.literal import detail as literal_of

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "APPEND",
    "READ",
    "TXN",
    "WRITE",
    "Mop",
    "Transaction",
    "TransactionError",
    "identity",
    "registers",
    "transaction_json",
    "transactions",
]

#: The operation of the call of a transaction.
TXN = "txn"

#: The function of a micro-operation that appends a value to a key.
APPEND: Final = "append"

#: The function of a micro-operation that reads the list or the value of a key.
READ: Final = "read"

#: The function of a micro-operation that writes a value to a register.
WRITE: Final = "write"

#: The function of a micro-operation.
Fn = Literal["append", "read", "write"]


class TransactionError(ValueError):
    """The error for a history that is not a history of transactions.

    A history of transactions is a list-append history or a register history.
    """


@dataclass(frozen=True, slots=True)
class Mop:
    """One micro-operation of a transaction.

    Attributes:
        fn: The function of the micro-operation.
        key: The key.
        value: The appended value of an append, and the written value of a
            write. A read has the list that it returned, or the list of the
            one value of a register, or None when its transaction did not
            commit.
    """

    fn: Fn
    key: Any
    value: Any


@dataclass(frozen=True, slots=True)
class Transaction:
    """One call of a history as a transaction.

    The micro-operations of an ok transaction come from its output. Each of
    its reads has the list that the read returned. The micro-operations of
    any other transaction come from its invocation.

    Attributes:
        call: The index of the invocation event of the call.
        completion: The index of the completion event of the call, or None
            for a pending transaction.
        kind: The kind of the completion of the call, or None for a pending
            transaction.
        process: The process that made the call.
        args: The arguments of the call.
        output: The output of an ok call. It is None for any other call.
        mops: The micro-operations.
    """

    call: int
    completion: int | None
    kind: Literal["ok", "fail", "unknown"] | None
    process: int
    args: tuple[Any, ...]
    output: Any
    mops: tuple[Mop, ...]


def identity(call: int, value: object) -> str:
    """Return the identity of a key or a value of a call.

    Args:
        call: The call whose micro-operations have value.
        value: The value.

    Returns:
        The identity.

    Raises:
        TransactionError: The value does not have a typed literal.
    """
    found = identity_of(value)
    if found is None:
        msg = f"call {call} has the value {value!r} without a typed literal"
        raise TransactionError(msg)
    return found


#: The parts of a micro-operation: the function, the key and the value.
_MOP_PARTS = 3


def _parts(raw: object) -> tuple[Fn, Any, Any] | None:
    """Return the function, the key and the value of a micro-operation.

    The result is None for a value that is not a sequence of three parts
    whose first part is append, read or write.
    """
    if not isinstance(raw, (list, tuple)) or len(raw) != _MOP_PARTS:
        return None
    parts: Sequence[Any] = raw
    fn = parts[0]
    if fn == APPEND:
        return APPEND, parts[1], parts[2]
    if fn == READ:
        return READ, parts[1], parts[2]
    if fn == WRITE:
        return WRITE, parts[1], parts[2]
    return None


def _invoked(call: int, position: int, raw: object) -> Mop:
    """Return the micro-operation of one argument of an invocation."""
    parts = _parts(raw)
    if parts is None:
        msg = (
            f"argument {position} of call {call} is {raw!r}, not [append, key, "
            "value], [write, key, value] or [read, key, None]"
        )
        raise TransactionError(msg)
    fn, key, value = parts
    if fn == READ and value is not None:
        msg = (
            f"the read at argument {position} of call {call} has a value before it ran"
        )
        raise TransactionError(msg)
    if fn == WRITE and value is None:
        msg = (
            f"the write at argument {position} of call {call} writes None, the "
            "initial value of every key"
        )
        raise TransactionError(msg)
    identity(call, key)
    if fn != READ:
        identity(call, value)
    return Mop(fn, key, None if fn == READ else value)


def _repeated(call: int, position: int, mop: Mop, raw: object) -> Mop:
    """Return the micro-operation of an ok output that repeats mop.

    The micro-operation of a read has what the read returned, which the
    workload of the history reads later.
    """
    parts = _parts(raw)
    repeats = (
        parts is not None
        and parts[0] == mop.fn
        and identity_of(parts[1]) == identity(call, mop.key)
        and (mop.fn == READ or identity_of(parts[2]) == identity(call, mop.value))
    )
    if parts is None or not repeats:
        stated = [mop.fn, mop.key, mop.value]
        msg = (
            f"micro-operation {position} of the output of call {call} is {raw!r} "
            f"and does not repeat {stated!r}"
        )
        raise TransactionError(msg)
    if mop.fn != READ:
        return mop
    return Mop(READ, mop.key, parts[2])


def _read_as(txn: Transaction, *, register: bool) -> Transaction:
    """Return an ok transaction with the list of each read.

    A list-append read that returned None returned the empty list. A
    register read returned the list of its one value, or the empty list for
    the initial value.
    """
    if txn.kind != "ok":
        return txn
    mops: list[Mop] = []
    for position, mop in enumerate(txn.mops):
        if mop.fn != READ:
            mops.append(mop)
            continue
        value = mop.value
        if register:
            items: list[Any] = [] if value is None else [value]
        elif value is None:
            items = []
        elif isinstance(value, (list, tuple)):
            items = list(value)
        else:
            msg = (
                f"the read at micro-operation {position} of the output of call "
                f"{txn.call} returned {value!r}, not a list"
            )
            raise TransactionError(msg)
        for item in items:
            identity(txn.call, item)
        mops.append(Mop(READ, mop.key, items))
    return dataclasses.replace(txn, mops=tuple(mops))


def registers(txns: Sequence[Transaction]) -> bool:
    """Report whether a history is a register history: whether it writes.

    Args:
        txns: The transactions of the history.

    Returns:
        True when a micro-operation of the history writes.

    Raises:
        TransactionError: The history both appends and writes.
    """
    first: dict[str, int] = {}
    for txn in txns:
        for mop in txn.mops:
            if mop.fn != READ:
                first.setdefault(mop.fn, txn.call)
    if len(first) > 1:
        msg = (
            f"call {first[APPEND]} appends and call {first[WRITE]} writes, and a "
            "history is either list-append or registers"
        )
        raise TransactionError(msg)
    return WRITE in first


def _returned(call: int, mops: Sequence[Mop], output: object) -> tuple[Mop, ...]:
    """Return the micro-operations of an ok output that repeat the invoked ones."""
    if not isinstance(output, (list, tuple)) or len(output) != len(mops):
        msg = (
            f"the output of call {call} does not repeat the micro-operations of its "
            "invocation"
        )
        raise TransactionError(msg)
    stated: Sequence[Any] = output
    return tuple(
        _repeated(call, position, mop, raw)
        for position, (mop, raw) in enumerate(zip(mops, stated, strict=True))
    )


def _transaction_of(
    invocation: Invocation, completion: Completion | None
) -> Transaction:
    """Return the transaction of one call. completion is None for a pending call."""
    call = invocation.index
    if invocation.operation != TXN:
        msg = (
            f"call {call} is {json.dumps(invocation.operation)}, not {json.dumps(TXN)}"
        )
        raise TransactionError(msg)
    mops = tuple(
        _invoked(call, position, raw) for position, raw in enumerate(invocation.args)
    )
    ok = completion is not None and completion.kind == "ok"
    output = completion.output if completion is not None and ok else None
    return Transaction(
        call,
        None if completion is None else completion.index,
        None if completion is None else completion.kind,
        invocation.process,
        invocation.args,
        output,
        _returned(call, mops, output) if ok else mops,
    )


def _register(txn: Transaction, produced: dict[tuple[str, str], int]) -> None:
    """Record each value that txn appends or writes, and refuse a second one."""
    for mop in txn.mops:
        if mop.fn == READ:
            continue
        verb = "appends" if mop.fn == APPEND else "writes"
        name = (identity(txn.call, mop.key), identity(txn.call, mop.value))
        first = produced.get(name)
        if first == txn.call:
            msg = f"call {txn.call} {verb} {mop.value!r} to the key {mop.key!r} twice"
            raise TransactionError(msg)
        if first is not None:
            both = "both append" if mop.fn == APPEND else "both write"
            msg = (
                f"calls {first} and {txn.call} {both} {mop.value!r} to the key "
                f"{mop.key!r}"
            )
            raise TransactionError(msg)
        produced[name] = txn.call


def transactions(events: Sequence[Event]) -> list[Transaction]:
    """Return the transactions of a history in the order of their invocations.

    Args:
        events: The events of the history.

    Returns:
        The transactions.

    Raises:
        TransactionError: A call is not a transaction, an ok output does not
            repeat the micro-operations of its invocation, a key or a value
            does not have a typed literal, a value is appended or written to
            one key twice, the history both appends and writes, or a
            list-append read returned no list.
    """
    completions = {e.call: e for e in events if isinstance(e, Completion)}
    produced: dict[tuple[str, str], int] = {}
    found: list[Transaction] = []
    for event in events:
        if not isinstance(event, Invocation):
            continue
        txn = _transaction_of(event, completions.get(event.index))
        _register(txn, produced)
        found.append(txn)
    register = registers(found)
    return [_read_as(txn, register=register) for txn in found]


def transaction_json(txn: Transaction) -> dict[str, Any]:
    """Return a transaction in the JSON form of the history.

    The form has the call, the completion and its kind, the process, the
    arguments as typed literals, and the output as a typed literal. A
    pending transaction does not have a completion and a kind. Only an ok
    transaction has an output.

    Args:
        txn: The transaction.

    Returns:
        The JSON value.
    """
    stated: dict[str, Any] = {"call": txn.call}
    if txn.completion is not None:
        stated["completion"] = txn.completion
        stated["kind"] = txn.kind
    stated["process"] = txn.process
    stated["args"] = [literal_of(arg) for arg in txn.args]
    if txn.kind == "ok":
        stated["output"] = literal_of(txn.output)
    return stated
