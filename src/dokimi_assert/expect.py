"""The assertions that record a failure and let the test continue.

The seat fixture raises every recorded failure when the test body ends, so
one run reports every property of a value that failed.

    from dokimi_assert import expect

    def test_reply(seat):
        expect.equal(seat, reply.status, 200, "the request succeeds")
        expect.contains(seat, reply.headers, "etag", "the reply is cacheable")

dokimi_assert.check has the same assertions under the same names and runs
the same comparisons. Only what happens on a failure differs. The
docstrings of check describe the rules of each assertion in full.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable, Sequence
from typing import Any, TypeVar

from dokimi_assert import rejects as _rejects
from dokimi_assert._matcher import behaviour, errors, order, relation, value, waiting
from dokimi_assert._matcher import raises as _raises
from dokimi_assert._matcher.option import Option
from dokimi_assert._matcher.seat import Mode, Seat
from dokimi_assert.failure import Failure

_E = TypeVar("_E", bound=BaseException)

__all__ = [
    "accumulates",
    "close_to",
    "completes_within",
    "contains",
    "contains_in_order",
    "does_not_raise",
    "equal",
    "error_as",
    "error_is",
    "error_is_not",
    "eventually",
    "eventually_true",
    "fails_after_close",
    "has_error",
    "has_prefix",
    "has_stable_order",
    "has_suffix",
    "honours_cancellation",
    "honours_deadline",
    "in_range",
    "is_associative",
    "is_commutative",
    "is_deterministic",
    "is_empty",
    "is_false",
    "is_idempotent",
    "is_monotonic",
    "is_none",
    "is_not_empty",
    "is_not_none",
    "is_not_pure",
    "is_permutation",
    "is_poisoned",
    "is_pure",
    "is_total",
    "is_true",
    "length",
    "matches",
    "no_duplicates",
    "no_error",
    "no_task_leaks",
    "none_handle_safe",
    "not_contains",
    "not_equal",
    "pairwise",
    "raises",
    "rejects",
    "round_trip",
]

_MODE = Mode.SOFT


def equal(seat: Seat, got: Any, want: Any, msg: str, *options: Option) -> None:
    """Record a failure when got and want differ.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The value that the code under test produced.
        want: The value that it is supposed to produce.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.equal(seat, store.get(key), item, "get returns the stored item")
    """
    __tracebackhide__ = True
    seat.helper()
    value.equal(seat, _MODE, got, want, msg, *options)


def not_equal(seat: Seat, got: Any, want: Any, msg: str, *options: Option) -> None:
    """Record a failure when got and want are equal by the rules of equal.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The value that the code under test produced.
        want: The value that it must not equal.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.not_equal(seat, token, previous, "a refresh issues a new token")
    """
    __tracebackhide__ = True
    seat.helper()
    value.not_equal(seat, _MODE, got, want, msg, *options)


def is_true(seat: Seat, condition: object, msg: str) -> None:
    """Record a failure when the condition is not true.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        condition: The condition.
        msg: The contract under test.

    Example:
        expect.is_true(seat, user.is_active, "a new user starts active")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_true(seat, _MODE, condition, msg)


def is_false(seat: Seat, condition: object, msg: str) -> None:
    """Record a failure when the condition is true.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        condition: The condition.
        msg: The contract under test.

    Example:
        expect.is_false(seat, cache.is_stale(), "a fresh read is not stale")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_false(seat, _MODE, condition, msg)


def is_none(seat: Seat, got: Any, msg: str) -> None:
    """Record a failure when got is not None.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The value that must be absent.
        msg: The contract under test.

    Example:
        expect.is_none(seat, validate(name), "a good name is accepted")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_none(seat, _MODE, got, msg)


def is_not_none(seat: Seat, got: Any, msg: str) -> None:
    """Record a failure when got is None.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The value that must be present.
        msg: The contract under test.

    Example:
        expect.is_not_none(seat, store.get(key), "get returns the stored item")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_not_none(seat, _MODE, got, msg)


def length(seat: Seat, got: Any, want: int, msg: str) -> None:
    """Record a failure when got does not have want items.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The container.
        want: The number of items that it must have.
        msg: The contract under test.

    Example:
        expect.length(seat, reply.items, 3, "every item comes back")
    """
    __tracebackhide__ = True
    seat.helper()
    value.length(seat, _MODE, got, want, msg)


def is_empty(seat: Seat, got: Any, msg: str) -> None:
    """Record a failure when got has an item or does not have a length.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The container that must be empty.
        msg: The contract under test.

    Example:
        expect.is_empty(seat, reply.errors, "a valid request has no errors")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_empty(seat, _MODE, got, msg)


