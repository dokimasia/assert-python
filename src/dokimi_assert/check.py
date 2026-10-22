# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The assertions that stop the test at the first failure.

Every assertion takes a seat first and the contract last. The contract is a
sentence about what must be true. It is the first line of the failure, so
the failure contains what was supposed to be true and not only what was
observed.

    from dokimi_assert import check

    def test_get(seat):
        check.equal(seat, store.get(key), item, "get returns the stored item")

The seat receives the failure. The package registers a pytest fixture named
seat that supplies one. dokimi_assert.expect has the same assertions under
the same names and runs the same comparisons. Only what happens on a failure
differs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

from dokimi_assert import rejects as _rejects
from dokimi_assert._matcher import behaviour, errors, order, relation, value, waiting
from dokimi_assert._matcher import raises as _raises
from dokimi_assert._matcher.seat import Mode, Seat

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterable, Sequence

    from dokimi_assert._matcher.option import Option
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

_MODE = Mode.FATAL


def equal(seat: Seat, got: Any, want: Any, msg: str, *options: Option) -> None:
    """Fail when got and want differ.

    The comparison is structural. Values of different types are never equal:
    0 does not equal False, and 1 does not equal 1.0. None does not equal an
    empty collection, and NaN does not equal itself, unless an option
    relaxes the rule. The failure has want and got.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The value that the code under test produced.
        want: The value that it is supposed to produce.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.equal(seat, store.get(key), item, "get returns the stored item")
    """
    __tracebackhide__ = True
    seat.helper()
    value.equal(seat, _MODE, got, want, msg, *options)


def not_equal(seat: Seat, got: Any, want: Any, msg: str, *options: Option) -> None:
    """Fail when got and want are equal by the rules of equal.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The value that the code under test produced.
        want: The value that it must not equal.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.not_equal(seat, token, previous, "a refresh issues a new token")
    """
    __tracebackhide__ = True
    seat.helper()
    value.not_equal(seat, _MODE, got, want, msg, *options)


def is_true(seat: Seat, condition: object, msg: str) -> None:
    """Fail when the condition is not true.

    The failure contains the contract alone. A more specific assertion also
    reports the values.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        condition: The condition.
        msg: The contract under test.

    Example:
        check.is_true(seat, user.is_active, "a new user starts active")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_true(seat, _MODE, condition, msg)


def is_false(seat: Seat, condition: object, msg: str) -> None:
    """Fail when the condition is true.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        condition: The condition.
        msg: The contract under test.

    Example:
        check.is_false(seat, cache.is_stale(), "a fresh read is not stale")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_false(seat, _MODE, condition, msg)


def is_none(seat: Seat, got: Any, msg: str) -> None:
    """Fail when got is not None.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The value that must be absent.
        msg: The contract under test.

    Example:
        check.is_none(seat, validate(name), "a good name is accepted")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_none(seat, _MODE, got, msg)


def is_not_none(seat: Seat, got: Any, msg: str) -> None:
    """Fail when got is None.

    Use it before the test reads an attribute of a value that can be absent.
    The test then stops with the contract, and not with an AttributeError.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The value that must be present.
        msg: The contract under test.

    Example:
        check.is_not_none(seat, store.get(key), "get returns the stored item")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_not_none(seat, _MODE, got, msg)


def length(seat: Seat, got: Any, want: int, msg: str) -> None:
    """Fail when got does not have want items.

    The length of a str is the number of its Unicode scalar values, and the
    length of bytes is the number of bytes. Any other sized value has the
    length that len returns. The assertion fails with got None for a str
    with a surrogate code point, for None, and for a value without a length.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The container.
        want: The number of items that it must have.
        msg: The contract under test.

    Example:
        check.length(seat, reply.items, 3, "every item comes back")
    """
    __tracebackhide__ = True
    seat.helper()
    value.length(seat, _MODE, got, want, msg)


