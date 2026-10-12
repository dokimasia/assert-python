"""The spec of _prop/forms.py tests the property forms.

Each form passes a true property, and it fails a false property with its
record.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable
from typing import Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._matcher.seat import Seat
from dokimi_assert._prop import forms
from dokimi_assert._prop import generators as prop
from dokimi_assert._prop.option import hermetic, seed, store, using
from dokimi_assert.option import equate_nans
from dokimi_assert.seat import Collector, Recorder
from helpers import subtract

#: The options of a reproducible run of the digits as the ints of an input.
DIGITS = (using(int, prop.integer(0, 9)), hermetic(), seed(1), store(""))

#: The sentinel error of the error forms.
SENTINEL = ValueError("the sentinel")

#: The contract of every form of this spec.
MSG = "the property is true"


class Counter:
    """A count that each call of a step raises by one."""

    def __init__(self) -> None:
        """Return a count of 0."""
        self.count: int = 0

    def step(self, _: int) -> int:
        """Raise the count by one, and return it."""
        self.count += 1
        return self.count

    def read(self) -> int:
        """Return the count."""
        return self.count


class Cell:
    """A cell of one value. Each put replaces the value."""

    def __init__(self) -> None:
        """Return a cell of 0."""
        self.value: int = 0

    def put(self, x: int) -> None:
        """Replace the value with x."""
        self.value = x

    def get(self) -> int:
        """Return the value."""
        return self.value


def same(x: int) -> int:
    """Return x."""
    return x


def zero(_: int) -> int:
    """Return 0."""
    return 0


def plus_one(x: int) -> int:
    """Return x plus one."""
    return x + 1


def not_negative(x: int) -> bool:
    """Report whether x is 0 or more."""
    return x >= 0


def below_five(x: int) -> bool:
    """Report whether x is below 5."""
    return x < 5


def negative(x: int) -> bool:
    """Report whether x is below 0."""
    return x < 0


def five_or_more(x: int) -> bool:
    """Report whether x is 5 or more."""
    return x >= 5


def nothing(_: int) -> None:
    """Return None."""


def listed(x: int) -> list[int]:
    """Return the list of x."""
    return [x]


def empty_list(_: int) -> list[int]:
    """Return an empty list."""
    return []


def empty_text(_: int) -> str:
    """Return an empty str."""
    return ""


def with_zero(x: int) -> list[int]:
    """Return x and 0."""
    return [x, 0]


def wrapped(x: int) -> str:
    """Return x between a and b."""
    return f"a{x}b"


def text(x: int) -> str:
    """Return the decimal text of x."""
    return str(x)


def prefixed(x: int) -> str:
    """Return x after a."""
    return f"a{x}"


def suffixed(x: int) -> str:
    """Return x before b."""
    return f"{x}b"


def with_one(x: int) -> list[int]:
    """Return x and 1."""
    return [x, 1]


def one_with(x: int) -> list[int]:
    """Return 1 and x."""
    return [1, x]


def ten(_: int) -> list[int]:
    """Return the list of 10."""
    return [10]


def ascending(x: int) -> list[int]:
    """Return x and x plus one."""
    return [x, x + 1]


def repeated(x: int) -> list[int]:
    """Return x twice."""
    return [x, x]


def less(a: int, b: int) -> bool:
    """Report whether a is below b."""
    return a < b


def big_error(x: int) -> Exception | None:
    """Return an error for a digit of 5 or more."""
    return ValueError("big") if x >= 5 else None


def an_error(_: int) -> Exception:
    """Return a ValueError."""
    return ValueError("e")


def no_exception(_: int) -> Exception | None:
    """Return None."""
    return None


def sentinel(_: int) -> Exception:
    """Return the sentinel."""
    return SENTINEL


def type_error(_: int) -> Exception:
    """Return a TypeError."""
    return TypeError("t")


def raise_value_error(_: int) -> None:
    """Raise a ValueError."""
    raise ValueError("e")


def raises_when_big(x: int) -> None:
    """Raise a ValueError for a digit of 5 or more."""
    if x >= 5:
        raise ValueError("big")


def nan(_: int) -> float:
    """Return NaN."""
    return math.nan


def add(a: int, b: int) -> int:
    """Return a plus b."""
    return a + b


def ignores_the_handle(handle: object, x: int) -> int:
    """Return x. The function does not read the handle."""
    del handle
    return x


def reads_the_handle(handle: Any, _: int) -> Any:
    """Read an attribute of the handle without a check."""
    return handle.cancelled()


async def awaits(_: int) -> None:
    """Await once. A cancellation or a deadline stops the coroutine at the await."""
    await asyncio.sleep(0)


async def returns_at_once(_: int) -> None:
    """Return before any await."""


def zero_of_text(_: str) -> int:
    """Return 0 for any text."""
    return 0


def pure_with_a_counter(s: Seat) -> None:
    """Check that a step of a counter does not change the counter."""
    state = Counter()
    forms.is_pure(s, state.read, state.step, MSG, *DIGITS)


def not_pure_with_a_counter(s: Seat) -> None:
    """Check that a step of a counter changes the counter."""
    state = Counter()
    forms.is_not_pure(s, state.read, state.step, MSG, *DIGITS)


def idempotent_with_a_cell(s: Seat) -> None:
    """Check that a second put of a cell does not change the cell."""
    cell = Cell()
    forms.is_idempotent(s, cell.put, cell.get, MSG, *DIGITS)


def idempotent_with_a_counter(s: Seat) -> None:
    """Check that a second step of a counter does not change the counter."""
    state = Counter()
    forms.is_idempotent(s, state.step, state.read, MSG, *DIGITS)


def accumulates_with_a_counter(s: Seat) -> None:
    """Check that each step of a counter raises the counter by the same amount."""
    state = Counter()
    forms.accumulates(s, state.step, state.read, MSG, *DIGITS)


def deterministic_with_a_counter(s: Seat) -> None:
    """Check that each step of a counter returns the same count."""
    forms.is_deterministic(s, Counter().step, MSG, *DIGITS)


#: One form. A row has the Python name of the form, the id of its assertion,
#: a call that passes, a call that fails, and a call that passes only under
#: its relaxation.
Row = tuple[
    str,
    str,
    Callable[[Seat], None],
    Callable[[Seat], None],
    Callable[[Seat], None] | None,
]

#: The forms of the spec.
ROWS: list[Row] = [
    (
        "equal",
        "equal",
        lambda s: forms.equal(s, same, same, MSG, *DIGITS),
        lambda s: forms.equal(s, same, zero, MSG, *DIGITS),
        lambda s: forms.equal(s, nan, nan, MSG, equate_nans(), *DIGITS),
    ),
    (
        "not_equal",
        "not-equal",
        lambda s: forms.not_equal(s, same, plus_one, MSG, *DIGITS),
        lambda s: forms.not_equal(s, same, same, MSG, *DIGITS),
        None,
    ),
    (
        "is_true",
        "true",
        lambda s: forms.is_true(s, not_negative, MSG, *DIGITS),
        lambda s: forms.is_true(s, below_five, MSG, *DIGITS),
        None,
    ),
    (
        "is_false",
        "false",
        lambda s: forms.is_false(s, negative, MSG, *DIGITS),
        lambda s: forms.is_false(s, five_or_more, MSG, *DIGITS),
        None,
    ),
    (
        "is_none",
        "nil",
        lambda s: forms.is_none(s, nothing, MSG, *DIGITS),
        lambda s: forms.is_none(s, same, MSG, *DIGITS),
        None,
    ),
    (
        "is_not_none",
        "not-nil",
        lambda s: forms.is_not_none(s, same, MSG, *DIGITS),
        lambda s: forms.is_not_none(s, nothing, MSG, *DIGITS),
        None,
    ),
    (
        "length",
        "length",
        lambda s: forms.length(s, listed, 1, MSG, *DIGITS),
        lambda s: forms.length(s, listed, 2, MSG, *DIGITS),
        None,
    ),
    (
        "is_empty",
        "empty",
        lambda s: forms.is_empty(s, empty_list, MSG, *DIGITS),
        lambda s: forms.is_empty(s, listed, MSG, *DIGITS),
        None,
    ),
    (
        "is_not_empty",
        "not-empty",
        lambda s: forms.is_not_empty(s, listed, MSG, *DIGITS),
        lambda s: forms.is_not_empty(s, empty_text, MSG, *DIGITS),
        None,
    ),
    (
        "contains",
        "contains",
        lambda s: forms.contains(s, with_zero, 0, MSG, *DIGITS),
        lambda s: forms.contains(s, listed, 10, MSG, *DIGITS),
        None,
    ),
    (
        "not_contains",
        "not-contains",
        lambda s: forms.not_contains(s, listed, 10, MSG, *DIGITS),
        lambda s: forms.not_contains(s, with_zero, 0, MSG, *DIGITS),
        None,
    ),
    (
        "contains_in_order",
        "contains-in-order",
        lambda s: forms.contains_in_order(s, wrapped, ["a", "b"], MSG, *DIGITS),
        lambda s: forms.contains_in_order(s, text, ["a"], MSG, *DIGITS),
        None,
    ),
    (
        "is_permutation",
        "permutation",
        lambda s: forms.is_permutation(s, with_one, one_with, MSG, *DIGITS),
        lambda s: forms.is_permutation(s, listed, ten, MSG, *DIGITS),
        None,
    ),
    (
        "has_prefix",
        "has-prefix",
        lambda s: forms.has_prefix(s, prefixed, "a", MSG, *DIGITS),
        lambda s: forms.has_prefix(s, text, "a", MSG, *DIGITS),
        None,
    ),
    (
        "has_suffix",
        "has-suffix",
        lambda s: forms.has_suffix(s, suffixed, "b", MSG, *DIGITS),
        lambda s: forms.has_suffix(s, text, "b", MSG, *DIGITS),
        None,
    ),
    (
        "matches",
        "matches",
        lambda s: forms.matches(s, text, "^[0-9]$", MSG, *DIGITS),
        lambda s: forms.matches(s, text, "^a", MSG, *DIGITS),
        None,
    ),
    (
        "close_to",
        "close-to",
        lambda s: forms.close_to(s, same, 5, 5, MSG, *DIGITS),
        lambda s: forms.close_to(s, same, 0, 0.5, MSG, *DIGITS),
        None,
    ),
    (
        "in_range",
        "in-range",
        lambda s: forms.in_range(s, same, 0, 9, MSG, *DIGITS),
        lambda s: forms.in_range(s, same, 0, 4, MSG, *DIGITS),
        None,
    ),
    (
        "pairwise",
        "pairwise",
        lambda s: forms.pairwise(s, ascending, less, MSG, *DIGITS),
        lambda s: forms.pairwise(s, repeated, less, MSG, *DIGITS),
        None,
    ),
    (
        "no_error",
        "err-absent",
        lambda s: forms.no_error(s, no_exception, MSG, *DIGITS),
        lambda s: forms.no_error(s, big_error, MSG, *DIGITS),
        None,
    ),
    (
        "has_error",
        "err-present",
        lambda s: forms.has_error(s, an_error, MSG, *DIGITS),
        lambda s: forms.has_error(s, no_exception, MSG, *DIGITS),
        None,
    ),
    (
        "error_is",
        "err-is",
        lambda s: forms.error_is(s, sentinel, SENTINEL, MSG, *DIGITS),
        lambda s: forms.error_is(s, no_exception, SENTINEL, MSG, *DIGITS),
        None,
    ),
    (
        "error_is_not",
        "err-is-not",
        lambda s: forms.error_is_not(s, no_exception, SENTINEL, MSG, *DIGITS),
        lambda s: forms.error_is_not(s, sentinel, SENTINEL, MSG, *DIGITS),
        None,
    ),
    (
        "error_as",
        "err-as",
        lambda s: forms.error_as(s, type_error, TypeError, MSG, *DIGITS),
        lambda s: forms.error_as(s, an_error, TypeError, MSG, *DIGITS),
        None,
    ),
    (
        "raises",
        "throws",
        lambda s: forms.raises(s, raise_value_error, MSG, *DIGITS),
        lambda s: forms.raises(s, same, MSG, *DIGITS),
        None,
    ),
    (
        "does_not_raise",
        "not-throws",
        lambda s: forms.does_not_raise(s, same, MSG, *DIGITS),
        lambda s: forms.does_not_raise(s, raises_when_big, MSG, *DIGITS),
        None,
    ),
    (
        "is_pure",
        "pure",
        lambda s: forms.is_pure(s, Counter().read, same, MSG, *DIGITS),
        pure_with_a_counter,
        None,
    ),
    (
        "is_not_pure",
        "not-pure",
        not_pure_with_a_counter,
        lambda s: forms.is_not_pure(s, Counter().read, same, MSG, *DIGITS),
        None,
    ),
    (
        "none_handle_safe",
        "nil-context-safe",
        lambda s: forms.none_handle_safe(s, ignores_the_handle, MSG, *DIGITS),
        lambda s: forms.none_handle_safe(s, reads_the_handle, MSG, *DIGITS),
        None,
    ),
    (
        "honours_cancellation",
        "honours-cancellation",
        lambda s: forms.honours_cancellation(s, awaits, MSG, *DIGITS),
        lambda s: forms.honours_cancellation(s, returns_at_once, MSG, *DIGITS),
        None,
    ),
    (
        "honours_deadline",
        "honours-deadline",
        lambda s: forms.honours_deadline(s, awaits, MSG, *DIGITS),
        lambda s: forms.honours_deadline(s, returns_at_once, MSG, *DIGITS),
        None,
    ),
    (
        "is_idempotent",
        "idempotent",
        idempotent_with_a_cell,
        idempotent_with_a_counter,
        None,
    ),
    (
        "accumulates",
        "accumulates",
        accumulates_with_a_counter,
        lambda s: forms.accumulates(s, nothing, Counter().read, MSG, *DIGITS),
        None,
    ),
    (
        "is_deterministic",
        "deterministic",
        lambda s: forms.is_deterministic(s, same, MSG, *DIGITS),
        deterministic_with_a_counter,
        None,
    ),
    (
        "is_commutative",
        "commutative",
        lambda s: forms.is_commutative(s, add, MSG, *DIGITS),
        lambda s: forms.is_commutative(s, subtract, MSG, *DIGITS),
        None,
    ),
    (
        "is_associative",
        "associative",
        lambda s: forms.is_associative(s, add, MSG, *DIGITS),
        lambda s: forms.is_associative(s, subtract, MSG, *DIGITS),
        None,
    ),
    (
        "round_trip",
        "round-trip",
        lambda s: forms.round_trip(s, text, int, MSG, *DIGITS),
        lambda s: forms.round_trip(s, text, zero_of_text, MSG, *DIGITS),
        None,
    ),
]


class TestFormIds:
    """FORM_IDS has the ids of the property forms."""

    def test_contains_the_id_of_every_form_that_the_module_exports(
        self, seat: Collector
    ) -> None:
        """The module exports 37 forms."""
        check.equal(
            seat,
            forms.FORM_IDS,
            tuple(f"prop-{row[1]}" for row in ROWS),
            "FORM_IDS has the 37 ids",
        )


class TestForms:
    """Each property form passes a true property and fails a false one."""

    rows: ClassVar[list[Row]] = ROWS

    @pytest.mark.parametrize("give", [row[2] for row in rows], ids=[r[0] for r in rows])
    def test_passes_a_property_that_is_true_for_every_input(
        self, seat: Collector, give: Callable[[Seat], None]
    ) -> None:
        """The call does not record a failure."""
        recorder = Recorder()
        give(recorder)
        check.equal(
            seat, [recorder.failures, recorder.message], [[], ""], "the form passes"
        )

    @pytest.mark.parametrize(
        ("assertion", "give"),
        [(row[1], row[3]) for row in rows],
        ids=[r[0] for r in rows],
    )
    def test_fails_with_the_record_of_the_form_whose_case_failed_its_assertion(
        self, seat: Collector, assertion: str, give: Callable[[Seat], None]
    ) -> None:
        """The record of the form has the failure of its case."""
        recorder = Recorder()
        give(recorder)
        failure = recorder.failures[0]
        check.equal(
            seat,
            [failure.assertion, failure.contract, failure.detail["failure"].assertion],
            [f"prop-{assertion}", MSG, assertion],
            "the form fails with its record",
        )

    def test_calls_a_relation_of_one_input_with_each_parameter_of_its_function(
        self, seat: Collector
    ) -> None:
        """The function add takes two ints."""
        recorder = Recorder()
        forms.is_deterministic(recorder, add, MSG, *DIGITS)
        check.equal(
            seat, [recorder.failures, recorder.message], [[], ""], "the form passes"
        )

    relaxed: ClassVar[list[Row]] = [row for row in ROWS if row[4] is not None]

    @pytest.mark.parametrize(
        "give", [row[4] for row in relaxed], ids=[r[0] for r in relaxed]
    )
    def test_passes_the_relaxations_to_the_assertion(
        self, seat: Collector, give: Callable[[Seat], None]
    ) -> None:
        """The relaxation applies."""
        recorder = Recorder()
        give(recorder)
        check.is_empty(seat, recorder.failures, "the form passes")