def is_not_empty(seat: Seat, got: Any, msg: str) -> None:
    """Record a failure when got is empty or does not have a length.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The container that must have an item.
        msg: The contract under test.

    Example:
        expect.is_not_empty(seat, results, "the search finds something")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_not_empty(seat, _MODE, got, msg)


def contains(
    seat: Seat, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Record a failure when haystack does not contain needle.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        haystack: The text or the collection.
        needle: The substring, the element or the key.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.contains(seat, reply.headers, "etag", "the reply is cacheable")
    """
    __tracebackhide__ = True
    seat.helper()
    value.contains(seat, _MODE, haystack, needle, msg, *options)


def not_contains(
    seat: Seat, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Record a failure when haystack contains needle.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        haystack: The text or the collection.
        needle: The substring, the element or the key that must be absent.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.not_contains(seat, body, "password", "no secret leaks")
    """
    __tracebackhide__ = True
    seat.helper()
    value.not_contains(seat, _MODE, haystack, needle, msg, *options)


def contains_in_order(seat: Seat, got: Any, needles: Sequence[str], msg: str) -> None:
    """Record a failure when got does not contain the needles in order.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The text.
        needles: The substrings in the order in which they must appear.
        msg: The contract under test.

    Example:
        expect.contains_in_order(seat, log, ["open", "close"], "it closes last")
    """
    __tracebackhide__ = True
    seat.helper()
    value.contains_in_order(seat, _MODE, got, needles, msg)


def has_prefix(seat: Seat, got: Any, prefix: str, msg: str) -> None:
    """Record a failure when got is not a str that starts with prefix.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The text.
        prefix: The text that got must start with.
        msg: The contract under test.

    Example:
        expect.has_prefix(seat, request_id, "req_", "the id has its prefix")
    """
    __tracebackhide__ = True
    seat.helper()
    value.has_prefix(seat, _MODE, got, prefix, msg)


def has_suffix(seat: Seat, got: Any, suffix: str, msg: str) -> None:
    """Record a failure when got is not a str that ends with suffix.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The text.
        suffix: The text that got must end with.
        msg: The contract under test.

    Example:
        expect.has_suffix(seat, path, ".json", "the export is JSON")
    """
    __tracebackhide__ = True
    seat.helper()
    value.has_suffix(seat, _MODE, got, suffix, msg)


def matches(seat: Seat, got: Any, pattern: str, msg: str) -> None:
    """Record a failure when got is not a str that a pattern of the subset matches.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The text.
        pattern: A pattern of the portable subset.
        msg: The contract under test.

    Example:
        expect.matches(seat, rid, r"^req_[0-9a-f]{16}$", "the id is well formed")
    """
    __tracebackhide__ = True
    seat.helper()
    value.matches(seat, _MODE, got, pattern, msg)


def close_to(seat: Seat, got: Any, want: float, tolerance: float, msg: str) -> None:
    """Record a failure when got is not a number within tolerance of want.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The number.
        want: The number that got must be near.
        tolerance: The largest absolute difference that passes.
        msg: The contract under test.

    Example:
        expect.close_to(seat, elapsed, 1.0, 0.05, "it waited about a second")
    """
    __tracebackhide__ = True
    seat.helper()
    value.close_to(seat, _MODE, got, want, tolerance, msg)


def in_range(seat: Seat, got: Any, low: float, high: float, msg: str) -> None:
    """Record a failure when got is not a number in the closed interval [low, high].

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The number.
        low: The lowest number of the range.
        high: The highest number of the range.
        msg: The contract under test.

    Example:
        expect.in_range(seat, reply.status, 200, 299, "the request succeeds")
    """
    __tracebackhide__ = True
    seat.helper()
    value.in_range(seat, _MODE, got, low, high, msg)


def no_error(seat: Seat, error: BaseException | None, msg: str) -> None:
    """Record a failure when error is not None.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        error: The error, or None when there was none.
        msg: The contract under test.

    Example:
        expect.no_error(seat, err, "the write succeeds")
    """
    __tracebackhide__ = True
    seat.helper()
    errors.no_error(seat, _MODE, error, msg)


def has_error(seat: Seat, error: BaseException | None, msg: str) -> None:
    """Record a failure when error is None.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        error: The error, or None when there was none.
        msg: The contract under test.

    Example:
        expect.has_error(seat, err, "an unwritable path is refused")
    """
    __tracebackhide__ = True
    seat.helper()
    errors.has_error(seat, _MODE, error, msg)


def error_is(seat: Seat, error: BaseException | None, target: object, msg: str) -> None:
    """Record a failure when target does not match an exception of the chain of error.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        error: The error, or None.
        target: The sentinel exception, or a class of exceptions.
        msg: The contract under test.

    Example:
        expect.error_is(seat, err, StoreClosed, "a closed store raises StoreClosed")
    """
    __tracebackhide__ = True
    seat.helper()
    errors.error_is(seat, _MODE, error, target, msg)


def error_is_not(
    seat: Seat, error: BaseException | None, target: object, msg: str
) -> None:
    """Record a failure when target matches error or an exception that it wraps.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        error: The error, or None.
        target: The sentinel exception, or a class of exceptions.
        msg: The contract under test.

    Example:
        expect.error_is_not(seat, err, Timeout, "a refusal is not a timeout")
    """
    __tracebackhide__ = True
    seat.helper()
    errors.error_is_not(seat, _MODE, error, target, msg)


def error_as(
    seat: Seat, error: BaseException | None, want: type[_E], msg: str
) -> _E | None:
    """Record a failure when the chain of error lacks an exception of the class want.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        error: The error, or None.
        want: The class of exceptions.
        msg: The contract under test.

    Returns:
        The exception, or None when the chain does not have one.

    Example:
        clash = expect.error_as(seat, err, Conflict, "a duplicate conflicts")
    """
    __tracebackhide__ = True
    seat.helper()
    return errors.error_as(seat, _MODE, error, want, msg)


def raises(seat: Seat, fn: Callable[[], Any], msg: str) -> Exception | None:
    """Record a failure when fn returns without raising an exception.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: A callable without arguments.
        msg: The contract under test.

    Returns:
        The exception that fn raised, or None when fn returned.

    Example:
        err = expect.raises(seat, lambda: parse("{"), "a cut body is refused")
    """
    __tracebackhide__ = True
    seat.helper()
    return _raises.raises(seat, _MODE, fn, msg)


def does_not_raise(seat: Seat, fn: Callable[[], Any], msg: str) -> None:
    """Record a failure when fn raises an exception.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: A callable without arguments.
        msg: The contract under test.

    Example:
        expect.does_not_raise(seat, lambda: parse(body), "a valid body parses")
    """
    __tracebackhide__ = True
    seat.helper()
    _raises.does_not_raise(seat, _MODE, fn, msg)


def pairwise(
    seat: Seat, items: Sequence[Any], predicate: Callable[[Any, Any], object], msg: str
) -> None:
    """Record a failure when an adjacent pair of items does not satisfy the predicate.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        items: The sequence.
        predicate: Receives an item and the item after it.
        msg: The contract under test.

    Example:
        expect.pairwise(seat, stamps, lambda a, b: a <= b, "the log is ordered")
    """
    __tracebackhide__ = True
    seat.helper()
    order.pairwise(seat, _MODE, items, predicate, msg)


def honours_cancellation(
    seat: Seat, fn: Callable[[], Awaitable[Any]], msg: str
) -> None:
    """Record a failure when a cancelled subject does not stop.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: A coroutine function without arguments.
        msg: The contract under test.

    Example:
        expect.honours_cancellation(seat, worker.serve, "it stops when cancelled")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.honours_cancellation(seat, _MODE, fn, msg)


def honours_deadline(seat: Seat, fn: Callable[[], Awaitable[Any]], msg: str) -> None:
    """Record a failure when a subject runs to its end under a deadline that has passed.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: A coroutine function without arguments.
        msg: The contract under test.

    Example:
        expect.honours_deadline(seat, client.fetch, "the fetch has a deadline")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.honours_deadline(seat, _MODE, fn, msg)


def completes_within(
    seat: Seat, within: float, fn: Callable[[], Any], msg: str
) -> None:
    """Record a failure when fn has not returned within within seconds.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        within: The most seconds that fn can take.
        fn: A callable without arguments.
        msg: The contract under test.

    Example:
        expect.completes_within(seat, 0.5, index.rebuild, "a rebuild is quick")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.completes_within(seat, _MODE, within, fn, msg)


def is_pure(
    seat: Seat,
    observe: Callable[[], Any],
    fn: Callable[[], Any],
    msg: str,
    *options: Option,
) -> None:
    """Record a failure when fn changes what observe returns.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        observe: Returns a copy of the state.
        fn: The call that must not change what observe returns.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.is_pure(seat, store.snapshot, reader.peek, "peek is read-only")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.is_pure(seat, _MODE, observe, fn, msg, *options)


def none_handle_safe(seat: Seat, fn: Callable[[Any], Any], msg: str) -> None:
    """Record a failure when fn crashes on None in place of a handle.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: A callable. The assertion calls it with None.
        msg: The contract under test.

    Example:
        expect.none_handle_safe(seat, worker.attach, "a missing handle does not crash")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.none_handle_safe(seat, _MODE, fn, msg)


def eventually(
    seat: Seat, timeout: float, interval: float, body: Callable[[Any], object], msg: str
) -> None:
    """Record a failure when a body of assertions does not pass within the timeout.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        timeout: The most seconds that the attempts can take.
        interval: The seconds between two attempts.
        body: Receives a seat and asserts the condition.
        msg: The contract under test.

    Example:
        expect.eventually(seat, 5.0, 0.1, settled, "the cache converges")
    """
    __tracebackhide__ = True
    seat.helper()
    waiting.eventually(seat, _MODE, timeout, interval, body, msg)


def eventually_true(
    seat: Seat, timeout: float, predicate: Callable[[], object], msg: str
) -> None:
    """Record a failure when a predicate does not become true within the timeout.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        timeout: The most seconds that the attempts can take.
        predicate: Returns True when the condition is met.
        msg: The contract under test.

    Example:
        expect.eventually_true(seat, 5.0, queue.is_drained, "the queue drains")
    """
    __tracebackhide__ = True
    seat.helper()
    waiting.eventually_true(seat, _MODE, timeout, predicate, msg)


def no_task_leaks(seat: Seat, msg: str) -> Callable[[], None]:
    """Return a check that records a failure when a thread or a task outlives the scope.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        msg: The contract under test.

    Returns:
        The check. Call it where the scope ends.

    Example:
        done = expect.no_task_leaks(seat, "the handler cleans up")
        handler.serve(request)
        done()
    """
    __tracebackhide__ = True
    seat.helper()
    return waiting.no_task_leaks(seat, _MODE, msg)


def rejects(seat: Seat, msg: str, body: Callable[[Any], object]) -> list[Failure]:
    """Record a failure when a check passes against a subject that it must reject.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        msg: The contract under test.
        body: The check that must fail.

    Returns:
        The failure records of the check in call order.

    Example:
        failures = expect.rejects(seat, "an overwriting store fails the check",
                                  lambda tb: refuses_a_duplicate(tb, Overwriting()))
    """
    __tracebackhide__ = True
    seat.helper()
    return _rejects.rejects(seat, _MODE, msg, body)


def is_idempotent(
    seat: Seat,
    call: Callable[[Any], Any],
    value: Any,
    observe: Callable[[], Any],
    msg: str,
    *options: Option,
) -> None:
    """Record a failure when a second call of call changes what observe returns.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        call: The subject, which receives value.
        value: The input of both calls.
        observe: Returns a copy of the state.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.is_idempotent(seat, store.put, entry, store.snapshot,
                             "a second put of one entry does not change the store")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.is_idempotent(seat, _MODE, call, value, observe, msg, *options)


def accumulates(
    seat: Seat,
    call: Callable[[Any], Any],
    value: Any,
    observe: Callable[[], Any],
    msg: str,
) -> None:
    """Record a failure when two calls of call change a number by different amounts.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        call: The subject, which receives value.
        value: The input of both calls.
        observe: Returns the number.
        msg: The contract under test.

    Example:
        expect.accumulates(seat, counter.add, 2, counter.total, "each add adds 2")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.accumulates(seat, _MODE, call, value, observe, msg)


def is_deterministic(
    seat: Seat, call: Callable[[Any], Any], value: Any, msg: str, *options: Option
) -> None:
    """Record a failure when one of 32 calls of call returns a different result.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        call: The subject, which receives value.
        value: The input of every call.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.is_deterministic(seat, render, page, "a page renders one way")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.is_deterministic(seat, _MODE, call, value, msg, *options)


def is_commutative(
    seat: Seat,
    combine: Callable[[Any, Any], Any],
    a: Any,
    b: Any,
    msg: str,
    *options: Option,
) -> None:
    """Record a failure when combine(a, b) differs from combine(b, a).

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        combine: The subject.
        a: The first operand.
        b: The second operand.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.is_commutative(seat, merge, left, right, "merge ignores order")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.is_commutative(seat, _MODE, combine, a, b, msg, *options)


def is_associative(
    seat: Seat,
    combine: Callable[[Any, Any], Any],
    a: Any,
    b: Any,
    c: Any,
    msg: str,
    *options: Option,
) -> None:
    """Record a failure when the two groupings of three operands differ.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        combine: The subject.
        a: The first operand.
        b: The second operand.
        c: The third operand.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.is_associative(seat, merge, x, y, z, "merge ignores grouping")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.is_associative(seat, _MODE, combine, a, b, c, msg, *options)


def round_trip(
    seat: Seat,
    forward: Callable[[Any], Any],
    inverse: Callable[[Any], Any],
    value: Any,
    msg: str,
    *options: Option,
) -> None:
    """Record a failure when inverse of forward of value differs from value.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        forward: The conversion.
        inverse: The inverse conversion.
        value: The input.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.round_trip(seat, encode, decode, order, "decoding undoes encoding")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.round_trip(seat, _MODE, forward, inverse, value, msg, *options)


def has_stable_order(
    seat: Seat, iterate: Callable[[], Any], msg: str, *options: Option
) -> None:
    """Record a failure when an iteration of iterate yields a different sequence.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        iterate: Returns an iterable, or an asynchronous iterable.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.has_stable_order(seat, index.keys, "the keys come in one order")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.has_stable_order(seat, _MODE, iterate, msg, *options)


def no_duplicates(
    seat: Seat, iterate: Callable[[], Any], msg: str, *options: Option
) -> None:
    """Record a failure when one iteration of iterate yields an element twice.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        iterate: Returns an iterable, or an asynchronous iterable.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.no_duplicates(seat, feed.items, "the feed lists each item once")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.no_duplicates(seat, _MODE, iterate, msg, *options)


def is_monotonic(
    seat: Seat,
    observe: Callable[[], Any],
    advance: Callable[[], Any],
    steps: int,
    msg: str,
) -> None:
    """Record a failure when a reading of observe falls or is NaN.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        observe: Returns the number.
        advance: Moves the subject one step.
        steps: The number of steps that the subject advances.
        msg: The contract under test.

    Example:
        expect.is_monotonic(seat, clock.read, clock.tick, 100, "time never falls")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.is_monotonic(seat, _MODE, observe, advance, steps, msg)


def is_total(
    seat: Seat, call: Callable[[Any], Any], domain: Iterable[Any], msg: str
) -> None:
    """Record a failure at the first element of domain for which call raises.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        call: The subject, which receives each element.
        domain: The inputs.
        msg: The contract under test.

    Example:
        expect.is_total(seat, parse_level, LEVELS, "every level parses")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.is_total(seat, _MODE, call, domain, msg)


def is_not_pure(
    seat: Seat,
    observe: Callable[[], Any],
    fn: Callable[[], Any],
    msg: str,
    *options: Option,
) -> None:
    """Record a failure when fn leaves what observe returns unchanged.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        observe: Returns a copy of the state.
        fn: The call that must change what observe returns.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.is_not_pure(seat, store.snapshot, store.clear, "clear removes data")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.is_not_pure(seat, _MODE, observe, fn, msg, *options)


def fails_after_close(
    seat: Seat,
    close: Callable[[], Any],
    call: Callable[[], Any],
    sentinel: object,
    msg: str,
) -> None:
    """Record a failure when call does not raise the sentinel after close.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        close: Closes the subject.
        call: A call of the closed subject.
        sentinel: The exception, or the class of exceptions.
        msg: The contract under test.

    Example:
        expect.fails_after_close(seat, conn.close, conn.ping, Closed,
                                 "a closed connection refuses a ping")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.fails_after_close(seat, _MODE, close, call, sentinel, msg)


def is_poisoned(
    seat: Seat, induce: Callable[[], Any], observe: Callable[[], Any], msg: str
) -> None:
    """Record a failure when one of 32 readings of observe returns after induce.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        induce: Induces the failure.
        observe: The reading that must raise.
        msg: The contract under test.

    Example:
        expect.is_poisoned(seat, disk.corrupt, store.read, "a corrupt store fails")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.is_poisoned(seat, _MODE, induce, observe, msg)


def is_permutation(seat: Seat, got: Any, want: Any, msg: str, *options: Option) -> None:
    """Record a failure when got is not a permutation of want.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The sequence that the code under test produced.
        want: The elements that it must contain.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        expect.is_permutation(seat, shuffle(deck), deck, "a shuffle keeps every card")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.is_permutation(seat, _MODE, got, want, msg, *options)
