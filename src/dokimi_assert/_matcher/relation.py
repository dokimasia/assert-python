"""The assertions about properties of a subject across calls.

Each callable can be a coroutine function, and the relation runs the
coroutine on an event loop of the call. A callable that raises fails the
relation. fails_after_close and is_poisoned require an exception instead.
The detail of the failure has the exception in the field of the step that it
ended, and None in the field of a step that did not run.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from typing import Any, TypeVar

from dokimi_assert._matcher.compare import equal as _equal
from dokimi_assert._matcher.errors import matches_target
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.loop import Loop
from dokimi_assert._matcher.option import Option, Relaxations, settings
from dokimi_assert._matcher.seat import Mode, Seat
from dokimi_assert._matcher.verdict import Running, fail, pass_
from dokimi_assert.failure import call_site

__all__ = [
    "REPETITIONS",
    "accumulates",
    "fails_after_close",
    "has_stable_order",
    "is_associative",
    "is_commutative",
    "is_deterministic",
    "is_idempotent",
    "is_monotonic",
    "is_not_pure",
    "is_permutation",
    "is_poisoned",
    "is_total",
    "matched",
    "no_duplicates",
    "round_trip",
]

_T = TypeVar("_T")

#: The number of times that is_deterministic calls its subject,
#: has_stable_order iterates it and is_poisoned reads it. A subject whose
#: results vary can agree with itself by chance in fewer runs.
REPETITIONS = 32


class _Threw:
    """The exception that a step raised.

    Attributes:
        error: The exception.
    """

    def __init__(self, error: Exception) -> None:
        """Return the outcome of a step that raised error."""
        self.error: Exception = error


def _attempt(step: Callable[[], _T]) -> _T | _Threw:
    """Run step, and return its value or the exception that it raised.

    A fault of the event loop propagates, because it is not an exception of
    the subject.
    """
    try:
        return step()
    except FaultError:
        raise
    except Exception as error:
        return _Threw(error)


def _failed_at(index: int, error: Exception) -> dict[str, Any]:
    """Return the detail of a step that raised in a relation of first and second."""
    if index == 0:
        return {"first": error, "second": None}
    return {"first": None, "second": error}


def _settle(
    call: Running,
    mode: Mode,
    assertion: str,
    msg: str,
    first: Callable[[], Any],
    second: Callable[[], Any],
    relax: Relaxations,
) -> None:
    """Run first and then second, and report the first that raises or a difference."""
    __tracebackhide__ = True
    a = _attempt(first)
    if isinstance(a, _Threw):
        call.failed(mode, assertion, msg, _failed_at(0, a.error))
        return
    b = _attempt(second)
    if isinstance(b, _Threw):
        call.failed(mode, assertion, msg, _failed_at(1, b.error))
        return
    if not _equal(b, a, relax):
        call.failed(mode, assertion, msg, {"first": a, "second": b})
        return
    call.passed(mode, assertion, msg)


def _agree(
    call: Running,
    mode: Mode,
    assertion: str,
    msg: str,
    produce: Callable[[], Any],
    relax: Relaxations,
) -> None:
    """Run produce 32 times, and report the first run that raises or differs."""
    __tracebackhide__ = True
    first: Any = None
    for index in range(REPETITIONS):
        outcome = _attempt(produce)
        if isinstance(outcome, _Threw):
            call.failed(mode, assertion, msg, _failed_at(index, outcome.error))
            return
        if index == 0:
            first = outcome
            continue
        if not _equal(outcome, first, relax):
            call.failed(mode, assertion, msg, {"first": first, "second": outcome})
            return
    call.passed(mode, assertion, msg)


def _collect(loop: Loop, iterate: Callable[[], Any]) -> list[Any] | None:
    """Return the elements of one iteration of iterate, or None for a None result.

    iterate returns an iterable, an asynchronous iterable, or an awaitable of
    either.
    """
    source = loop.resolve(iterate())
    if source is None:
        return None
    if hasattr(source, "__aiter__"):

        async def drain() -> list[Any]:
            return [item async for item in source]

        items: list[Any] = loop.resolve(drain())
        return items
    return list(source)


def _faulted(
    call: Running, mode: Mode, assertion: str, msg: str, error: FaultError
) -> None:
    """Report the fault of the event loop of a relation."""
    __tracebackhide__ = True
    call.faulted(mode, assertion, msg, error)


def is_idempotent(
    seat: Seat,
    mode: Mode,
    call: Callable[[Any], Any],
    value: Any,
    observe: Callable[[], Any],
    msg: str,
    *options: Option,
) -> None:
    """Report when a second call of call changes what observe returns after the first.

    first is the observation after one call. second is the observation after
    two calls.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        call: The subject. It receives value.
        value: The input of both calls.
        observe: Returns a copy of the state after a call.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())
    with Loop("idempotent") as loop:

        def step() -> Any:
            loop.resolve(call(value))
            return loop.resolve(observe())

        try:
            _settle(run, mode, "idempotent", msg, step, step, settings(options))
        except FaultError as error:
            _faulted(run, mode, "idempotent", msg, error)


