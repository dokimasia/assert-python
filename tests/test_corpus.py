"""The corpus, driven against both surfaces.

This is what checks meaning rather than membership: the same cases run
against every implementation of the standard, so a library that means
something different by the same name fails here.

Every case runs twice, once per surface. The two carrying the same
assertions means they produce the same outcome from the same case, and
running one and trusting the other would leave that untested.

Written with pytest's assert rather than with this library. Everything
here reports through one function, so a verdict written with the
subject goes quiet exactly when the subject does: silencing that
function leaves every case passing, having checked nothing.
"""

from __future__ import annotations

from typing import Any

import pytest

from dokimi_assert.clock import Controlled
from dokimi_assert.conformance import definition
from dokimi_assert.conformance.corpus import SURFACES, Case, cases
from dokimi_assert.conformance.driver import run_subject
from dokimi_assert.seat import Recorder

CASES = list(cases())


def test_the_corpus_is_not_empty() -> None:
    """A corpus that read nothing would pass having checked nothing."""
    assert CASES, "the vendored corpus states cases"


def test_both_surfaces_are_driven() -> None:
    """Driving one surface would leave the other's meaning untested."""
    assert sorted(SURFACES) == ["check", "expect"], "both surfaces are driven"


@pytest.mark.parametrize("surface", sorted(SURFACES))
@pytest.mark.parametrize("case", CASES, ids=lambda c: c.id)
def test_case(case: Case, surface: str) -> None:
    """Drive one case through one surface and hold it to what it states."""
    reason = case.skip_reason
    if reason is not None:
        pytest.skip(f"declared skip: {reason}")

    if case.subject is not None:
        pytest.skip("driven by the subject runner")

    invoke = SURFACES[surface].get(case.assertion)
    assert invoke is not None, f"{surface} carries an invoker for {case.assertion}"

    recorder = Recorder()
    invoke(recorder, *case.args, case.id)

    mismatch = case.check(recorder)
    assert mismatch is None, f"{surface} disagrees with the corpus: {mismatch}"


def test_a_failure_carries_exactly_the_fields_it_declares() -> None:
    """The definition states what a record holds, and it holds that.

    A case checks the fields it names and ignores the rest, so nothing
    else would notice an assertion reporting a field the definition does
    not state, or dropping one it does.
    """
    declared = definition.detail_fields()
    mismatched: list[str] = []

    for case in cases():
        if case.expect != "fail" or case.skip_reason:
            continue
        invoke = SURFACES["check"].get(case.assertion)
        if invoke is None:
            continue

        seat = _drive(invoke, case)
        if seat is None or not seat.failures:
            continue

        got = set(seat.failures[0].detail)
        want = declared[case.assertion]
        if got != want:
            mismatched.append(
                f"{case.id}: reports {sorted(got)}, declares {sorted(want)}"
            )

    assert not mismatched, "\n".join(mismatched)


def _drive(invoke: Any, case: Case) -> Recorder | None:
    """Run one case however it states itself, or None when it cannot run.

    A case hands over values or names a behaviour, and the two are driven
    differently. Both end at the same seat, so a check over every case
    reads one shape.

    Args:
        invoke: The assertion under test, on the surface being driven.
        case: The case to run.

    Returns:
        The seat it reported to, or None when the case could not run.
    """
    seat = Recorder().with_clock(Controlled())
    if case.subject is None:
        invoke(seat, *case.args, case.id)
        return seat
    if run_subject(invoke, case.assertion, case.subject, seat, case.id):
        return seat
    return None


def _check_where(seat: Recorder, case: Case) -> None:
    """Hold every record to naming a real call site outside the library.

    A case cannot state a line: the line is wherever the caller put the
    call. What every case can state is that the record points somewhere
    a reader can open, and never at the machinery that built it. Both
    call-site bugs this standard has found were of that shape.

    Args:
        seat: The seat the assertion reported to.
        case: The case that was driven, for the failure message.
    """
    for held in seat.failures:
        assert held.where is not None, (
            f"{case.id}: {held.assertion} reported no call site"
        )
        assert held.where.line > 0, f"{case.id}: {held.assertion} reported line zero"
        assert "_matcher" not in held.where.file, (
            f"{case.id}: {held.assertion} points at {held.where.file}, "
            "which is the library reporting its own frame"
        )


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_a_named_subject_is_driven_or_reported_as_unbuildable(surface: str) -> None:
    """Every case naming a behaviour is driven, and the rest are counted.

    A subject kind this language cannot build is a case nobody checks, so
    the count is printed rather than left silent.
    """
    driven = 0
    unbuildable: list[str] = []

    for case in cases():
        if case.subject is None or case.skip_reason:
            continue
        invoke = SURFACES[surface].get(case.assertion)
        if invoke is None:
            unbuildable.append(f"{case.id}: no invoker")
            continue

        seat = Recorder().with_clock(Controlled())
        if not run_subject(invoke, case.assertion, case.subject, seat, case.id):
            unbuildable.append(f"{case.id}: no subject named {case.subject!r}")
            continue

        mismatch = case.check(seat)
        assert mismatch is None, f"{surface} disagrees with the corpus: {mismatch}"
        driven += 1

    print(f"\n{surface}: {driven} subject cases driven, {len(unbuildable)} unbuildable")
    assert driven > 0, f"{surface} drove no subject case at all"
    assert not unbuildable, "\n".join(unbuildable)


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_every_reported_record_names_a_call_site(surface: str) -> None:
    """A failure a reader cannot locate is half a failure."""
    for case in cases():
        if case.expect != "fail" or case.skip_reason:
            continue
        invoke = SURFACES[surface].get(case.assertion)
        if invoke is None:
            continue

        seat = _drive(invoke, case)
        if seat is not None:
            _check_where(seat, case)
