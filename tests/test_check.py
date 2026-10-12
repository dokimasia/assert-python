"""The spec of check.py tests the surface that stops the test at the first failure.

It uses pytest's assert alone, because the other specs assert with this
surface.
"""

from __future__ import annotations

import pytest

from dokimi_assert import check
from dokimi_assert.seat import Recorder
from helpers import FAILING, MSG, records, seated


def test_exports_an_assertion_for_each_failing_call_of_the_shared_table() -> None:
    """The names of the surface are the names of the table."""
    assert sorted(check.__all__) == sorted(FAILING)


@pytest.mark.parametrize("name", sorted(FAILING))
def test_reports_its_failure_through_fail(name: str) -> None:
    """A failure goes to the aborting surface of the seat alone."""
    seat, clock = seated()
    FAILING[name](check, seat, clock, MSG)
    assert [f.contract for f in seat.failures] == [MSG]
    assert seat.message != ""
    assert seat.messages == []


@pytest.mark.parametrize("name", sorted(FAILING))
def test_writes_a_call_record_of_the_aborting_surface(name: str) -> None:
    """The record of the call has aborting true."""
    seat, clock = seated()
    FAILING[name](check, seat, clock, MSG)
    assert [r["aborting"] for r in records(seat) if r.get("parent") is None] == [True]


class TestRaises:
    """check.raises returns the exception that fn raised."""

    def test_returns_what_fn_raised(self) -> None:
        """A caller reads the exception that the call returns."""
        error = ValueError("boom")

        def fn() -> None:
            raise error

        assert check.raises(Recorder(), fn, MSG) is error


class TestErrorAs:
    """check.error_as returns the exception of a class in the chain of an error."""

    def test_returns_the_exception_of_the_class_in_the_chain(self) -> None:
        """A caller reads the fields of the exception that the call returns."""
        cause = KeyError("k")
        error = ValueError("v")
        error.__cause__ = cause
        assert check.error_as(Recorder(), error, KeyError, MSG) is cause


class TestRejects:
    """check.rejects returns the failure records of a check."""

    def test_returns_the_failure_records_of_the_check(self) -> None:
        """A caller reads the records of the check that the call returns."""
        failures = check.rejects(
            Recorder(),
            MSG,
            lambda inner: check.is_true(inner, False, "the flag is true"),
        )
        assert [f.contract for f in failures] == ["the flag is true"]
