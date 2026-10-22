# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of expect.py tests the surface that records a failure and continues.

It uses pytest's assert alone, because the other specs assert with the
library's surfaces.
"""

from __future__ import annotations

import pytest

from dokimi_assert import check, expect
from dokimi_assert.seat import Recorder
from helpers import FAILING, MSG, records, seated


def test_exports_an_assertion_for_each_failing_call_of_the_shared_table() -> None:
    """The names of the surface are the names of the table."""
    assert sorted(expect.__all__) == sorted(FAILING)


@pytest.mark.parametrize("name", sorted(FAILING))
def test_reports_its_failure_through_record(name: str) -> None:
    """A failure goes to the recording surface of the seat alone."""
    seat, clock = seated()
    FAILING[name](expect, seat, clock, MSG)
    assert [f.contract for f in seat.failures] == [MSG]
    assert seat.messages == [seat.message]


@pytest.mark.parametrize("name", sorted(FAILING))
def test_writes_the_call_records_of_check_as_a_recording_surface(name: str) -> None:
    """The records differ from those of check in the field aborting alone."""
    aborting, aborting_clock = seated()
    recording, recording_clock = seated()
    FAILING[name](check, aborting, aborting_clock, MSG)
    FAILING[name](expect, recording, recording_clock, MSG)
    want = [{**r, "aborting": False} for r in records(aborting)]
    assert records(recording) == want


class TestRaises:
    """expect.raises returns the exception that fn raised."""

    def test_returns_what_fn_raised(self) -> None:
        """A caller reads the exception that the call returns."""
        error = ValueError("boom")

        def fn() -> None:
            raise error

        assert expect.raises(Recorder(), fn, MSG) is error


class TestErrorAs:
    """expect.error_as returns the exception of a class in the chain of an error."""

    def test_returns_the_exception_of_the_class_in_the_chain(self) -> None:
        """A caller reads the fields of the exception that the call returns."""
        cause = KeyError("k")
        error = ValueError("v")
        error.__cause__ = cause
        assert expect.error_as(Recorder(), error, KeyError, MSG) is cause


class TestRejects:
    """expect.rejects returns the failure records of a check."""

    def test_returns_the_failure_records_of_the_check(self) -> None:
        """A caller reads the records of the check that the call returns."""
        failures = expect.rejects(
            Recorder(),
            MSG,
            lambda inner: expect.is_true(inner, False, "the flag is true"),
        )
        assert [f.contract for f in failures] == ["the flag is true"]
