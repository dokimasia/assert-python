# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The environment variables that set the defaults of every property of a test run.

A hermetic run does not read them. An unset variable and an empty variable do
not have a value.

- DOKIMI_ASSERT_PROP_SEED has the seed in decimal of every run without a seed
  option.
- DOKIMI_ASSERT_PROP_PROFILE has the name of the profile. The profile default
  draws a random seed for each run, ci derives the seed of each run from its
  contract, and campaign runs each property as a campaign.
- DOKIMI_ASSERT_PROP_BUDGET has the length of a campaign in whole seconds.
- DOKIMI_ASSERT_PROP_REPLAY has the token that every run without a replay
  option replays.

A mutation run sets DOKIMI_MUTATE_MUTANT in the environment of each process
that it instruments. Such a process derives every seed from the contract. It
does not run a campaign, and it does not write a store entry.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from dokimi_assert._matcher.fault import FaultError, of_operation
from dokimi_assert._matcher.verdict import end
from dokimi_assert._prop.engine.source import mix, utf8

if TYPE_CHECKING:
    from dokimi_assert._matcher.seat import Seat

__all__ = [
    "BUDGET_VARIABLE",
    "PROFILE_VARIABLE",
    "REPLAY_VARIABLE",
    "SEED_VARIABLE",
    "Profile",
    "Replay",
    "budget_of",
    "mutated",
    "profile_of",
    "run_seed",
    "seed_of",
    "token_of",
]

#: The variables of the engine.
SEED_VARIABLE = "DOKIMI_ASSERT_PROP_SEED"
PROFILE_VARIABLE = "DOKIMI_ASSERT_PROP_PROFILE"
BUDGET_VARIABLE = "DOKIMI_ASSERT_PROP_BUDGET"
REPLAY_VARIABLE = "DOKIMI_ASSERT_PROP_REPLAY"

#: The variable that a mutation run sets in every process that it instruments.
_MUTANT_VARIABLE = "DOKIMI_MUTATE_MUTANT"

#: A budget is below 2^33 seconds in every language, and a seed is below 2^64.
_BUDGET_LIMIT = 2**33
_SEED_LIMIT = 2**64

#: The whole text of a decimal number.
_DIGITS = re.compile("[0-9]+")

#: A set of defaults for a whole test run.
Profile = Literal["default", "ci", "campaign"]

#: The profiles by their names.
_PROFILES: dict[str, Profile] = {
    "default": "default",
    "ci": "ci",
    "campaign": "campaign",
}


@dataclass(frozen=True, slots=True)
class Replay:
    """The token that a run replays, and the source of the token.

    Attributes:
        token: The token.
        source: The option replay, or the variable DOKIMI_ASSERT_PROP_REPLAY.
    """

    token: str
    source: str


def _variable(name: str) -> str | None:
    """Return the value of a variable, or None for an unset or empty one."""
    return os.environ.get(name) or None


def _decimal(text: str, limit: int) -> int | None:
    """Return the number of a decimal text below limit, or None for any other text.

    The length check comes first, because int refuses a text of more digits
    than the interpreter converts.
    """
    if not _DIGITS.fullmatch(text) or len(text.lstrip("0")) > len(str(limit)):
        return None
    number = int(text)
    return number if number < limit else None


def mutated() -> bool:
    """Report whether this process runs under a mutation run.

    Returns:
        True when the environment contains DOKIMI_MUTATE_MUTANT.
    """
    return _MUTANT_VARIABLE in os.environ


def profile_of() -> Profile:
    """Return the profile of the environment.

    Returns:
        The profile.

    Raises:
        FaultError: The variable has a profile other than default, ci and
            campaign.
    """
    name = _variable(PROFILE_VARIABLE) or "default"
    profile = _PROFILES.get(name)
    if profile is None:
        raise FaultError(
            PROFILE_VARIABLE,
            f"{json.dumps(name)} is not one of the profiles default, ci and campaign",
        )
    return profile


