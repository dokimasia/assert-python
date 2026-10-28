# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _history/transaction.py tests the transactions of a history.

The reference implementation of the definition refuses the same histories.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._history.history import History
from dokimi_assert._history.transaction import (
    APPEND,
    READ,
    TXN,
    WRITE,
    Mop,
    Transaction,
    TransactionError,
    identity,
    registers,
    transaction_json,
    transactions,
)
from helpers import append, invoke_txn, read_of, refusal, run_txn, write

if TYPE_CHECKING:
    from collections.abc import Callable

    from dokimi_assert.seat import Collector


def refused(history: History) -> str:
    """Return the text of the TransactionError that transactions raises for history."""
    with pytest.raises(TransactionError) as raised:
        transactions(history.events())
    return str(raised.value)


def appended_twice(history: History) -> None:
    """Record two calls of client 0 that each append 1 to x."""
    run_txn(history, 0, append("x", 1))
    run_txn(history, 0, append("x", 1))


def written_twice(history: History) -> None:
    """Record two calls of client 0 that each write 1 to x."""
    run_txn(history, 0, write("x", 1))
    run_txn(history, 0, write("x", 1))


def appends_and_writes(history: History) -> None:
    """Record a call that appends 1 to x and a call that writes 2 to y."""
    run_txn(history, 0, append("x", 1))
    run_txn(history, 0, write("y", 2))


class TestNames:
    """TXN, APPEND, READ and WRITE are the operation and the workload functions."""

    def test_has_the_strings_of_the_workload(self, seat: Collector) -> None:
        """The workload uses the strings txn, append, read and write."""
        check.equal(
            seat,
            [TXN, APPEND, READ, WRITE],
            ["txn", "append", "read", "write"],
            "the constants are txn, append, read and write",
        )


class TestRegisters:
    """registers reports whether a history writes."""

    def test_reports_a_history_that_writes(self, seat: Collector) -> None:
        """Call 0 writes 1 to x."""
        history = History()
        run_txn(history, 0, write("x", 1))
        check.is_true(
            seat, registers(transactions(history.events())), "the history writes"
        )

    def test_reports_a_history_that_only_reads(self, seat: Collector) -> None:
        """A read-only history is a list-append history."""
        history = History()
        run_txn(history, 0, read_of("x", None))
        check.is_false(
            seat,
            registers(transactions(history.events())),
            "the history does not write",
        )


class TestTransactionError:
    """TransactionError is the error for calls that are not transactions."""

    def test_is_a_value_error_of_its_text(self, seat: Collector) -> None:
        """The error has the text that it received."""
        error = TransactionError("call 0 is not a transaction")
        check.error_as(seat, error, ValueError, "the error is a ValueError")
        check.equal(
            seat, str(error), "call 0 is not a transaction", "the error keeps its text"
        )


class TestMop:
    """Mop is one micro-operation of a transaction."""

    def test_keeps_its_fields(self, seat: Collector) -> None:
        """The micro-operation appends 1 to x."""
        mop = Mop("append", "x", 1)
        check.equal(
            seat,
            [mop.fn, mop.key, mop.value],
            ["append", "x", 1],
            "the micro-operation keeps its fields",
        )


class TestTransaction:
    """Transaction is one call of a history as a transaction."""

    def test_keeps_its_fields(self, seat: Collector) -> None:
        """The transaction of call 0 is pending."""
        txn = Transaction(0, None, None, 0, (), None, ())
        check.equal(
            seat,
            [txn.call, txn.completion, txn.kind, txn.mops],
            [0, None, None, ()],
            "the transaction keeps its fields",
        )


class TestIdentity:
    """identity returns the identity of a key or a value of a transaction."""

    def test_returns_the_identity_of_a_value(self, seat: Collector) -> None:
        """The identity of x is the JSON text of its typed literal."""
        check.equal(
            seat,
            identity(0, "x"),
            '{"type":"string","value":"x"}',
            "the identity is the JSON of the literal",
        )

    def test_raises_transaction_error_for_a_value_without_a_typed_literal(
        self, seat: Collector
    ) -> None:
        """A class does not have a typed literal."""
        check.equal(
            seat,
            refusal(seat, lambda: identity(3, object), TransactionError),
            "call 3 has the value <class 'object'> without a typed literal",
            "the text of the refusal has the call",
        )


