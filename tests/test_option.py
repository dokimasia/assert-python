# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of option.py: the relaxations that a caller passes to one comparison."""

from __future__ import annotations

import math

from dokimi_assert import check, option
from dokimi_assert._matcher import option as matcher
from dokimi_assert.seat import Collector, Recorder


def test_re_exports_the_options_of_the_matcher(seat: Collector) -> None:
    """Each public option is the matcher's function."""
    check.equal(
        seat,
        [
            option.equate_empty is matcher.equate_empty,
            option.equate_nans is matcher.equate_nans,
            option.by_identity is matcher.by_identity,
            option.Option is matcher.Option,
        ],
        [True, True, True, True],
        "the public options",
    )


class TestEquateEmpty:
    """equate_empty."""

    def test_relaxes_the_call_that_it_is_passed_to_alone(self, seat: Collector) -> None:
        """A call without the option compares strictly."""
        recorder = Recorder()
        check.equal(recorder, None, [], "relaxed", option.equate_empty())
        check.equal(recorder, None, [], "strict")
        check.equal(
            seat,
            [f.contract for f in recorder.failures],
            ["strict"],
            "only the call without the option fails",
        )


class TestEquateNans:
    """equate_nans."""

    def test_relaxes_the_call_that_it_is_passed_to_alone(self, seat: Collector) -> None:
        """A call without the option compares strictly."""
        recorder = Recorder()
        check.equal(recorder, math.nan, math.nan, "relaxed", option.equate_nans())
        check.equal(recorder, math.nan, math.nan, "strict")
        check.equal(
            seat,
            [f.contract for f in recorder.failures],
            ["strict"],
            "only the call without the option fails",
        )


class TestByIdentity:
    """by_identity."""

    def test_narrows_the_call_that_it_is_passed_to_alone(self, seat: Collector) -> None:
        """A call without the option compares by structure."""
        recorder = Recorder()
        check.equal(recorder, {"n": 1}, {"n": 1}, "by identity", option.by_identity())
        check.equal(recorder, {"n": 1}, {"n": 1}, "by structure")
        check.equal(
            seat,
            [f.contract for f in recorder.failures],
            ["by identity"],
            "only the call with the option fails",
        )
