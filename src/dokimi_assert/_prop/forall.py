# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The assertion that a body passes for every case that a run generates."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.verdict import Running
from dokimi_assert._prop.detail import FOR_ALL
from dokimi_assert._prop.option import Option, configure
from dokimi_assert._prop.property import Call, Property
from dokimi_assert.failure import call_site

if TYPE_CHECKING:
    from collections.abc import Callable

    from dokimi_assert._matcher.seat import Seat
    from dokimi_assert._prop.case import Case

__all__ = ["for_all"]


def for_all(
    seat: Seat, contract: str, body: Callable[[Case], object], *options: Option
) -> None:
    """Fail when body fails for a case that a run generates.

    A run that does not pass fails the test on seat with one record of
    prop-for-all. The contract of the record is contract. Its location is
    the call of for_all.

    A run tries the case of the draws option first. It then replays the
    stored cases of the property from the oldest, and runs the case whose
    every choice is its target. Then it runs random cases of the seed. After
    each random case, it runs a prefix case and an edge case. The run stops
    when it has run the number of valid cases that the cases option sets,
    when it has tested every input of the domain, or when it has generated
    ten times that number of cases. A failing case is replayed, shrunk to
    the smallest case that fails in the same way, and explained.

    A run without a failing case fails in three cases. The run checks them
    in this order:

    - It rejected more than ten cases for every valid one.
    - The cases did not request an input.
    - It refuted a coverage requirement or left one unmet.

    Under the campaign profile, for_all runs a campaign for the number of
    seconds in DOKIMI_ASSERT_PROP_BUDGET on the platform clock. The campaign
    explores the cases near those that counted a new label, recorded a new
    fingerprint or scored higher. It shrinks, explains and stores each
    failure of a new identity when it finds the failure. A hermetic run and
    a run in a process of a mutation run do not run a campaign.

    The detail of the record has the ten fields of prop-for-all: outcome,
    cases, rejected, seed, counterexample, failure, choices, others,
    divergence and coverage. A field that the outcome does not use is None.
    A seat that takes records receives the record. Any other seat receives
    the sentence of the record. The sentence contains the notes of the
    failing case. The call record of a pass contains the detail of the run
    too. The record of each call of a case has the call of for_all as its
    parent and the phase of the case.

    for_all ends the call with a fault before a run in these cases:

    - DOKIMI_ASSERT_PROP_PROFILE is not default, ci or campaign.
    - DOKIMI_ASSERT_PROP_SEED is not a decimal number below 2^64.
    - The budget of a campaign is not a whole number of seconds above 0.
    - The token to replay is not a replay token.
    - The text of the draws option is not a JSON array of draw entries and
      step entries.
    - The store cannot be read or has a damaged file.
    - A second property of the test has the same contract and store.

    An entry of the draws option that the body cannot follow ends the call
    with a fault before any other case. for_all writes an entry of each
    failure of a counterexample to the store. It does not write an entry
    when a file of the name of the entry exists, or in a process of a
    mutation run. It notes a store that cannot keep an entry: a seat with
    report_fault receives the fault with ending False, and any other seat a
    warning.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        contract: The property under test.
        body: The body. It takes its inputs from its case. It can be a
            coroutine function.
        *options: The settings of the run.

    Example:
        prop.for_all(seat, "a sorted list is ordered", sorted_is_ordered)
    """
    __tracebackhide__ = True
    seat.helper()
    where = call_site()
    running = Running.begin(seat, where)
    call = Call("prop.for_all", FOR_ALL, contract, where)
    try:
        prop = Property.of(seat, call, configure(options))
    except FaultError as error:
        Property.fault(running, call, error)
        return
    prop.run(seat, running, body)