class TestTransactions:
    """transactions returns the transactions of a history in invocation order."""

    def test_returns_the_transactions_in_the_order_of_their_invocations(
        self, seat: Collector
    ) -> None:
        """The aborted call 0 completes after call 1."""
        history = History()
        pending = invoke_txn(history, 0, append("x", 1))
        run_txn(history, 1, read_of("x", []))
        pending.fail("aborted")
        check.equal(
            seat,
            [(t.call, t.completion, t.kind) for t in transactions(history.events())],
            [(0, 3, "fail"), (1, 2, "ok")],
            "call 0 comes before call 1",
        )

    def test_returns_the_micro_operations_of_an_ok_output_with_the_list_of_each_read(
        self, seat: Collector
    ) -> None:
        """Call 0 appends 1 to x and then reads [1]."""
        history = History()
        run_txn(history, 0, append("x", 1), read_of("x", [1]))
        check.equal(
            seat,
            transactions(history.events())[0].mops,
            (Mop("append", "x", 1), Mop("read", "x", [1])),
            "the read has the list that it returned",
        )

    def test_returns_the_invoked_micro_operations_of_a_call_that_did_not_commit(
        self, seat: Collector
    ) -> None:
        """The read ends without an outcome."""
        history = History()
        invoke_txn(history, 0, read_of("x", None)).unknown("timed out")
        check.equal(
            seat,
            transactions(history.events())[0].mops,
            (Mop("read", "x", None),),
            "the read does not have a list",
        )

    def test_reads_a_read_that_returned_none_as_a_read_of_the_empty_list(
        self, seat: Collector
    ) -> None:
        """The output of the read is None."""
        history = History()
        invoke_txn(history, 0, read_of("x", None)).ok([read_of("x", None)])
        check.equal(
            seat,
            transactions(history.events())[0].mops[0].value,
            [],
            "the read has the empty list",
        )

    def test_reads_a_list_of_a_tuple(self, seat: Collector) -> None:
        """The read returned a tuple."""
        history = History()
        invoke_txn(history, 0, read_of("x", None)).ok([read_of("x", (1, 2))])
        check.equal(
            seat,
            transactions(history.events())[0].mops[0].value,
            [1, 2],
            "the read has the list [1, 2]",
        )

    def test_reads_a_register_read_as_the_list_of_its_value(
        self, seat: Collector
    ) -> None:
        """Call 0 writes 1 to x, and call 1 reads 1 and the initial value of y."""
        history = History()
        run_txn(history, 0, write("x", 1))
        run_txn(history, 1, read_of("x", 1), read_of("y", None))
        check.equal(
            seat,
            transactions(history.events())[1].mops,
            (Mop("read", "x", [1]), Mop("read", "y", [])),
            "each read has the list of its value",
        )

    def test_accepts_one_value_appended_to_two_keys(self, seat: Collector) -> None:
        """Call 0 appends 1 to x and to y."""
        history = History()
        run_txn(history, 0, append("x", 1), append("y", 1))
        check.length(
            seat,
            transactions(history.events()),
            1,
            "the history has one transaction",
        )

    tests: ClassVar[list[tuple[str, Callable[[History], object], str]]] = [
        (
            "a call that is not a transaction",
            lambda h: h.invoke(0, "write", [1], "x").ok(None),
            'call 0 is "write", not "txn"',
        ),
        (
            "an argument that is not a micro-operation",
            lambda h: h.invoke(0, TXN, [[APPEND, "x"]], "x"),
            (
                "argument 0 of call 0 is ['append', 'x'], not [append, key, value], "
                "[write, key, value] or [read, key, None]"
            ),
        ),
        (
            "an argument of another function",
            lambda h: h.invoke(0, TXN, [["delete", "x", None]], "x"),
            (
                "argument 0 of call 0 is ['delete', 'x', None], not [append, key, "
                "value], [write, key, value] or [read, key, None]"
            ),
        ),
        (
            "a read that has a value before it ran",
            lambda h: h.invoke(0, TXN, [read_of("x", [1])], "x"),
            "the read at argument 0 of call 0 has a value before it ran",
        ),
        (
            "a write of None",
            lambda h: h.invoke(0, TXN, [write("x", None)], "x"),
            (
                "the write at argument 0 of call 0 writes None, the initial value of "
                "every key"
            ),
        ),
        (
            "a value that two calls write to one key",
            written_twice,
            "calls 0 and 2 both write 1 to the key 'x'",
        ),
        (
            "a value that one call writes to one key twice",
            lambda h: run_txn(h, 0, write("x", 1), write("x", 1)),
            "call 0 writes 1 to the key 'x' twice",
        ),
        (
            "a history that appends and writes",
            appends_and_writes,
            (
                "call 0 appends and call 2 writes, and a history is either list-append "
                "or registers"
            ),
        ),
        (
            "an output that repeats another value",
            lambda h: invoke_txn(h, 0, append("x", 1)).ok([append("x", 2)]),
            (
                "micro-operation 0 of the output of call 0 is ['append', 'x', 2] and "
                "does not repeat ['append', 'x', 1]"
            ),
        ),
        (
            "an output that repeats a read as an append",
            lambda h: invoke_txn(h, 0, read_of("x", None)).ok([append("x", 1)]),
            (
                "micro-operation 0 of the output of call 0 is ['append', 'x', 1] and "
                "does not repeat ['read', 'x', None]"
            ),
        ),
        (
            "an output that is not a micro-operation",
            lambda h: invoke_txn(h, 0, append("x", 1)).ok([7]),
            (
                "micro-operation 0 of the output of call 0 is 7 and does not repeat "
                "['append', 'x', 1]"
            ),
        ),
        (
            "an output of another number of micro-operations",
            lambda h: invoke_txn(h, 0, append("x", 1)).ok(
                [append("x", 1), read_of("x", [1])]
            ),
            (
                "the output of call 0 does not repeat the micro-operations of its "
                "invocation"
            ),
        ),
        (
            "an output that is not a list",
            lambda h: invoke_txn(h, 0, append("x", 1)).ok(7),
            (
                "the output of call 0 does not repeat the micro-operations of its "
                "invocation"
            ),
        ),
        (
            "a read that did not return a list",
            lambda h: invoke_txn(h, 0, read_of("x", None)).ok([read_of("x", 5)]),
            (
                "the read at micro-operation 0 of the output of call 0 returned 5, "
                "not a list"
            ),
        ),
        (
            "a value that two calls append to one key",
            appended_twice,
            "calls 0 and 2 both append 1 to the key 'x'",
        ),
        (
            "a value that one call appends to one key twice",
            lambda h: run_txn(h, 0, append("x", 1), append("x", 1)),
            "call 0 appends 1 to the key 'x' twice",
        ),
        (
            "a key without a typed literal",
            lambda h: h.invoke(0, TXN, [read_of(object, None)]),
            "call 0 has the value <class 'object'> without a typed literal",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_transaction_error_for(
        self, seat: Collector, give: Callable[[History], object], want: str
    ) -> None:
        """The function refuses the history before it returns a transaction."""
        history = History()
        give(history)
        check.equal(seat, refused(history), want, "the refusal has the expected text")


class TestTransactionJson:
    """transaction_json returns a transaction in the JSON form of the history."""

    def test_returns_an_ok_transaction_with_its_output(self, seat: Collector) -> None:
        """Call 0 reads [9]."""
        history = History()
        run_txn(history, 0, read_of("x", [9]))
        txn = transactions(history.events())[0]
        check.equal(
            seat,
            transaction_json(txn),
            {
                "call": 0,
                "completion": 1,
                "kind": "ok",
                "process": 0,
                "args": [
                    {
                        "type": "list",
                        "items": [
                            {"type": "string", "value": "read"},
                            {"type": "string", "value": "x"},
                            {"type": "null"},
                        ],
                    }
                ],
                "output": {
                    "type": "list",
                    "items": [
                        {
                            "type": "list",
                            "items": [
                                {"type": "string", "value": "read"},
                                {"type": "string", "value": "x"},
                                {"type": "list", "of": "int", "value": [9]},
                            ],
                        }
                    ],
                },
            },
            "the JSON has the completion, the kind and the output",
        )

    def test_returns_a_pending_transaction_without_a_completion(
        self, seat: Collector
    ) -> None:
        """The append does not complete."""
        history = History()
        invoke_txn(history, 0, append("x", 1))
        txn = transactions(history.events())[0]
        check.equal(
            seat,
            list(transaction_json(txn)),
            ["call", "process", "args"],
            "the JSON has only the keys of the invocation",
        )

    def test_returns_a_failed_transaction_without_an_output(
        self, seat: Collector
    ) -> None:
        """The append aborts."""
        history = History()
        invoke_txn(history, 0, append("x", 1)).fail("aborted")
        txn = transactions(history.events())[0]
        check.equal(
            seat,
            list(transaction_json(txn)),
            ["call", "completion", "kind", "process", "args"],
            "the JSON has the kind and not an output",
        )
