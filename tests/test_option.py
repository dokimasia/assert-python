"""Relaxations a caller may apply to one comparison."""

from __future__ import annotations

import math

from dokimi import check
from dokimi._matcher.option import equate_empty, equate_nans, settings
from dokimi.seat import Recorder, Standard

OUTER = Standard()


def test_no_options_relax_nothing() -> None:
    """The default comparison applies every rule."""
    folded = settings(())
    check.is_false(OUTER, folded.equate_empty, "empty is not relaxed by default")
    check.is_false(OUTER, folded.equate_nans, "NaN is not relaxed by default")


def test_an_option_relaxes_only_its_own_rule() -> None:
    """The flags are independent."""
    folded = settings((equate_empty(),))
    check.is_true(OUTER, folded.equate_empty, "the asked-for rule is relaxed")
    check.is_false(OUTER, folded.equate_nans, "the other rule is not")


def test_options_fold_together() -> None:
    """Several options apply at once."""
    folded = settings((equate_empty(), equate_nans()))
    check.is_true(OUTER, folded.equate_empty, "the first is relaxed")
    check.is_true(OUTER, folded.equate_nans, "the second is relaxed")


def test_passing_one_twice_is_passing_it_once() -> None:
    """An option sets a flag rather than appending to a list."""
    check.equal(
        OUTER,
        settings((equate_empty(), equate_empty())),
        settings((equate_empty(),)),
        "a repeated option changes nothing",
    )


def test_an_option_applies_to_one_call_only() -> None:
    """An option never leaks into a call it was not passed to."""
    relaxed, strict = Recorder(), Recorder()

    check.equal(relaxed, [], None, "opted in", equate_empty())
    check.equal(strict, [], None, "not opted in")

    check.is_false(OUTER, relaxed.failed, "the opted-in call passes")
    check.is_true(OUTER, strict.failed, "the next call is unaffected")


def test_equate_nans_applies_to_one_call_only() -> None:
    """The same holds for the NaN relaxation."""
    relaxed, strict = Recorder(), Recorder()
    nan = math.nan

    check.equal(relaxed, nan, nan, "opted in", equate_nans())
    check.equal(strict, nan, nan, "not opted in")

    check.is_false(OUTER, relaxed.failed, "the opted-in call passes")
    check.is_true(OUTER, strict.failed, "the next call is unaffected")
