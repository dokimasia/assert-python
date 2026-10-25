# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _files/reader.py tests the reads of a tree and of one entry."""

from __future__ import annotations

import errno
import os
import pathlib
import sys
from typing import TYPE_CHECKING

import pytest

from dokimi_assert import check
from dokimi_assert._files.entry import bytes, directory, executable, link, text
from dokimi_assert._files.reader import kind_of_mode, read_path, read_tree
from dokimi_assert._matcher.fault import FaultError
from helpers import LONG_NAMES_ABSENT, UNENFORCED, WINDOWS

if TYPE_CHECKING:
    import builtins
    from collections.abc import Callable

    from dokimi_assert.seat import Collector


def write_file(
    path: pathlib.Path, content: str | builtins.bytes, mode: int = 0o644
) -> None:
    """Write the file at path with content, and give it mode."""
    if isinstance(content, str):
        path.write_text(content)
    else:
        path.write_bytes(content)
    path.chmod(mode)


def make_dir(path: pathlib.Path, mode: int = 0o755) -> None:
    """Create the directory at path, and give it mode."""
    path.mkdir()
    path.chmod(mode)


@pytest.fixture
def fixture(tmp_path: pathlib.Path) -> pathlib.Path:
    """Return a directory of a file, a script, a directory with a mode, and a link."""
    write_file(tmp_path / "a.txt", "a\n")
    write_file(tmp_path / "run.sh", "#!/bin/sh\n", 0o755)
    make_dir(tmp_path / "keys", 0o700)
    write_file(tmp_path / "keys" / "id", b"\x89\x50", 0o600)
    (tmp_path / "current").symlink_to("a.txt")
    return tmp_path


def fault_of(read: Callable[[], object]) -> str:
    """Return the text of the fault that read raises, or the empty string."""
    try:
        read()
    except FaultError as error:
        return str(error)
    return ""


class TestKindOfMode:
    """kind_of_mode returns the kind of an entry from its lstat mode."""

    def test_returns_file_for_a_file(
        self, seat: Collector, fixture: pathlib.Path
    ) -> None:
        """A regular file is a file."""
        mode = os.lstat(fixture / "a.txt").st_mode
        check.equal(seat, kind_of_mode(mode), "file", "kind_of_mode returns file")

    def test_returns_directory_for_a_directory(
        self, seat: Collector, fixture: pathlib.Path
    ) -> None:
        """A directory is a directory."""
        check.equal(
            seat,
            kind_of_mode(os.lstat(fixture).st_mode),
            "directory",
            "kind_of_mode returns directory",
        )

    def test_returns_link_for_a_link(
        self, seat: Collector, fixture: pathlib.Path
    ) -> None:
        """A link is a link and not its target."""
        mode = os.lstat(fixture / "current").st_mode
        check.equal(seat, kind_of_mode(mode), "link", "kind_of_mode returns link")

    @pytest.mark.skipif(WINDOWS, reason="Windows does not have /dev/null")
    def test_returns_none_for_a_device(self, seat: Collector) -> None:
        """A device is not an entry of a tree."""
        check.is_none(
            seat,
            kind_of_mode(pathlib.Path("/dev/null").stat().st_mode),
            "kind_of_mode returns None",
        )


