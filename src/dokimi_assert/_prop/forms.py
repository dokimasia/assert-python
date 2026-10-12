"""The property forms.

Each form runs an assertion on every case of a run in the same way as for_all
runs a body. A form that does not pass fails the test with one record of the
id of the form. The id is prop- followed by the id of the assertion. The
detail of the record has the fields of prop-for-all, and its failure is the
record of the assertion on the minimal case.

A form takes a function of the generated input where its assertion takes
the value that it checks. The form reads the type of the input from the
annotation of the first parameter of that function, and generates a value
of the type. For a function of more than one parameter, the form generates
the parameters in order as the fields of a record. A form of a relation
generates the arguments that the relation takes. is_commutative generates a
and b, and is_associative generates a, b and c.

Every form takes the options of a run, the generators that using gives
types, and the cases of example and examples. A form whose assertion takes
relaxations takes them too.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from dokimi_assert._matcher import behaviour, errors, order, relation, value
from dokimi_assert._matcher import raises as raising
from dokimi_assert._matcher.seat import Mode, Seat
from dokimi_assert._prop.form import INPUT, PAIR, TRIPLE, Form, run_form
from dokimi_assert._prop.option import FormOption

__all__ = [
    "FORM_IDS",
    "accumulates",
    "close_to",
    "contains",
    "contains_in_order",
    "does_not_raise",
    "equal",
    "error_as",
    "error_is",
    "error_is_not",
    "has_error",
    "has_prefix",
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
    "is_none",
    "is_not_empty",
    "is_not_none",
    "is_not_pure",
    "is_permutation",
    "is_pure",
    "is_true",
    "length",
    "matches",
    "no_error",
    "none_handle_safe",
    "not_contains",
    "not_equal",
    "pairwise",
    "raises",
    "round_trip",
]

#: The mode of the assertion of every form. The assertion stops the case at
#: its failure.
_MODE = Mode.FATAL


def _form(
    name: str,
    id: str,
    relaxed: bool,
    labels: tuple[str, ...] = INPUT,
    skip: int = 0,
) -> Form:
    """Return the form of the assertion id. Its Python name is name."""
    return Form(f"prop.{name}", f"prop-{id}", relaxed, labels, skip)


#: The forms, by their Python names.
_FORMS: dict[str, Form] = {
    "equal": _form("equal", "equal", True),
    "not_equal": _form("not_equal", "not-equal", True),
    "is_true": _form("is_true", "true", False),
    "is_false": _form("is_false", "false", False),
    "is_none": _form("is_none", "nil", False),
    "is_not_none": _form("is_not_none", "not-nil", False),
    "length": _form("length", "length", False),
    "is_empty": _form("is_empty", "empty", False),
    "is_not_empty": _form("is_not_empty", "not-empty", False),
    "contains": _form("contains", "contains", True),
    "not_contains": _form("not_contains", "not-contains", True),
    "contains_in_order": _form("contains_in_order", "contains-in-order", False),
    "is_permutation": _form("is_permutation", "permutation", True),
    "has_prefix": _form("has_prefix", "has-prefix", False),
    "has_suffix": _form("has_suffix", "has-suffix", False),
    "matches": _form("matches", "matches", False),
    "close_to": _form("close_to", "close-to", False),
    "in_range": _form("in_range", "in-range", False),
    "pairwise": _form("pairwise", "pairwise", False),
    "no_error": _form("no_error", "err-absent", False),
    "has_error": _form("has_error", "err-present", False),
    "error_is": _form("error_is", "err-is", False),
    "error_is_not": _form("error_is_not", "err-is-not", False),
    "error_as": _form("error_as", "err-as", False),
    "raises": _form("raises", "throws", False),
    "does_not_raise": _form("does_not_raise", "not-throws", False),
    "is_pure": _form("is_pure", "pure", True),
    "is_not_pure": _form("is_not_pure", "not-pure", True),
    "none_handle_safe": _form("none_handle_safe", "nil-context-safe", False, skip=1),
    "honours_cancellation": _form(
        "honours_cancellation", "honours-cancellation", False
    ),
    "honours_deadline": _form("honours_deadline", "honours-deadline", False),
    "is_idempotent": _form("is_idempotent", "idempotent", True),
    "accumulates": _form("accumulates", "accumulates", False),
    "is_deterministic": _form("is_deterministic", "deterministic", True),
    "is_commutative": _form("is_commutative", "commutative", True, PAIR),
    "is_associative": _form("is_associative", "associative", True, TRIPLE),
    "round_trip": _form("round_trip", "round-trip", True),
}

#: The ids of the property forms. The record of a form has its id as its
#: assertion.
FORM_IDS: tuple[str, ...] = tuple(form.id for form in _FORMS.values())


def _single(
    function: Callable[..., Any], args: tuple[Any, ...]
) -> tuple[Callable[[Any], Any], Any]:
    """Return a function of one value and that value, for a relation of one input.

    A function of more than one parameter takes the tuple of the values of
    its parameters.
    """
    if len(args) == 1:
        return function, args[0]
    return (lambda values: function(*values)), args


def equal(
    seat: Seat,
    got: Callable[..., Any],
    want: Callable[..., Any],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when got and want return different values for a generated input.

    It is the form prop-equal of equal, and it takes the relaxations of
    equal. got takes the input.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the value that the code under test produces.
        want: Returns the value that the code under test is supposed to
            produce.
        msg: The contract under test.
        *options: The options of the run and of the form, and the
            relaxations.

    Example:
        prop.equal(seat, sort_twice, sort_once, "sorting is idempotent")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["equal"],
        msg,
        got,
        options,
        lambda c, args, relax: value.equal(
            c, _MODE, got(*args), want(*args), msg, *relax
        ),
    )


def not_equal(
    seat: Seat,
    got: Callable[..., Any],
    want: Callable[..., Any],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when got and want return equal values for a generated input.

    It is the form prop-not-equal of not_equal, and it takes the
    relaxations of not_equal. got takes the input.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the value that the code under test produces.
        want: Returns the value that the result must not equal.
        msg: The contract under test.
        *options: The options of the run and of the form, and the
            relaxations.

    Example:
        prop.not_equal(seat, hash_of, hash_with_suffix, "a suffix changes the hash")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["not_equal"],
        msg,
        got,
        options,
        lambda c, args, relax: value.not_equal(
            c, _MODE, got(*args), want(*args), msg, *relax
        ),
    )


def is_true(
    seat: Seat, condition: Callable[..., object], msg: str, *options: FormOption
) -> None:
    """Fail when condition is false for a generated input.

    It is the form prop-true of is_true.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        condition: Returns the condition for the input.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.is_true(seat, is_not_negative, "abs is never negative")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["is_true"],
        msg,
        condition,
        options,
        lambda c, args, _: value.is_true(c, _MODE, condition(*args), msg),
    )


