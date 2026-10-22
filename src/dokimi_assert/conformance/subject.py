# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The behaviours that a corpus case passes in place of a callable.

A case has its arguments as typed literals, and a typed literal cannot be a
callable. A case of an assertion that takes a callable has the kind of a
behaviour of a fixed set instead. This module builds each behaviour.
"""

from __future__ import annotations

import asyncio
import os
import pathlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dokimi_assert._files.literal import CONTENT_LIMIT
from dokimi_assert.conformance.literal import RefInt

__all__ = ["SUBJECTS", "Subject", "SubjectError"]

#: The mode with which a subject creates a file.
_NEW_FILE_MODE = 0o644


class SubjectError(Exception):
    """The exception of a subject that fails for a reason of its own."""


#: The exception that a closed subject of fails_after_close raises.
_CLOSED = SubjectError("the subject is closed")


@dataclass(frozen=True)
class Subject:
    """One built behaviour with a function for each shape that an assertion calls.

    A shape that the behaviour does not have is None.

    Attributes:
        handled: The coroutine function of the cancellation assertions, or the
            callable to which none_handle_safe passes None.
        bare: The call of raises and does_not_raise. It raises or returns.
        seated: The body that eventually runs.
        call: The operation of an input. It changes the number that observe
            returns, or raises.
        observe: Returns the number that call and advance change.
        input: The input that an assertion passes to call, compute and
            render.
        compute: The computation that is_deterministic calls.
        combine: The operation with which is_commutative and is_associative
            combine their operands.
        operands: The operands a, b and c of combine.
        render: Renders an input as decimal text. round_trip parses the text.
        iterate: Returns one iteration of the sequence of has_stable_order and
            no_duplicates.
        advance: Moves the number that is_monotonic reads through observe.
        steps: The number of calls of advance by is_monotonic.
        domain: The inputs of is_total.
        close: Closes the subject of fails_after_close.
        use: The call that fails_after_close makes after close.
        sentinel: The exception that use raises after the subject is closed.
        induce: Induces the failure that is_poisoned reads through read.
        read: One reading of the subject of is_poisoned.
        files: Reads or writes the files of the tree in a directory. It is the
            callable of files.unchanged.
    """

    handled: Callable[..., Any] | None = None
    bare: Callable[[], Any] | None = None
    seated: Callable[[Any], None] | None = None
    call: Callable[[Any], Any] | None = None
    observe: Callable[[], Any] | None = None
    input: Any = None
    compute: Callable[[Any], Any] | None = None
    combine: Callable[[Any, Any], Any] | None = None
    operands: tuple[Any, Any, Any] | None = None
    render: Callable[[Any], str] | None = None
    iterate: Callable[[], list[Any]] | None = None
    advance: Callable[[], None] | None = None
    steps: int = 0
    domain: tuple[Any, ...] = ()
    close: Callable[[], None] | None = None
    use: Callable[[], Any] | None = None
    sentinel: Any = None
    induce: Callable[[], None] | None = None
    read: Callable[[], Any] | None = None
    files: Callable[[str], None] | None = None


def _returns_ok() -> Subject:
    """Return a subject whose every shape succeeds.

    Its input is 1, and its domain is 1, 2 and 3.
    """

    async def handled(*_: Any) -> str:
        return "did the work"

    return Subject(
        handled=handled,
        bare=lambda: None,
        call=lambda _: None,
        input=1,
        compute=lambda x: x,
        domain=(1, 2, 3),
    )


def _reads_handle() -> Subject:
    """Return a subject that awaits, so a cancellation stops it at its await."""

    async def handled(*_: Any) -> str:
        await asyncio.sleep(0)
        return "did the work"

    return Subject(handled=handled)


def _ignores_handle() -> Subject:
    """Return a subject that succeeds and does not await."""

    async def handled(*_: Any) -> str:
        return "did the work"

    return Subject(handled=handled)


def _raises() -> Subject:
    """Return a subject that raises and does not return."""

    def bare() -> Any:
        msg = "the subject raised"
        raise SubjectError(msg)

    return Subject(bare=bare)


def _fails_otherwise() -> Subject:
    """Return a subject that fails for a reason of its own.

    Its domain is 1, 2 and 3.
    """

    def fails(*_: Any) -> Any:
        msg = "the subject failed for its own reason"
        raise SubjectError(msg)

    async def handled(*_: Any) -> Any:
        return fails()

    return Subject(handled=handled, call=fails, domain=(1, 2, 3))


def _dereferences_handle() -> Subject:
    """Return a subject that reads an attribute of its handle without a check."""

    def handled(handle: Any = None) -> Any:
        return handle.cancelled()

    return Subject(handled=handled)


def _never_settles() -> Subject:
    """Return a subject that fails on every attempt and every reading.

    Its induce does not change anything.
    """

    def read() -> Any:
        msg = "never settles"
        raise SubjectError(msg)

    return Subject(
        seated=lambda trial: trial.record("never settles"),
        induce=lambda: None,
        read=read,
    )


#: The attempt at which the subject of _settles_after succeeds.
_SETTLING_ATTEMPT = 3


def _settles_after() -> Subject:
    """Return a subject that fails twice and succeeds at the third attempt or reading.

    Its induce does not change anything.
    """
    attempts = [0]

    def settled() -> bool:
        attempts[0] += 1
        return attempts[0] >= _SETTLING_ATTEMPT

    def seated(trial: Any) -> None:
        if not settled():
            trial.record("not yet")

    def read() -> None:
        if not settled():
            msg = "not yet"
            raise SubjectError(msg)

    return Subject(seated=seated, induce=lambda: None, read=read)


def _counter(step: int) -> Subject:
    """Return a subject whose number starts at 0 and rises by step on each call.

    The calls ignore their input. The subject advances 5 steps.
    """
    count = [0]

    def rise(*_: Any) -> None:
        count[0] += step

    return Subject(call=rise, advance=rise, steps=5, observe=lambda: count[0])


def _sets_value() -> Subject:
    """Return a cell that starts at 0. A call sets the cell to its input 7."""
    cell = [0]

    def call(value: Any) -> None:
        cell[0] = value

    return Subject(call=call, input=7, observe=lambda: cell[0])


def _counts_calls() -> Subject:
    """Return a computation that returns the number of its runs.

    The input is 1.
    """
    calls = [0]

    def compute(_: Any) -> int:
        calls[0] += 1
        return calls[0]

    return Subject(compute=compute, input=1)


def _combines(op: Callable[[int, int], int]) -> Subject:
    """Return a subject that combines two ints with op.

    Its operands are 2, 3 and 5.
    """
    return Subject(combine=op, operands=(2, 3, 5))


def _renders(drop_sign: bool) -> Subject:
    """Return a subject that renders an int or its absolute value as decimal text.

    The input is -42.
    """
    return Subject(input=-42, render=lambda x: str(abs(x) if drop_sign else x))


def _yields(*items: Any) -> Subject:
    """Return a subject that yields items on every iteration."""
    return Subject(iterate=lambda: list(items))


def _rotates() -> Subject:
    """Return a subject that yields 1 to 5 and rotates them by one place each time."""
    items = [1, 2, 3, 4, 5]

    def iterate() -> list[Any]:
        out = list(items)
        items.append(items.pop(0))
        return out

    return Subject(iterate=iterate)


def _wraps_around() -> Subject:
    """Return a number that starts at 0, rises by one per advance and wraps after 3.

    The subject advances 5 steps.
    """
    count = [0]

    def advance() -> None:
        count[0] = (count[0] + 1) % 4

    return Subject(observe=lambda: count[0], advance=advance, steps=5)


def _closes(refuses: bool) -> Subject:
    """Return a subject whose calls succeed until it closes.

    After the close, a subject that refuses raises its sentinel on every
    call. A subject that does not refuse still succeeds.
    """
    closed = [False]

    def close() -> None:
        closed[0] = True

    def use() -> None:
        if closed[0] and refuses:
            raise _CLOSED

    return Subject(close=close, use=use, sentinel=_CLOSED)


def _one_object_twice() -> Subject:
    """Return a subject that yields one object of the value 1 twice."""
    one = RefInt(1)
    return _yields(one, one)


def _each_file(directory: str, fn: Callable[[pathlib.Path], object]) -> None:
    """Call fn with the path of each file of the tree in directory.

    Links are skipped.
    """
    for root, _, names in os.walk(directory):
        for name in names:
            path = pathlib.Path(root, name)
            # Path.is_file raises an error of the file system before Python
            # 3.14, and os.path.isfile returns False.
            if os.path.isfile(path) and not os.path.islink(path):  # noqa: PTH113, PTH114
                fn(path)


def _read_file(path: pathlib.Path) -> bytes:
    """Return the bytes of the file at path."""
    return path.read_bytes()


def _write_file(path: pathlib.Path, content: bytes) -> None:
    """Write content into the file at path. An existing file keeps its mode."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _NEW_FILE_MODE)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(content)