def accumulates(
    seat: Seat,
    mode: Mode,
    call: Callable[[Any], Any],
    value: Any,
    observe: Callable[[], Any],
    msg: str,
) -> None:
    """Report when the calls of call change an observed number by different amounts.

    The relation also fails when the first call leaves the number unchanged.
    first and second are the changes of the first and the second call.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        call: The subject. It receives value.
        value: The input of both calls.
        observe: Returns the number, an int or a float.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())
    readings: list[Any] = []
    with Loop("accumulates") as loop:

        def first_step() -> Any:
            readings.append(loop.resolve(observe()))
            loop.resolve(call(value))
            readings.append(loop.resolve(observe()))
            return readings[1] - readings[0]

        def second_step() -> Any:
            loop.resolve(call(value))
            return loop.resolve(observe()) - readings[1]

        try:
            first = _attempt(first_step)
            if isinstance(first, _Threw):
                run.failed(mode, "accumulates", msg, _failed_at(0, first.error))
                return
            second = _attempt(second_step)
        except FaultError as error:
            _faulted(run, mode, "accumulates", msg, error)
            return
    if isinstance(second, _Threw):
        run.failed(mode, "accumulates", msg, _failed_at(1, second.error))
        return
    if readings[1] == readings[0] or first != second:
        run.failed(mode, "accumulates", msg, {"first": first, "second": second})
        return
    run.passed(mode, "accumulates", msg)


def is_deterministic(
    seat: Seat,
    mode: Mode,
    call: Callable[[Any], Any],
    value: Any,
    msg: str,
    *options: Option,
) -> None:
    """Report when one of 32 calls of call returns a result other than the first.

    first is the first result. second is the first result that differs.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        call: The subject. It receives value.
        value: The input of every call.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())
    with Loop("deterministic") as loop:
        try:
            _agree(
                run,
                mode,
                "deterministic",
                msg,
                lambda: loop.resolve(call(value)),
                settings(options),
            )
        except FaultError as error:
            _faulted(run, mode, "deterministic", msg, error)


