"""The assertion that an assertion can fail."""

from __future__ import annotations

from dokimi import check
from dokimi.seat import Recorder, Standard

OUTER = Standard()


def test_it_returns_the_driven_check_s_own_message() -> None:
    """The rejection carries the reason the check was written for."""
    got = check.rejects(
        OUTER,
        "it rejects two",
        lambda tb: check.equal(tb, 2, 1, "the value is one"),
    )
    check.contains(OUTER, got, "the value is one", "it carries the check's reason")


def test_it_reports_when_the_driven_check_passes() -> None:
    """A check that cannot fail is the defect this catches."""
    seat = Recorder()
    check.rejects(
        seat,
        "it rejects one",
        lambda tb: check.equal(tb, 1, 1, "the value is one"),
    )

    check.is_true(OUTER, seat.failed, "a check that passed is reported")
    check.contains(
        OUTER, seat.message, "must reject", "the failure names what did not happen"
    )


def test_it_returns_empty_when_nothing_failed() -> None:
    """Nothing to carry when the check did not fail."""
    got = check.rejects(
        Recorder(),
        "it rejects one",
        lambda tb: check.equal(tb, 1, 1, "the value is one"),
    )
    check.is_empty(OUTER, got, "nothing is carried when nothing failed")


def test_an_exception_in_the_body_is_not_caught() -> None:
    """A check that raises is a defect, not a rejection."""

    def crash(_: Recorder) -> None:
        """Raise rather than assert, which is a defect in the check."""
        raise RuntimeError("the check itself is broken")

    caught = check.raises(
        OUTER,
        lambda: check.rejects(Recorder(), "it rejects", crash),
        "a raising body is not reported as a rejection",
    )
    check.contains(
        OUTER, str(caught), "the check itself is broken", "the defect surfaces"
    )