def is_false(
    seat: Seat, condition: Callable[..., object], msg: str, *options: FormOption
) -> None:
    """Fail when condition is true for a generated input.

    It is the form prop-false of is_false.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        condition: Returns the condition for the input.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.is_false(seat, has_line_break, "a slug does not have a line break")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["is_false"],
        msg,
        condition,
        options,
        lambda c, args, _: value.is_false(c, _MODE, condition(*args), msg),
    )


def is_none(
    seat: Seat, got: Callable[..., Any], msg: str, *options: FormOption
) -> None:
    """Fail when got returns a value other than None for a generated input.

    It is the form prop-nil of is_none.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the value for the input.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.is_none(seat, lookup_in_empty, "an empty map does not have an entry")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["is_none"],
        msg,
        got,
        options,
        lambda c, args, _: value.is_none(c, _MODE, got(*args), msg),
    )


def is_not_none(
    seat: Seat, got: Callable[..., Any], msg: str, *options: FormOption
) -> None:
    """Fail when got returns None for a generated input.

    It is the form prop-not-nil of is_not_none.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the value for the input.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.is_not_none(seat, lookup_seeded, "every seeded id is stored")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["is_not_none"],
        msg,
        got,
        options,
        lambda c, args, _: value.is_not_none(c, _MODE, got(*args), msg),
    )


def length(
    seat: Seat, got: Callable[..., Any], want: int, msg: str, *options: FormOption
) -> None:
    """Fail when the value that got returns for a generated input is not of length want.

    It is the form prop-length of length.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the value for the input.
        want: The length of the value.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.length(seat, digest, 32, "a digest has 32 bytes")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["length"],
        msg,
        got,
        options,
        lambda c, args, _: value.length(c, _MODE, got(*args), want, msg),
    )


