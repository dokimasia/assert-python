# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/option.py tests the options of a property and a property form."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.choice import IntegerBounds
from dokimi_assert._prop.engine.generator import Integer
from dokimi_assert._prop.engine.runner import Requirement
from dokimi_assert._prop.option import (
    Config,
    FormOnly,
    Option,
    around,
    cases,
    configure,
    draws,
    example,
    examples,
    explain,
    hermetic,
    max_choices,
    replay,
    require,
    seed,
    shrink,
    shrink_time,
    store,
    using,
    workers,
)
from dokimi_assert._prop.registry import Generators
from helpers import refusal

if TYPE_CHECKING:
    from collections.abc import Callable

    from dokimi_assert.seat import Collector


def _wrap(run: Callable[[], None]) -> None:
    """Call run once, as a wrapper of the around option does."""
    run()


class TestOption:
    """Option is one setting of a run."""

    def test_does_not_have_a_value_by_default(self, seat: Collector) -> None:
        """The option of hermetic does not need a value."""
        check.is_none(
            seat, Option("hermetic").value, "the option does not have a value"
        )


class TestFormOnly:
    """FormOnly is an option that only a property form takes."""

    def test_keeps_its_kind_and_its_value(self, seat: Collector) -> None:
        """The option is an example of one value."""
        option = FormOnly("example", (1,))
        check.equal(
            seat,
            [option.kind, option.value],
            ["example", (1,)],
            "the option keeps its kind and its value",
        )


class TestConfig:
    """Config has the settings of one run."""

    def test_has_the_defaults_of_a_run_without_options(self, seat: Collector) -> None:
        """Each setting has its default."""
        check.equal(
            seat,
            Config(),
            Config(
                cases=100,
                seed=None,
                replay=None,
                requirements=(),
                shrink=2000,
                shrink_time=30.0,
                max_choices=8192,
                store=None,
                explain=True,
                workers=1,
                hermetic=False,
                draws=None,
                around=None,
            ),
            "Config has the defaults of a run",
        )


class TestConfigure:
    """configure applies each option to the defaults in order."""

    def test_returns_the_defaults_without_an_option(self, seat: Collector) -> None:
        """Each setting keeps its default."""
        check.equal(seat, configure([]), Config(), "configure returns the defaults")

    def test_returns_the_setting_of_every_option(self, seat: Collector) -> None:
        """The requirements keep their order."""
        check.equal(
            seat,
            configure(
                [
                    cases(5),
                    seed(9),
                    replay("prop1:AA"),
                    require("a", 0.5),
                    require("b", 0.25),
                    shrink(10),
                    shrink_time(20.0),
                    max_choices(30),
                    store("dir"),
                    explain(False),
                    workers(2),
                    hermetic(),
                    draws("[]"),
                    around(_wrap),
                ]
            ),
            Config(
                cases=5,
                seed=9,
                replay="prop1:AA",
                requirements=(Requirement("a", 0.5), Requirement("b", 0.25)),
                shrink=10,
                shrink_time=20.0,
                max_choices=30,
                store="dir",
                explain=False,
                workers=2,
                hermetic=True,
                draws="[]",
                around=_wrap,
            ),
            "each option sets its setting",
        )

    def test_returns_the_setting_of_the_later_of_two_options_of_one_kind(
        self, seat: Collector
    ) -> None:
        """The later option overrides the earlier one."""
        check.equal(
            seat, configure([cases(5), cases(6)]).cases, 6, "the later option applies"
        )

    def test_returns_the_generator_of_each_type_that_a_using_option_states(
        self, seat: Collector
    ) -> None:
        """A later using of one type replaces an earlier one."""
        five = Integer(IntegerBounds(0, 5))
        digits = Integer(IntegerBounds(0, 9))
        letters = Integer(IntegerBounds(97, 122))
        check.equal(
            seat,
            configure([using(int, five), using(str, letters), using(int, digits)]),
            Config(using=Generators({int: digits, str: letters})),
            "the run has the later generator of int",
        )


