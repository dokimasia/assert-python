"""The spec of pytest_plugin.py drives the fixtures in the same way as a consumer suite.

The cases run pytest inside pytest with the pytester fixture, because the
behaviour under test is the report of a run. The report has the phase of a
failure, the failures of one test, the line of the traceback and the
properties of the JUnit XML report. The spec uses pytest's assert alone,
because the other specs assert on the seat that the plugin supplies.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ElementTree

import pytest

from dokimi_assert.pytest_plugin import RECORDS
from dokimi_assert.seat import Collector, Recorder

pytest_plugins = ["pytester"]


class TestRecords:
    """RECORDS is the prefix of the name of the user property of a call record."""

    def test_contains_the_prefix_dokimi_assert(self) -> None:
        """The name of a record is RECORDS followed by its number."""
        assert RECORDS == "dokimi.assert."


class TestSeats:
    """SEATS is the key of the collectors that the fixture gave to a test."""

    def test_keys_the_seat_of_the_test_in_the_stash_of_its_item(
        self, pytester: pytest.Pytester
    ) -> None:
        """The stash of the item has the one seat of the test."""
        pytester.makepyfile(
            """
            from dokimi_assert.pytest_plugin import SEATS

            def test_it(seat, request):
                assert request.node.stash[SEATS] == [seat]
            """
        )
        pytester.runpytest().assert_outcomes(passed=1)


class TestSeat:
    """seat supplies the seat of a test."""

    def test_supplies_a_collector(self, seat: Collector) -> None:
        """The seat of a test is a Collector."""
        assert isinstance(seat, Collector)

    def test_does_not_need_a_conftest(self, pytester: pytest.Pytester) -> None:
        """The installed package registers the fixture."""
        pytester.makepyfile(
            """
            from dokimi_assert import check

            def test_it(seat):
                check.equal(seat, 1, 1, "the values are equal")
            """
        )
        pytester.runpytest().assert_outcomes(passed=1)

    def test_fails_the_test_at_the_first_failure_of_check(
        self, pytester: pytest.Pytester
    ) -> None:
        """An aborting assertion stops the body."""
        pytester.makepyfile(
            """
            from dokimi_assert import check

            def test_it(seat):
                check.equal(seat, 1, 2, "the first values are equal")
                raise RuntimeError("this line does not run")
            """
        )
        result = pytester.runpytest()
        result.assert_outcomes(failed=1)
        result.stdout.fnmatch_lines(["*the first values are equal: want 2, got 1*"])
        result.stdout.no_fnmatch_line("*this line does not run*")

    def test_points_the_traceback_at_the_caller(
        self, pytester: pytest.Pytester
    ) -> None:
        """The traceback does not have a frame of the library."""
        pytester.makepyfile(
            test_caller="""
            from dokimi_assert import check

            def test_it(seat):
                check.equal(seat, 1, 2, "the values are equal")
            """
        )
        result = pytester.runpytest()
        result.stdout.fnmatch_lines(["*test_caller.py:4*"])
        result.stdout.no_fnmatch_line("*dokimi_assert/*.py:*")

    def test_names_the_test_by_its_module_path_class_and_name(
        self, pytester: pytest.Pytester
    ) -> None:
        """The path of a test is the path of its store."""
        pytester.makepyfile(
            **{
                "sub/test_path": """
                import pytest
                from dokimi_assert._matcher.seat import named_test

                class TestA:
                    @pytest.mark.parametrize("n", [1])
                    def test_b(self, seat, n):
                        want = ("sub", "test_path.py", "TestA", "test_b[1]")
                        assert named_test(seat) == want
                """
            }
        )
        pytester.runpytest().assert_outcomes(passed=1)

    def test_does_not_write_a_property_with_recording_off(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A test without the switch does not have records in its report."""
        monkeypatch.delenv("DOKIMI_ASSERT_RECORD", raising=False)
        pytester.makepyfile(
            """
            from dokimi_assert import check

            def test_it(seat):
                check.is_true(seat, True, "the flag is set")
            """
        )
        pytester.runpytest_subprocess("--junitxml=report.xml").assert_outcomes(passed=1)
        report = ElementTree.parse(pytester.path / "report.xml")
        assert report.findall(".//property") == []

    def test_writes_each_call_record_as_a_property_of_the_report(
        self, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The JUnit XML report has the records in call order."""
        monkeypatch.setenv("DOKIMI_ASSERT_RECORD", "1")
        pytester.makepyfile(
            """
            from dokimi_assert import check, expect

            def test_it(seat):
                check.is_true(seat, True, "the first is true")
                expect.equal(seat, 1, 2, "the second fails")
            """
        )
        result = pytester.runpytest_subprocess("--junitxml=report.xml")
        result.assert_outcomes(failed=1)
        report = ElementTree.parse(pytester.path / "report.xml")
        properties = report.findall(".//testcase/properties/property")
        stated = [(p.get("name"), json.loads(p.get("value", ""))) for p in properties]
        assert [
            (name, r["seq"], r["assertion"], r["verdict"]) for name, r in stated
        ] == [
            ("dokimi.assert.1", 1, "true", "pass"),
            ("dokimi.assert.2", 2, "equal", "fail"),
        ]
        assert stated[1][1]["detail"] == {
            "want": {"type": "int", "value": 2},
            "got": {"type": "int", "value": 1},
        }


class TestRecorder:
    """recorder supplies a seat that does not fail the test."""

    def test_supplies_a_recorder(self, recorder: Recorder) -> None:
        """The fixture supplies a new Recorder."""
        assert isinstance(recorder, Recorder)
        assert not recorder.failed

    def test_does_not_fail_the_test(self, pytester: pytest.Pytester) -> None:
        """A failure on the recorder does not fail the test."""
        pytester.makepyfile(
            """
            from dokimi_assert import check

            def test_it(recorder):
                check.equal(recorder, 1, 2, "recorded, not raised")
                assert recorder.message == "recorded, not raised: want 2, got 1"
            """
        )
        pytester.runpytest().assert_outcomes(passed=1)


class TestPytestRuntestCall:
    """pytest_runtest_call runs the cleanups and reports the failures of a test."""

    def test_reports_every_failure_of_expect_in_one_run(
        self, pytester: pytest.Pytester
    ) -> None:
        """The recorded failures of a test are one numbered list."""
        pytester.makepyfile(
            """
            from dokimi_assert import expect

            def test_it(seat):
                expect.equal(seat, 1, 2, "the first values are equal")
                expect.equal(seat, 3, 4, "the second values are equal")
            """
        )
        result = pytester.runpytest()
        result.assert_outcomes(failed=1)
        result.stdout.fnmatch_lines(
            [
                "*2 failures:*",
                "*1. the first values are equal: want 2, got 1*",
                "*2. the second values are equal: want 4, got 3*",
            ]
        )

    def test_fails_the_call_phase_and_not_the_teardown(
        self, pytester: pytest.Pytester
    ) -> None:
        """A recorded failure fails the test itself."""
        pytester.makepyfile(
            """
            from dokimi_assert import expect

            def test_it(seat):
                expect.equal(seat, 1, 2, "the values are equal")
            """
        )
        pytester.runpytest().assert_outcomes(failed=1, errors=0, passed=0)

    def test_keeps_the_exception_of_a_body_that_raised(
        self, pytester: pytest.Pytester
    ) -> None:
        """The exception of the body comes first, and the run reports it."""
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

    def test_reports_the_failures_of_both_surfaces_on_one_seat(
        self, pytester: pytest.Pytester
    ) -> None:
        """A recorded failure waits for the end of the body."""
        pytester.makepyfile(
            """
            from dokimi_assert import check, expect

            def test_it(seat):
                expect.equal(seat, 1, 2, "recorded first")
                check.equal(seat, 3, 3, "these values are equal")
                expect.equal(seat, 4, 5, "recorded second")
            """
        )
        result = pytester.runpytest()
        result.assert_outcomes(failed=1)
        result.stdout.fnmatch_lines(["*2 failures:*"])

    def test_reports_the_failures_of_every_seat_of_a_test(
        self, pytester: pytest.Pytester
    ) -> None:
        """A fixture that takes the seat shares it with the test."""
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

    def test_passes_a_test_whose_assertions_pass(
        self, pytester: pytest.Pytester
    ) -> None:
        """A seat without collected failures does not raise."""
        pytester.makepyfile(
            """
            from dokimi_assert import check, expect

            def test_it(seat):
                check.equal(seat, 1, 1, "the values are equal")
                expect.contains(seat, [1, 2], 1, "the list contains 1")
            """
        )
        pytester.runpytest().assert_outcomes(passed=1)

    def test_runs_the_cleanups_after_the_body_the_last_registered_first(
        self, pytester: pytest.Pytester
    ) -> None:
        """The cleanups have run when the next test starts."""
        pytester.makepyfile(
            """
            ran = []

            def test_registers(seat):
                seat.cleanup(lambda: ran.append("first"))
                seat.cleanup(lambda: ran.append("second"))
                assert ran == []

            def test_ran():
                assert ran == ["second", "first"]
            """
        )
        pytester.runpytest().assert_outcomes(passed=2)

    def test_runs_the_cleanups_of_a_test_that_failed(
        self, pytester: pytest.Pytester
    ) -> None:
        """A failure of the body does not skip the cleanups."""
        pytester.makepyfile(
            """
            from dokimi_assert import check

            ran = []

            def test_fails(seat):
                seat.cleanup(lambda: ran.append("after a failure"))
                check.is_true(seat, False, "the test fails")

            def test_ran():
                assert ran == ["after a failure"]
            """
        )
        pytester.runpytest().assert_outcomes(failed=1, passed=1)

    def test_fails_a_test_whose_cleanup_raises(self, pytester: pytest.Pytester) -> None:
        """The error of a cleanup is a failure of the test."""
        pytester.makepyfile(
            """
            def test_it(seat):
                def busy():
                    raise OSError("the directory is busy")

                seat.cleanup(busy)
            """
        )
        result = pytester.runpytest()
        result.assert_outcomes(failed=1, errors=0)
        result.stdout.fnmatch_lines(["*a cleanup failed: the directory is busy*"])