def _leaves_files_alone() -> Subject:
    """Return a subject that reads every file of a tree and does not write."""
    return Subject(files=lambda directory: _each_file(directory, _read_file))


def _rewrites_files() -> Subject:
    """Return a subject that writes every file of a tree again, with its bytes."""
    return Subject(
        files=lambda directory: _each_file(
            directory, lambda path: _write_file(path, _read_file(path))
        )
    )


def _writes_file(name: str, content: bytes) -> Subject:
    """Return a subject that writes content into the file name at the root of a tree."""
    return Subject(
        files=lambda directory: _write_file(pathlib.Path(directory, name), content)
    )


#: The builder of each behaviour by kind. This language cannot build a kind
#: that is absent here, and the case of such a kind fails.
SUBJECTS: dict[str, Callable[[], Subject]] = {
    "returns-ok": _returns_ok,
    "reads-handle": _reads_handle,
    "ignores-handle": _ignores_handle,
    "raises": _raises,
    "fails-otherwise": _fails_otherwise,
    "dereferences-handle": _dereferences_handle,
    "never-settles": _never_settles,
    "settles-after": _settles_after,
    "accumulates": lambda: _counter(1),
    "leaves-state-alone": lambda: _counter(0),
    "sets-value": _sets_value,
    "counts-calls": _counts_calls,
    "adds": lambda: _combines(lambda a, b: a + b),
    "subtracts": lambda: _combines(lambda a, b: a - b),
    "renders-decimal": lambda: _renders(False),
    "drops-the-sign": lambda: _renders(True),
    "yields-in-order": lambda: _yields(1, 2, 3, 4, 5),
    "rotates": _rotates,
    "repeats-an-element": lambda: _yields(1, 2, 2, 3),
    "wraps-around": _wraps_around,
    "refuses-after-close": lambda: _closes(True),
    "serves-after-close": lambda: _closes(False),
    "yields-one-object-twice": _one_object_twice,
    "yields-two-equal-objects": lambda: _yields(RefInt(1), RefInt(1)),
    "leaves-files-alone": _leaves_files_alone,
    "rewrites-files": _rewrites_files,
    "writes-a-file": lambda: _writes_file("new.txt", b"new"),
    # The content is one byte longer than a record contains in full.
    "writes-a-large-file": lambda: _writes_file(
        "large.bin", b"a" * (CONTENT_LIMIT + 1)
    ),
}