def is_commutative(
    seat: Seat,
    mode: Mode,
    combine: Callable[[Any, Any], Any],
    a: Any,
    b: Any,
    msg: str,
    *options: Option,
) -> None:
    """Report when combine(a, b) differs from combine(b, a).

    first is combine(a, b), and second is combine(b, a).

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        combine: The subject.
        a: The first operand.
        b: The second operand.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())
    with Loop("commutative") as loop:
        try:
            _settle(
                run,
                mode,
                "commutative",
                msg,
                lambda: loop.resolve(combine(a, b)),
                lambda: loop.resolve(combine(b, a)),
                settings(options),
            )
        except FaultError as error:
            _faulted(run, mode, "commutative", msg, error)


def is_associative(
    seat: Seat,
    mode: Mode,
    combine: Callable[[Any, Any], Any],
    a: Any,
    b: Any,
    c: Any,
    msg: str,
    *options: Option,
) -> None:
    """Report when combine(combine(a, b), c) differs from combine(a, combine(b, c)).

    first is the left grouping, and second is the right grouping.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        combine: The subject.
        a: The first operand.
        b: The second operand.
        c: The third operand.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())
    with Loop("associative") as loop:

        def left() -> Any:
            return loop.resolve(combine(loop.resolve(combine(a, b)), c))

        def right() -> Any:
            return loop.resolve(combine(a, loop.resolve(combine(b, c))))

        try:
            _settle(run, mode, "associative", msg, left, right, settings(options))
        except FaultError as error:
            _faulted(run, mode, "associative", msg, error)


def round_trip(
    seat: Seat,
    mode: Mode,
    forward: Callable[[Any], Any],
    inverse: Callable[[Any], Any],
    value: Any,
    msg: str,
    *options: Option,
) -> None:
    """Report when inverse of forward of value differs from value.

    want is value, and got is the value that inverse returned. When forward
    or inverse raises, want is None and got is the exception.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        forward: The conversion.
        inverse: The inverse conversion.
        value: The input.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())
    with Loop("round-trip") as loop:
        try:
            back = _attempt(lambda: loop.resolve(inverse(loop.resolve(forward(value)))))
        except FaultError as error:
            _faulted(run, mode, "round-trip", msg, error)
            return
    if isinstance(back, _Threw):
        run.failed(mode, "round-trip", msg, {"want": None, "got": back.error})
        return
    if not _equal(back, value, settings(options)):
        run.failed(mode, "round-trip", msg, {"want": value, "got": back})
        return
    run.passed(mode, "round-trip", msg)


def has_stable_order(
    seat: Seat, mode: Mode, iterate: Callable[[], Any], msg: str, *options: Option
) -> None:
    """Report when one of 32 iterations of iterate yields a different sequence.

    first is the first sequence. second is the first sequence that differs.
    An absent sequence is None.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        iterate: Returns an iterable, an asynchronous iterable, or an
            awaitable of either.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())
    with Loop("stable-order") as loop:
        try:
            _agree(
                run,
                mode,
                "stable-order",
                msg,
                lambda: _collect(loop, iterate),
                settings(options),
            )
        except FaultError as error:
            _faulted(run, mode, "stable-order", msg, error)