def is_empty(
    seat: Seat, got: Callable[..., Any], msg: str, *options: FormOption
) -> None:
    """Fail when got returns a value that is not empty for a generated input.

    It is the form prop-empty of is_empty.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the value for the input.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.is_empty(seat, diff_with_itself, "a list does not differ from itself")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["is_empty"],
        msg,
        got,
        options,
        lambda c, args, _: value.is_empty(c, _MODE, got(*args), msg),
    )


def is_not_empty(
    seat: Seat, got: Callable[..., Any], msg: str, *options: FormOption
) -> None:
    """Fail when got returns an empty value for a generated input.

    It is the form prop-not-empty of is_not_empty.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the value for the input.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.is_not_empty(seat, slug, "a slug is never empty")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["is_not_empty"],
        msg,
        got,
        options,
        lambda c, args, _: value.is_not_empty(c, _MODE, got(*args), msg),
    )


def contains(
    seat: Seat,
    got: Callable[..., Any],
    needle: Any,
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when got returns a haystack without needle for a generated input.

    It is the form prop-contains of contains, and it takes the relaxations
    of contains.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the haystack for the input.
        needle: The element, the key or the substring of the haystack.
        msg: The contract under test.
        *options: The options of the run and of the form, and the
            relaxations.

    Example:
        prop.contains(seat, with_sentinel, -1, "the sentinel is added")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["contains"],
        msg,
        got,
        options,
        lambda c, args, relax: value.contains(
            c, _MODE, got(*args), needle, msg, *relax
        ),
    )


def not_contains(
    seat: Seat,
    got: Callable[..., Any],
    needle: Any,
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when the value that got returns for a generated input contains needle.

    It is the form prop-not-contains of not_contains, and it takes the
    relaxations of not_contains.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the haystack for the input.
        needle: The element, the key or the substring that the haystack
            must not contain.
        msg: The contract under test.
        *options: The options of the run and of the form, and the
            relaxations.

    Example:
        prop.not_contains(seat, escape, "<", "escaping removes every <")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["not_contains"],
        msg,
        got,
        options,
        lambda c, args, relax: value.not_contains(
            c, _MODE, got(*args), needle, msg, *relax
        ),
    )


def contains_in_order(
    seat: Seat,
    got: Callable[..., Any],
    needles: Sequence[str],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when got returns a text without needles in order for a generated input.

    It is the form prop-contains-in-order of contains_in_order.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the text for the input.
        needles: The substrings of the text in their order.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.contains_in_order(seat, greet, ["Hello", "!"], "a greeting is complete")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["contains_in_order"],
        msg,
        got,
        options,
        lambda c, args, _: value.contains_in_order(c, _MODE, got(*args), needles, msg),
    )


def is_permutation(
    seat: Seat,
    got: Callable[..., Any],
    want: Callable[..., Any],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when got does not return an ordering of what want returns for an input.

    It is the form prop-permutation of is_permutation, and it takes the
    relaxations of is_permutation. got takes the input.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the elements that the code under test produces.
        want: Returns the elements. The result of got must be an ordering of
            them.
        msg: The contract under test.
        *options: The options of the run and of the form, and the
            relaxations.

    Example:
        prop.is_permutation(seat, shuffle, identity, "a shuffle keeps every element")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["is_permutation"],
        msg,
        got,
        options,
        lambda c, args, relax: relation.is_permutation(
            c, _MODE, got(*args), want(*args), msg, *relax
        ),
    )


def has_prefix(
    seat: Seat,
    got: Callable[..., Any],
    prefix: str,
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when got returns a text without the prefix for a generated input.

    It is the form prop-has-prefix of has_prefix.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the text for the input.
        prefix: The start of the text.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.has_prefix(seat, key_of, "user:", "every key has a namespace")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["has_prefix"],
        msg,
        got,
        options,
        lambda c, args, _: value.has_prefix(c, _MODE, got(*args), prefix, msg),
    )


def has_suffix(
    seat: Seat,
    got: Callable[..., Any],
    suffix: str,
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when got returns a text without the suffix for a generated input.

    It is the form prop-has-suffix of has_suffix.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the text for the input.
        suffix: The end of the text.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.has_suffix(seat, sentence_of, ".", "a sentence ends in a period")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["has_suffix"],
        msg,
        got,
        options,
        lambda c, args, _: value.has_suffix(c, _MODE, got(*args), suffix, msg),
    )


def matches(
    seat: Seat,
    got: Callable[..., Any],
    pattern: str,
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when pattern does not match the text that got returns for a generated input.

    It is the form prop-matches of matches.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the text for the input.
        pattern: A pattern of the portable subset.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.matches(seat, format_number, "^-?[0-9]+$", "a number formats as digits")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["matches"],
        msg,
        got,
        options,
        lambda c, args, _: value.matches(c, _MODE, got(*args), pattern, msg),
    )