def seed_of(contract: str, given: int | None, hermetic: bool) -> int:
    """Return the seed of a run of a contract.

    The seed of the seed option comes first. A run that is not hermetic then
    takes the seed of DOKIMI_ASSERT_PROP_SEED. Next, the seed is derived from
    the contract in a process of a mutation run and in a run under the ci
    profile that is not hermetic. Every other run draws a random seed. A run
    that is not hermetic checks the profile first, so a misspelled profile
    fails every such run.

    Args:
        contract: The contract of the property.
        given: The seed of the seed option, or None.
        hermetic: When True, the run does not read the variables.

    Returns:
        The seed.

    Raises:
        FaultError: The profile is not default, ci or campaign, or the seed
            of the variable is not a decimal number below 2^64.
    """
    profile = "default" if hermetic else profile_of()
    if given is not None:
        return given
    text = None if hermetic else _variable(SEED_VARIABLE)
    if text is not None:
        seed = _decimal(text, _SEED_LIMIT)
        if seed is None:
            raise FaultError(
                SEED_VARIABLE, f"{json.dumps(text)} is not a decimal number below 2^64"
            )
        return seed
    if mutated() or profile == "ci":
        return mix(utf8(contract))
    return int.from_bytes(os.urandom(8), "little")


def run_seed(seat: Seat, contract: str) -> int:
    """Return the seed that a run of contract takes without the option seed.

    The run is not hermetic. run_seed returns the value of
    DOKIMI_ASSERT_PROP_SEED when the variable is set. In a process of a
    mutation run, and under the ci profile, it returns the seed that a run
    derives from the contract. Otherwise each call returns a new random seed.
    A caller that passes the result to seed in each of its runs gives every
    run the seed that its first run would take:

        chosen = prop.seed(prop.run_seed(seat, "the suite of the ledger"))
        prop.for_all(seat, "a write is read back", write_read, chosen)
        prop.for_all(seat, "a delete hides the key", delete_hides, chosen)

    A malformed DOKIMI_ASSERT_PROP_SEED and a profile other than default, ci
    and campaign end the call with a fault of prop.run_seed, as seat.fault
    ends one. run_seed then returns 0.

    Args:
        seat: The seat of the call.
        contract: The contract of the property.

    Returns:
        The seed, or 0 after a fault.
    """
    __tracebackhide__ = True
    try:
        return seed_of(contract, None, False)
    except FaultError as error:
        end(seat, of_operation("prop.run_seed", error))
        return 0


def budget_of(hermetic: bool) -> int:
    """Return the length of a campaign in whole seconds.

    Under the campaign profile, the budget is the value of
    DOKIMI_ASSERT_PROP_BUDGET. It is 0 for a run that is not a campaign. A
    hermetic run and a run in a process of a mutation run are not campaigns,
    and they do not read a budget.

    Args:
        hermetic: When True, the run does not read the variables.

    Returns:
        The budget, or 0.

    Raises:
        FaultError: The profile is not default, ci or campaign, or the budget
            is not a whole number of seconds from 1 to 2^33 - 1.
    """
    if hermetic or mutated() or profile_of() != "campaign":
        return 0
    text = os.environ.get(BUDGET_VARIABLE, "")
    seconds = _decimal(text, _BUDGET_LIMIT)
    if seconds is None or seconds < 1:
        raise FaultError(
            BUDGET_VARIABLE,
            f"{json.dumps(text)} is not a whole number of seconds above 0",
        )
    return seconds


def token_of(given: str | None, hermetic: bool) -> Replay | None:
    """Return the token that a run replays, and its source.

    The token of the replay option comes first. A run that is not hermetic
    then takes the token of DOKIMI_ASSERT_PROP_REPLAY.

    Args:
        given: The token of the replay option, or None.
        hermetic: When True, the run does not read the variables.

    Returns:
        The token and its source, or None for a run that does not replay a
        token.
    """
    if given is not None:
        return Replay(given, "replay")
    token = None if hermetic else _variable(REPLAY_VARIABLE)
    return None if token is None else Replay(token, REPLAY_VARIABLE)
