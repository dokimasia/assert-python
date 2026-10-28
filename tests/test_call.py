# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of call.py tests the assertion call that a seat observes."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING

import pytest

from dokimi_assert import check
from dokimi_assert.call import Call

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


class TestCall:
    """Call is an assertion call: the id of the assertion and the contract."""

    def test_states_the_assertion_and_the_contract(self, seat: Collector) -> None:
        """A call has the two fields that a seat observes."""
        call = Call("equal", "the totals match")
        check.equal(
            seat,
            [call.assertion, call.contract],
            ["equal", "the totals match"],
            "the fields of the call",
        )

    def test_equals_a_call_of_the_same_assertion_and_contract(
        self, seat: Collector
    ) -> None:
        """Two calls with the same fields are equal."""
        check.equal(seat, Call("true", "c"), Call("true", "c"), "the calls are equal")

    def test_refuses_a_change_of_a_field(self, seat: Collector) -> None:
        """A seat cannot change a call that it observes."""
        call = Call("true", "c")
        with pytest.raises(dataclasses.FrozenInstanceError):
            call.contract = "d"  # type: ignore[misc]
        check.equal(seat, call.contract, "c", "the contract is unchanged")
