# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/values.py tests the values of a generator for a seed."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check, prop
from dokimi_assert._prop.registry import Generators, scope
from dokimi_assert.option import equate_empty

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


def refuse(_: int) -> int:
    """Raise the error of a conversion that refuses every value."""
    msg = "the conversion refuses the value"
    raise LookupError(msg)


@dataclass(frozen=True)
class Order:
    """An order of a shop: its status and its number of lines."""

    status: int
    lines: int


def within(orders: list[Order], low: int, high: int) -> bool:
    """Report whether every int of orders is in [low, high]."""
    return all(low <= o.status <= high and low <= o.lines <= high for o in orders)


class TestValues:
    """values returns the values of the random cases of a seed."""

    def test_returns_the_values_of_the_random_cases_of_the_seed(
        self, seat: Collector
    ) -> None:
        """The vector integer/draws-from-a-signed-range pins the six values."""
        check.equal(
            seat,
            prop.values(prop.integer(-100, 100), 42, 6),
            [11, 0, 76, 0, 96, 11],
            "the values of the first six cases of seed 42",
        )

    def test_leaves_out_the_cases_that_the_generator_rejects(
        self, seat: Collector
    ) -> None:
        """The vector filter/reuses-no-value-of-a-rejected-attempt pins the values.

        Its filter rejects the cases 0, 2 and 3 of seed 7.
        """
        lists = prop.list(prop.integer(0, 9), max_size=4).filter(
            lambda xs: sum(xs) > 10
        )
        check.equal(
            seat,
            prop.values(lists, 7, 3),
            [[0, 6, 8, 8], [2, 2, 9], [7, 4, 0, 5]],
            "the values of cases 1, 4 and 5",
        )

    def test_returns_the_same_first_values_for_a_larger_count(
        self, seat: Collector
    ) -> None:
        """The values of one seed form one sequence."""
        digits = prop.integer(-100, 100)
        check.equal(
            seat,
            prop.values(digits, 42, 6)[:3],
            prop.values(digits, 42, 3),
            "the first three values",
        )

    def test_decodes_a_draw_of_of_with_the_generator_of_the_test_process(
        self, seat: Collector
    ) -> None:
        """The run gives int the generator of 7, and values does not take it."""
        with scope(Generators({int: prop.just(7)})):
            inside = prop.values(prop.of(int), 42, 3)
        check.equal(
            seat,
            inside,
            prop.values(prop.of(int), 42, 3),
            "values decodes the ints of the test process",
        )

    def test_decodes_a_draw_of_of_with_the_generator_that_using_states(
        self, seat: Collector
    ) -> None:
        """The option gives int the generator of 7."""
        check.equal(
            seat,
            prop.values(prop.of(int), 42, 3, prop.using(int, prop.just(7))),
            [7, 7, 7],
            "every value is 7",
        )

    def test_generates_each_value_of_a_stated_type_inside_a_derived_value(
        self, seat: Collector
    ) -> None:
        """Both ints of each order are from 1 to 3, and they are not without it."""
        stated = prop.values(
            prop.of(Order), 42, 20, prop.using(int, prop.integer(1, 3))
        )
        check.is_true(seat, within(stated, 1, 3), "every int of an order is 1 to 3")
        check.is_false(
            seat,
            within(prop.values(prop.of(Order), 42, 20), 1, 3),
            "the ints of the test process are wider",
        )

    def test_decodes_a_draw_of_its_type_inside_the_stated_generator_without_it(
        self, seat: Collector
    ) -> None:
        """The stated generator of int adds 100 to the int of the test process."""
        above = prop.of(int).map(lambda x: x + 100)
        check.equal(
            seat,
            prop.values(prop.of(int), 42, 3, prop.using(int, above)),
            [x + 100 for x in prop.values(prop.of(int), 42, 3)],
            "each value is 100 above the int of the test process",
        )

    def test_takes_the_later_option_of_one_type(self, seat: Collector) -> None:
        """The second option of int replaces the first."""
        check.equal(
            seat,
            prop.values(
                prop.of(int),
                42,
                2,
                prop.using(int, prop.just(1)),
                prop.using(int, prop.just(2)),
            ),
            [2, 2],
            "the later option applies",
        )

    def test_returns_no_value_for_a_count_of_0(self, seat: Collector) -> None:
        """A count of 0 decodes no case."""
        check.is_empty(
            seat, prop.values(prop.integer(-100, 100), 42, 0), "the values of no case"
        )

    def test_passes_on_an_exception_of_the_generator(self, seat: Collector) -> None:
        """The exception of a conversion leaves the call."""
        error = check.raises(
            seat,
            lambda: prop.values(prop.integer(0, 9).map(refuse), 42, 1),
            "values raises the error of the generator",
        )
        check.equal(
            seat,
            (type(error), str(error)),
            (LookupError, "the conversion refuses the value"),
            "the error of the conversion",
        )

    def test_raises_value_error_for_a_generator_that_rejects_every_case(
        self, seat: Collector
    ) -> None:
        """The call stops past ten rejected cases for each value."""
        never = prop.integer(0, 9).filter(lambda _: False)
        error = check.raises(
            seat, lambda: prop.values(never, 42, 2), "values raises at the limit"
        )
        check.equal(
            seat,
            (type(error), str(error)),
            (
                ValueError,
                (
                    "prop: values(generator, 42, 2) stops after the generator rejects "
                    "21 cases for 2 values"
                ),
            ),
            "the error counts the rejected cases",
        )

    tests: ClassVar[list[tuple[str, Any, Any, str]]] = [
        (
            "raises value error for a negative count",
            42,
            -1,
            "prop: values(generator, 42, -1) needs a count that is an int of 0 or more",
        ),
        (
            "raises value error for a count that is a bool",
            42,
            True,
            (
                "prop: values(generator, 42, True) needs a count that is an int of 0 "
                "or more"
            ),
        ),
        (
            "raises value error for a negative seed",
            -1,
            3,
            "prop: values(generator, -1, 3) needs a seed that is an int in [0, 2^64)",
        ),
        (
            "raises value error for a seed of 2 to the 64",
            2**64,
            3,
            (
                "prop: values(generator, 18446744073709551616, 3) needs a seed that is "
                "an int in [0, 2^64)"
            ),
        ),
        (
            "raises value error for a seed that is a float",
            1.5,
            3,
            "prop: values(generator, 1.5, 3) needs a seed that is an int in [0, 2^64)",
        ),
    ]

    @pytest.mark.parametrize(
        ("give_seed", "give_n", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_raises_value_error_for_an_argument_that_it_refuses(
        self, seat: Collector, give_seed: Any, give_n: Any, want: str
    ) -> None:
        """The error has the call."""
        error = check.raises(
            seat,
            lambda: prop.values(prop.integer(0, 9), give_seed, give_n),
            "values raises",
        )
        check.equal(
            seat,
            (type(error), str(error)),
            (ValueError, want),
            "the error names the call",
        )

    refused: ClassVar[list[tuple[str, Any, str]]] = [
        (
            "raises value error for an option of another setting",
            prop.cases(5),
            "cases",
        ),
        ("raises value error for an example of a form", prop.example(1), "example"),
        (
            "raises value error for an option of a comparison",
            equate_empty(),
            "equate-empty",
        ),
        ("raises value error for a value that is not an option", "using", "str"),
    ]

    @pytest.mark.parametrize(
        ("give_option", "want_kind"),
        [t[1:] for t in refused],
        ids=[t[0] for t in refused],
    )
    def test_raises_value_error_for_an_option_that_it_refuses(
        self, seat: Collector, give_option: Any, want_kind: str
    ) -> None:
        """The error has the call and the kind of the option."""
        error = check.raises(
            seat,
            lambda: prop.values(prop.integer(0, 9), 42, 3, give_option),
            "values raises",
        )
        check.equal(
            seat,
            (type(error), str(error)),
            (
                ValueError,
                (
                    "prop: values(generator, 42, 3) takes the options of using alone, "
                    f"not {want_kind}"
                ),
            ),
            "the error names the option",
        )
