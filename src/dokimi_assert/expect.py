"""Assertions that record a failure and let the test continue.

Every assertion takes a seat first and a message last. The message
states the contract under test and is the first line of the failure, so
a failure says what was supposed to be true rather than only what was
observed.

Reach for this where several properties of one value are each worth
seeing. One run reports all of them rather than the first:

    from dokimi_assert import expect

    expect.is_not_none(seat, user, "the user was found")
    expect.has_prefix(seat, user.id, "usr_", "the id carries its prefix")

dokimi_assert.check carries the same assertions under the same names
and runs the same comparison. Only what happens on failure differs.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, TypeVar

from dokimi_assert._matcher import behaviour, errors, order, value, waiting
from dokimi_assert._matcher import raises as raising
from dokimi_assert._matcher.option import Option
from dokimi_assert._matcher.seat import Mode, Seat

_E = TypeVar("_E", bound=BaseException)

__all__ = [
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
    "has_error",
    "has_prefix",
    "has_suffix",
    "honours_cancellation",
    "honours_deadline",
    "in_range",
    "is_empty",
    "is_false",
    "is_none",
    "is_not_empty",
    "is_not_none",
    "is_pure",
    "is_true",
    "length",
    "matches",
    "no_error",
    "no_task_leaks",
    "none_handle_safe",
    "not_contains",
    "not_equal",
    "pairwise",
    "raises",
]

_MODE = Mode.SOFT


def equal(seat: Seat, got: Any, want: Any, msg: str, *options: Option) -> None:
    """Record a failure when got and want differ.

    Comparison is structural and reaches nested values. Types must match
    exactly: 0 does not equal False and 1 does not equal
    1.0, because bool subclasses int and Python's == calls
    both pairs equal.

    An absent collection does not equal an empty one, and NaN does not
    equal itself. The failure carries want and then got.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.equal() for the rules this shares with the
    aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The value produced by the code under test.
        want: The value it is supposed to produce.
        msg: The contract under test. It is the first line of the failure.
        *options: Relaxations for this call alone, from dokimi_assert.option.

    Example:
        expect.equal(seat, store.get(id), item, "Get returns the item")
    """
    __tracebackhide__ = True
    seat.helper()
    value.equal(seat, _MODE, got, want, msg, *options)


def not_equal(seat: Seat, got: Any, want: Any, msg: str, *options: Option) -> None:
    """Record a failure when got and want are equal.

    Comparison follows the rules of equal(). The failure shows the
    value the two shared, since printing one says everything.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.not_equal() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The value produced by the code under test.
        want: The value it must not equal.
        msg: The contract under test. It is the first line of the failure.
        *options: Relaxations for this call alone, from dokimi_assert.option.

    Example:
        expect.not_equal(seat, token, previous, "Refresh issues a new token")
    """
    __tracebackhide__ = True
    seat.helper()
    value.not_equal(seat, _MODE, got, want, msg, *options)


def is_true(seat: Seat, condition: bool, msg: str) -> None:
    """Record a failure when the condition does not hold.

    The failure carries the message alone: a bare False says nothing
    the message does not. Where a more specific assertion exists, it will
    say more on failure than this one can.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.is_true() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        condition: The condition that must hold.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.is_true(seat, user.is_active, "a new user starts active")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_true(seat, _MODE, condition, msg)


def is_false(seat: Seat, condition: bool, msg: str) -> None:
    """Record a failure when the condition holds.

    The failure carries the message alone, as is_true() describes.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.is_false() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        condition: The condition that must not hold.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.is_false(seat, cache.is_stale(), "a fresh read is not stale")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_false(seat, _MODE, condition, msg)


def is_none(seat: Seat, got: Any, msg: str) -> None:
    """Record a failure when got is not None.

    For a function that answers with an error or None, this states that
    it found nothing to report.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.is_none() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The value that must be absent.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.is_none(seat, validate(name), "a good name is accepted")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_none(seat, _MODE, got, msg)


