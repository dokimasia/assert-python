"""The spec of files.py tests the trees of a test and the assertions about files."""

from __future__ import annotations

import asyncio
import errno
import json
import os
import pathlib
import shutil
import tempfile
from collections.abc import Callable
from typing import Any, ClassVar

import pytest

from dokimi_assert import check, files
from dokimi_assert._files.entry import Entry
from dokimi_assert.seat import Collector, Recorder
from helpers import LONG_NAMES_ABSENT, WINDOWS, records

#: The signature of a PNG file. Its bytes are not UTF-8 text.
PNG = b"\x89PNG"

#: A name that is longer than a file system allows. A read refuses it.
TOO_LONG = "n" * 300


class Cleaning(Recorder):
    """A recorder that keeps the cleanups that it receives. A test runs them."""

    def __init__(self) -> None:
        """Return a recorder without cleanups."""
        super().__init__()
        self.cleanups: list[Callable[[], object]] = []

    def cleanup(self, fn: Callable[[], object]) -> None:
        """Keep fn."""
        self.cleanups.append(fn)

    def end(self) -> None:
        """Run the cleanups in reverse order of registration."""
        for fn in reversed(self.cleanups):
            fn()


def verdicts(recorder: Recorder) -> list[Any]:
    """Return the verdict of each call record of recorder."""
    return [r["verdict"] for r in records(recorder)]


def as_written(e: Entry) -> Entry:
    """Return e with the mode 0o644 of a written file where modes are recorded."""
    return e if WINDOWS else e.with_mode(0o644)


def outcome(call: Callable[[Recorder], None]) -> list[Any]:
    """Return the verdict of call on a new recorder.

    The detail of a failure or the text of a fault follows the verdict.
    """
    recorder = Recorder()
    call(recorder)
    verdict = records(recorder)[0]["verdict"]
    if verdict == "fail":
        return [verdict, dict(recorder.failures[0].detail)]
    if verdict == "error":
        return [verdict, recorder.message]
    return [verdict]


@pytest.fixture
def fixture(seat: Collector) -> str:
    """Return a workspace of two files, a directory with a mode and two links."""
    return files.workspace(
        seat,
        {
            "a.txt": files.text("a\n"),
            "logo.png": files.bytes(PNG),
            "keys": files.directory().with_mode(0o700),
            "keys/id": files.text("secret\n").with_mode(0o600),
            "current": files.link("a.txt"),
            "dangling": files.link("missing.txt"),
        },
    )


def test_exports_the_names_of_the_module(seat: Collector) -> None:
    """The module declares the names of the naming table."""
    check.equal(
        seat,
        sorted(files.__all__),
        [
            "Entry",
            "Tree",
            "absent",
            "bytes",
            "contains",
            "directory",
            "equal",
            "executable",
            "has_content",
            "has_mode",
            "is_dir",
            "is_file",
            "link",
            "links_to",
            "read",
            "text",
            "unchanged",
            "workspace",
            "write",
        ],
        "files exports the names of the naming table",
    )