def close_to(
    seat: Seat,
    got: Callable[..., Any],
    want: float,
    tolerance: float,
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when got returns a number farther than tolerance from want for an input.

    It is the form prop-close-to of close_to.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the number for the input.
        want: The target number.
        tolerance: The largest difference from want.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.close_to(seat, sin_cos_sum, 1.0, 1e-9, "sin^2 + cos^2 is 1")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["close_to"],
        msg,
        got,
        options,
        lambda c, args, _: value.close_to(c, _MODE, got(*args), want, tolerance, msg),
    )


def in_range(
    seat: Seat,
    got: Callable[..., Any],
    low: float,
    high: float,
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when got returns a number outside [low, high] for a generated input.

    It is the form prop-in-range of in_range.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the number for the input.
        low: The smallest value.
        high: The largest value.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.in_range(seat, total, 0, 2**63 - 1, "a total is never negative")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["in_range"],
        msg,
        got,
        options,
        lambda c, args, _: value.in_range(c, _MODE, got(*args), low, high, msg),
    )


def pairwise(
    seat: Seat,
    got: Callable[..., Sequence[Any]],
    predicate: Callable[[Any, Any], object],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when predicate is false for two adjacent items of what got returns.

    It is the form prop-pairwise of pairwise. got takes the generated input,
    and predicate takes each pair of adjacent items with the earlier item
    first.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        got: Returns the sequence for the input.
        predicate: The relation of two adjacent items.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.pairwise(seat, sorted_digits, operator.le, "sorted orders the list")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["pairwise"],
        msg,
        got,
        options,
        lambda c, args, _: order.pairwise(c, _MODE, got(*args), predicate, msg),
    )


def no_error(
    seat: Seat,
    fn: Callable[..., BaseException | None],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when fn returns an error for a generated input.

    It is the form prop-err-absent of no_error.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: Returns the error for the input, or None.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.no_error(seat, validation_error, "every slug validates")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["no_error"],
        msg,
        fn,
        options,
        lambda c, args, _: errors.no_error(c, _MODE, fn(*args), msg),
    )


def has_error(
    seat: Seat,
    fn: Callable[..., BaseException | None],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when fn returns None for a generated input.

    It is the form prop-err-present of has_error.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: Returns the error for the input, or None.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.has_error(seat, error_with_leading_space, "a leading space is refused")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["has_error"],
        msg,
        fn,
        options,
        lambda c, args, _: errors.has_error(c, _MODE, fn(*args), msg),
    )


def error_is(
    seat: Seat,
    fn: Callable[..., BaseException | None],
    target: object,
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when fn returns an error whose chain does not match target for an input.

    It is the form prop-err-is of error_is.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: Returns the error for the input, or None.
        target: The error or the class that the chain must contain.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.error_is(seat, read_closed, StoreClosed, "a closed store refuses a read")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["error_is"],
        msg,
        fn,
        options,
        lambda c, args, _: errors.error_is(c, _MODE, fn(*args), target, msg),
    )


def error_is_not(
    seat: Seat,
    fn: Callable[..., BaseException | None],
    target: object,
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when fn returns an error whose chain matches target for a generated input.

    It is the form prop-err-is-not of error_is_not.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: Returns the error for the input, or None.
        target: The error or the class that the chain must not contain.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.error_is_not(seat, parse_error, TimeoutError, "parsing never times out")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["error_is_not"],
        msg,
        fn,
        options,
        lambda c, args, _: errors.error_is_not(c, _MODE, fn(*args), target, msg),
    )


def error_as(
    seat: Seat,
    fn: Callable[..., BaseException | None],
    want: type[BaseException],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when fn returns an error whose chain does not contain a want for an input.

    It is the form prop-err-as of error_as.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: Returns the error for the input, or None.
        want: The class of the error that the chain must contain.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.error_as(seat, add_taken, Conflict, "a taken id conflicts")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["error_as"],
        msg,
        fn,
        options,
        lambda c, args, _: errors.error_as(c, _MODE, fn(*args), want, msg),
    )