def is_empty(seat: Seat, got: Any, msg: str) -> None:
    """Fail when got has an item or does not have a length.

    Empty is not absent. None does not have a length, so it fails. The
    failure has got and length. length is None for a value without a length.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The container that must be empty.
        msg: The contract under test.

    Example:
        check.is_empty(seat, reply.errors, "a valid request has no errors")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_empty(seat, _MODE, got, msg)


def is_not_empty(seat: Seat, got: Any, msg: str) -> None:
    """Fail when got is empty or does not have a length.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The container that must have an item.
        msg: The contract under test.

    Example:
        check.is_not_empty(seat, results, "the search finds something")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_not_empty(seat, _MODE, got, msg)


def contains(
    seat: Seat, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Fail when haystack does not contain needle.

    A str contains a substring, bytes contain a byte string or a byte, a
    mapping contains a key, and a sequence or a set contains an element. A
    key and an element compare in the same way as in equal, so the int 1
    does not match the float 1.0. A haystack of another type fails.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        haystack: The text or the collection.
        needle: The substring, the element or the key.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.contains(seat, reply.headers, "etag", "the reply is cacheable")
    """
    __tracebackhide__ = True
    seat.helper()
    value.contains(seat, _MODE, haystack, needle, msg, *options)


def not_contains(
    seat: Seat, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Fail when haystack contains needle.

    Containment follows the rules of contains. A haystack that is not a str,
    bytes, a mapping, a sequence or a set fails too.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        haystack: The text or the collection.
        needle: The substring, the element or the key that must be absent.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.not_contains(seat, body, "password", "no secret leaks")
    """
    __tracebackhide__ = True
    seat.helper()
    value.not_contains(seat, _MODE, haystack, needle, msg, *options)


def contains_in_order(seat: Seat, got: Any, needles: Sequence[str], msg: str) -> None:
    """Fail when got does not contain the needles in order.

    The search for a needle starts where the match of the needle before it
    ends, so one part of the text cannot match two needles. An empty list of
    needles passes.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The text.
        needles: The substrings in the order in which they must appear.
        msg: The contract under test.

    Example:
        check.contains_in_order(seat, log, ["open", "close"], "it closes last")
    """
    __tracebackhide__ = True
    seat.helper()
    value.contains_in_order(seat, _MODE, got, needles, msg)


def has_prefix(seat: Seat, got: Any, prefix: str, msg: str) -> None:
    """Fail when got is not a str that starts with prefix.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The text.
        prefix: The text that got must start with.
        msg: The contract under test.

    Example:
        check.has_prefix(seat, request_id, "req_", "the id has its prefix")
    """
    __tracebackhide__ = True
    seat.helper()
    value.has_prefix(seat, _MODE, got, prefix, msg)


def has_suffix(seat: Seat, got: Any, suffix: str, msg: str) -> None:
    """Fail when got is not a str that ends with suffix.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The text.
        suffix: The text that got must end with.
        msg: The contract under test.

    Example:
        check.has_suffix(seat, path, ".json", "the export is JSON")
    """
    __tracebackhide__ = True
    seat.helper()
    value.has_suffix(seat, _MODE, got, suffix, msg)


def matches(seat: Seat, got: Any, pattern: str, msg: str) -> None:
    r"""Fail when got is not a str that a pattern of the portable subset matches.

    The pattern matches anywhere in the text. Use ^ and $ to match the whole
    text. $ matches at the end of the text only. \d, \w and \s are their
    ASCII classes, and the dot does not match a line terminator. A pattern
    with a backreference or a lookaround is outside the subset. Such a
    pattern fails, and the field reason of the failure has the cause.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The text.
        pattern: A pattern of the portable subset.
        msg: The contract under test.

    Example:
        check.matches(seat, rid, r"^req_[0-9a-f]{16}$", "the id is well formed")
    """
    __tracebackhide__ = True
    seat.helper()
    value.matches(seat, _MODE, got, pattern, msg)


def close_to(seat: Seat, got: Any, want: float, tolerance: float, msg: str) -> None:
    """Fail when got is not a number within tolerance of want.

    The tolerance is an absolute difference, and a difference equal to it
    passes. A NaN fails, whether it is got, want or the tolerance. Two equal
    infinities fail as well. A bool is not a number.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The number.
        want: The number that got must be near.
        tolerance: The largest absolute difference that passes.
        msg: The contract under test.

    Example:
        check.close_to(seat, elapsed, 1.0, 0.05, "it waited about a second")
    """
    __tracebackhide__ = True
    seat.helper()
    value.close_to(seat, _MODE, got, want, tolerance, msg)


def in_range(seat: Seat, got: Any, low: float, high: float, msg: str) -> None:
    """Fail when got is not a number in the closed interval from low to high.

    Both bounds pass. A NaN is not in any range. A range whose low is above
    its high does not contain a number, and neither does a range with a NaN
    bound.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The number.
        low: The lowest number of the range.
        high: The highest number of the range.
        msg: The contract under test.

    Example:
        check.in_range(seat, reply.status, 200, 299, "the request succeeds")
    """
    __tracebackhide__ = True
    seat.helper()
    value.in_range(seat, _MODE, got, low, high, msg)


def no_error(seat: Seat, error: BaseException | None, msg: str) -> None:
    """Fail when error is not None.

    Use it for code that returns an exception. For code that raises, use
    raises or does_not_raise.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        error: The error, or None when there was none.
        msg: The contract under test.

    Example:
        check.no_error(seat, err, "the write succeeds")
    """
    __tracebackhide__ = True
    seat.helper()
    errors.no_error(seat, _MODE, error, msg)


def has_error(seat: Seat, error: BaseException | None, msg: str) -> None:
    """Fail when error is None.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        error: The error, or None when there was none.
        msg: The contract under test.

    Example:
        check.has_error(seat, err, "an unwritable path is refused")
    """
    __tracebackhide__ = True
    seat.helper()
    errors.has_error(seat, _MODE, error, msg)


def error_is(seat: Seat, error: BaseException | None, target: object, msg: str) -> None:
    """Fail when target matches neither error nor an exception that error wraps.

    The match follows __cause__ and __context__, so an exception that
    raise ... from wrapped still matches. An exception matches the same
    object, and a class matches each of its instances.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        error: The error, or None.
        target: The sentinel exception, or a class of exceptions.
        msg: The contract under test.

    Example:
        check.error_is(seat, err, StoreClosed, "a closed store raises StoreClosed")
    """
    __tracebackhide__ = True
    seat.helper()
    errors.error_is(seat, _MODE, error, target, msg)


def error_is_not(
    seat: Seat, error: BaseException | None, target: object, msg: str
) -> None:
    """Fail when target matches error or an exception that error wraps.

    The match follows the rules of error_is.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        error: The error, or None.
        target: The sentinel exception, or a class of exceptions.
        msg: The contract under test.

    Example:
        check.error_is_not(seat, err, Timeout, "a refusal is not a timeout")
    """
    __tracebackhide__ = True
    seat.helper()
    errors.error_is_not(seat, _MODE, error, target, msg)


def error_as(
    seat: Seat, error: BaseException | None, want: type[_E], msg: str
) -> _E | None:
    """Fail when the chain of error does not contain an exception of the class want.

    Use it to read the fields of an exception of a known class, and not its
    text.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        error: The error, or None.
        want: The class of exceptions.
        msg: The contract under test.

    Returns:
        The exception, or None when the chain does not have one.

    Example:
        clash = check.error_as(seat, err, Conflict, "a duplicate conflicts")
    """
    __tracebackhide__ = True
    seat.helper()
    return errors.error_as(seat, _MODE, error, want, msg)


def raises(seat: Seat, fn: Callable[[], Any], msg: str) -> Exception | None:
    """Fail when fn returns without raising an exception.

    The assertion does not catch a KeyboardInterrupt or a SystemExit, because
    they end the run. When the class matters, assert on the returned
    exception or use error_as.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: A callable without arguments.
        msg: The contract under test.

    Returns:
        The exception that fn raised, or None when fn returned.

    Example:
        err = check.raises(seat, lambda: parse("{"), "a cut body is refused")
    """
    __tracebackhide__ = True
    seat.helper()
    return _raises.raises(seat, _MODE, fn, msg)


def does_not_raise(seat: Seat, fn: Callable[[], Any], msg: str) -> None:
    """Fail when fn raises an exception. The failure has the exception.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: A callable without arguments.
        msg: The contract under test.

    Example:
        check.does_not_raise(seat, lambda: parse(body), "a valid body parses")
    """
    __tracebackhide__ = True
    seat.helper()
    _raises.does_not_raise(seat, _MODE, fn, msg)


def pairwise(
    seat: Seat, items: Sequence[Any], predicate: Callable[[Any, Any], object], msg: str
) -> None:
    """Fail when an adjacent pair of items does not satisfy the predicate.

    The predicate receives each item and the item after it. An empty sequence
    and a sequence of one item pass. The failure has the position of the
    first item of the pair as index, and the two items as first and second.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        items: The sequence.
        predicate: Receives an item and the item after it.
        msg: The contract under test.

    Example:
        check.pairwise(seat, stamps, lambda a, b: a <= b, "the log is ordered")
    """
    __tracebackhide__ = True
    seat.helper()
    order.pairwise(seat, _MODE, items, predicate, msg)


def honours_cancellation(
    seat: Seat, fn: Callable[[], Awaitable[Any]], msg: str
) -> None:
    """Fail when a cancelled subject does not stop.

    The assertion starts the coroutine and cancels it at its first await, and
    the coroutine must raise CancelledError. A subject that returns before it
    awaits fails, and so does one that catches the cancellation and
    continues. The assertion runs the event loop itself, so the test is a
    plain def.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: A coroutine function without arguments.
        msg: The contract under test.

    Example:
        check.honours_cancellation(seat, worker.serve, "it stops when cancelled")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.honours_cancellation(seat, _MODE, fn, msg)


def honours_deadline(seat: Seat, fn: Callable[[], Awaitable[Any]], msg: str) -> None:
    """Fail when a subject runs to its end under a deadline that has passed.

    The deadline cuts a subject short at its first await, and such a subject
    passes. A subject fails when it does not await, or when it catches the
    cancellation and returns.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: A coroutine function without arguments.
        msg: The contract under test.

    Example:
        check.honours_deadline(seat, client.fetch, "the fetch has a deadline")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.honours_deadline(seat, _MODE, fn, msg)


def completes_within(
    seat: Seat, within: float, fn: Callable[[], Any], msg: str
) -> None:
    """Fail when fn has not returned within within seconds.

    The assertion calls fn on a daemon thread. A subject that has not
    returned when the duration has passed fails then, and the assertion does
    not wait for it. A subject that returns is measured on the clock of the
    seat.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        within: The most seconds that fn can take.
        fn: A callable without arguments.
        msg: The contract under test.

    Example:
        check.completes_within(seat, 0.5, index.rebuild, "a rebuild is quick")
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
    """Fail when fn changes what observe returns.

    The assertion calls observe before and after fn, and compares the two
    readings in the same way as equal. observe must return a copy. A
    projection that shares state with the subject compares one object with
    itself, so it passes whatever fn did.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        observe: Returns a copy of the state.
        fn: The call that must not change what observe returns.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.is_pure(seat, store.snapshot, reader.peek, "peek is read-only")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.is_pure(seat, _MODE, observe, fn, msg, *options)


def none_handle_safe(seat: Seat, fn: Callable[[Any], Any], msg: str) -> None:
    """Fail when fn crashes on None in place of a handle.

    An AttributeError and a TypeError fail, because a subject raises them
    when it reads None without a check. Any other exception passes, and it is
    often the correct behaviour.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: A callable. The assertion calls it with None.
        msg: The contract under test.

    Example:
        check.none_handle_safe(seat, worker.attach, "a missing handle does not crash")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.none_handle_safe(seat, _MODE, fn, msg)


def eventually(
    seat: Seat, timeout: float, interval: float, body: Callable[[Any], object], msg: str
) -> None:
    """Fail when a body of assertions does not pass within the timeout.

    The body receives a seat of its own, so an assertion inside it ends the
    attempt and not the test. The body runs at least once, and the failure
    contains the failure of the last attempt. On the platform clock the
    assertion spends real time. On a controlled clock it advances the clock
    between attempts.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        timeout: The most seconds that the attempts can take.
        interval: The seconds between two attempts.
        body: Receives a seat and asserts the condition.
        msg: The contract under test.

    Example:
        check.eventually(seat, 5.0, 0.1, settled, "the cache converges")
    """
    __tracebackhide__ = True
    seat.helper()
    waiting.eventually(seat, _MODE, timeout, interval, body, msg)


def eventually_true(
    seat: Seat, timeout: float, predicate: Callable[[], object], msg: str
) -> None:
    """Fail when a predicate does not become true within the timeout.

    The assertion calls the predicate with a backoff that starts at a
    millisecond and doubles. A predicate does not give a reason, so the
    failure has the attempts alone. When the reason matters, use eventually.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        timeout: The most seconds that the attempts can take.
        predicate: Returns True when the condition is met.
        msg: The contract under test.

    Example:
        check.eventually_true(seat, 5.0, queue.is_drained, "the queue drains")
    """
    __tracebackhide__ = True
    seat.helper()
    waiting.eventually_true(seat, _MODE, timeout, predicate, msg)


def no_task_leaks(seat: Seat, msg: str) -> Callable[[], None]:
    """Return a check that fails when a thread or a task outlives the scope.

    The scope starts at this call and ends at the call of the check. A
    thread or an asyncio task that started in the scope and still runs at
    its end is a leak. A cancelled request leaves work running in this way.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        msg: The contract under test.

    Returns:
        The check. Call it where the scope ends.

    Example:
        done = check.no_task_leaks(seat, "the handler cleans up")
        handler.serve(request)
        done()
    """
    __tracebackhide__ = True
    seat.helper()
    return waiting.no_task_leaks(seat, _MODE, msg)


def rejects(seat: Seat, msg: str, body: Callable[[Any], object]) -> list[Failure]:
    """Fail when a check passes against a subject that it must reject.

    The body receives a seat of its own. That seat keeps every failure record
    of the check and ends the check at its first aborting failure. Assert on
    the returned records to confirm that the check fails for the reason that
    it was written to catch.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        msg: The contract under test.
        body: The check that must fail.

    Returns:
        The failure records of the check in call order.

    Example:
        failures = check.rejects(seat, "an overwriting store fails the check",
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
    """Fail when a second call of call changes what observe returns after the first.

    first is the observation after one call, and second is the observation
    after two.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        call: The subject, which receives value.
        value: The input of both calls.
        observe: Returns a copy of the state.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.is_idempotent(seat, store.put, entry, store.snapshot,
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
    """Fail when two calls of call change an observed number by different amounts.

    The assertion fails also when the first call leaves the number unchanged.
    first and second are the changes of the two calls.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        call: The subject, which receives value.
        value: The input of both calls.
        observe: Returns the number.
        msg: The contract under test.

    Example:
        check.accumulates(seat, counter.add, 2, counter.total, "each add adds 2")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.accumulates(seat, _MODE, call, value, observe, msg)


def is_deterministic(
    seat: Seat, call: Callable[[Any], Any], value: Any, msg: str, *options: Option
) -> None:
    """Fail when one of 32 calls of call returns a result that differs from the first.

    first is the first result, and second is the first result that differs.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        call: The subject, which receives value.
        value: The input of every call.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.is_deterministic(seat, render, page, "a page renders one way")
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
    """Fail when combine(a, b) differs from combine(b, a).

    first is combine(a, b), and second is combine(b, a).

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        combine: The subject.
        a: The first operand.
        b: The second operand.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.is_commutative(seat, merge, left, right, "merge ignores order")
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
    """Fail when combine(combine(a, b), c) differs from combine(a, combine(b, c)).

    first is the left grouping, and second is the right one.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        combine: The subject.
        a: The first operand.
        b: The second operand.
        c: The third operand.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.is_associative(seat, merge, x, y, z, "merge ignores grouping")
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
    """Fail when inverse of forward of value differs from value.

    want is value, and got is the value that came back. An exception of
    forward or of inverse fails with want None and got the exception.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        forward: The conversion.
        inverse: The inverse conversion.
        value: The input.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.round_trip(seat, encode, decode, order, "decoding undoes encoding")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.round_trip(seat, _MODE, forward, inverse, value, msg, *options)


def has_stable_order(
    seat: Seat, iterate: Callable[[], Any], msg: str, *options: Option
) -> None:
    """Fail when an iteration of iterate yields a sequence that differs from the first.

    The assertion runs 32 iterations. first is the first sequence, and second
    is the first sequence that differs.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        iterate: Returns an iterable, or an asynchronous iterable.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.has_stable_order(seat, index.keys, "the keys come in one order")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.has_stable_order(seat, _MODE, iterate, msg, *options)


def no_duplicates(
    seat: Seat, iterate: Callable[[], Any], msg: str, *options: Option
) -> None:
    """Fail when one iteration of iterate yields an element equal to an earlier one.

    got is the element, and index is its position.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        iterate: Returns an iterable, or an asynchronous iterable.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.no_duplicates(seat, feed.items, "the feed lists each item once")
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
    """Fail when a reading of observe falls or is NaN while the subject advances.

    index is the position of that reading. The reading before the first step
    is at position 0. first is the reading before it, and second is that
    reading.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        observe: Returns the number.
        advance: Moves the subject one step.
        steps: The number of steps that the subject advances.
        msg: The contract under test.

    Example:
        check.is_monotonic(seat, clock.read, clock.tick, 100, "time never falls")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.is_monotonic(seat, _MODE, observe, advance, steps, msg)


def is_total(
    seat: Seat, call: Callable[[Any], Any], domain: Iterable[Any], msg: str
) -> None:
    """Fail at the first element of domain for which call raises.

    index is its position, and got is the exception. An empty domain passes.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        call: The subject, which receives each element.
        domain: The inputs.
        msg: The contract under test.

    Example:
        check.is_total(seat, parse_level, LEVELS, "every level parses")
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
    """Fail when fn leaves what observe returns unchanged.

    got is the observation that did not change.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        observe: Returns a copy of the state.
        fn: The call that must change what observe returns.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.is_not_pure(seat, store.snapshot, store.clear, "clear removes data")
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
    """Fail when call does not raise the sentinel after close.

    The sentinel matches through the chain of causes in the same way as in
    error_is. want is the sentinel. got is the exception that call raised,
    or None when call returned.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        close: Closes the subject.
        call: A call of the closed subject.
        sentinel: The exception, or the class of exceptions.
        msg: The contract under test.

    Example:
        check.fails_after_close(seat, conn.close, conn.ping, Closed,
                                "a closed connection refuses a ping")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.fails_after_close(seat, _MODE, close, call, sentinel, msg)


def is_poisoned(
    seat: Seat, induce: Callable[[], Any], observe: Callable[[], Any], msg: str
) -> None:
    """Fail when one of 32 readings of observe returns after induce.

    index is the position of that reading, and got is the value that it
    returned.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        induce: Induces the failure.
        observe: The reading that must raise.
        msg: The contract under test.

    Example:
        check.is_poisoned(seat, disk.corrupt, store.read, "a corrupt store fails")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.is_poisoned(seat, _MODE, induce, observe, msg)


def is_permutation(seat: Seat, got: Any, want: Any, msg: str, *options: Option) -> None:
    """Fail when got does not contain each element of want as often as want does.

    The order does not matter. Elements compare in the same way as in equal.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: The sequence that the code under test produced.
        want: The elements that it must contain.
        msg: The contract under test.
        *options: The relaxations of dokimi_assert.option that apply to the call.

    Example:
        check.is_permutation(seat, shuffle(deck), deck, "a shuffle keeps every card")
    """
    __tracebackhide__ = True
    seat.helper()
    relation.is_permutation(seat, _MODE, got, want, msg, *options)