class TestWorkspace:
    """workspace writes a tree into a new directory of the test."""

    def test_returns_a_directory_that_contains_the_tree(self, seat: Collector) -> None:
        """The directory is a temporary directory of the test."""
        dir = files.workspace(seat, {"docs/a.md": files.text("# a\n")})
        prefix = os.path.join(tempfile.gettempdir(), "dokimi-files-")
        check.has_prefix(
            seat, dir, prefix, "the directory is in the temporary directory"
        )
        check.equal(
            seat,
            files.read(seat, os.path.join(dir, "docs", "a.md")),
            "# a\n",
            "the directory contains the file",
        )

    def test_registers_the_removal_of_its_directory_with_the_seat(
        self, seat: Collector
    ) -> None:
        """The cleanup removes the directory."""
        cleaning = Cleaning()
        dir = files.workspace(cleaning, {"a.txt": files.text("a")})
        cleaning.end()
        check.is_false(seat, os.path.exists(dir), "the directory is removed")

    def test_removes_a_directory_whose_mode_forbids_the_owner_to_write_it(
        self, seat: Collector
    ) -> None:
        """The cleanup gives the owner the permission first."""
        cleaning = Cleaning()
        dir = files.workspace(
            cleaning,
            {
                "sealed": files.directory().with_mode(0o500),
                "sealed/a.txt": files.text("a").with_mode(0o400),
            },
        )
        cleaning.end()
        check.is_false(seat, os.path.exists(dir), "the directory is removed")

    def test_does_not_fail_for_a_directory_that_is_gone(self, seat: Collector) -> None:
        """A test can remove the workspace itself."""
        cleaning = Cleaning()
        dir = files.workspace(cleaning, {})
        shutil.rmtree(dir)
        check.does_not_raise(seat, cleaning.end, "the cleanup does not raise")

    def test_ends_the_call_with_a_fault_for_a_tree_that_breaks_a_rule(
        self, seat: Collector
    ) -> None:
        """The call does not write anything."""
        cleaning = Cleaning()
        dir = files.workspace(cleaning, {"a.txt": files.text("a"), "b": Entry()})
        try:
            check.equal(
                seat,
                [cleaning.message, os.listdir(dir)],
                [
                    "files.workspace: b: the entry is not a file, a directory or a "
                    "link",
                    [],
                ],
                "the call ends with a fault and does not write anything",
            )
        finally:
            cleaning.end()

    def test_ends_the_call_with_a_fault_for_a_seat_without_cleanup(
        self, seat: Collector
    ) -> None:
        """A seat that cannot remove the directory does not get one."""
        recorder = Recorder()
        dir = files.workspace(recorder, {})
        check.equal(
            seat,
            [dir, recorder.message],
            [
                "",
                "files.workspace: the seat does not have a cleanup method to remove "
                "the workspace",
            ],
            "the call returns an empty path and ends with a fault",
        )

    def test_ends_the_call_with_a_fault_when_the_directory_cannot_be_created(
        self, seat: Collector, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The workspace cannot be created in a missing temporary directory."""
        monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "missing"))
        cleaning = Cleaning()
        dir = files.workspace(cleaning, {})
        check.equal(seat, dir, "", "the call returns an empty path")
        want = f"files.workspace: [Errno {errno.ENOENT}]"
        check.has_prefix(
            seat, cleaning.message, want, "the fault has the error of the file system"
        )


class TestWrite:
    """write writes a tree over the entries of a directory."""

    def test_writes_the_tree_over_the_entries_of_the_directory(
        self, seat: Collector
    ) -> None:
        """The other files keep their content."""
        dir = files.workspace(
            seat,
            {"api/store.gen.go": files.text("generated"), "kept.txt": files.text("k")},
        )
        files.write(seat, pathlib.Path(dir), {"api/store.gen.go": files.text("edited")})
        files.contains(
            seat,
            dir,
            {"api/store.gen.go": files.text("edited"), "kept.txt": files.text("k")},
            "write edits one file and keeps the other",
        )

    def test_ends_the_call_with_a_fault_for_an_entry_of_a_different_kind(
        self, seat: Collector
    ) -> None:
        """A file is not a directory."""
        dir = files.workspace(seat, {"docs": files.text("a file")})
        recorder = Recorder()
        files.write(recorder, dir, {"docs/a.md": files.text("a")})
        check.equal(
            seat,
            recorder.message,
            "files.write: docs: the entry is a file, and the tree has a directory",
            "the fault has the path and the reason",
        )


class TestRead:
    """read returns the content of one file."""

    def test_returns_the_content_of_the_file_at_the_path(self, seat: Collector) -> None:
        """A path can be a pathlib.Path."""
        dir = files.workspace(seat, {"go.mod": files.text("module example.com/a\n")})
        path = pathlib.Path(dir) / "go.mod"
        check.equal(
            seat,
            files.read(seat, path),
            "module example.com/a\n",
            "read returns the content",
        )

    def test_decodes_bytes_that_are_not_utf8_as_replacement_characters(
        self, seat: Collector
    ) -> None:
        """The read loses content that is not text."""
        dir = files.workspace(seat, {"logo.png": files.bytes(PNG)})
        content = files.read(seat, os.path.join(dir, "logo.png"))
        check.equal(
            seat,
            content,
            "\N{REPLACEMENT CHARACTER}PNG",
            "read replaces the invalid byte",
        )

    @pytest.mark.parametrize("give", ["missing.txt", "docs", "current"])
    def test_ends_the_call_with_a_fault_for_a_path_without_a_file(
        self, seat: Collector, give: str
    ) -> None:
        """A missing entry, a directory and a link to a file are not files."""
        dir = files.workspace(
            seat,
            {
                "a.txt": files.text("a"),
                "docs": files.directory(),
                "current": files.link("a.txt"),
            },
        )
        path = os.path.join(dir, give)
        recorder = Recorder()
        content = files.read(recorder, path)
        check.equal(
            seat,
            [content, recorder.message],
            ["", f"files.read: the path {json.dumps(path)} does not have a file"],
            "read returns an empty str and ends with a fault",
        )

    @pytest.mark.skipif(
        LONG_NAMES_ABSENT, reason="Windows reports such a name as absent"
    )
    def test_ends_the_call_with_a_fault_for_a_path_that_the_file_system_refuses(
        self, seat: Collector
    ) -> None:
        """A name past the limit of its length cannot be read."""
        dir = files.workspace(seat, {})
        recorder = Recorder()
        files.read(recorder, os.path.join(dir, TOO_LONG))
        want = f"files.read: the entry cannot be read: [Errno {errno.ENAMETOOLONG}]"
        check.has_prefix(
            seat, recorder.message, want, "the fault has the error of the file system"
        )


class TestEqual:
    """equal compares the tree in a directory with a wanted tree."""

    def test_passes_the_tree_of_the_directory(self, seat: Collector) -> None:
        """The order of the wanted paths does not matter."""
        dir = files.workspace(
            seat, {"a.txt": files.text("a"), "docs/b.md": files.text("b")}
        )
        recorder = Recorder()
        want = {"docs/b.md": files.text("b"), "a.txt": files.text("a")}
        files.equal(recorder, dir, want, "the trees are equal")
        check.equal(seat, verdicts(recorder), ["pass"], "the call passes")

    def test_reports_the_record_of_tree_equal_for_a_tree_that_differs(
        self, seat: Collector
    ) -> None:
        """The record has both sides of each path that differs."""
        dir = files.workspace(
            seat, {"a.txt": files.text("a"), "c.txt": files.text("c")}
        )
        recorder = Recorder()
        want = {"a.txt": files.text("x"), "b.txt": files.text("b")}
        files.equal(recorder, dir, want, "the trees are equal")
        [failure] = recorder.failures
        check.equal(
            seat,
            [failure.assertion, failure.contract, dict(failure.detail)],
            [
                "tree-equal",
                "the trees are equal",
                {
                    "want": {"a.txt": files.text("x"), "b.txt": files.text("b")},
                    "got": {"a.txt": files.text("a"), "c.txt": files.text("c")},
                    "differences": 3,
                },
            ],
            "the failure has the record of tree-equal",
        )

    def test_reports_the_call_site_of_the_test(self, seat: Collector) -> None:
        """The failure has the call site in this spec."""
        dir = files.workspace(seat, {})
        recorder = Recorder()
        files.equal(recorder, dir, {"a.txt": files.text("a")}, "the trees are equal")
        where = recorder.failures[0].where
        check.equal(
            seat,
            None if where is None else where.file,
            __file__,
            "the call site is in this spec",
        )

    def test_ends_the_call_with_a_fault_for_a_wanted_tree_that_breaks_a_rule(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The wanted tree is checked first."""
        recorder = Recorder()
        files.equal(recorder, tmp_path, {"a": Entry()}, "the trees are equal")
        check.equal(
            seat,
            [recorder.message, verdicts(recorder)],
            [
                "files.equal: a: the entry is not a file, a directory or a link",
                ["error"],
            ],
            "the call ends with a fault",
        )

    def test_ends_the_call_with_a_fault_for_a_tree_that_cannot_be_read(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A missing directory does not have a tree."""
        recorder = Recorder()
        files.equal(recorder, tmp_path / "missing", {}, "the trees are equal")
        want = f"files.equal: the tree cannot be read: [Errno {errno.ENOENT}]"
        check.has_prefix(
            seat, recorder.message, want, "the fault has the error of the file system"
        )


class TestContains:
    """contains checks that the tree in a directory has the wanted entries."""

    def test_passes_a_tree_that_has_more_entries_than_the_wanted_one(
        self, seat: Collector
    ) -> None:
        """An extra entry is not a difference."""
        dir = files.workspace(
            seat, {"a.txt": files.text("a"), "b.txt": files.text("b")}
        )
        recorder = Recorder()
        files.contains(recorder, dir, {"b.txt": files.text("b")}, "the tree has b.txt")
        check.equal(seat, verdicts(recorder), ["pass"], "the call passes")

    def test_reports_the_record_of_tree_contains_for_a_missing_entry(
        self, seat: Collector
    ) -> None:
        """A missing entry is only in want."""
        dir = files.workspace(seat, {"a.txt": files.text("a")})
        recorder = Recorder()
        files.contains(recorder, dir, {"b.txt": files.text("b")}, "the tree has b.txt")
        check.equal(
            seat,
            [recorder.failures[0].assertion, dict(recorder.failures[0].detail)],
            [
                "tree-contains",
                {"want": {"b.txt": files.text("b")}, "got": {}, "differences": 1},
            ],
            "the failure has the record of tree-contains",
        )

    def test_ends_the_call_with_a_fault_of_contains(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The fault starts with the operation."""
        recorder = Recorder()
        files.contains(recorder, str(tmp_path / "missing"), {}, "the tree has b.txt")
        check.has_prefix(
            seat,
            recorder.message,
            "files.contains: ",
            "the fault starts with files.contains",
        )


class TestUnchanged:
    """unchanged compares the tree in a directory before and after a call."""

    def test_passes_a_callable_that_does_not_write(self, seat: Collector) -> None:
        """The two trees are equal."""
        dir = files.workspace(seat, {"a.txt": files.text("a")})
        recorder = Recorder()
        files.unchanged(recorder, dir, lambda: None, "the callable does not write")
        check.equal(seat, verdicts(recorder), ["pass"], "the call passes")

    def test_reports_the_record_of_tree_unchanged_for_a_callable_that_writes(
        self, seat: Collector
    ) -> None:
        """The tree before the call is the wanted tree."""
        dir = files.workspace(seat, {"a.txt": files.text("a")})
        recorder = Recorder()
        path = pathlib.Path(dir) / "a.txt"
        files.unchanged(
            recorder, dir, lambda: path.write_text("b"), "the callable does not write"
        )
        check.equal(
            seat,
            [recorder.failures[0].assertion, dict(recorder.failures[0].detail)],
            [
                "tree-unchanged",
                {
                    "want": {"a.txt": as_written(files.text("a"))},
                    "got": {"a.txt": as_written(files.text("b"))},
                    "differences": 1,
                },
            ],
            "the failure has the record of tree-unchanged",
        )

    def test_runs_a_coroutine_function(self, seat: Collector) -> None:
        """The call runs the coroutine to its end."""
        dir = files.workspace(seat, {})
        recorder = Recorder()

        async def late() -> None:
            (pathlib.Path(dir) / "late.txt").write_text("late")

        files.unchanged(recorder, dir, late, "the callable does not write")
        check.equal(
            seat, verdicts(recorder), ["fail"], "the call fails on the late write"
        )

    def test_raises_the_exception_of_the_callable(self, seat: Collector) -> None:
        """The call does not have a verdict."""
        dir = files.workspace(seat, {})
        recorder = Recorder()

        def broken() -> None:
            raise RuntimeError("the subject broke")

        raised = check.raises(
            seat,
            lambda: files.unchanged(
                recorder, dir, broken, "the callable does not write"
            ),
            "unchanged raises the error of the callable",
        )
        check.error_as(seat, raised, RuntimeError, "the error is a RuntimeError")
        check.is_empty(seat, records(recorder), "the call does not have a verdict")

    def test_ends_the_call_with_a_fault_inside_a_running_event_loop(
        self, seat: Collector
    ) -> None:
        """The call ends with a fault when it cannot run a coroutine."""
        dir = files.workspace(seat, {})
        recorder = Recorder()

        async def subject() -> None:
            return None

        async def test() -> None:
            files.unchanged(recorder, dir, subject, "the callable does not write")

        asyncio.run(test())
        check.has_prefix(
            seat,
            recorder.message,
            "tree-unchanged runs a coroutine",
            "the fault has the reason",
        )

    def test_ends_the_call_with_a_fault_for_a_tree_that_cannot_be_read_before(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The callable is not called."""
        recorder = Recorder()
        called: list[bool] = []
        files.unchanged(
            recorder,
            tmp_path / "missing",
            lambda: called.append(True),
            "the callable does not write",
        )
        want = "files.unchanged: the tree cannot be read"
        check.has_prefix(seat, recorder.message, want, "the fault has the reason")
        check.is_empty(seat, called, "the callable is not called")

    def test_ends_the_call_with_a_fault_for_a_tree_that_cannot_be_read_after(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The callable removed the tree."""
        dir = tmp_path / "tree"
        dir.mkdir()
        recorder = Recorder()
        files.unchanged(
            recorder, dir, lambda: shutil.rmtree(dir), "the callable does not write"
        )
        want = "files.unchanged: the tree cannot be read"
        check.has_prefix(seat, recorder.message, want, "the fault has the reason")


class TestAbsent:
    """absent checks that a path does not have an entry."""

    def test_passes_a_missing_path(self, seat: Collector, fixture: str) -> None:
        """The path does not have an entry."""
        got = outcome(lambda r: files.absent(r, os.path.join(fixture, "b.txt"), "m"))
        check.equal(seat, got, ["pass"], "the call passes")

    def test_passes_a_path_below_a_file(self, seat: Collector, fixture: str) -> None:
        """A file does not have entries below it."""
        path = os.path.join(fixture, "a.txt", "b")
        check.equal(
            seat,
            outcome(lambda r: files.absent(r, path, "m")),
            ["pass"],
            "the call passes",
        )

    def test_reports_the_kind_of_the_entry_at_the_path(
        self, seat: Collector, fixture: str
    ) -> None:
        """The path has a file."""
        path = os.path.join(fixture, "a.txt")
        got = outcome(lambda r: files.absent(r, path, "m"))
        check.equal(
            seat, got, ["fail", {"got": "file"}], "the failure has the kind file"
        )

    def test_reports_a_link_whose_target_is_missing(
        self, seat: Collector, fixture: str
    ) -> None:
        """The path has the link."""
        path = os.path.join(fixture, "dangling")
        got = outcome(lambda r: files.absent(r, path, "m"))
        check.equal(
            seat, got, ["fail", {"got": "link"}], "the failure has the kind link"
        )

    @pytest.mark.skipif(
        LONG_NAMES_ABSENT, reason="Windows reports such a name as absent"
    )
    def test_ends_the_call_with_a_fault_for_a_path_that_the_file_system_refuses(
        self, seat: Collector, fixture: str
    ) -> None:
        """A name past the limit of its length cannot be read."""
        path = os.path.join(fixture, TOO_LONG)
        verdict, fault = outcome(lambda r: files.absent(r, path, "m"))
        want = f"files.absent: the entry cannot be read: [Errno {errno.ENAMETOOLONG}]"
        check.equal(seat, verdict, "error", "the call ends with a fault")
        check.has_prefix(
            seat, fault, want, "the fault has the error of the file system"
        )


class TestIsFile:
    """is_file checks that a path has a file."""

    tests: ClassVar[list[tuple[str, str, list[Any]]]] = [
        ("passes a file", "a.txt", ["pass"]),
        ("reports a directory", "keys", ["fail", {"got": "directory"}]),
        ("reports a link to a file", "current", ["fail", {"got": "link"}]),
        ("reports none for a missing path", "b.txt", ["fail", {"got": None}]),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_outcome(
        self, seat: Collector, fixture: str, give: str, want: list[Any]
    ) -> None:
        """The verdict depends on the kind of the entry."""
        path = os.path.join(fixture, give)
        check.equal(
            seat,
            outcome(lambda r: files.is_file(r, path, "m")),
            want,
            "is_file returns the outcome",
        )

    @pytest.mark.skipif(WINDOWS, reason="Windows does not have /dev/null")
    def test_ends_the_call_with_a_fault_for_a_device(self, seat: Collector) -> None:
        """A device is not an entry of a tree."""
        check.equal(
            seat,
            outcome(lambda r: files.is_file(r, "/dev/null", "m")),
            ["error", "files.is_file: the entry is not a file, a directory or a link"],
            "the call ends with a fault",
        )


class TestIsDir:
    """is_dir checks that a path has a directory."""

    tests: ClassVar[list[tuple[str, str, list[Any]]]] = [
        ("passes a directory", "keys", ["pass"]),
        ("reports a file", "a.txt", ["fail", {"got": "file"}]),
        ("reports none for a missing path", "build", ["fail", {"got": None}]),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_outcome(
        self, seat: Collector, fixture: str, give: str, want: list[Any]
    ) -> None:
        """The verdict depends on the kind of the entry."""
        path = os.path.join(fixture, give)
        check.equal(
            seat,
            outcome(lambda r: files.is_dir(r, path, "m")),
            want,
            "is_dir returns the outcome",
        )

    @pytest.mark.skipif(
        LONG_NAMES_ABSENT, reason="Windows reports such a name as absent"
    )
    def test_ends_the_call_with_a_fault_of_is_dir(
        self, seat: Collector, fixture: str
    ) -> None:
        """The fault starts with the operation."""
        path = os.path.join(fixture, TOO_LONG)
        _, fault = outcome(lambda r: files.is_dir(r, path, "m"))
        check.has_prefix(
            seat, fault, "files.is_dir: ", "the fault starts with files.is_dir"
        )


class TestLinksTo:
    """links_to checks that a path has a link to a target."""

    tests: ClassVar[list[tuple[str, str, str, list[Any]]]] = [
        ("passes a link to the target", "current", "a.txt", ["pass"]),
        (
            "reports a different target",
            "current",
            "b.txt",
            ["fail", {"want": "b.txt", "got": "a.txt", "kind": "link"}],
        ),
        (
            "reports a file",
            "a.txt",
            "b.txt",
            ["fail", {"want": "b.txt", "got": None, "kind": "file"}],
        ),
        (
            "reports none for a missing path",
            "missing",
            "b.txt",
            ["fail", {"want": "b.txt", "got": None, "kind": None}],
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "give_target", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_returns_the_outcome(
        self,
        seat: Collector,
        fixture: str,
        give: str,
        give_target: str,
        want: list[Any],
    ) -> None:
        """The target is compared as text."""
        path = os.path.join(fixture, give)
        got = outcome(lambda r: files.links_to(r, path, give_target, "m"))
        check.equal(seat, got, want, "links_to returns the outcome")

    @pytest.mark.skipif(
        LONG_NAMES_ABSENT, reason="Windows reports such a name as absent"
    )
    def test_ends_the_call_with_a_fault_of_links_to(
        self, seat: Collector, fixture: str
    ) -> None:
        """The fault starts with the operation."""
        path = os.path.join(fixture, TOO_LONG)
        _, fault = outcome(lambda r: files.links_to(r, path, "a", "m"))
        check.has_prefix(
            seat, fault, "files.links_to: ", "the fault starts with files.links_to"
        )


class TestHasContent:
    """has_content checks that a path has a file with the wanted content."""

    tests: ClassVar[list[tuple[str, str, str | bytes, list[Any]]]] = [
        ("passes a file of the text", "a.txt", "a\n", ["pass"]),
        ("passes a file of the bytes", "logo.png", PNG, ["pass"]),
        ("compares bytes with a file of text", "a.txt", b"a\n", ["pass"]),
        (
            "reports a different text",
            "a.txt",
            "a\r\n",
            ["fail", {"want": "a\r\n", "got": "a\n", "kind": "file"}],
        ),
        (
            "reports different bytes as bytes",
            "logo.png",
            b"\x89",
            ["fail", {"want": b"\x89", "got": PNG, "kind": "file"}],
        ),
        (
            "reports a directory",
            "keys",
            "",
            ["fail", {"want": "", "got": None, "kind": "directory"}],
        ),
        (
            "reports none for a missing path",
            "b.txt",
            "b",
            ["fail", {"want": "b", "got": None, "kind": None}],
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "give_content", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_returns_the_outcome(
        self,
        seat: Collector,
        fixture: str,
        give: str,
        give_content: str | bytes,
        want: list[Any],
    ) -> None:
        """Content is compared as bytes."""
        path = os.path.join(fixture, give)
        got = outcome(lambda r: files.has_content(r, path, give_content, "m"))
        check.equal(seat, got, want, "has_content returns the outcome")

    def test_ends_the_call_with_a_fault_for_text_with_a_lone_surrogate(
        self, seat: Collector, fixture: str
    ) -> None:
        """UTF-8 cannot encode the wanted text."""
        path = os.path.join(fixture, "a.txt")
        check.equal(
            seat,
            outcome(lambda r: files.has_content(r, path, "\ud800", "m")),
            [
                "error",
                "files.has_content: UTF-8 cannot encode the wanted text with a lone "
                "surrogate",
            ],
            "the call ends with a fault",
        )


class TestHasMode:
    """has_mode checks that a path has a file or a directory with a mode."""

    tests: ClassVar[list[tuple[str, str, int, list[Any]]]] = [
        ("passes a file of the mode", "keys/id", 0o600, ["pass"]),
        ("passes a directory of the mode", "keys", 0o700, ["pass"]),
        (
            "reports a different mode",
            "keys/id",
            0o644,
            ["fail", {"want": 0o644, "got": 0o600, "kind": "file"}],
        ),
        (
            "reports a link without a mode",
            "current",
            0o644,
            ["fail", {"want": 0o644, "got": None, "kind": "link"}],
        ),
        (
            "reports none for a missing path",
            "b.txt",
            0o644,
            ["fail", {"want": 0o644, "got": None, "kind": None}],
        ),
    ]

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    @pytest.mark.parametrize(
        ("give", "give_mode", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_returns_the_outcome(
        self, seat: Collector, fixture: str, give: str, give_mode: int, want: list[Any]
    ) -> None:
        """The verdict depends on the nine bits."""
        path = os.path.join(fixture, give)
        got = outcome(lambda r: files.has_mode(r, path, give_mode, "m"))
        check.equal(seat, got, want, "has_mode returns the outcome")

    def test_ends_the_call_with_a_fault_for_a_mode_beyond_the_nine_bits(
        self, seat: Collector, fixture: str
    ) -> None:
        """The mode is checked first."""
        path = os.path.join(fixture, "a.txt")
        check.equal(
            seat,
            outcome(lambda r: files.has_mode(r, path, 0o1000, "m")),
            [
                "error",
                "files.has_mode: the mode 0o1000 is not an integer from 0 to 0o777",
            ],
            "the call ends with a fault",
        )

    @pytest.mark.skipif(not WINDOWS, reason="the case runs on Windows only")
    def test_ends_the_call_with_a_fault_on_a_platform_without_permission_bits(
        self, seat: Collector, fixture: str
    ) -> None:
        """Windows does not have a mode to read."""
        path = os.path.join(fixture, "a.txt")
        check.equal(
            seat,
            outcome(lambda r: files.has_mode(r, path, 0o644, "m")),
            [
                "error",
                "files.has_mode: the file system does not record permission bits",
            ],
            "the call ends with a fault",
        )