def no_duplicates(
    seat: Seat, mode: Mode, iterate: Callable[[], Any], msg: str, *options: Option
) -> None:
    """Report when one iteration of iterate yields an element equal to an earlier one.

    got is the element, and index is its position. Each element is compared
    with every earlier element. When iterate raises, got is the exception and
    index is None.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        iterate: Returns an iterable, an asynchronous iterable, or an
            awaitable of either.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())
    with Loop("no-duplicates") as loop:
        try:
            iterated = _attempt(lambda: _collect(loop, iterate))
        except FaultError as error:
            _faulted(run, mode, "no-duplicates", msg, error)
            return
    if isinstance(iterated, _Threw):
        run.failed(mode, "no-duplicates", msg, {"got": iterated.error, "index": None})
        return
    relax = settings(options)
    items = iterated or []
    for index, item in enumerate(items):
        if any(_equal(item, earlier, relax) for earlier in items[:index]):
            run.failed(mode, "no-duplicates", msg, {"got": item, "index": index})
            return
    run.passed(mode, "no-duplicates", msg)


def _is_nan(value: object) -> bool:
    """Report whether value is a float NaN."""
    return isinstance(value, float) and math.isnan(value)


def is_monotonic(
    seat: Seat,
    mode: Mode,
    observe: Callable[[], Any],
    advance: Callable[[], Any],
    steps: int,
    msg: str,
) -> None:
    """Report when a reading falls below the one before it or is NaN.

    The relation calls observe once. It then calls advance and observe steps
    times. index is the position of the reading that falls or is NaN. The
    reading before the first step is at position 0. first is the reading
    before that reading, or None at position 0. second is the reading at
    index. When advance or observe raises, index and first are None, and
    second is the exception.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        observe: Returns the number.
        advance: Moves the subject one step.
        steps: The number of steps that the subject advances.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())

    def raised(error: Exception) -> None:
        detail = {"index": None, "first": None, "second": error}
        run.failed(mode, "monotonic", msg, detail)

    with Loop("monotonic") as loop:
        try:
            start = _attempt(lambda: loop.resolve(observe()))
            if isinstance(start, _Threw):
                raised(start.error)
                return
            if _is_nan(start):
                detail = {"index": 0, "first": None, "second": start}
                run.failed(mode, "monotonic", msg, detail)
                return
            previous = start

            def step() -> Any:
                loop.resolve(advance())
                return loop.resolve(observe())

            for index in range(1, steps + 1):
                reading = _attempt(step)
                if isinstance(reading, _Threw):
                    raised(reading.error)
                    return
                if _is_nan(reading) or reading < previous:
                    detail = {"index": index, "first": previous, "second": reading}
                    run.failed(mode, "monotonic", msg, detail)
                    return
                previous = reading
        except FaultError as error:
            _faulted(run, mode, "monotonic", msg, error)
            return
    run.passed(mode, "monotonic", msg)


def is_total(
    seat: Seat, mode: Mode, call: Callable[[Any], Any], domain: Iterable[Any], msg: str
) -> None:
    """Report the first element of domain for which call raises.

    index is its position, and got is the exception. An empty domain passes.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        call: The subject. It receives each element.
        domain: The inputs.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())
    with Loop("total") as loop:

        def step(element: Any) -> Callable[[], Any]:
            return lambda: loop.resolve(call(element))

        try:
            for index, element in enumerate(list(domain)):
                outcome = _attempt(step(element))
                if isinstance(outcome, _Threw):
                    run.failed(
                        mode, "total", msg, {"index": index, "got": outcome.error}
                    )
                    return
        except FaultError as error:
            _faulted(run, mode, "total", msg, error)
            return
    run.passed(mode, "total", msg)


def is_not_pure(
    seat: Seat,
    mode: Mode,
    observe: Callable[[], Any],
    fn: Callable[[], Any],
    msg: str,
    *options: Option,
) -> None:
    """Report when fn leaves what observe returns unchanged.

    got is the observation that did not change, or the exception of observe
    or of fn.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        observe: Returns a copy of the state. It runs before and after fn.
        fn: The call that must change what observe returns.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())
    with Loop("not-pure") as loop:

        def readings() -> tuple[Any, Any]:
            before = loop.resolve(observe())
            loop.resolve(fn())
            return before, loop.resolve(observe())

        try:
            outcome = _attempt(readings)
        except FaultError as error:
            _faulted(run, mode, "not-pure", msg, error)
            return
    if isinstance(outcome, _Threw):
        run.failed(mode, "not-pure", msg, {"got": outcome.error})
        return
    before, after = outcome
    if _equal(after, before, settings(options)):
        run.failed(mode, "not-pure", msg, {"got": after})
        return
    run.passed(mode, "not-pure", msg)


