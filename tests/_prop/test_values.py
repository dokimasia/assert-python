"""The spec of _prop/values.py tests the values of a generator for a seed."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from dokimi_assert import check, prop
from dokimi_assert._prop.registry import Generators, scope
from dokimi_assert.seat import Collector


def refuse(_: int) -> int:
    """Raise the error of a conversion that refuses every value."""
    raise LookupError("the conversion refuses the value")


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
                "prop: values(generator, 42, 2) stops after the generator rejects "
                "21 cases for 2 values",
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
            "prop: values(generator, 42, True) needs a count that is an int of 0 "
            "or more",
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
            "prop: values(generator, 18446744073709551616, 3) needs a seed that is "
            "an int in [0, 2^64)",
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
