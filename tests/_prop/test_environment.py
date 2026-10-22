# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/environment.py tests the variables of the property engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._prop.engine.source import mix
from dokimi_assert._prop.environment import (
    BUDGET_VARIABLE,
    PROFILE_VARIABLE,
    REPLAY_VARIABLE,
    SEED_VARIABLE,
    Replay,
    budget_of,
    mutated,
    profile_of,
    seed_of,
    token_of,
)
from helpers import refusal

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

#: The variable that a mutation run sets in every process that it instruments.
MUTANT = "DOKIMI_MUTATE_MUTANT"

#: The seed that the engine derives from the contract.
DERIVED = mix(b"a contract")

#: The fault of a misspelled profile.
PROFILE_FAULT = (
    'DOKIMI_ASSERT_PROP_PROFILE: "fast" is not one of the profiles default, ci '
    "and campaign"
)


def put(monkeypatch: pytest.MonkeyPatch, name: str, value: str | None) -> None:
    """Set a variable for one case, or remove it for None."""
    if value is None:
        monkeypatch.delenv(name, raising=False)
    else:
        monkeypatch.setenv(name, value)


class TestMutated:
    """mutated reports whether this process runs under a mutation run."""

    def test_returns_false_outside_a_mutation_run(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The process is not mutated."""
        put(monkeypatch, MUTANT, None)
        check.is_false(seat, mutated(), "the process is not mutated")

    def test_returns_true_for_the_mutant_variable_with_any_value(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty value counts."""
        put(monkeypatch, MUTANT, "")
        check.is_true(seat, mutated(), "the process is mutated")


class TestProfileOf:
    """profile_of returns the profile of the environment."""

    tests: ClassVar[list[tuple[str, str | None, str]]] = [
        ("returns default for an unset variable", None, "default"),
        ("returns default for an empty variable", "", "default"),
        ("returns the profile of the variable", "campaign", "campaign"),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_profile(
        self,
        seat: Collector,
        monkeypatch: pytest.MonkeyPatch,
        give: str | None,
        want: str,
    ) -> None:
        """The variable sets the profile."""
        put(monkeypatch, PROFILE_VARIABLE, give)
        check.equal(seat, profile_of(), want, "profile_of returns the profile")

    def test_raises_a_fault_at_the_variable_for_an_unknown_profile(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The fault has the variable."""
        put(monkeypatch, PROFILE_VARIABLE, "fast")
        check.equal(
            seat,
            refusal(seat, profile_of, FaultError),
            PROFILE_FAULT,
            "the fault has the variable",
        )


class TestSeedOf:
    """seed_of returns the seed of a run of a contract."""

    def test_returns_the_seed_of_the_option_over_the_variable(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The seed of the option comes first."""
        put(monkeypatch, PROFILE_VARIABLE, None)
        put(monkeypatch, SEED_VARIABLE, "5")
        check.equal(
            seat, seed_of("a contract", 9, False), 9, "seed_of returns the seed 9"
        )

    def test_returns_the_seed_of_the_variable(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The variable has the largest seed."""
        put(monkeypatch, PROFILE_VARIABLE, None)
        put(monkeypatch, SEED_VARIABLE, "18446744073709551615")
        check.equal(
            seat,
            seed_of("a contract", None, False),
            2**64 - 1,
            "seed_of returns the largest seed",
        )

    def test_returns_the_seed_of_a_variable_with_leading_zeros(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Leading zeros do not count towards the digits."""
        put(monkeypatch, PROFILE_VARIABLE, None)
        put(monkeypatch, SEED_VARIABLE, "0" * 30 + "7")
        check.equal(
            seat, seed_of("a contract", None, False), 7, "seed_of returns the seed 7"
        )

    tests: ClassVar[list[tuple[str, str]]] = [
        ("raises a fault at the variable for a hexadecimal seed", "0x10"),
        ("raises a fault at the variable for a seed of 2^64", "18446744073709551616"),
        ("raises a fault at the variable for a seed of 5000 digits", "1" * 5000),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in tests], ids=[t[0] for t in tests])
    def test_raises_a_fault_at_the_variable(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch, give: str
    ) -> None:
        """The fault has the variable and the quoted text."""
        put(monkeypatch, PROFILE_VARIABLE, None)
        put(monkeypatch, SEED_VARIABLE, give)
        check.equal(
            seat,
            refusal(seat, lambda: seed_of("a contract", None, False), FaultError),
            f'DOKIMI_ASSERT_PROP_SEED: "{give}" is not a decimal number below 2^64',
            "the fault has the variable",
        )

    def test_derives_the_seed_from_the_contract_under_the_ci_profile(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The engine derives the seed from the contract."""
        put(monkeypatch, SEED_VARIABLE, None)
        put(monkeypatch, PROFILE_VARIABLE, "ci")
        check.equal(
            seat,
            seed_of("a contract", None, False),
            DERIVED,
            "seed_of returns the seed of the contract",
        )

    def test_derives_the_seed_from_the_contract_in_a_process_of_a_mutation_run(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The engine derives the seed from the contract."""
        put(monkeypatch, SEED_VARIABLE, None)
        put(monkeypatch, MUTANT, "1")
        check.equal(
            seat,
            seed_of("a contract", None, True),
            DERIVED,
            "seed_of returns the seed of the contract",
        )

    def test_ignores_the_variables_in_a_hermetic_run(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The run draws a random seed of 64 bits."""
        put(monkeypatch, SEED_VARIABLE, "0x10")
        put(monkeypatch, PROFILE_VARIABLE, "fast")
        put(monkeypatch, MUTANT, None)
        drawn = seed_of("a contract", None, True)
        check.in_range(
            seat, drawn, 0, 2**64 - 1, "seed_of returns a random seed of 64 bits"
        )

    def test_raises_the_fault_of_a_misspelled_profile_in_a_run_with_a_seed_option(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The profile is checked first."""
        put(monkeypatch, PROFILE_VARIABLE, "fast")
        check.equal(
            seat,
            refusal(seat, lambda: seed_of("a contract", 9, False), FaultError),
            PROFILE_FAULT,
            "the profile is checked first",
        )


class TestBudgetOf:
    """budget_of returns the length of a campaign."""

    def test_returns_the_budget_in_seconds_under_the_campaign_profile(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The budget is five seconds."""
        put(monkeypatch, MUTANT, None)
        put(monkeypatch, PROFILE_VARIABLE, "campaign")
        put(monkeypatch, BUDGET_VARIABLE, "5")
        check.equal(seat, budget_of(False), 5, "budget_of returns five seconds")

    def test_returns_0_under_the_default_profile(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The run is not a campaign."""
        put(monkeypatch, MUTANT, None)
        put(monkeypatch, PROFILE_VARIABLE, None)
        put(monkeypatch, BUDGET_VARIABLE, "5")
        check.equal(seat, budget_of(False), 0, "the run is not a campaign")

    def test_returns_0_for_a_hermetic_run(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The run is not a campaign."""
        put(monkeypatch, PROFILE_VARIABLE, "campaign")
        check.equal(seat, budget_of(True), 0, "the run is not a campaign")

    def test_returns_0_in_a_process_of_a_mutation_run(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The run is not a campaign."""
        put(monkeypatch, MUTANT, "1")
        put(monkeypatch, PROFILE_VARIABLE, "campaign")
        check.equal(seat, budget_of(False), 0, "the run is not a campaign")

    tests: ClassVar[list[tuple[str, str | None]]] = [
        ("raises a fault at the variable for an unset budget", None),
        ("raises a fault at the variable for a budget of 0", "0"),
        ("raises a fault at the variable for a budget of 2^33 seconds", "8589934592"),
        ("raises a fault at the variable for a budget with a fraction", "1.5"),
        ("raises a fault at the variable for a budget of 5000 digits", "1" * 5000),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in tests], ids=[t[0] for t in tests])
    def test_raises_a_fault_at_the_variable(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch, give: str | None
    ) -> None:
        """The fault has the variable and the quoted text."""
        put(monkeypatch, MUTANT, None)
        put(monkeypatch, PROFILE_VARIABLE, "campaign")
        put(monkeypatch, BUDGET_VARIABLE, give)
        text = "" if give is None else give
        check.equal(
            seat,
            refusal(seat, lambda: budget_of(False), FaultError),
            f'DOKIMI_ASSERT_PROP_BUDGET: "{text}" is not a whole number of seconds '
            "above 0",
            "the fault has the variable",
        )


class TestReplay:
    """Replay has the token that a run replays and its source."""

    def test_keeps_its_fields(self, seat: Collector) -> None:
        """The replay keeps the token and the source."""
        replay = Replay("prop1:AA", "replay")
        check.equal(
            seat,
            [replay.token, replay.source],
            ["prop1:AA", "replay"],
            "the replay keeps both fields",
        )


class TestTokenOf:
    """token_of returns the token that a run replays."""

    def test_returns_the_token_of_the_option_with_the_option_as_its_source(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The option comes first."""
        put(monkeypatch, REPLAY_VARIABLE, "prop1:AB")
        check.equal(
            seat,
            token_of("prop1:AA", False),
            Replay("prop1:AA", "replay"),
            "the source is the option",
        )

    def test_returns_the_token_of_the_variable_with_the_variable_as_its_source(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The variable comes second."""
        put(monkeypatch, REPLAY_VARIABLE, "prop1:AB")
        check.equal(
            seat,
            token_of(None, False),
            Replay("prop1:AB", REPLAY_VARIABLE),
            "the source is the variable",
        )

    def test_returns_none_for_a_hermetic_run_without_a_token_option(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A hermetic run does not replay a token."""
        put(monkeypatch, REPLAY_VARIABLE, "prop1:AB")
        check.is_none(
            seat, token_of(None, True), "a hermetic run does not replay a token"
        )

    def test_returns_none_for_an_empty_variable(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An empty variable does not have a token."""
        put(monkeypatch, REPLAY_VARIABLE, "")
        check.is_none(
            seat, token_of(None, False), "an empty variable does not have a token"
        )