def raises(seat: Seat, fn: Callable[..., Any], msg: str, *options: FormOption) -> None:
    """Fail when a call of fn with a generated input does not raise.

    It is the form prop-throws of raises.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: Called with the input.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.raises(seat, parse_after_open_brace, "an open brace is refused")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["raises"],
        msg,
        fn,
        options,
        lambda c, args, _: raising.raises(c, _MODE, lambda: fn(*args), msg),
    )


def does_not_raise(
    seat: Seat, fn: Callable[..., Any], msg: str, *options: FormOption
) -> None:
    """Fail when a call of fn with a generated input raises.

    It is the form prop-not-throws of does_not_raise.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: Called with the input.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.does_not_raise(seat, decode, "decode does not raise")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["does_not_raise"],
        msg,
        fn,
        options,
        lambda c, args, _: raising.does_not_raise(c, _MODE, lambda: fn(*args), msg),
    )


def is_pure(
    seat: Seat,
    observe: Callable[[], Any],
    fn: Callable[..., Any],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when a call of fn with a generated input changes what observe returns.

    It is the form prop-pure of is_pure, and it takes the relaxations of
    is_pure. fn takes the input.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        observe: Returns a copy of the state that fn must not change.
        fn: Called with the input. It can be a coroutine function.
        msg: The contract under test.
        *options: The options of the run and of the form, and the
            relaxations.

    Example:
        prop.is_pure(seat, store.snapshot, store.peek, "peek does not change the store")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["is_pure"],
        msg,
        fn,
        options,
        lambda c, args, relax: behaviour.is_pure(
            c, _MODE, observe, lambda: fn(*args), msg, *relax
        ),
    )


def is_not_pure(
    seat: Seat,
    observe: Callable[[], Any],
    fn: Callable[..., Any],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when a call of fn with a generated input does not change the observed state.

    It is the form prop-not-pure of is_not_pure, and it takes the
    relaxations of is_not_pure. fn takes the input.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        observe: Returns a copy of the state that fn must change.
        fn: Called with the input. It can be a coroutine function.
        msg: The contract under test.
        *options: The options of the run and of the form, and the
            relaxations.

    Example:
        prop.is_not_pure(seat, log_length, log.append, "every write grows the log")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["is_not_pure"],
        msg,
        fn,
        options,
        lambda c, args, relax: relation.is_not_pure(
            c, _MODE, observe, lambda: fn(*args), msg, *relax
        ),
    )


def none_handle_safe(
    seat: Seat, fn: Callable[..., Any], msg: str, *options: FormOption
) -> None:
    """Fail when fn raises for None in place of a handle and a generated input.

    It is the form prop-nil-context-safe of none_handle_safe. The first
    parameter of fn takes the handle, and the type of the input is the
    annotation of its second parameter.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: Called with None and the input.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.none_handle_safe(seat, fetch, "a fetch works without a session")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["none_handle_safe"],
        msg,
        fn,
        options,
        lambda c, args, _: behaviour.none_handle_safe(
            c, _MODE, lambda handle: fn(handle, *args), msg
        ),
    )


def honours_cancellation(
    seat: Seat,
    fn: Callable[..., Awaitable[Any]],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when the coroutine of fn for an input does not stop when it is cancelled.

    It is the form prop-honours-cancellation of honours_cancellation.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: A coroutine function of the input.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.honours_cancellation(seat, run_job, "every job stops when it is cancelled")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["honours_cancellation"],
        msg,
        fn,
        options,
        lambda c, args, _: behaviour.honours_cancellation(
            c, _MODE, lambda: fn(*args), msg
        ),
    )


def honours_deadline(
    seat: Seat,
    fn: Callable[..., Awaitable[Any]],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when the coroutine of fn for an input does not stop at an expired deadline.

    It is the form prop-honours-deadline of honours_deadline.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        fn: A coroutine function of the input.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.honours_deadline(seat, fetch, "every fetch has a deadline")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["honours_deadline"],
        msg,
        fn,
        options,
        lambda c, args, _: behaviour.honours_deadline(c, _MODE, lambda: fn(*args), msg),
    )


def is_idempotent(
    seat: Seat,
    call: Callable[..., Any],
    observe: Callable[[], Any],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when a second call of call with an input changes what observe returns.

    It is the form prop-idempotent of is_idempotent, and it takes the
    relaxations of is_idempotent.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        call: Called twice with the input. It can be a coroutine function.
        observe: Returns a copy of the state after each call.
        msg: The contract under test.
        *options: The options of the run and of the form, and the
            relaxations.

    Example:
        prop.is_idempotent(seat, cart.remove, cart.items, "removing twice removes once")
    """
    __tracebackhide__ = True

    def check(c: Any, args: tuple[Any, ...], relax: tuple[Any, ...]) -> None:
        subject, input_value = _single(call, args)
        relation.is_idempotent(c, _MODE, subject, input_value, observe, msg, *relax)

    run_form(seat, _FORMS["is_idempotent"], msg, call, options, check)