def is_not_none(seat: Seat, got: Any, msg: str) -> None:
    """Record a failure when got is None.

    Use it before reading attributes of a value that may be absent: the
    test stops here with your message rather than further down with an
    AttributeError nobody wrote.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.is_not_none() for the rules this shares
    with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The value that must be present.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.is_not_none(seat, store.get(id), "Get returns the item")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_not_none(seat, _MODE, got, msg)


def length(seat: Seat, got: Any, want: int, msg: str) -> None:
    """Record a failure when got does not hold want items.

    Answers for anything with a length: a string, bytes, a list, a tuple,
    a dict, a set. A value with no length is itself the failure rather
    than a TypeError, so a wrong type reads like every other failure.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.length() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The container to measure.
        want: The number of items it must hold.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.length(seat, reply.items, 3, "every item comes back")
    """
    __tracebackhide__ = True
    seat.helper()
    value.length(seat, _MODE, got, want, msg)


def is_empty(seat: Seat, got: Any, msg: str) -> None:
    """Record a failure when got holds anything.

    Empty is not absent. None has no length, so it fails here rather
    than passing as empty.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.is_empty() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The container that must hold nothing.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.is_empty(seat, reply.errors, "a valid request has no errors")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_empty(seat, _MODE, got, msg)


def is_not_empty(seat: Seat, got: Any, msg: str) -> None:
    """Record a failure when got holds nothing.

    A value with no length fails here, as is_empty() describes.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.is_not_empty() for the rules this shares
    with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The container that must hold something.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.is_not_empty(seat, results, "the search finds something")
    """
    __tracebackhide__ = True
    seat.helper()
    value.is_not_empty(seat, _MODE, got, msg)


