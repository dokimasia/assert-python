"""The spec of conformance/subject.py tests the behaviours of the corpus cases."""

from __future__ import annotations

import asyncio
import pathlib
from collections.abc import Callable
from typing import Any

import pytest

from dokimi_assert import check
from dokimi_assert._files.literal import CONTENT_LIMIT
from dokimi_assert.conformance.subject import SUBJECTS, Subject, SubjectError
from dokimi_assert.seat import Collector, Recorder
from helpers import UNENFORCED


def build(kind: str) -> Subject:
    """Return a new subject of kind."""
    return SUBJECTS[kind]()


def shape(subject: Subject, name: str) -> Callable[..., Any]:
    """Return the shape name of subject. The behaviour must have the shape."""
    found: Callable[..., Any] | None = getattr(subject, name)
    assert found is not None, f"the subject does not have the shape {name}"
    return found


def failed_attempts(subject: Subject, runs: int) -> int:
    """Return the number of failed attempts in runs attempts of the seated shape."""
    failed = 0
    for _ in range(runs):
        trial = Recorder()
        shape(subject, "seated")(trial)
        failed += trial.failed
    return failed


def failed_readings(subject: Subject, runs: int) -> int:
    """Return the number of raising readings in runs readings of the read shape."""
    failed = 0
    for _ in range(runs):
        try:
            shape(subject, "read")()
        except SubjectError:
            failed += 1
    return failed


def count_after(subject: Subject) -> int:
    """Return the count that a counter reads after one call and one advance."""
    shape(subject, "call")(subject.input)
    shape(subject, "advance")()
    count: int = shape(subject, "observe")()
    return count


