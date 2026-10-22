# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _stateful/option.py tests the options of the steps of a machine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._stateful.option import (
    Config,
    Option,
    clients,
    concurrent,
    configure,
    max_steps,
    mean,
    repeat,
    swarm,
    tasks,
)
from dokimi_assert._stateful.scheduler import Scheduler
from dokimi_assert._stateful.strategy import uniform
from helpers import body_case, refusal, replaying

if TYPE_CHECKING:
    from collections.abc import Callable

    from dokimi_assert.seat import Collector


class TestConfig:
    """Config states the settings of a run of steps."""

    def test_has_the_settings_that_the_definition_fixes_by_default(
        self, seat: Collector
    ) -> None:
        """The definition fixes each default."""
        check.equal(
            seat,
            Config(),
            Config(30, 100, True, 1, 16, None, 4),
            "the defaults are the settings that the definition fixes",
        )


class TestMean:
    """mean sets the mean number of sequential steps."""

    def test_returns_an_option_that_sets_the_mean_alone(self, seat: Collector) -> None:
        """The option sets a mean of 0."""
        check.equal(
            seat, configure([mean(0)]), Config(mean=0), "the option sets the mean"
        )

    def test_raises_value_error_for_a_mean_below_0(self, seat: Collector) -> None:
        """A mean of -1 steps is refused."""
        check.equal(
            seat,
            refusal(seat, lambda: mean(-1)),
            "stateful: mean(-1) needs an int of 0 or more",
            "the text of the refusal contains the call",
        )


class TestMaxSteps:
    """max_steps sets the most sequential steps and the most steps of the drain."""

    def test_returns_an_option_that_sets_the_most_steps_alone(
        self, seat: Collector
    ) -> None:
        """The option sets 7 steps."""
        check.equal(
            seat,
            configure([max_steps(7)]),
            Config(max_steps=7),
            "the option sets the most steps",
        )

    def test_raises_value_error_for_a_fraction_of_a_step(self, seat: Collector) -> None:
        """A count of 1.5 steps is refused."""
        check.equal(
            seat,
            refusal(seat, lambda: max_steps(cast("Any", 1.5))),
            "stateful: max_steps(1.5) needs an int of 0 or more",
            "the text of the refusal contains the call",
        )


class TestSwarm:
    """swarm sets whether a case first chooses the actions that it keeps."""

    def test_returns_an_option_that_turns_the_swarm_off(self, seat: Collector) -> None:
        """The option turns the swarm off."""
        check.equal(
            seat,
            configure([swarm(False)]),
            Config(swarm=False),
            "the option turns the swarm off",
        )


class TestClients:
    """clients sets the clients of the concurrent section besides client 0."""

    def test_returns_an_option_that_sets_the_clients_alone(
        self, seat: Collector
    ) -> None:
        """The option sets 3 clients."""
        check.equal(
            seat,
            configure([clients(3)]),
            Config(clients=3),
            "the option sets the clients",
        )

    def test_raises_value_error_for_no_client(self, seat: Collector) -> None:
        """A section needs one client besides client 0."""
        check.equal(
            seat,
            refusal(seat, lambda: clients(0)),
            "stateful: clients(0) needs an int of 1 or more",
            "the text of the refusal contains the call",
        )


class TestConcurrent:
    """concurrent sets the most steps of a concurrent section."""

    def test_returns_an_option_that_sets_the_most_steps_of_a_section_alone(
        self, seat: Collector
    ) -> None:
        """The option sets 0 steps."""
        check.equal(
            seat,
            configure([concurrent(0)]),
            Config(concurrent=0),
            "the option sets the most steps of a section",
        )

    def test_raises_value_error_for_a_count_below_0(self, seat: Collector) -> None:
        """A section of -1 steps is refused."""
        check.equal(
            seat,
            refusal(seat, lambda: concurrent(-1)),
            "stateful: concurrent(-1) needs an int of 0 or more",
            "the text of the refusal contains the call",
        )


class TestTasks:
    """tasks makes the clients of a concurrent section run as tasks of a scheduler."""

    def test_returns_an_option_that_sets_the_scheduler_alone(
        self, seat: Collector
    ) -> None:
        """The option sets a scheduler of a case."""
        c, _ = body_case(replaying())
        scheduler = Scheduler(c, uniform())
        check.equal(
            seat,
            configure([tasks(scheduler)]),
            Config(scheduler=scheduler),
            "the option sets the scheduler",
        )


class TestRepeat:
    """repeat sets the runs of a case whose concurrent section runs on threads."""

    def test_returns_an_option_that_sets_the_runs_alone(self, seat: Collector) -> None:
        """The option sets 2 runs."""
        check.equal(
            seat, configure([repeat(2)]), Config(repeat=2), "the option sets the runs"
        )

    tests: ClassVar[list[tuple[str, Callable[[], Option], str]]] = [
        ("no run", lambda: repeat(0), "stateful: repeat(0) needs an int of 1 or more"),
        (
            "a bool",
            lambda: repeat(cast("Any", True)),
            "stateful: repeat(True) needs an int of 1 or more",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_value_error_for(
        self, seat: Collector, give: Callable[[], Option], want: str
    ) -> None:
        """The text of the refusal contains the call."""
        check.equal(
            seat, refusal(seat, give), want, "the text of the refusal contains the call"
        )


class TestConfigure:
    """configure applies the options of a run to the defaults in order."""

    def test_returns_the_defaults_without_an_option(self, seat: Collector) -> None:
        """The list of options is empty."""
        check.equal(seat, configure([]), Config(), "configure returns the defaults")

    def test_lets_a_later_option_replace_an_earlier_one(self, seat: Collector) -> None:
        """A mean of 5 follows a mean of 3."""
        check.equal(
            seat,
            configure([mean(3), mean(5)]).mean,
            5,
            "the later mean replaces the earlier one",
        )