def contains(
    seat: Seat, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Record a failure when haystack does not hold needle.

    What containment means follows the haystack. Text holds a substring;
    bytes hold a substring, with a str needle encoded first; a mapping
    holds a key; any other sequence or set holds an element, compared by
    the rules of equal().

    A haystack that cannot be searched, or a needle that cannot be in it,
    is reported rather than raised.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.contains() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        haystack: The container or text to search.
        needle: The element, key or substring to find.
        msg: The contract under test. It is the first line of the failure.
        *options: Relaxations for this call alone, from dokimi_assert.option.

    Example:
        expect.contains(seat, reply.headers, "etag", "the reply is cacheable")
    """
    __tracebackhide__ = True
    seat.helper()
    value.contains(seat, _MODE, haystack, needle, msg, *options)


def not_contains(
    seat: Seat, haystack: Any, needle: Any, msg: str, *options: Option
) -> None:
    """Record a failure when haystack holds needle.

    Containment follows the rules of contains().

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.not_contains() for the rules this shares
    with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        haystack: The container or text to search.
        needle: The element, key or substring that must be absent.
        msg: The contract under test. It is the first line of the failure.
        *options: Relaxations for this call alone, from dokimi_assert.option.

    Example:
        expect.not_contains(seat, body, "password", "no secret leaks")
    """
    __tracebackhide__ = True
    seat.helper()
    value.not_contains(seat, _MODE, haystack, needle, msg, *options)


def contains_in_order(seat: Seat, got: Any, needles: Sequence[str], msg: str) -> None:
    """Record a failure when got does not hold every needle, in order.

    Each needle is looked for after the previous one's match ends, so the
    same text cannot satisfy two needles. Anything may sit between them.
    An empty list of needles passes.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.contains_in_order() for the rules this
    shares with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The text to search.
        needles: The substrings, in the order they must appear.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.contains_in_order(seat, log, ["open", "close"], "it runs in order")
    """
    __tracebackhide__ = True
    seat.helper()
    value.contains_in_order(seat, _MODE, got, needles, msg)


def has_prefix(seat: Seat, got: Any, prefix: str, msg: str) -> None:
    """Record a failure when got does not start with prefix.

    Answers for str and bytes. A value that is neither is reported
    rather than raised.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.has_prefix() for the rules this shares
    with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The text to inspect.
        prefix: What it must start with.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.has_prefix(seat, request_id, "req_", "the id carries its prefix")
    """
    __tracebackhide__ = True
    seat.helper()
    value.has_prefix(seat, _MODE, got, prefix, msg)


def has_suffix(seat: Seat, got: Any, suffix: str, msg: str) -> None:
    """Record a failure when got does not end with suffix.

    Answers for str and bytes, as has_prefix() describes.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.has_suffix() for the rules this shares
    with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The text to inspect.
        suffix: What it must end with.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.has_suffix(seat, path, ".json", "the export is JSON")
    """
    __tracebackhide__ = True
    seat.helper()
    value.has_suffix(seat, _MODE, got, suffix, msg)


def matches(seat: Seat, got: Any, pattern: str, msg: str) -> None:
    """Record a failure when got does not match the pattern.

    The pattern is searched rather than anchored: use ^ and $
    where you mean the whole value. A pattern that does not compile is
    reported as the failure, so a typo in a pattern does not read like a
    failing subject.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.matches() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The text to match.
        pattern: A Python regular expression.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.matches(seat, rid, r"^req_[0-9a-f]{16}$", "the id is well formed")
    """
    __tracebackhide__ = True
    seat.helper()
    value.matches(seat, _MODE, got, pattern, msg)


def close_to(seat: Seat, got: Any, want: float, tolerance: float, msg: str) -> None:
    """Record a failure when got is further than tolerance from want.

    The tolerance is an absolute difference and the bound is inclusive,
    so a difference exactly equal to tolerance passes. This is the
    assertion for a float, where exact equality is the wrong question.

    NaN is outside every tolerance, whether it is the value, the target or
    the tolerance. bool is not a number here.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.close_to() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The number produced.
        want: The number it should be near.
        tolerance: The largest acceptable absolute difference.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.close_to(seat, elapsed, 1.0, 0.05, "it waited about a second")
    """
    __tracebackhide__ = True
    seat.helper()
    value.close_to(seat, _MODE, got, want, tolerance, msg)


def in_range(seat: Seat, got: Any, low: float, high: float, msg: str) -> None:
    """Record a failure when got falls outside low to high.

    The interval is closed, so both bounds pass. A range with low above
    high can hold nothing, and says so rather than reporting the value.
    NaN is in no range.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.in_range() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        got: The number to place.
        low: The lowest acceptable value.
        high: The highest acceptable value.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.in_range(seat, reply.status, 200, 299, "the request succeeds")
    """
    __tracebackhide__ = True
    seat.helper()
    value.in_range(seat, _MODE, got, low, high, msg)


def no_error(seat: Seat, exc: BaseException | None, msg: str) -> None:
    """Record a failure when exc is not None.

    For code that hands an exception back rather than raising it. Where
    the code raises, use raises() or does_not_raise().

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.no_error() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        exc: The error value, or None when there was none.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.no_error(seat, err, "the write succeeds")
    """
    __tracebackhide__ = True
    seat.helper()
    errors.no_error(seat, _MODE, exc, msg)


def has_error(seat: Seat, exc: BaseException | None, msg: str) -> None:
    """Record a failure when exc is None.

    For code that hands an exception back rather than raising it.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.has_error() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        exc: The error value, or None when there was none.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.has_error(seat, err, "an unwritable path is refused")
    """
    __tracebackhide__ = True
    seat.helper()
    errors.has_error(seat, _MODE, exc, msg)


def error_is(
    seat: Seat, exc: BaseException | None, target: BaseException, msg: str
) -> None:
    """Record a failure when exc does not match target.

    Matching follows the chain of causes, so an exception wrapped by
    raise ... from still matches.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.error_is() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        exc: The error to inspect, or None.
        target: The sentinel exception or class it must match.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.error_is(seat, err, StoreClosed, "a closed store says so")
    """
    __tracebackhide__ = True
    seat.helper()
    errors.error_is(seat, _MODE, exc, target, msg)


def error_is_not(
    seat: Seat, exc: BaseException | None, target: BaseException, msg: str
) -> None:
    """Record a failure when exc matches target.

    Matching follows the chain of causes, as error_is() describes.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.error_is_not() for the rules this shares
    with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        exc: The error to inspect, or None.
        target: The sentinel exception or class it must not match.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.error_is_not(seat, err, Timeout, "a refusal is not a timeout")
    """
    __tracebackhide__ = True
    seat.helper()
    errors.error_is_not(seat, _MODE, exc, target, msg)


def error_as(
    seat: Seat, exc: BaseException | None, want: type[_E], msg: str
) -> _E | None:
    """Record a failure when no error of type want is in the chain.

    Use it to read fields off a specific error type rather than parsing
    its text.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.error_as() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        exc: The error to inspect, or None.
        want: The exception class to look for.
        msg: The contract under test. It is the first line of the failure.

    Returns:
        The matching exception, so its fields can be read, or None when
        nothing matched.

    Example:
        clash = expect.error_as(seat, err, Conflict, "a duplicate conflicts")
    """
    __tracebackhide__ = True
    seat.helper()
    return errors.error_as(seat, _MODE, exc, want, msg)


def raises(seat: Seat, fn: Callable[[], Any], msg: str) -> BaseException | None:
    """Record a failure when fn does not raise.

    Any BaseException counts, including KeyboardInterrupt and SystemExit.
    Where the type matters, assert on the return value or use
    error_as().

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.raises() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        fn: Called with no arguments.
        msg: The contract under test. It is the first line of the failure.

    Returns:
        What fn raised, so the reason can be asserted on, or None when fn
        returned.

    Example:
        err = expect.raises(seat, lambda: parse("{"), "a cut body is refused")
    """
    __tracebackhide__ = True
    seat.helper()
    return raising.raises(seat, _MODE, fn, msg)


def does_not_raise(seat: Seat, fn: Callable[[], Any], msg: str) -> None:
    """Record a failure when fn raises.

    The failure carries what was raised.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.does_not_raise() for the rules this shares
    with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        fn: Called with no arguments.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.does_not_raise(seat, lambda: parse(body), "a valid body parses")
    """
    __tracebackhide__ = True
    seat.helper()
    raising.does_not_raise(seat, _MODE, fn, msg)


def pairwise(
    seat: Seat,
    items: Sequence[Any],
    predicate: Callable[[Any, Any], bool],
    msg: str,
) -> None:
    """Record a failure when an adjacent pair does not satisfy the predicate.

    The predicate is called on every neighbouring pair in turn and must
    answer True for each. Nought or one item passes, since neither has a
    pair. The failure names the index where it broke.

    This is one assertion rather than sorted, unique and strictly
    increasing, because each of those is a relation between neighbours.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.pairwise() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        items: The sequence to walk.
        predicate: Called as predicate(earlier, later) for each pair.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.pairwise(seat, timestamps, lambda a, b: a <= b, "the log is ordered")
    """
    __tracebackhide__ = True
    seat.helper()
    order.pairwise(seat, _MODE, items, predicate, msg)


def honours_cancellation(
    seat: Seat, fn: Callable[[], Awaitable[Any]], msg: str
) -> None:
    """Record a failure when a cancelled subject does not stop.

    The subject is started, cancelled at once, and must raise
    CancelledError. One that returns without ever awaiting, or that
    catches the cancellation and carries on, fails.

    The assertion runs the event loop itself, so the test stays a plain
    def and needs no async plugin.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.honours_cancellation() for the rules this
    shares with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        fn: A coroutine function, called with no arguments.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.honours_cancellation(seat, worker.serve, "it stops when told")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.honours_cancellation(seat, _MODE, fn, msg)


def honours_deadline(seat: Seat, fn: Callable[[], Awaitable[Any]], msg: str) -> None:
    """Record a failure when a subject given no time runs to completion.

    The subject runs under a deadline that has already passed. One that
    yields is cut short and passes; one that never yields, or that catches
    the cancellation and returns anyway, fails.

    This asks whether the subject can be interrupted at all, not how
    quickly it notices.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.honours_deadline() for the rules this
    shares with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        fn: A coroutine function, called with no arguments.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.honours_deadline(seat, client.fetch, "the fetch has a deadline")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.honours_deadline(seat, _MODE, fn, msg)


def completes_within(
    seat: Seat, within: float, fn: Callable[[], Any], msg: str
) -> None:
    """Record a failure when fn takes longer than within seconds.

    fn is measured, not interrupted: a slow subject runs to completion
    and then fails. This spends real time, up to however long fn takes.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.completes_within() for the rules this
    shares with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        within: The ceiling, in seconds.
        fn: Called with no arguments.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.completes_within(seat, 0.5, index.rebuild, "rebuilds stay quick")
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
    """Record a failure when fn changes what observe reads.

    observe is read before and after fn, and the two readings must be
    equal by the rules of equal(). What observe returns defines what
    nothing means: whatever it leaves out, fn may change.

    Return a copy from observe. A projection sharing memory with the
    subject reads the same object twice and passes whatever fn did.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.is_pure() for the rules this shares with
    the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        observe: Called before and after fn; returns a projection of state.
        fn: The call that must change nothing observed.
        msg: The contract under test. It is the first line of the failure.
        *options: Relaxations for this call alone, from dokimi_assert.option.

    Example:
        expect.is_pure(seat, store.snapshot, reader.peek, "peek changes nothing")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.is_pure(seat, _MODE, observe, fn, msg, *options)


def none_handle_safe(seat: Seat, fn: Callable[[Any], Any], msg: str) -> None:
    """Record a failure when fn crashes on a None handle.

    Raising an error of its own is fine and is usually the right answer.
    What fails here is dereferencing the None, which is what a caller hits
    by accident and a middlebox by omission.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.none_handle_safe() for the rules this
    shares with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        fn: Called with a single argument, None.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.none_handle_safe(seat, worker.attach, "no handle is not fatal")
    """
    __tracebackhide__ = True
    seat.helper()
    behaviour.none_handle_safe(seat, _MODE, fn, msg)


def eventually(
    seat: Seat,
    timeout: float,
    interval: float,
    body: Callable[[Any], None],
    msg: str,
) -> None:
    """Record a failure when a body of assertions never passes in time.

    The body is called with a seat of its own, so assertions inside it
    record an attempt rather than ending the test. It runs at least once
    however short the timeout, and the failure carries the last attempt's
    own reason rather than a bare timeout.

    This spends real time. It is for a condition something outside the
    test makes true; where the subject reads a clock the test controls,
    drive that clock and assert the answer instead.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.eventually() for the rules this shares
    with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        timeout: How long to keep retrying, in seconds.
        interval: How long to wait between attempts, in seconds.
        body: Called with a seat; states the condition as assertions.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.eventually(seat, 5.0, 0.1, settled, "the cache converges")
    """
    __tracebackhide__ = True
    seat.helper()
    waiting.eventually(seat, _MODE, timeout, interval, body, msg)


def eventually_true(
    seat: Seat, timeout: float, predicate: Callable[[], bool], msg: str
) -> None:
    """Record a failure when a predicate never becomes true in time.

    Retried with a backoff that starts small and doubles. A predicate
    carries no reason, so the failure says only that the wait ran out;
    where the reason matters, write the condition as assertions and use
    eventually(). This spends real time for the same reason.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.eventually_true() for the rules this
    shares with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        timeout: How long to keep retrying, in seconds.
        predicate: Called with no arguments; must eventually answer True.
        msg: The contract under test. It is the first line of the failure.

    Example:
        expect.eventually_true(seat, 5.0, queue.is_drained, "the queue drains")
    """
    __tracebackhide__ = True
    seat.helper()
    waiting.eventually_true(seat, _MODE, timeout, predicate, msg)


def no_task_leaks(seat: Seat, msg: str) -> Callable[[], None]:
    """Answer a callable that records a failure when a task outlives the scope.

    Any asyncio task started after this call and still running when the
    returned callable runs is a leak, which is how a cancelled request
    leaves work going behind it.

    The test carries on either way, and everything recorded is reported when
    the test body ends. See check.no_task_leaks() for the rules this shares
    with the aborting surface.

    Args:
        seat: Where the failure is reported. Use the seat fixture.
        msg: The contract under test. It is the first line of the failure.

    Returns:
        A callable to invoke where the scope ends. It reports the leak.

    Example:
        done = expect.no_task_leaks(seat, "the handler cleans up")
        await handler.serve(request)
        done()
    """
    __tracebackhide__ = True
    seat.helper()
    return waiting.no_task_leaks(seat, _MODE, msg)
