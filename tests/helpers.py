"""The helpers, the subjects and the tables that more than one spec uses."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
from collections.abc import Callable
from dataclasses import dataclass
from types import ModuleType
from typing import Any, NoReturn

from dokimi_assert import check
from dokimi_assert._history.history import Call, History
from dokimi_assert._history.spec import Operation
from dokimi_assert._prop.case import Case as BodyCase
from dokimi_assert._prop.case import Location
from dokimi_assert._prop.engine.case import Case, Provider, Replaying
from dokimi_assert._prop.engine.choice import Choice, Value
from dokimi_assert.clock import Controlled
from dokimi_assert.seat import Collector, Recorder

#: The contract that every call of the table FAILING passes.
MSG = "the stated contract"

#: True on Windows. Its file systems do not record permission bits.
WINDOWS = os.name == "nt"

#: True on Windows and for root. The file system then grants this process
#: every permission whatever the mode, so a test of an error that a
#: permission causes cannot run.
UNENFORCED = WINDOWS or os.geteuid() == 0

#: True when the file system reports a name past its length limit as absent.
#: Windows does so. A test of a path that the file system refuses cannot run
#: then.
LONG_NAMES_ABSENT = WINDOWS


def records(seat: Recorder) -> list[dict[str, Any]]:
    """Return the call records of a recorder as decoded JSON.

    Args:
        seat: The recorder.

    Returns:
        One dict per record in the order of their numbers.
    """
    return [json.loads(line) for line in seat.records]


def refusal(
    seat: Collector,
    call: Callable[[], object],
    kind: type[Exception] = ValueError,
) -> str:
    """Return the text of the error that call raises.

    Args:
        seat: The seat of the checks.
        call: The call that refuses its arguments.
        kind: The class of the error.

    Returns:
        The text of the error.
    """
    error = check.raises(seat, call, "the call refuses")
    check.error_as(seat, error, kind, f"the refusal is a {kind.__name__}")
    return str(error)


def no_draw(_: object) -> NoReturn:
    """Raise AssertionError, because the code under test never draws a value."""
    raise AssertionError("the code under test drew a value from its source")


@dataclass(frozen=True)
class Decoding:
    """A generator of the engine whose decode is a function of the case.

    Attributes:
        fn: The function.
    """

    fn: Callable[[Case], Any]

    def decode(self, c: Case) -> Any:
        """Return the value of the function."""
        return self.fn(c)


def integers(*values: int) -> list[Choice]:
    """Return integer choices of values that a case replays."""
    return [Choice("integer", value) for value in values]


def values_of(choices: list[Choice]) -> list[tuple[str, Value]]:
    """Return the kind and the value of each choice."""
    return [(choice.kind, choice.value) for choice in choices]


def replaying(*values: int) -> Replaying:
    """Return the provider that replays integer choices of values."""
    return Replaying(integers(*values))


def body_case(provider: Provider) -> tuple[BodyCase, Case]:
    """Return the case of a body on a recorder, and its engine case.

    The values of the case come from provider.
    """
    engine = Case(provider)
    return BodyCase(engine, Recorder(), None, Location(None)), engine


def run_python(code: str, **env: str) -> subprocess.CompletedProcess[str]:
    """Run code in a child Python process of this environment.

    The child reads the process-wide switches of the library afresh.
    DOKIMI_ASSERT_RECORD is one of them.

    Args:
        code: The program. The function dedents it.
        **env: Variables that the child receives besides the environment of
            this process.

    Returns:
        The completed process. Its output is text.
    """
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        env={**os.environ, **env},
        check=False,
    )


def seated() -> tuple[Recorder, Controlled]:
    """Return a recorder that reads a clock that the test controls, and the clock."""
    clock = Controlled(0)
    return Recorder().with_clock(clock), clock


class Register:
    """The register of the history specs.

    Its one value is None at first. A write leaves its value. A read returns
    the value and leaves it.
    """

    def initial(self) -> object:
        """Return the value before any write."""
        return None

    def next(self, state: object, op: Operation) -> list[object]:
        """Return the value after op, or an empty list for a read of another value."""
        if op.name == "write":
            return [op.args[0]]
        return [state] if op.returned(state) else []


#: The register of the history specs.
REGISTER = Register()


def append(key: object, value: object) -> list[object]:
    """Return a micro-operation of a transaction that appends value to key."""
    return ["append", key, value]


def read_of(key: object, values: object) -> list[object]:
    """Return a micro-operation of a transaction that read values from key."""
    return ["read", key, values]


def invoke_txn(history: History, client: int, *mops: list[object]) -> Call:
    """Invoke a transaction of mops by client.

    Each read of the invocation is without its list. The keys of the call
    are the keys of mops in the order of their first use.
    """
    invoked = [[fn, key, None if fn == "read" else value] for fn, key, value in mops]
    keys: list[object] = []
    for _, key, _ in mops:
        if key not in keys:
            keys.append(key)
    return history.invoke(client, "txn", invoked, *keys)


def run_txn(history: History, client: int, *mops: list[object]) -> None:
    """Record a transaction of mops by client that commits at once and returns mops."""
    invoke_txn(history, client, *mops).ok([list(mop) for mop in mops])


def read_skew(completes: str | None, observed: bool) -> History:
    """Return a read skew in which call 0 reads one of the two appends of call 1.

    Call 0 reads the append to y and misses the append to x. completes is the
    kind of the completion of call 1, ok or unknown. Call 1 does not complete
    when completes is None. When observed is False, call 0 reads y empty, so
    no read observes the appends of call 1.
    """
    history = History()
    reader = invoke_txn(history, 0, read_of("x", None), read_of("y", None))
    writer = invoke_txn(history, 1, append("x", 1), append("y", 2))
    if completes == "ok":
        writer.ok([append("x", 1), append("y", 2)])
    elif completes == "unknown":
        writer.unknown("timed out")
    reader.ok([read_of("x", []), read_of("y", [2] if observed else [])])
    return history


def write_skew() -> History:
    """Return a write skew of calls 0 and 1.

    Each of the two calls reads the key that the other call appends to.
    """
    history = History()
    first = invoke_txn(history, 0, read_of("x", None), append("y", 1))
    second = invoke_txn(history, 1, read_of("y", None), append("x", 2))
    first.ok([read_of("x", []), append("y", 1)])
    second.ok([read_of("y", []), append("x", 2)])
    return history


#: One failing call of an assertion on a surface. The call uses seat and the
#: contract msg. Its arguments use the clock that seat reads.
Failing = Callable[[ModuleType, Recorder, Controlled, str], object]


async def returns_at_once() -> None:
    """Return before any await, so neither a cancellation nor a deadline stops it."""


def boom(*_: object) -> None:
    """Raise ValueError for any arguments."""
    raise ValueError("boom")


def ascending(a: int, b: int) -> bool:
    """Report whether a comes before b."""
    return a < b


def subtract(a: int, b: int) -> int:
    """Return a less b. Subtraction neither commutes nor associates."""
    return a - b


def absolute_text(x: int) -> str:
    """Return the decimal text of the absolute value of x. The text drops a sign."""
    return str(abs(x))


def reads_the_handle(handle: Any) -> Any:
    """Read an attribute of handle without a check."""
    return handle.cancelled()


def passes(_: object) -> None:
    """Pass any check. The body does not assert anything."""


def _eventually(s: ModuleType, seat: Recorder, _: Controlled, msg: str) -> object:
    def never_converges(trial: Any) -> None:
        s.is_true(trial, False, "it converges")

    return s.eventually(seat, 5, 1, never_converges, msg)


def _error_is_not(s: ModuleType, seat: Recorder, _: Controlled, msg: str) -> object:
    error = ValueError("boom")
    return s.error_is_not(seat, error, error, msg)


def _is_pure(s: ModuleType, seat: Recorder, _: Controlled, msg: str) -> object:
    state = [1]
    return s.is_pure(seat, lambda: list(state), lambda: state.append(2), msg)


def _no_task_leaks(s: ModuleType, seat: Recorder, _: Controlled, msg: str) -> object:
    release = threading.Event()
    done = s.no_task_leaks(seat, msg)
    worker = threading.Thread(target=release.wait, name="leaked")
    worker.start()
    try:
        return done()
    finally:
        release.set()
        worker.join()


def _is_idempotent(s: ModuleType, seat: Recorder, _: Controlled, msg: str) -> object:
    state: list[int] = []
    return s.is_idempotent(seat, state.append, 1, lambda: list(state), msg)


def _accumulates(s: ModuleType, seat: Recorder, _: Controlled, msg: str) -> object:
    cell = [0]

    def put(x: int) -> None:
        cell[0] = x

    return s.accumulates(seat, put, 7, lambda: cell[0], msg)


def _is_deterministic(s: ModuleType, seat: Recorder, _: Controlled, msg: str) -> object:
    calls = [0]

    def counts(_: object) -> int:
        calls[0] += 1
        return calls[0]

    return s.is_deterministic(seat, counts, 1, msg)


def _has_stable_order(s: ModuleType, seat: Recorder, _: Controlled, msg: str) -> object:
    items = [1, 2, 3]

    def rotated() -> list[int]:
        items.append(items.pop(0))
        return list(items)

    return s.has_stable_order(seat, rotated, msg)


def _is_monotonic(s: ModuleType, seat: Recorder, _: Controlled, msg: str) -> object:
    count = [0]

    def step() -> None:
        count[0] = (count[0] + 1) % 4

    return s.is_monotonic(seat, lambda: count[0], step, 5, msg)


#: A failing call of each assertion of check and expect, by name.
#:
#: Each entry builds its arguments again for each call. A stateful subject
#: then starts clean. A subject that takes time advances the clock that the
#: seat reads.
FAILING: dict[str, Failing] = {
    "equal": lambda s, seat, _, msg: s.equal(seat, 1, 2, msg),
    "not_equal": lambda s, seat, _, msg: s.not_equal(seat, 1, 1, msg),
    "is_true": lambda s, seat, _, msg: s.is_true(seat, False, msg),
    "is_false": lambda s, seat, _, msg: s.is_false(seat, True, msg),
    "is_none": lambda s, seat, _, msg: s.is_none(seat, 0, msg),
    "is_not_none": lambda s, seat, _, msg: s.is_not_none(seat, None, msg),
    "length": lambda s, seat, _, msg: s.length(seat, [1], 2, msg),
    "is_empty": lambda s, seat, _, msg: s.is_empty(seat, [1], msg),
    "is_not_empty": lambda s, seat, _, msg: s.is_not_empty(seat, [], msg),
    "contains": lambda s, seat, _, msg: s.contains(seat, [1], 2, msg),
    "not_contains": lambda s, seat, _, msg: s.not_contains(seat, [1], 1, msg),
    "contains_in_order": lambda s, seat, _, msg: s.contains_in_order(
        seat, "ab", ["b", "a"], msg
    ),
    "has_prefix": lambda s, seat, _, msg: s.has_prefix(seat, "ab", "b", msg),
    "has_suffix": lambda s, seat, _, msg: s.has_suffix(seat, "ab", "a", msg),
    "matches": lambda s, seat, _, msg: s.matches(seat, "ab", "^b", msg),
    "close_to": lambda s, seat, _, msg: s.close_to(seat, 1.0, 2.0, 0.5, msg),
    "in_range": lambda s, seat, _, msg: s.in_range(seat, 5, 0, 1, msg),
    "pairwise": lambda s, seat, _, msg: s.pairwise(seat, [2, 1], ascending, msg),
    "no_error": lambda s, seat, _, msg: s.no_error(seat, ValueError("boom"), msg),
    "has_error": lambda s, seat, _, msg: s.has_error(seat, None, msg),
    "error_is": lambda s, seat, _, msg: s.error_is(
        seat, ValueError("boom"), KeyError, msg
    ),
    "error_is_not": _error_is_not,
    "error_as": lambda s, seat, _, msg: s.error_as(
        seat, ValueError("boom"), KeyError, msg
    ),
    "raises": lambda s, seat, _, msg: s.raises(seat, lambda: 1, msg),
    "does_not_raise": lambda s, seat, _, msg: s.does_not_raise(seat, boom, msg),
    "honours_cancellation": lambda s, seat, _, msg: s.honours_cancellation(
        seat, returns_at_once, msg
    ),
    "honours_deadline": lambda s, seat, _, msg: s.honours_deadline(
        seat, returns_at_once, msg
    ),
    "completes_within": lambda s, seat, clock, msg: s.completes_within(
        seat, 1.0, lambda: clock.advance(5), msg
    ),
    "none_handle_safe": lambda s, seat, _, msg: s.none_handle_safe(
        seat, reads_the_handle, msg
    ),
    "is_pure": _is_pure,
    "eventually": _eventually,
    "eventually_true": lambda s, seat, _, msg: s.eventually_true(
        seat, 5, lambda: False, msg
    ),
    "no_task_leaks": _no_task_leaks,
    "rejects": lambda s, seat, _, msg: s.rejects(seat, msg, passes),
    "is_idempotent": _is_idempotent,
    "accumulates": _accumulates,
    "is_deterministic": _is_deterministic,
    "is_commutative": lambda s, seat, _, msg: s.is_commutative(
        seat, subtract, 2, 3, msg
    ),
    "is_associative": lambda s, seat, _, msg: s.is_associative(
        seat, subtract, 2, 3, 5, msg
    ),
    "round_trip": lambda s, seat, _, msg: s.round_trip(
        seat, absolute_text, int, -42, msg
    ),
    "has_stable_order": _has_stable_order,
    "no_duplicates": lambda s, seat, _, msg: s.no_duplicates(
        seat, lambda: [1, 2, 2, 3], msg
    ),
    "is_monotonic": _is_monotonic,
    "is_total": lambda s, seat, _, msg: s.is_total(seat, boom, [1, 2, 3], msg),
    "is_not_pure": lambda s, seat, _, msg: s.is_not_pure(
        seat, lambda: 0, lambda: None, msg
    ),
    "fails_after_close": lambda s, seat, _, msg: s.fails_after_close(
        seat, lambda: None, lambda: None, ValueError("closed"), msg
    ),
    "is_poisoned": lambda s, seat, _, msg: s.is_poisoned(
        seat, lambda: None, lambda: None, msg
    ),
    "is_permutation": lambda s, seat, _, msg: s.is_permutation(
        seat, [1, 1, 2], [1, 2, 2], msg
    ),
}
