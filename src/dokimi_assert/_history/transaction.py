"""The transactions of a history of list appends. The isolation checks read them.

A transaction is one call of the operation txn. Its arguments are its
micro-operations in the order in which it ran them. An append is
["append", key, value]. A read is ["read", key, None]. An ok completion
commits the transaction. Its output repeats the micro-operations. Each read
in the output has its list, or None for an empty list. A fail completion
aborts the transaction. A value can be appended to its key only once, so a
value identifies the append that produced it. Keys and values compare by
their typed literals.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from dokimi_assert._history.event import Completion, Event, Invocation
from dokimi_assert._history.history import identity_of
from dokimi_assert._record.literal import detail as literal_of

__all__ = [
    "APPEND",
    "READ",
    "TXN",
    "Mop",
    "Transaction",
    "TransactionError",
    "identity",
    "transaction_json",
    "transactions",
]

#: The operation of the call of a transaction.
TXN = "txn"

#: The function of a micro-operation that appends a value to a key.
APPEND: Final = "append"

#: The function of a micro-operation that reads the list of a key.
READ: Final = "read"

#: The function of a micro-operation.
Fn = Literal["append", "read"]


class TransactionError(ValueError):
    """The error for a history that is not a history of list-append transactions."""


@dataclass(frozen=True, slots=True)
class Mop:
    """One micro-operation of a transaction.

    Attributes:
        fn: The function of the micro-operation.
        key: The key.
        value: The appended value of an append. A read has the list that it
            returned, or None when its transaction did not commit.
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
        raise TransactionError(
            f"call {call} has the value {value!r} without a typed literal"
        )
    return found


def _parts(raw: object) -> tuple[Fn, Any, Any] | None:
    """Return the function, the key and the value of a micro-operation.

    The result is None for a value that is not a sequence of three parts
    whose first part is append or read.
    """
    if not isinstance(raw, (list, tuple)) or len(raw) != 3:
        return None
    parts: Sequence[Any] = raw
    fn = parts[0]
    if fn == APPEND:
        return APPEND, parts[1], parts[2]
    if fn == READ:
        return READ, parts[1], parts[2]
    return None


def _invoked(call: int, position: int, raw: object) -> Mop:
    """Return the micro-operation of one argument of an invocation."""
    parts = _parts(raw)
    if parts is None:
        raise TransactionError(
            f"argument {position} of call {call} is {raw!r}, not [append, key, "
            "value] or [read, key, None]"
        )
    fn, key, value = parts
    if fn == READ and value is not None:
        raise TransactionError(
            f"the read at argument {position} of call {call} has a list before it ran"
        )
    identity(call, key)
    if fn == APPEND:
        identity(call, value)
    return Mop(fn, key, None if fn == READ else value)


def _repeated(call: int, position: int, mop: Mop, raw: object) -> Mop:
    """Return the micro-operation of an ok output that repeats mop.

    The micro-operation of a read has the list that the read returned.
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
        raise TransactionError(
            f"micro-operation {position} of the output of call {call} is {raw!r} "
            f"and does not repeat {stated!r}"
        )
    if mop.fn == APPEND:
        return mop
    value = parts[2]
    if value is None:
        return Mop(READ, mop.key, [])
    if not isinstance(value, (list, tuple)):
        raise TransactionError(
            f"the read at micro-operation {position} of the output of call {call} "
            f"returned {value!r}, not a list"
        )
    items: list[Any] = list(value)
    for item in items:
        identity(call, item)
    return Mop(READ, mop.key, items)


def _returned(call: int, mops: Sequence[Mop], output: object) -> tuple[Mop, ...]:
    """Return the micro-operations of an ok output that repeat the invoked ones."""
    if not isinstance(output, (list, tuple)) or len(output) != len(mops):
        raise TransactionError(
            f"the output of call {call} does not repeat the micro-operations of its "
            "invocation"
        )
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
        raise TransactionError(
            f"call {call} is {json.dumps(invocation.operation)}, not {json.dumps(TXN)}"
        )
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


def _register(txn: Transaction, appended: dict[tuple[str, str], int]) -> None:
    """Record each value that txn appends, and refuse a second append of a value."""
    for mop in txn.mops:
        if mop.fn != APPEND:
            continue
        name = (identity(txn.call, mop.key), identity(txn.call, mop.value))
        first = appended.get(name)
        if first == txn.call:
            raise TransactionError(
                f"call {txn.call} appends {mop.value!r} to the key {mop.key!r} twice"
            )
        if first is not None:
            raise TransactionError(
                f"calls {first} and {txn.call} both append {mop.value!r} to the key "
                f"{mop.key!r}"
            )
        appended[name] = txn.call


def transactions(events: Sequence[Event]) -> list[Transaction]:
    """Return the transactions of a history in the order of their invocations.

    Args:
        events: The events of the history.

    Returns:
        The transactions.

    Raises:
        TransactionError: A call is not a list-append transaction, an ok
            output does not repeat the micro-operations of its invocation, a
            key or a value does not have a typed literal, or a value is
            appended to one key twice.
    """
    completions = {e.call: e for e in events if isinstance(e, Completion)}
    appended: dict[tuple[str, str], int] = {}
    found: list[Transaction] = []
    for event in events:
        if not isinstance(event, Invocation):
            continue
        txn = _transaction_of(event, completions.get(event.index))
        _register(txn, appended)
        found.append(txn)
    return found


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
