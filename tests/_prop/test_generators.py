"""The spec of _prop/generators.py tests the generators of the property engine."""

from __future__ import annotations

import math
from collections.abc import Callable
from fractions import Fraction
from typing import Any, ClassVar, TypeVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._prop import generators as prop
from dokimi_assert._prop.engine.case import Case as Engine
from dokimi_assert._prop.engine.case import Replaying
from dokimi_assert._prop.engine.choice import Choice
from dokimi_assert._prop.engine.generator import Generator
from dokimi_assert._prop.engine.inverse import invert
from dokimi_assert._prop.engine.value import Pairs
from dokimi_assert.seat import Collector
from helpers import integers, refusal

_T = TypeVar("_T")

#: A generator of one digit.
DIGITS = prop.integer(0, 9)

#: The durations of the specs in nanoseconds. The bounds of the durations are
#: one second before zero and two days after it.
SECOND = 10**9
TWO_DAYS = 2 * 86_400 * SECOND


def decoded(generator: Generator[_T], *choices: Choice) -> _T:
    """Return the value that generator decodes from choices."""
    return Engine(Replaying([*choices])).draw(generator, "value")


def ints(*values: int) -> tuple[Choice, ...]:
    """Return integer choices of values."""
    return tuple(integers(*values))


def sequence(*values: int) -> Choice:
    """Return the sequence choice of values."""
    return Choice("sequence", values)


#: A case of a refusal. It has a name, the call, and the text of its ValueError.
Refusal = tuple[str, Callable[[], object], str]