def accumulates(
    seat: Seat,
    call: Callable[..., Any],
    observe: Callable[[], Any],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when two calls of call with an input change a number by different amounts.

    It is the form prop-accumulates of accumulates.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        call: Called twice with the input. It can be a coroutine function.
        observe: Returns the number after each call.
        msg: The contract under test.
        *options: The options of the run and of the form.

    Example:
        prop.accumulates(seat, counter.add, counter.total, "each add counts")
    """
    __tracebackhide__ = True

    def check(c: Any, args: tuple[Any, ...], _: tuple[Any, ...]) -> None:
        subject, input_value = _single(call, args)
        relation.accumulates(c, _MODE, subject, input_value, observe, msg)

    run_form(seat, _FORMS["accumulates"], msg, call, options, check)


def is_deterministic(
    seat: Seat, call: Callable[..., Any], msg: str, *options: FormOption
) -> None:
    """Fail when call returns different results for one generated input.

    It is the form prop-deterministic of is_deterministic, and it takes the
    relaxations of is_deterministic.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        call: Called 32 times with the input. It can be a coroutine
            function.
        msg: The contract under test.
        *options: The options of the run and of the form, and the
            relaxations.

    Example:
        prop.is_deterministic(seat, render, "rendering is deterministic")
    """
    __tracebackhide__ = True

    def check(c: Any, args: tuple[Any, ...], relax: tuple[Any, ...]) -> None:
        subject, input_value = _single(call, args)
        relation.is_deterministic(c, _MODE, subject, input_value, msg, *relax)

    run_form(seat, _FORMS["is_deterministic"], msg, call, options, check)


def is_commutative(
    seat: Seat,
    combine: Callable[[Any, Any], Any],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when combine(a, b) differs from combine(b, a) for generated a and b.

    It is the form prop-commutative of is_commutative, and it takes the
    relaxations of is_commutative. The type of a and b is the annotation of
    the first parameter of combine.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        combine: Combines two inputs. It can be a coroutine function.
        msg: The contract under test.
        *options: The options of the run and of the form, and the
            relaxations.

    Example:
        prop.is_commutative(seat, union, "union is commutative")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["is_commutative"],
        msg,
        combine,
        options,
        lambda c, args, relax: relation.is_commutative(
            c, _MODE, combine, args[0], args[1], msg, *relax
        ),
    )


def is_associative(
    seat: Seat,
    combine: Callable[[Any, Any], Any],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when the two groupings of combine differ for generated a, b and c.

    It is the form prop-associative of is_associative, and it takes the
    relaxations of is_associative. The type of a, b and c is the annotation
    of the first parameter of combine.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        combine: Combines two inputs. It can be a coroutine function.
        msg: The contract under test.
        *options: The options of the run and of the form, and the
            relaxations.

    Example:
        prop.is_associative(seat, operator.add, "addition is associative")
    """
    __tracebackhide__ = True
    run_form(
        seat,
        _FORMS["is_associative"],
        msg,
        combine,
        options,
        lambda c, args, relax: relation.is_associative(
            c, _MODE, combine, args[0], args[1], args[2], msg, *relax
        ),
    )


def round_trip(
    seat: Seat,
    forward: Callable[..., Any],
    inverse: Callable[[Any], Any],
    msg: str,
    *options: FormOption,
) -> None:
    """Fail when inverse does not return the input from what forward returns for it.

    It is the form prop-round-trip of round_trip, and it takes the
    relaxations of round_trip. forward takes the input.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        forward: Encodes the input. It can be a coroutine function.
        inverse: Decodes what forward returned. It can be a coroutine
            function.
        msg: The contract under test.
        *options: The options of the run and of the form, and the
            relaxations.

    Example:
        prop.round_trip(seat, encode, decode, "an encoded order decodes to itself")
    """
    __tracebackhide__ = True

    def check(c: Any, args: tuple[Any, ...], relax: tuple[Any, ...]) -> None:
        subject, input_value = _single(forward, args)
        relation.round_trip(c, _MODE, subject, inverse, input_value, msg, *relax)

    run_form(seat, _FORMS["round_trip"], msg, forward, options, check)
