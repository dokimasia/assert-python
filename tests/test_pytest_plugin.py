"""The fixtures, driven as a consumer's test suite would drive them.

These run pytest inside pytest with the pytester fixture, because what
is under test is what a failure looks like from outside: which phase it
lands in, how many failures one run shows, and whose line the traceback
points at. None of that is visible from calling the assertion directly.
"""

from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]


def test_the_seat_fixture_needs_no_conftest(pytester: pytest.Pytester) -> None:
    """Installing the package is the whole setup."""
    pytester.makepyfile(
        """
        from dokimi_assert import check

        def test_it(seat):
            check.equal(seat, 1, 1, "it holds")
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_check_fails_the_test_at_the_first_failure(pytester: pytest.Pytester) -> None:
    """An aborting assertion stops the body where it stands."""
    pytester.makepyfile(
        """
        from dokimi_assert import check

        def test_it(seat):
            check.equal(seat, 1, 2, "the first property holds")
            raise RuntimeError("this line must not run")
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*the first property holds: want 2, got 1*"])


def test_expect_reports_every_failure_in_one_run(pytester: pytest.Pytester) -> None:
    """Recording the failures is what makes seeing all of them possible."""
    pytester.makepyfile(
        """
        from dokimi_assert import expect

        def test_it(seat):
            expect.equal(seat, 1, 2, "the first property holds")
            expect.equal(seat, 3, 4, "the second property holds")
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(
        [
            "*2 failures:*",
            "*1. the first property holds: want 2, got 1*",
            "*2. the second property holds: want 4, got 3*",
        ]
    )


def test_a_recorded_failure_fails_the_test_not_the_teardown(
    pytester: pytest.Pytester,
) -> None:
    """A teardown error reads as a passing test with a problem after it."""
    pytester.makepyfile(
        """
        from dokimi_assert import expect

        def test_it(seat):
            expect.equal(seat, 1, 2, "it holds")
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(failed=1, errors=0, passed=0)


def test_the_traceback_points_at_the_caller(pytester: pytest.Pytester) -> None:
    """A library frame in the traceback buries the line that matters."""
    pytester.makepyfile(
        """
        from dokimi_assert import check

        def test_it(seat):
            check.equal(seat, 1, 2, "it holds")
        """
    )
    result = pytester.runpytest()
    result.stdout.fnmatch_lines(["*test_the_traceback_points_at_the_caller.py:4*"])
    result.stdout.no_fnmatch_line("*dokimi_assert/check.py*")
    result.stdout.no_fnmatch_line("*_matcher*")


def test_a_body_that_raised_keeps_its_own_failure(pytester: pytest.Pytester) -> None:
    """The first failure explains the rest, so it is the one shown."""
    pytester.makepyfile(
        """
        from dokimi_assert import expect

        def test_it(seat):
            expect.equal(seat, 1, 2, "recorded before the crash")
            raise RuntimeError("the real problem")
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*RuntimeError: the real problem*"])


def test_both_surfaces_share_one_seat(pytester: pytest.Pytester) -> None:
    """A recorded failure survives until the body ends, then reports."""
    pytester.makepyfile(
        """
        from dokimi_assert import check, expect

        def test_it(seat):
            expect.equal(seat, 1, 2, "recorded first")
            check.equal(seat, 3, 3, "this one holds")
            expect.equal(seat, 4, 5, "recorded second")
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*2 failures:*"])


def test_a_passing_test_reports_nothing(pytester: pytest.Pytester) -> None:
    """Nothing recorded means nothing raised at the end of the body."""
    pytester.makepyfile(
        """
        from dokimi_assert import check, expect

        def test_it(seat):
            check.equal(seat, 1, 1, "it holds")
            expect.contains(seat, [1, 2], 1, "it is there")
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_the_recorder_fixture_fails_nothing(pytester: pytest.Pytester) -> None:
    """It is for testing an assertion, so it must not fail the test."""
    pytester.makepyfile(
        """
        from dokimi_assert import check

        def test_it(recorder):
            check.equal(recorder, 1, 2, "recorded, not suffered")
            assert recorder.failed
            assert "want 2, got 1" in recorder.message
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_two_seats_in_one_test_both_report(pytester: pytest.Pytester) -> None:
    """A fixture that takes a seat leaves its failures reportable too."""
    pytester.makepyfile(
        """
        import pytest
        from dokimi_assert import expect

        @pytest.fixture
        def subject(seat):
            expect.equal(seat, "set up", "wrong", "the fixture's own contract")
            return seat

        def test_it(subject):
            expect.equal(subject, 1, 2, "the test's contract")
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*2 failures:*"])
