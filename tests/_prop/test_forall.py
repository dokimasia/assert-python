# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/forall.py tests the assertion that a body passes for every case."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from dokimi_assert import check
from dokimi_assert._prop.detail import FOR_ALL
from dokimi_assert._prop.engine.choice import IntegerBounds
from dokimi_assert._prop.engine.generator import Integer
from dokimi_assert._prop.environment import PROFILE_VARIABLE, SEED_VARIABLE
from dokimi_assert._prop.forall import for_all
from dokimi_assert._prop.option import hermetic, seed, store
from dokimi_assert.seat import Collector, Recorder, Standard
from helpers import records

if TYPE_CHECKING:
    import pytest

    from dokimi_assert._prop.case import Case

#: A generator of one digit.
DIGITS = Integer(IntegerBounds(0, 9))


def below_five(c: Case) -> None:
    """Fail for a digit of 5 or more under the label x."""
    check.is_true(c, c.draw(DIGITS, "x") < 5, "x is below 5")


class TestForAll:
    """for_all checks that a body passes for every case of a run."""

    def test_passes_a_body_that_passes_every_case_on_the_seat_of_the_test(
        self, seat: Collector
    ) -> None:
        """Every digit is in its range."""
        for_all(
            seat,
            "every digit is a digit",
            lambda c: check.in_range(c, c.draw(DIGITS, "x"), 0, 9, "x is a digit"),
            hermetic(),
            seed(1),
            store(""),
        )

    def test_fails_with_one_record_of_prop_for_all_at_the_call_of_for_all(
        self, seat: Collector
    ) -> None:
        """The record contains the failure of the case."""
        recorder = Recorder()
        for_all(recorder, "every digit is below 5", below_five, hermetic(), seed(1))
        failure = recorder.failures[0]
        check.equal(
            seat,
            [
                len(recorder.failures),
                failure.assertion,
                failure.contract,
                failure.detail["failure"].assertion,
            ],
            [1, FOR_ALL, "every digit is below 5", "true"],
            "the run has one record with the failure of the case",
        )
        where = failure.where
        check.has_suffix(
            seat,
            None if where is None else where.file,
            "test_forall.py",
            "the location is the call of for_all",
        )

    def test_awaits_each_case_of_a_coroutine_body(self, seat: Collector) -> None:
        """The record counts every case that settled."""
        recorder = Recorder()
        settled: list[int] = []

        async def body(c: Case) -> None:
            c.draw(DIGITS, "x")
            await asyncio.sleep(0)
            settled.append(1)

        for_all(recorder, "a coroutine body is awaited", body, hermetic(), seed(1))
        check.equal(
            seat,
            records(recorder)[0]["detail"]["cases"],
            len(settled),
            "the record counts every case that settled",
        )

    def test_ends_the_call_with_a_fault_for_a_seed_variable_that_is_not_a_number(
        self, seat: Collector, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The variable has the value abc."""
        monkeypatch.delenv(PROFILE_VARIABLE, raising=False)
        monkeypatch.setenv(SEED_VARIABLE, "abc")
        recorder = Recorder()
        for_all(recorder, "c", below_five)
        check.equal(
            seat,
            recorder.message,
            'prop.for_all: DOKIMI_ASSERT_PROP_SEED: "abc" is not a decimal number '
            "below 2^64",
            "the fault has the variable and the reason",
        )

    def test_raises_the_sentence_of_the_record_on_a_seat_that_stops(
        self, seat: Collector
    ) -> None:
        """A recorder receives the same sentence from the same run."""
        recorder = Recorder()
        for_all(recorder, "every digit is below 5", below_five, hermetic(), seed(1))
        error = check.raises(
            seat,
            lambda: for_all(
                Standard(), "every digit is below 5", below_five, hermetic(), seed(1)
            ),
            "the run stops the test",
        )
        check.equal(
            seat,
            [type(error), str(error)],
            [AssertionError, recorder.message],
            "the error has the sentence of the record",
        )
