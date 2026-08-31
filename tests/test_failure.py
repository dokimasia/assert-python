"""The record a failing assertion reports, and the sentence it renders to."""

from __future__ import annotations

from dokimi_assert import check
from dokimi_assert.failure import Failure, Where, call_site, render
from dokimi_assert.seat import Recorder, Standard

#: The seat these tests state their own verdicts on.
OUTER = Standard()


def test_a_record_carrying_nothing_renders_the_contract_alone() -> None:
    """True and false report the contract and no more."""
    said = render(Failure(assertion="true", contract="the flag is set"))

    check.equal(OUTER, said, "the flag is set", "it says the contract and no more")


def test_want_is_said_before_got() -> None:
    """Python reads want before got, the way the language's own idiom does."""
    said = render(
        Failure(
            assertion="length",
            contract="every item comes back",
            detail={"got": 2, "want": 3},
        )
    )

    check.equal(
        OUTER, said, "every item comes back: want 3, got 2", "want leads, then got"
    )


def test_a_field_it_does_not_know_follows_the_ones_it_does() -> None:
    """An unlisted field still reads, after the ones with a fixed place."""
    said = render(
        Failure(
            assertion="made-up",
            contract="the contract",
            detail={"zebra": 1, "got": 2, "apple": 3},
        )
    )

    check.equal(
        OUTER, said, "the contract: got 2, apple 3, zebra 1", "the known field leads"
    )


def test_a_reported_failure_carries_the_call_site() -> None:
    """A record says where the assertion was written, not where it reports."""
    seat = Recorder()
    check.equal(seat, 1, 2, "the values match")

    where = seat.failures[0].where
    check.is_not_none(OUTER, where, "the record carries a call site")
    assert where is not None
    check.contains(
        OUTER, where.file, "test_failure.py", "it names the file the caller wrote in"
    )
    check.is_true(OUTER, where.line > 0, "it names a line")


def test_call_site_answers_none_when_it_runs_out_of_frames() -> None:
    """Climbing past the stack answers nothing rather than raising."""
    check.is_none(
        OUTER, call_site(depth=10_000), "it answers nothing above the outermost frame"
    )


def test_where_states_a_file_and_a_line() -> None:
    """The pair is what a reader needs to open the call site."""
    at = Where(file="store_test.py", line=42)

    check.equal(OUTER, at.file, "store_test.py", "it names the file")
    check.equal(OUTER, at.line, 42, "it names the line")