class TestInteger:
    """integer returns the generator of the integers between two bounds."""

    def test_returns_the_int_of_a_choice(self, seat: Collector) -> None:
        """The choice is -3."""
        check.equal(
            seat,
            decoded(prop.integer(-5, 5), *ints(-3)),
            -3,
            "the value is the choice",
        )

    def test_returns_ints_up_to_two_to_the_64_minus_one(self, seat: Collector) -> None:
        """The choice is the largest unsigned 64-bit value."""
        check.equal(
            seat,
            decoded(prop.integer(0, 2**64 - 1), *ints(2**64 - 1)),
            2**64 - 1,
            "the value is 2^64 - 1",
        )

    def test_runs_an_int_back_to_one_choice(self, seat: Collector) -> None:
        """The inverse of 3 is the choice 3."""
        check.equal(seat, invert(DIGITS, 3), [*ints(3)], "the inverse is one choice")

    tests: ClassVar[list[Refusal]] = [
        (
            "a bound that is not an int",
            lambda: prop.integer(0, cast("Any", 1.5)),
            "prop: integer(0, 1.5) needs two ints",
        ),
        (
            "a bound that is a bool",
            lambda: prop.integer(cast("Any", False), 1),
            "prop: integer(False, 1) needs two ints",
        ),
        (
            "bounds out of order",
            lambda: prop.integer(5, 1),
            "prop: integer(5, 1): integer bounds [5, 1] are empty",
        ),
        (
            "bounds beyond both 64-bit ranges",
            lambda: prop.integer(-1, 2**64 - 1),
            f"prop: integer(-1, {2**64 - 1}): integer bounds [-1, {2**64 - 1}] are "
            "inside neither the signed nor the unsigned 64-bit range",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for(
        self, seat: Collector, give: Callable[[], object], want: str
    ) -> None:
        """The text of the refusal contains the call."""
        check.equal(
            seat, refusal(seat, give), want, "the error has the call and the reason"
        )


class TestFloat:
    """float returns the generator of the floats between two bounds."""

    def test_returns_the_float_of_a_choice(self, seat: Collector) -> None:
        """The choice is 0.5."""
        check.equal(
            seat,
            decoded(prop.float(0, 1), Choice("float", 0.5)),
            0.5,
            "the value is the choice",
        )

    def test_returns_nan_when_allow_nan_is_true(self, seat: Collector) -> None:
        """The choice is NaN."""
        value = decoded(prop.float(0, 1, allow_nan=True), Choice("float", math.nan))
        check.is_true(seat, math.isnan(value), "the value is NaN")

    tests: ClassVar[list[Refusal]] = [
        (
            "a bound that is not a number",
            lambda: prop.float(cast("Any", "a"), 1),
            "prop: float('a', 1) needs two numbers",
        ),
        (
            "bounds out of order",
            lambda: prop.float(2, 1),
            "prop: float(2, 1): float bounds [2.0, 1.0] are empty",
        ),
        (
            "a bound that is not a value of the width",
            lambda: prop.float(0.1, 1, width=32),
            "prop: float(0.1, 1): float bound 0.1 is not a value of width 32",
        ),
        (
            "a width that is neither 32 nor 64",
            lambda: prop.float(0, 1, width=cast("Any", 16)),
            "prop: float(0, 1): float width 16 is neither 32 nor 64",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for(
        self, seat: Collector, give: Callable[[], object], want: str
    ) -> None:
        """The text of the refusal contains the call."""
        check.equal(
            seat, refusal(seat, give), want, "the error has the call and the reason"
        )


class TestBoolean:
    """boolean returns the generator of bools."""

    def test_returns_the_bool_of_a_choice_of_0_or_1(self, seat: Collector) -> None:
        """The choices are 0 and 1."""
        check.equal(
            seat,
            [decoded(prop.boolean(), *ints(0)), decoded(prop.boolean(), *ints(1))],
            [False, True],
            "the values are False and True",
        )

    def test_takes_a_probability_of_an_int(self, seat: Collector) -> None:
        """The probability is 1."""
        check.is_true(seat, decoded(prop.boolean(1), *ints(1)), "the value is True")

    tests: ClassVar[list[Refusal]] = [
        (
            "a probability above 1",
            lambda: prop.boolean(Fraction(3, 2)),
            "prop: boolean(Fraction(3, 2)) needs a Fraction or an int from 0 to 1",
        ),
        (
            "a probability that is a float",
            lambda: prop.boolean(cast("Any", 0.5)),
            "prop: boolean(0.5) needs a Fraction or an int from 0 to 1",
        ),
        (
            "a probability that is a bool",
            lambda: prop.boolean(True),
            "prop: boolean(True) needs a Fraction or an int from 0 to 1",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for(
        self, seat: Collector, give: Callable[[], object], want: str
    ) -> None:
        """The text of the refusal contains the call."""
        check.equal(seat, refusal(seat, give), want, "the error has the call")


class TestJust:
    """just returns the generator of one value."""

    def test_returns_the_value_without_a_choice(self, seat: Collector) -> None:
        """The value is x."""
        engine = Engine(Replaying([]))
        check.equal(
            seat,
            [engine.draw(prop.just("x"), "v"), engine.choices],
            ["x", []],
            "the generator returns x without a choice",
        )


class TestSampledFrom:
    """sampled_from returns the generator of one of its values."""

    def test_returns_the_value_of_an_index(self, seat: Collector) -> None:
        """The index is 2."""
        check.equal(
            seat,
            decoded(prop.sampled_from("a", "b", "c"), *ints(2)),
            "c",
            "the value is the third value",
        )

    def test_raises_value_error_without_a_value(self, seat: Collector) -> None:
        """The call does not have a value."""
        check.equal(
            seat,
            refusal(seat, prop.sampled_from),
            "prop: sampled_from() needs a value",
            "the error has the call",
        )


class TestOneOf:
    """one_of returns the generator of a value of one of its generators."""

    def test_returns_a_value_of_the_generator_of_an_index(
        self, seat: Collector
    ) -> None:
        """The index is 1."""
        check.equal(
            seat,
            decoded(prop.one_of(prop.just(10), DIGITS), *ints(1, 4)),
            4,
            "the value is a value of the second generator",
        )

    def test_raises_value_error_without_a_generator(self, seat: Collector) -> None:
        """The call does not have a generator."""
        check.equal(
            seat,
            refusal(seat, prop.one_of),
            "prop: one_of() needs a generator",
            "the error has the call",
        )


class TestOptional:
    """optional returns the generator of a value or None."""

    def test_returns_none_only_for_an_absent_value(self, seat: Collector) -> None:
        """The first value is absent, and the second value is present."""
        check.equal(
            seat,
            [
                decoded(prop.optional(DIGITS), *ints(0)),
                decoded(prop.optional(DIGITS), *ints(1, 7)),
            ],
            [None, 7],
            "the absent value is None",
        )


class TestList:
    """list returns the generator of lists."""

    def test_returns_the_elements_of_the_continue_choices(
        self, seat: Collector
    ) -> None:
        """Two continue choices come before the stop."""
        check.equal(
            seat,
            decoded(prop.list(DIGITS), *ints(1, 4, 1, 5, 0)),
            [4, 5],
            "the list has two elements",
        )

    def test_discards_an_element_equal_to_an_earlier_one_of_a_unique_list(
        self, seat: Collector
    ) -> None:
        """The second element repeats the first element."""
        check.equal(
            seat,
            decoded(prop.list(DIGITS, unique=True), *ints(1, 4, 1, 4, 0)),
            [4],
            "the list has one element",
        )

    tests: ClassVar[list[Refusal]] = [
        (
            "a maximum below the minimum",
            lambda: prop.list(DIGITS, min_size=2, max_size=1),
            "prop: list(min_size=2, max_size=1): sizes [2, 1] are empty",
        ),
        (
            "a negative minimum",
            lambda: prop.list(DIGITS, min_size=-1),
            "prop: list(min_size=-1, max_size=None): sizes [-1, None] are empty",
        ),
        (
            "a maximum that is not an int",
            lambda: prop.list(DIGITS, max_size=cast("Any", 1.5)),
            "prop: list(min_size=0, max_size=1.5) needs sizes that are ints",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for(
        self, seat: Collector, give: Callable[[], object], want: str
    ) -> None:
        """The text of the refusal contains the call."""
        check.equal(seat, refusal(seat, give), want, "the error has the call")


class TestDict:
    """dict returns the generator of dicts."""

    def test_returns_a_dict_of_the_entries(self, seat: Collector) -> None:
        """The choices have one entry."""
        check.equal(
            seat,
            decoded(prop.dict(DIGITS, prop.boolean()), *ints(1, 3, 1, 0)),
            {3: True},
            "the dict has one entry",
        )

    def test_runs_a_dict_or_the_entries_of_the_engine_back_to_choices(
        self, seat: Collector
    ) -> None:
        """The dict and its pairs have the same inverse."""
        generator = prop.dict(DIGITS, prop.boolean(), max_size=1)
        check.equal(
            seat,
            invert(generator, {3: True}),
            invert(generator, Pairs(((3, True),))),
            "a dict and its pairs have the same choices",
        )

    def test_raises_value_error_for_sizes_that_do_not_admit_a_length(
        self, seat: Collector
    ) -> None:
        """The maximum is below the minimum."""
        check.equal(
            seat,
            refusal(seat, lambda: prop.dict(DIGITS, DIGITS, min_size=3, max_size=2)),
            "prop: dict(min_size=3, max_size=2): sizes [3, 2] are empty",
            "the error has the call and the reason",
        )


class TestString:
    """string returns the generator of strings."""

    def test_returns_the_characters_of_the_default_alphabet_with_the_digits_first(
        self, seat: Collector
    ) -> None:
        """The indices 0, 1 and 10 are the characters 0, 1 and a."""
        check.equal(
            seat,
            decoded(prop.string(), sequence(0, 1, 10)),
            "01a",
            "the string is 01a",
        )

    def test_returns_the_characters_of_a_given_alphabet(self, seat: Collector) -> None:
        """The indices 1 and 0 are the characters y and x."""
        check.equal(
            seat,
            decoded(prop.string(alphabet="xy"), sequence(1, 0)),
            "yx",
            "the string is yx",
        )

    tests: ClassVar[list[Refusal]] = [
        (
            "an empty alphabet",
            lambda: prop.string(alphabet=""),
            "prop: string(alphabet=''): the alphabet is empty",
        ),
        (
            "an alphabet that repeats a character",
            lambda: prop.string(alphabet="aa"),
            "prop: string(alphabet='aa'): the alphabet repeats a character",
        ),
        (
            "an alphabet with a lone surrogate",
            lambda: prop.string(alphabet="a\ud800"),
            "prop: string(alphabet='a\\ud800'): the alphabet contains a lone surrogate",
        ),
        (
            "sizes that do not admit a length",
            lambda: prop.string(max_size=-1),
            "prop: string(min_size=0, max_size=-1): sizes [0, -1] are empty",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for(
        self, seat: Collector, give: Callable[[], object], want: str
    ) -> None:
        """The text of the refusal contains the call."""
        check.equal(
            seat, refusal(seat, give), want, "the error has the call and the reason"
        )


class TestBytes:
    """bytes returns the generator of byte strings."""

    def test_returns_the_bytes_of_a_sequence(self, seat: Collector) -> None:
        """The sequence has the elements 1 and 255."""
        check.equal(
            seat,
            decoded(prop.bytes(), sequence(1, 255)),
            b"\x01\xff",
            "the bytes are 1 and 255",
        )

    def test_raises_value_error_for_a_size_that_is_not_an_int(
        self, seat: Collector
    ) -> None:
        """The minimum is 0.5."""
        check.equal(
            seat,
            refusal(seat, lambda: prop.bytes(min_size=cast("Any", 0.5))),
            "prop: bytes(min_size=0.5, max_size=None) needs sizes that are ints",
            "the error has the call",
        )


class TestDuration:
    """duration returns the generator of durations in nanoseconds."""

    def test_returns_the_nanoseconds_of_a_choice(self, seat: Collector) -> None:
        """The choice is twenty-five hours."""
        hours = 25 * 3_600 * SECOND
        check.equal(
            seat,
            decoded(prop.duration(-SECOND, TWO_DAYS), *ints(hours)),
            hours,
            "the duration is 25 hours",
        )

    def test_runs_a_duration_back_to_one_choice(self, seat: Collector) -> None:
        """The inverse of an hour is one choice."""
        hour = 3_600 * SECOND
        check.equal(
            seat,
            invert(prop.duration(-SECOND, TWO_DAYS), hour),
            [*ints(hour)],
            "the inverse is the choice of an hour",
        )

    tests: ClassVar[list[Refusal]] = [
        (
            "a bound that is not an int",
            lambda: prop.duration(0, cast("Any", 1.5)),
            "prop: duration(0, 1.5) needs two ints",
        ),
        (
            "bounds out of order",
            lambda: prop.duration(TWO_DAYS, -SECOND),
            f"prop: duration({TWO_DAYS}, {-SECOND}) needs bounds in order inside "
            "the signed 64-bit range",
        ),
        (
            "a bound beyond 2^63 - 1 nanoseconds",
            lambda: prop.duration(0, 2**63),
            f"prop: duration(0, {2**63}) needs bounds in order inside the signed "
            "64-bit range",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for(
        self, seat: Collector, give: Callable[[], object], want: str
    ) -> None:
        """The text of the refusal contains the call."""
        check.equal(seat, refusal(seat, give), want, "the error has the call")


class TestPermutation:
    """permutation returns the generator of the orderings of its values."""

    def test_returns_the_values_in_their_order_for_the_target_swaps(
        self, seat: Collector
    ) -> None:
        """Each swap choice is its target."""
        check.equal(
            seat,
            decoded(prop.permutation("a", "b", "c"), *ints(0, 1)),
            ["a", "b", "c"],
            "the values keep their order",
        )


class TestStringMatching:
    """string_matching returns the generator of the strings that a pattern matches."""

    def test_returns_a_string_that_the_pattern_matches(self, seat: Collector) -> None:
        """The pattern is a literal."""
        check.equal(
            seat,
            decoded(prop.string_matching("ab")),
            "ab",
            "the string is the literal",
        )

    def test_raises_value_error_for_a_pattern_outside_the_portable_subset(
        self, seat: Collector
    ) -> None:
        """A group is not closed."""
        check.equal(
            seat,
            refusal(seat, lambda: prop.string_matching("(")),
            "prop: string_matching('('): pattern \"(\" at 1: a group is not closed",
            "the error has the call and the reason",
        )


class TestRecursive:
    """recursive returns the generator of recursive values."""

    def test_returns_the_value_of_the_base_at_a_position_that_takes_the_base(
        self, seat: Collector
    ) -> None:
        """The first position takes the base."""
        base = cast("Generator[Any]", DIGITS)
        generator = prop.recursive(base, lambda inner: prop.list(inner))
        check.equal(
            seat, decoded(generator, *ints(0, 6)), 6, "the value is a leaf of the base"
        )

    def test_raises_value_error_for_a_max_leaves_below_1(self, seat: Collector) -> None:
        """The value of max_leaves is 0."""
        check.equal(
            seat,
            refusal(seat, lambda: prop.recursive(DIGITS, lambda g: g, max_leaves=0)),
            "prop: recursive(max_leaves=0) needs an int of 1 or more",
            "the error has the call",
        )


class TestComposite:
    """composite returns the generator of the values of a function of a case."""

    def test_returns_the_value_that_its_function_draws_from_the_case(
        self, seat: Collector
    ) -> None:
        """The function draws two digits."""
        pair = prop.composite(lambda c: [c.draw(DIGITS, "a"), c.draw(DIGITS, "b")])
        check.equal(
            seat,
            decoded(pair, *ints(1, 2)),
            [1, 2],
            "the value is the list of both draws",
        )