class TestReadTree:
    """read_tree reads the tree in a directory."""

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_returns_every_entry_with_its_mode(
        self, seat: Collector, fixture: pathlib.Path
    ) -> None:
        """A tree read with modes has the bits of each file and directory."""
        check.equal(
            seat,
            read_tree(str(fixture), True),
            {
                "a.txt": text("a\n").with_mode(0o644),
                "current": link("a.txt"),
                "keys": directory().with_mode(0o700),
                "keys/id": bytes(b"\x89\x50").with_mode(0o600),
                "run.sh": text("#!/bin/sh\n").with_mode(0o755),
            },
            "read_tree returns every entry with its mode",
        )

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record an execute bit")
    def test_returns_only_the_execute_bit_of_each_file_without_modes(
        self, seat: Collector, fixture: pathlib.Path
    ) -> None:
        """A tree read without modes has the flag of a script."""
        check.equal(
            seat,
            read_tree(str(fixture), False),
            {
                "a.txt": text("a\n"),
                "current": link("a.txt"),
                "keys": directory(),
                "keys/id": bytes(b"\x89\x50"),
                "run.sh": executable("#!/bin/sh\n"),
            },
            "read_tree returns the execute flag of the script",
        )

    def test_reads_the_tree_of_a_root_that_is_a_link_to_a_directory(
        self,
        seat: Collector,
        fixture: pathlib.Path,
        tmp_path_factory: pytest.TempPathFactory,
    ) -> None:
        """The read follows the link of the root."""
        root = tmp_path_factory.mktemp("root") / "root"
        root.symlink_to(fixture)
        check.equal(
            seat,
            sorted(read_tree(str(root), False)),
            ["a.txt", "current", "keys", "keys/id", "run.sh"],
            "read_tree reads the paths below the link",
        )

    def test_raises_the_fault_of_a_root_that_is_missing(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A missing root cannot be read."""
        fault = fault_of(lambda: read_tree(str(tmp_path / "missing"), True))
        want = f"the tree cannot be read: [Errno {errno.ENOENT}]"
        check.has_prefix(
            seat, fault, want, "the fault has the error of the file system"
        )

    def test_raises_the_fault_of_a_root_that_is_not_a_directory(
        self, seat: Collector, fixture: pathlib.Path
    ) -> None:
        """A file cannot be a root."""
        fault = fault_of(lambda: read_tree(str(fixture / "a.txt"), True))
        check.equal(
            seat,
            fault,
            "the root of the tree is not a directory",
            "the fault has the reason",
        )

    @pytest.mark.skipif(UNENFORCED, reason="every permission is granted here")
    def test_raises_the_fault_of_a_directory_that_cannot_be_read(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A directory without the read bit cannot be listed."""
        make_dir(tmp_path / "sealed", 0o300)
        fault = fault_of(lambda: read_tree(str(tmp_path), True))
        (tmp_path / "sealed").chmod(0o700)
        want = f"sealed: the tree cannot be read: [Errno {errno.EACCES}]"
        check.has_prefix(seat, fault, want, "the fault has the path and the error")

    @pytest.mark.skipif(UNENFORCED, reason="every permission is granted here")
    def test_raises_the_fault_of_a_file_that_cannot_be_read(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A file without the read bit cannot be read."""
        write_file(tmp_path / "secret", "s", 0o000)
        fault = fault_of(lambda: read_tree(str(tmp_path), True))
        want = f"secret: the entry cannot be read: [Errno {errno.EACCES}]"
        check.has_prefix(seat, fault, want, "the fault has the path and the error")

    @pytest.mark.skipif(WINDOWS, reason="Windows does not have named pipes")
    def test_raises_the_fault_of_an_entry_that_is_not_a_file_a_directory_or_a_link(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A pipe is not an entry of a tree."""
        make_dir(tmp_path / "run")
        if sys.platform != "win32":
            os.mkfifo(tmp_path / "run" / "fifo")
        fault = fault_of(lambda: read_tree(str(tmp_path), True))
        check.equal(
            seat,
            fault,
            "run/fifo: the entry is not a file, a directory or a link",
            "the fault has the path and the reason",
        )


class TestReadPath:
    """read_path reads the entry at one path."""

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_returns_a_file_with_its_mode(
        self, seat: Collector, fixture: pathlib.Path
    ) -> None:
        """The entry has the content and the mode."""
        read = read_path(str(fixture / "a.txt"), True)
        check.equal(
            seat,
            read,
            text("a\n").with_mode(0o644),
            "read_path returns the content and the mode",
        )

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_returns_a_file_without_its_content_when_content_is_false(
        self, seat: Collector, fixture: pathlib.Path
    ) -> None:
        """The read does not read the content."""
        read = read_path(str(fixture / "a.txt"), False)
        check.equal(
            seat,
            read,
            text("").with_mode(0o644),
            "read_path returns an empty file with the mode",
        )

    def test_returns_the_link_at_a_path_without_following_it(
        self, seat: Collector, fixture: pathlib.Path
    ) -> None:
        """The read does not follow the link."""
        read = read_path(str(fixture / "current"), True)
        check.equal(seat, read, link("a.txt"), "read_path returns the link")

    def test_returns_none_for_a_missing_path(
        self, seat: Collector, fixture: pathlib.Path
    ) -> None:
        """The path does not have an entry."""
        check.is_none(
            seat, read_path(str(fixture / "b.txt"), True), "read_path returns None"
        )

    def test_returns_none_for_a_path_below_a_file(
        self, seat: Collector, fixture: pathlib.Path
    ) -> None:
        """A file does not have entries below it."""
        check.is_none(
            seat,
            read_path(str(fixture / "a.txt" / "b"), True),
            "read_path returns None",
        )

    @pytest.mark.skipif(
        LONG_NAMES_ABSENT, reason="Windows reports such a name as absent"
    )
    def test_raises_the_fault_of_a_path_that_the_file_system_refuses(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A name past the limit of its length cannot be read."""
        fault = fault_of(lambda: read_path(str(tmp_path / ("n" * 300)), True))
        want = f"the entry cannot be read: [Errno {errno.ENAMETOOLONG}]"
        check.has_prefix(
            seat, fault, want, "the fault has the error of the file system"
        )

    @pytest.mark.skipif(WINDOWS, reason="Windows does not have /dev/null")
    def test_raises_the_fault_of_an_entry_that_is_not_a_file_a_directory_or_a_link(
        self, seat: Collector
    ) -> None:
        """A device is not an entry of a tree."""
        fault = fault_of(lambda: read_path("/dev/null", True))
        check.equal(
            seat,
            fault,
            "the entry is not a file, a directory or a link",
            "the fault has the reason",
        )

    @pytest.mark.skipif(UNENFORCED, reason="every permission is granted here")
    def test_raises_the_fault_of_a_file_that_cannot_be_read(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A file without the read bit cannot be read."""
        write_file(tmp_path / "secret", "s", 0o000)
        fault = fault_of(lambda: read_path(str(tmp_path / "secret"), True))
        want = f"the entry cannot be read: [Errno {errno.EACCES}]"
        check.has_prefix(
            seat, fault, want, "the fault has the error of the file system"
        )