def fails_after_close(
    seat: Seat,
    mode: Mode,
    close: Callable[[], Any],
    call: Callable[[], Any],
    sentinel: object,
    msg: str,
) -> None:
    """Report when call does not raise the sentinel after close.

    The sentinel can match any exception in the chain of causes. want is the
    sentinel. got is the exception that call raised, or None when call
    returned. When close raises, want is None and got is the exception.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        close: Closes the subject.
        call: A call of the closed subject.
        sentinel: The exception or the class of exceptions that call must
            raise.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())
    with Loop("after-close") as loop:
        try:
            closed = _attempt(lambda: loop.resolve(close()))
            if isinstance(closed, _Threw):
                run.failed(
                    mode, "after-close", msg, {"want": None, "got": closed.error}
                )
                return
            used = _attempt(lambda: loop.resolve(call()))
        except FaultError as error:
            _faulted(run, mode, "after-close", msg, error)
            return
    if not isinstance(used, _Threw) or not matches_target(used.error, sentinel):
        got = used.error if isinstance(used, _Threw) else None
        run.failed(mode, "after-close", msg, {"want": sentinel, "got": got})
        return
    run.passed(mode, "after-close", msg)


def is_poisoned(
    seat: Seat,
    mode: Mode,
    induce: Callable[[], Any],
    observe: Callable[[], Any],
    msg: str,
) -> None:
    """Report when one of 32 readings of observe returns after induce.

    index is the position of the reading, and got is the value that it
    returned. When induce raises, index is None and got is the exception.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        induce: Induces the failure.
        observe: Reads the subject. It must raise.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    run = Running.of(seat, call_site())
    with Loop("poisoned") as loop:
        try:
            induced = _attempt(lambda: loop.resolve(induce()))
            if isinstance(induced, _Threw):
                run.failed(mode, "poisoned", msg, {"index": None, "got": induced.error})
                return
            for index in range(REPETITIONS):
                reading = _attempt(lambda: loop.resolve(observe()))
                if not isinstance(reading, _Threw):
                    run.failed(mode, "poisoned", msg, {"index": index, "got": reading})
                    return
        except FaultError as error:
            _faulted(run, mode, "poisoned", msg, error)
            return
    run.passed(mode, "poisoned", msg)


def matched(got: Sequence[Any], want: Sequence[Any], relax: Relaxations) -> bool:
    """Report whether each element of got has a partner of its own in want.

    The partners are a matching of the bipartite graph whose edges join equal
    elements. The search for augmenting paths finds the matching when one
    exists. A greedy match is not enough under equate-empty. Under that
    option, None equals both [] and {}, and those two differ.

    Args:
        got: The elements of one side.
        want: The elements of the other side.
        relax: The relaxations in force for the comparison.

    Returns:
        True when the two sides have the same elements with the same counts.
    """
    if len(got) != len(want):
        return False
    edges = [[_equal(g, w, relax) for w in want] for g in got]
    partner = [-1] * len(want)

    def augment(i: int, seen: list[bool]) -> bool:
        for j in range(len(want)):
            if not edges[i][j] or seen[j]:
                continue
            seen[j] = True
            if partner[j] < 0 or augment(partner[j], seen):
                partner[j] = i
                return True
        return False

    return all(augment(i, [False] * len(want)) for i in range(len(got)))


def is_permutation(
    seat: Seat, mode: Mode, got: Any, want: Any, msg: str, *options: Option
) -> None:
    """Report when got and want do not have the same elements with the same counts.

    The order does not matter. The elements are compared by the rules of
    equal. When got or want is not a list or a tuple, the two values are
    compared by the rules of equal.

    Args:
        seat: The seat that receives the failure.
        mode: FATAL to stop the test at a failure, or SOFT to record it.
        got: The sequence that the code under test produced.
        want: The elements that it must contain.
        msg: The contract under test.
        *options: The relaxations of the call.
    """
    __tracebackhide__ = True
    seat.helper()
    relax = settings(options)
    sequences = (list, tuple)
    if isinstance(got, sequences) and isinstance(want, sequences):
        same = matched(got, want, relax)
    else:
        same = _equal(got, want, relax)
    if not same:
        fail(seat, mode, "permutation", msg, {"want": want, "got": got})
        return
    pass_(seat, mode, "permutation", msg)