class TestCases:
    """cases sets the number of valid cases that a run tries to generate."""

    def test_returns_the_option_of_the_number(self, seat: Collector) -> None:
        """The number is 5."""
        check.equal(seat, cases(5), Option("cases", 5), "the option sets 5 cases")

    tests: ClassVar[list[tuple[str, Any, str]]] = [
        ("refuses 0", 0, "prop: cases(0) needs an int of 1 or more"),
        ("refuses a float", 1.5, "prop: cases(1.5) needs an int of 1 or more"),
        ("refuses a bool", True, "prop: cases(True) needs an int of 1 or more"),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for_a_number_that_is_not_an_int_of_1_or_more(
        self, seat: Collector, give: Any, want: str
    ) -> None:
        """The error has the call."""
        check.equal(
            seat, refusal(seat, lambda: cases(give)), want, "the error has the call"
        )


class TestSeed:
    """seed sets the seed of the run."""

    tests: ClassVar[list[tuple[str, int]]] = [
        ("returns the option of the seed 0", 0),
        ("returns the option of the largest seed", 2**64 - 1),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in tests], ids=[t[0] for t in tests])
    def test_returns_the_option_of_the_seed(self, seat: Collector, give: int) -> None:
        """The seeds are the bounds of the range."""
        check.equal(seat, seed(give), Option("seed", give), "the option has the seed")

    refusals: ClassVar[list[tuple[str, Any, str]]] = [
        (
            "refuses 2^64",
            2**64,
            "prop: seed(18446744073709551616) needs an int in [0, 2^64)",
        ),
        ("refuses -1", -1, "prop: seed(-1) needs an int in [0, 2^64)"),
        ("refuses a float", 0.5, "prop: seed(0.5) needs an int in [0, 2^64)"),
        ("refuses a bool", True, "prop: seed(True) needs an int in [0, 2^64)"),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_value_error_for_a_seed_that_is_not_an_int_in_range(
        self, seat: Collector, give: Any, want: str
    ) -> None:
        """The error has the call."""
        check.equal(
            seat, refusal(seat, lambda: seed(give)), want, "the error has the call"
        )


class TestReplay:
    """replay sets the token of the one case that a run tests."""

    def test_returns_the_option_of_the_token(self, seat: Collector) -> None:
        """The option has the token."""
        check.equal(
            seat,
            replay("prop1:AA"),
            Option("replay", "prop1:AA"),
            "the option has the token",
        )


class TestRequire:
    """require adds a coverage requirement."""

    tests: ClassVar[list[tuple[str, float]]] = [
        ("returns the option of a share of 0", 0),
        ("returns the option of a share of a quarter", 0.25),
        ("returns the option of a share of 1", 1),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in tests], ids=[t[0] for t in tests])
    def test_returns_the_option_of_the_requirement(
        self, seat: Collector, give: float
    ) -> None:
        """The requirement has the label and the share."""
        check.equal(
            seat,
            require("even", give),
            Option("require", Requirement("even", give)),
            "the option has the requirement",
        )

    refusals: ClassVar[list[tuple[str, Any, str]]] = [
        (
            "refuses a share above 1",
            1.5,
            "prop: require('even', 1.5) needs a share from 0 to 1",
        ),
        (
            "refuses a share below 0",
            -0.5,
            "prop: require('even', -0.5) needs a share from 0 to 1",
        ),
        (
            "refuses a share of nan",
            math.nan,
            "prop: require('even', nan) needs a share from 0 to 1",
        ),
        (
            "refuses a bool",
            True,
            "prop: require('even', True) needs a share from 0 to 1",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_value_error_for_a_share_outside_0_to_1(
        self, seat: Collector, give: Any, want: str
    ) -> None:
        """The error has the call."""
        check.equal(
            seat,
            refusal(seat, lambda: require("even", give)),
            want,
            "the error has the call",
        )


class TestShrink:
    """shrink sets the number of calls that shrinking and explaining can make."""

    def test_returns_the_option_of_a_budget_of_0(self, seat: Collector) -> None:
        """A budget of 0 turns off shrinking."""
        check.equal(seat, shrink(0), Option("shrink", 0), "the option has the budget 0")

    tests: ClassVar[list[tuple[str, Any, str]]] = [
        ("refuses -1", -1, "prop: shrink(-1) needs an int of 0 or more"),
        ("refuses a float", 2.0, "prop: shrink(2.0) needs an int of 0 or more"),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for_a_budget_that_is_not_an_int_of_0_or_more(
        self, seat: Collector, give: Any, want: str
    ) -> None:
        """The error has the call."""
        check.equal(
            seat, refusal(seat, lambda: shrink(give)), want, "the error has the call"
        )


class TestShrinkTime:
    """shrink_time sets the seconds that shrinking and explaining can take."""

    tests: ClassVar[list[tuple[str, float]]] = [
        ("returns the option of a time of 0", 0),
        ("returns the option of a quarter of a second", 0.25),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in tests], ids=[t[0] for t in tests])
    def test_returns_the_option_of_the_time(self, seat: Collector, give: float) -> None:
        """The option has the seconds."""
        check.equal(
            seat,
            shrink_time(give),
            Option("shrink-time", give),
            "the option has the seconds",
        )

    refusals: ClassVar[list[tuple[str, Any, str]]] = [
        (
            "refuses -1",
            -1,
            "prop: shrink_time(-1) needs a finite number of 0 or more",
        ),
        (
            "refuses infinity",
            math.inf,
            "prop: shrink_time(inf) needs a finite number of 0 or more",
        ),
        (
            "refuses nan",
            math.nan,
            "prop: shrink_time(nan) needs a finite number of 0 or more",
        ),
        (
            "refuses a bool",
            True,
            "prop: shrink_time(True) needs a finite number of 0 or more",
        ),
        (
            "refuses a str",
            "1",
            "prop: shrink_time('1') needs a finite number of 0 or more",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_value_error_for_a_time_that_is_not_a_finite_number_of_0_or_more(
        self, seat: Collector, give: Any, want: str
    ) -> None:
        """The error has the call."""
        check.equal(
            seat,
            refusal(seat, lambda: shrink_time(give)),
            want,
            "the error has the call",
        )


class TestMaxChoices:
    """max_choices sets the largest number of choices that one case can make."""

    def test_returns_the_option_of_the_cap(self, seat: Collector) -> None:
        """The cap is 64 choices."""
        check.equal(
            seat,
            max_choices(64),
            Option("max-choices", 64),
            "the option has the cap 64",
        )

    def test_raises_value_error_for_a_cap_of_0(self, seat: Collector) -> None:
        """The error has the call."""
        check.equal(
            seat,
            refusal(seat, lambda: max_choices(0)),
            "prop: max_choices(0) needs an int of 1 or more",
            "the error has the call",
        )


class TestStore:
    """store sets the directory of the store."""

    def test_returns_the_option_of_the_directory(self, seat: Collector) -> None:
        """The empty string turns off the store."""
        check.equal(
            seat, store(""), Option("store", ""), "the option has the empty directory"
        )


class TestExplain:
    """explain sets whether a run explains its counterexample."""

    def test_returns_the_option_that_turns_off_the_explanation(
        self, seat: Collector
    ) -> None:
        """The run does not explain."""
        check.equal(
            seat,
            explain(False),
            Option("explain", False),
            "the option turns off the explanation",
        )


class TestWorkers:
    """workers sets the number of cases that run at once."""

    def test_returns_the_option_of_the_number(self, seat: Collector) -> None:
        """The number is 4."""
        check.equal(
            seat, workers(4), Option("workers", 4), "the option has four workers"
        )

    def test_raises_value_error_for_0_workers(self, seat: Collector) -> None:
        """The error has the call."""
        check.equal(
            seat,
            refusal(seat, lambda: workers(0)),
            "prop: workers(0) needs an int of 1 or more",
            "the error has the call",
        )


class TestHermetic:
    """hermetic makes a run ignore the variables of the engine."""

    def test_returns_the_option_without_a_value(self, seat: Collector) -> None:
        """The option does not have a value."""
        check.equal(
            seat,
            hermetic(),
            Option("hermetic", None),
            "the option does not have a value",
        )


class TestDraws:
    """draws sets the entries that the first case follows."""

    def test_returns_the_option_of_the_entries(self, seat: Collector) -> None:
        """The array is empty."""
        check.equal(
            seat, draws("[]"), Option("draws", "[]"), "the option has the empty array"
        )


class TestAround:
    """around sets the wrapper of each run of the body."""

    def test_returns_the_option_of_the_wrapper(self, seat: Collector) -> None:
        """The option has the function."""
        check.equal(
            seat, around(_wrap), Option("around", _wrap), "the option has the wrapper"
        )

    def test_raises_value_error_for_a_wrapper_that_is_not_callable(
        self, seat: Collector
    ) -> None:
        """The error has the call."""
        wrapper: Any = None
        check.equal(
            seat,
            refusal(seat, lambda: around(wrapper)),
            "prop: around(None) needs a callable",
            "the error has the call",
        )


class TestUsing:
    """using sets the generator of a type in a run."""

    def test_returns_the_option_of_the_type_and_its_generator(
        self, seat: Collector
    ) -> None:
        """The option has the type and the generator."""
        digits = Integer(IntegerBounds(0, 9))
        check.equal(
            seat,
            using(int, digits),
            Option("using", (int, digits)),
            "the option has the type and its generator",
        )


class TestExample:
    """example adds a case of values."""

    def test_returns_the_option_of_the_values(self, seat: Collector) -> None:
        """The case has two values."""
        check.equal(
            seat,
            example(1, 2),
            FormOnly("example", (1, 2)),
            "the option has the two values",
        )


class TestExamples:
    """examples adds one case per value."""

    def test_returns_the_option_of_the_values(self, seat: Collector) -> None:
        """Each of the two values is a case."""
        check.equal(
            seat,
            examples(1, 2),
            FormOnly("examples", (1, 2)),
            "the option has the two values",
        )