class TestSubjects:
    """SUBJECTS has the builder of each behaviour."""

    def test_builds_a_returns_ok_subject_whose_coroutine_does_the_work(
        self, seat: Collector
    ) -> None:
        """The coroutine returns at once."""
        done = asyncio.run(shape(build("returns-ok"), "handled")())
        check.equal(seat, done, "did the work", "the subject does its work")

    def test_builds_a_returns_ok_subject_whose_shapes_return(
        self, seat: Collector
    ) -> None:
        """The shapes succeed, and compute returns its input."""
        subject = build("returns-ok")
        check.equal(
            seat,
            [
                shape(subject, "bare")(),
                shape(subject, "call")(1),
                shape(subject, "compute")(subject.input),
                subject.domain,
            ],
            [None, None, 1, (1, 2, 3)],
            "the subject succeeds and returns its input",
        )

    def test_builds_a_reads_handle_subject_that_awaits(self, seat: Collector) -> None:
        """A cancellation stops the coroutine at its await."""

        async def cancelled() -> bool:
            task = asyncio.ensure_future(shape(build("reads-handle"), "handled")())
            await asyncio.sleep(0)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                return True
            return False

        check.is_true(
            seat, asyncio.run(cancelled()), "the cancellation stops the coroutine"
        )

    def test_builds_a_reads_handle_subject_that_does_the_work_unless_cancelled(
        self, seat: Collector
    ) -> None:
        """Without a cancellation the coroutine returns after its await."""
        done = asyncio.run(shape(build("reads-handle"), "handled")())
        check.equal(
            seat,
            done,
            "did the work",
            "the coroutine returns without a cancellation",
        )

    def test_builds_an_ignores_handle_subject_that_never_awaits(
        self, seat: Collector
    ) -> None:
        """The coroutine returns at its first run."""

        async def returned() -> bool:
            task = asyncio.ensure_future(shape(build("ignores-handle"), "handled")())
            await asyncio.sleep(0)
            return bool(task.done() and task.result() == "did the work")

        check.is_true(seat, asyncio.run(returned()), "the subject returned at once")

    def test_builds_a_raises_subject_whose_bare_shape_raises(
        self, seat: Collector
    ) -> None:
        """The bare shape raises a SubjectError."""
        error = check.raises(seat, shape(build("raises"), "bare"), "the subject raises")
        check.is_true(
            seat, isinstance(error, SubjectError), "the error is a SubjectError"
        )

    def test_builds_a_fails_otherwise_subject_whose_coroutine_raises(
        self, seat: Collector
    ) -> None:
        """The coroutine raises a SubjectError."""
        handled = shape(build("fails-otherwise"), "handled")
        error = check.raises(seat, lambda: asyncio.run(handled()), "the subject fails")
        check.is_true(
            seat, isinstance(error, SubjectError), "the error is a SubjectError"
        )

    def test_builds_a_fails_otherwise_subject_whose_call_raises_for_its_domain(
        self, seat: Collector
    ) -> None:
        """The call raises a SubjectError for each input."""
        subject = build("fails-otherwise")
        error = check.raises(seat, lambda: shape(subject, "call")(1), "the call fails")
        check.is_true(
            seat, isinstance(error, SubjectError), "the error is a SubjectError"
        )
        check.equal(seat, subject.domain, (1, 2, 3), "the domain is 1, 2 and 3")

    def test_builds_a_dereferences_handle_subject_that_reads_none(
        self, seat: Collector
    ) -> None:
        """The subject reads an attribute of None."""
        handled = shape(build("dereferences-handle"), "handled")
        error = check.raises(
            seat, lambda: handled(None), "the subject reads an attribute of None"
        )
        check.is_true(
            seat, isinstance(error, AttributeError), "the error is an AttributeError"
        )

    def test_builds_a_never_settles_subject_whose_every_attempt_fails(
        self, seat: Collector
    ) -> None:
        """Every attempt records a failure."""
        check.equal(
            seat,
            failed_attempts(build("never-settles"), 4),
            4,
            "all four attempts fail",
        )

    def test_builds_a_never_settles_subject_whose_every_reading_raises(
        self, seat: Collector
    ) -> None:
        """Every reading after induce raises."""
        subject = build("never-settles")
        shape(subject, "induce")()
        check.equal(seat, failed_readings(subject, 4), 4, "all four readings raise")

    def test_builds_a_settles_after_subject_whose_first_two_attempts_fail(
        self, seat: Collector
    ) -> None:
        """The third attempt passes."""
        check.equal(
            seat,
            failed_attempts(build("settles-after"), 4),
            2,
            "the first two attempts fail",
        )

    def test_builds_a_settles_after_subject_whose_first_two_readings_raise(
        self, seat: Collector
    ) -> None:
        """The third reading returns."""
        subject = build("settles-after")
        shape(subject, "induce")()
        check.equal(
            seat, failed_readings(subject, 4), 2, "the first two readings raise"
        )

    def test_builds_an_accumulates_subject_whose_calls_raise_the_count(
        self, seat: Collector
    ) -> None:
        """Each call and each advance adds one."""
        subject = build("accumulates")
        check.equal(
            seat,
            [count_after(subject), subject.steps],
            [2, 5],
            "the count is 2 after a call and an advance",
        )

    def test_builds_a_leaves_state_alone_subject_whose_count_is_0(
        self, seat: Collector
    ) -> None:
        """The calls do not change the count."""
        check.equal(seat, count_after(build("leaves-state-alone")), 0, "the count is 0")

    def test_builds_a_sets_value_subject_whose_call_sets_the_cell(
        self, seat: Collector
    ) -> None:
        """The cell is the input after a call."""
        subject = build("sets-value")
        shape(subject, "call")(subject.input)
        check.equal(seat, shape(subject, "observe")(), 7, "the cell is the input")

    def test_builds_a_counts_calls_subject_whose_computation_counts(
        self, seat: Collector
    ) -> None:
        """The computation returns the number of its calls."""
        compute = shape(build("counts-calls"), "compute")
        check.equal(seat, [compute(1), compute(1)], [1, 2], "the calls count from 1")

    def test_builds_an_adds_subject_that_adds_its_operands(
        self, seat: Collector
    ) -> None:
        """The combination is the sum."""
        subject = build("adds")
        combined = shape(subject, "combine")(2, 3)
        check.equal(
            seat,
            [combined, subject.operands],
            [5, (2, 3, 5)],
            "the combination is the sum",
        )

    def test_builds_a_subtracts_subject_that_subtracts(self, seat: Collector) -> None:
        """The combination is the difference."""
        check.equal(
            seat,
            shape(build("subtracts"), "combine")(2, 3),
            -1,
            "the combination is the difference",
        )

    def test_builds_a_renders_decimal_subject_that_renders_its_input(
        self, seat: Collector
    ) -> None:
        """The text keeps the sign."""
        subject = build("renders-decimal")
        check.equal(
            seat,
            shape(subject, "render")(subject.input),
            "-42",
            "the text keeps the sign",
        )

    def test_builds_a_drops_the_sign_subject_that_renders_the_absolute_value(
        self, seat: Collector
    ) -> None:
        """The text does not have a sign."""
        subject = build("drops-the-sign")
        check.equal(
            seat,
            shape(subject, "render")(subject.input),
            "42",
            "the text drops the sign",
        )

    def test_builds_a_rotates_subject_that_rotates_on_each_iteration(
        self, seat: Collector
    ) -> None:
        """The second iteration starts one place later."""
        iterate = shape(build("rotates"), "iterate")
        check.equal(
            seat,
            [iterate(), iterate()],
            [[1, 2, 3, 4, 5], [2, 3, 4, 5, 1]],
            "the iterations rotate",
        )

    def test_builds_a_repeats_an_element_subject_that_yields_2_twice(
        self, seat: Collector
    ) -> None:
        """The iteration has a duplicate."""
        check.equal(
            seat,
            shape(build("repeats-an-element"), "iterate")(),
            [1, 2, 2, 3],
            "the iteration yields 2 twice",
        )

    def test_builds_a_yields_in_order_subject_that_yields_one_order(
        self, seat: Collector
    ) -> None:
        """Every iteration is the same."""
        iterate = shape(build("yields-in-order"), "iterate")
        check.equal(seat, iterate(), iterate(), "the iterations are equal")

    def test_builds_a_wraps_around_subject_whose_count_returns_to_0(
        self, seat: Collector
    ) -> None:
        """The count wraps after 3."""
        subject = build("wraps-around")
        for _ in range(4):
            shape(subject, "advance")()
        check.equal(
            seat,
            [shape(subject, "observe")(), subject.steps],
            [0, 5],
            "the count is 0 after four advances",
        )

    def test_builds_a_refuses_after_close_subject_that_raises_its_sentinel(
        self, seat: Collector
    ) -> None:
        """The closed subject raises the sentinel."""
        subject = build("refuses-after-close")
        use = shape(subject, "use")
        check.does_not_raise(seat, use, "the open subject serves")
        shape(subject, "close")()
        error = check.raises(seat, use, "the closed subject refuses")
        check.is_true(seat, error is subject.sentinel, "the refusal is the sentinel")

    def test_builds_a_serves_after_close_subject_that_serves_when_closed(
        self, seat: Collector
    ) -> None:
        """The closed subject still succeeds."""
        subject = build("serves-after-close")
        shape(subject, "close")()
        check.does_not_raise(seat, shape(subject, "use"), "the closed subject serves")

    def test_builds_a_yields_one_object_twice_subject(self, seat: Collector) -> None:
        """The two elements are one object."""
        first, second = shape(build("yields-one-object-twice"), "iterate")()
        check.is_true(seat, first is second, "the elements are one object")

    def test_builds_a_yields_two_equal_objects_subject(self, seat: Collector) -> None:
        """The two elements are two objects of one value."""
        first, second = shape(build("yields-two-equal-objects"), "iterate")()
        check.is_true(seat, first is not second, "the elements are two objects")
        check.equal(seat, first, second, "the objects are equal")

    @pytest.mark.skipif(UNENFORCED, reason="every permission is granted here")
    def test_builds_a_leaves_files_alone_subject_that_reads_every_file(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """An unreadable file stops the subject."""
        (tmp_path / "docs").mkdir()
        unreadable = tmp_path / "docs" / "a.md"
        unreadable.write_text("a")
        unreadable.chmod(0o000)
        files = shape(build("leaves-files-alone"), "files")
        error = check.raises(
            seat, lambda: files(str(tmp_path)), "the subject reads the file"
        )
        check.is_true(
            seat, isinstance(error, PermissionError), "the error is a PermissionError"
        )

    def test_builds_a_leaves_files_alone_subject_that_does_not_write(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The files keep their bytes and their times, and a link is skipped."""
        target = tmp_path / "a.txt"
        target.write_text("a")
        (tmp_path / "b").symlink_to("a.txt")
        before = target.stat().st_mtime_ns
        shape(build("leaves-files-alone"), "files")(str(tmp_path))
        check.equal(
            seat,
            [target.read_text(), target.stat().st_mtime_ns],
            ["a", before],
            "the file keeps its bytes and its time",
        )

    @pytest.mark.skipif(UNENFORCED, reason="every permission is granted here")
    def test_builds_a_rewrites_files_subject_that_writes_every_file(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A read-only file stops the subject."""
        (tmp_path / "docs").mkdir()
        read_only = tmp_path / "docs" / "a.md"
        read_only.write_text("a")
        read_only.chmod(0o400)
        files = shape(build("rewrites-files"), "files")
        error = check.raises(
            seat, lambda: files(str(tmp_path)), "the subject writes the file"
        )
        check.is_true(
            seat, isinstance(error, PermissionError), "the error is a PermissionError"
        )

    @pytest.mark.skipif(UNENFORCED, reason="every permission is granted here")
    def test_builds_a_rewrites_files_subject_that_does_not_follow_a_link(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A link to a read-only file outside the tree is not written."""
        outside = tmp_path / "outside.txt"
        outside.write_text("a")
        outside.chmod(0o400)
        tree = tmp_path / "tree"
        tree.mkdir()
        (tree / "b").symlink_to(outside)
        files = shape(build("rewrites-files"), "files")
        check.does_not_raise(seat, lambda: files(str(tree)), "the link is not followed")

    def test_builds_a_rewrites_files_subject_that_writes_the_bytes_of_each_file(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """Each file keeps its bytes and its mode."""
        (tmp_path / "keys").mkdir()
        secret = tmp_path / "keys" / "id"
        secret.write_bytes(b"s\x00")
        secret.chmod(0o600)
        mode = secret.stat().st_mode
        shape(build("rewrites-files"), "files")(str(tmp_path))
        check.equal(
            seat,
            [secret.read_bytes(), secret.stat().st_mode],
            [b"s\x00", mode],
            "the file keeps its bytes and its mode",
        )

    def test_builds_a_writes_a_file_subject_that_writes_new_txt(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The subject writes new.txt at the root of the tree."""
        shape(build("writes-a-file"), "files")(str(tmp_path))
        check.equal(
            seat,
            (tmp_path / "new.txt").read_bytes(),
            b"new",
            "new.txt has the bytes new",
        )

    def test_builds_a_writes_a_large_file_subject_one_byte_past_the_limit(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The file is one byte longer than a record contains in full."""
        shape(build("writes-a-large-file"), "files")(str(tmp_path))
        check.equal(
            seat,
            (tmp_path / "large.bin").read_bytes(),
            b"a" * (CONTENT_LIMIT + 1),
            "large.bin is one byte past the limit",
        )
