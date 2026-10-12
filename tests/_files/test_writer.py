"""The spec of _files/writer.py tests the writes of a tree into a directory."""

from __future__ import annotations

import errno
import os
import pathlib
from collections.abc import Callable, Iterator
from typing import ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._files.entry import Entry, directory, executable, link, text
from dokimi_assert._files.writer import (
    DIRECTORY_MODE,
    EXECUTABLE_MODE,
    FILE_MODE,
    create,
    mode_of,
    overwrite,
    unlock,
    update,
)
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.seat import Collector
from helpers import LONG_NAMES_ABSENT, UNENFORCED, WINDOWS

#: The umasks under which a test of the modes that a write sets runs.
UMASKS = [0o022, 0o027, 0o077]


def mode_at(path: pathlib.Path) -> int:
    """Return the permission bits of the entry at path."""
    return os.lstat(path).st_mode & 0o777


def names(dir: pathlib.Path) -> list[str]:
    """Return the names in dir, sorted."""
    return sorted(os.listdir(dir))


def fault_of(write: Callable[[], object]) -> str:
    """Return the text of the fault that write raises, or the empty string."""
    try:
        write()
    except FaultError as error:
        return str(error)
    return ""


@pytest.fixture(params=UMASKS, ids=[f"umask {mask:#o}" for mask in UMASKS])
def umask(request: pytest.FixtureRequest) -> Iterator[int]:
    """Set the umask of the process for the test, and restore it afterwards."""
    mask: int = request.param
    before = os.umask(mask)
    yield mask
    os.umask(before)


class TestFileMode:
    """FILE_MODE is the mode of a file that does not have one."""

    def test_is_0o644(self, seat: Collector) -> None:
        """The owner can read and write the file, and others can read it."""
        check.equal(seat, FILE_MODE, 0o644, "FILE_MODE is 0o644")


class TestExecutableMode:
    """EXECUTABLE_MODE is the mode of an executable file that does not have one."""

    def test_is_0o755(self, seat: Collector) -> None:
        """The owner can write the file, and everyone can read and execute it."""
        check.equal(seat, EXECUTABLE_MODE, 0o755, "EXECUTABLE_MODE is 0o755")


class TestDirectoryMode:
    """DIRECTORY_MODE is the mode of a directory that does not have one."""

    def test_is_0o755(self, seat: Collector) -> None:
        """The owner can write the directory, and everyone can list it."""
        check.equal(seat, DIRECTORY_MODE, 0o755, "DIRECTORY_MODE is 0o755")


class TestModeOf:
    """mode_of returns the mode that a write sets."""

    tests: ClassVar[list[tuple[str, Entry, int]]] = [
        ("returns the mode of the entry", text("a").with_mode(0o600), 0o600),
        ("returns 0o755 for a directory", directory(), 0o755),
        ("returns 0o755 for an executable file", executable("a"), 0o755),
        ("returns 0o644 for a file", text("a"), 0o644),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_mode(self, seat: Collector, give: Entry, want: int) -> None:
        """An entry without a mode gets the mode of its kind."""
        check.equal(seat, mode_of(give), want, "mode_of returns the mode")


class TestCreate:
    """create writes a tree into a directory that exists."""

    def test_writes_each_kind_of_entry(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """Each entry is created."""
        create(
            str(tmp_path),
            {
                "docs/a.md": text("# a\n"),
                "empty": directory(),
                "current": link("docs/a.md"),
            },
        )
        check.equal(
            seat,
            [
                (tmp_path / "docs" / "a.md").read_text(),
                names(tmp_path / "empty"),
                os.readlink(tmp_path / "current"),
            ],
            ["# a\n", [], os.path.join("docs", "a.md")],
            "create writes the file, the directory and the link",
        )

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_sets_the_modes_of_the_tree_under_any_umask(
        self, seat: Collector, tmp_path: pathlib.Path, umask: int
    ) -> None:
        """The umask does not change a mode."""
        create(
            str(tmp_path),
            {
                "notes.txt": text("n"),
                "bin/run": executable("r"),
                "keys": directory().with_mode(0o700),
                "keys/id": text("s").with_mode(0o600),
            },
        )
        paths = ["notes.txt", "bin", "bin/run", "keys", "keys/id"]
        check.equal(
            seat,
            [mode_at(tmp_path / p) for p in paths],
            [0o644, 0o755, 0o755, 0o700, 0o600],
            f"create sets the modes under the umask {umask:#o}",
        )

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_writes_below_a_directory_whose_mode_forbids_writes(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The mode of a directory is set after the entries below it."""
        create(
            str(tmp_path),
            {"sealed": directory().with_mode(0o500), "sealed/a.txt": text("a")},
        )
        check.equal(
            seat,
            [mode_at(tmp_path / "sealed"), (tmp_path / "sealed" / "a.txt").read_text()],
            [0o500, "a"],
            "create writes the file and then sets the mode",
        )
        (tmp_path / "sealed").chmod(0o700)

    def test_raises_the_fault_of_a_tree_that_breaks_a_rule_before_it_writes(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The write does not write anything."""
        fault = fault_of(
            lambda: create(str(tmp_path), {"a.txt": text("a"), "b//c": text("c")})
        )
        check.equal(
            seat,
            [fault, names(tmp_path)],
            ['b//c: the path "b//c" has the name ""', []],
            "create does not write anything",
        )

    def test_raises_the_fault_of_a_directory_that_cannot_be_opened(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A missing directory cannot be opened."""
        fault = fault_of(lambda: create(str(tmp_path / "missing"), {"a": text("a")}))
        want = f"the directory cannot be opened: [Errno {errno.ENOENT}]"
        check.has_prefix(
            seat, fault, want, "the fault has the error of the file system"
        )

    def test_raises_the_fault_of_an_existing_entry(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """An existing file keeps its content."""
        (tmp_path / "a.txt").write_text("old")
        fault = fault_of(lambda: create(str(tmp_path), {"a.txt": text("new")}))
        want = f"a.txt: the entry cannot be written: [Errno {errno.EEXIST}]"
        check.has_prefix(seat, fault, want, "the fault has the path and the error")
        check.equal(
            seat, (tmp_path / "a.txt").read_text(), "old", "the file keeps its content"
        )

    def test_refuses_to_write_through_an_existing_link(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A file is not written through a link at its path."""
        (tmp_path / "target.txt").write_text("kept")
        (tmp_path / "a.txt").symlink_to("target.txt")
        fault = fault_of(lambda: create(str(tmp_path), {"a.txt": text("new")}))
        want = f"a.txt: the entry cannot be written: [Errno {errno.EEXIST}]"
        check.has_prefix(seat, fault, want, "the fault has the path and the error")
        check.equal(
            seat,
            (tmp_path / "target.txt").read_text(),
            "kept",
            "the target keeps its content",
        )


class TestOverwrite:
    """overwrite writes a tree over the entries of a directory."""

    def test_replaces_the_content_of_a_file_that_its_owner_may_not_write(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The write gives the owner the permission first."""
        (tmp_path / "a.txt").write_text("old")
        (tmp_path / "a.txt").chmod(0o400)
        overwrite(str(tmp_path), {"a.txt": text("new")})
        check.equal(
            seat,
            (tmp_path / "a.txt").read_text(),
            "new",
            "overwrite replaces the content",
        )

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_sets_the_mode_of_each_file(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A file without a mode gets 0o644."""
        for name in ("a.txt", "b.txt"):
            (tmp_path / name).write_text("old")
            (tmp_path / name).chmod(0o600)
        overwrite(
            str(tmp_path), {"a.txt": text("a"), "b.txt": text("b").with_mode(0o640)}
        )
        check.equal(
            seat,
            [mode_at(tmp_path / "a.txt"), mode_at(tmp_path / "b.txt")],
            [0o644, 0o640],
            "overwrite sets 0o644 and the mode of the entry",
        )

    def test_replaces_the_target_of_a_link(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The link is removed and created again."""
        (tmp_path / "current").symlink_to("a.txt")
        overwrite(str(tmp_path), {"current": link("b.txt")})
        check.equal(
            seat,
            os.readlink(tmp_path / "current"),
            "b.txt",
            "overwrite replaces the target",
        )

    def test_keeps_the_entries_that_the_tree_does_not_have(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A directory keeps its entries, and another file keeps its content."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs" / "kept.md").write_text("kept")
        (tmp_path / "other.txt").write_text("other")
        overwrite(str(tmp_path), {"docs/new.md": text("new")})
        check.equal(
            seat,
            [names(tmp_path / "docs"), (tmp_path / "other.txt").read_text()],
            [["kept.md", "new.md"], "other"],
            "overwrite keeps the other entries",
        )

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_keeps_the_mode_of_a_parent_that_the_tree_implies(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A parent that the tree does not have keeps its mode."""
        (tmp_path / "docs").mkdir()
        (tmp_path / "docs").chmod(0o750)
        overwrite(str(tmp_path), {"docs/a.md": text("a")})
        check.equal(
            seat,
            mode_at(tmp_path / "docs"),
            0o750,
            "overwrite keeps the mode of the parent",
        )

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_sets_the_mode_of_a_directory_that_the_tree_has(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A directory of the tree gets its mode."""
        (tmp_path / "keys").mkdir()
        overwrite(str(tmp_path), {"keys": directory().with_mode(0o700)})
        check.equal(
            seat,
            mode_at(tmp_path / "keys"),
            0o700,
            "overwrite sets the mode of the directory",
        )

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_gives_a_directory_that_it_creates_the_mode_of_a_directory(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A created parent gets 0o755."""
        overwrite(str(tmp_path), {"a/b.txt": text("b")})
        check.equal(
            seat, mode_at(tmp_path / "a"), 0o755, "overwrite gives the new parent 0o755"
        )

    def _a_file_where_a_directory_is_wanted(self, dir: pathlib.Path) -> None:
        (dir / "docs").write_text("a file")

    def _a_link_where_a_directory_is_wanted(self, dir: pathlib.Path) -> None:
        (dir / "real").mkdir()
        (dir / "docs").symlink_to("real")

    def _a_second_name_of_a_file(self, dir: pathlib.Path) -> None:
        (dir / "a.txt").write_text("a")
        os.link(dir / "a.txt", dir / "b.txt")

    refusals: ClassVar[list[tuple[str, str, dict[str, Entry], str]]] = [
        (
            "refuses a file where the tree has a directory",
            "_a_file_where_a_directory_is_wanted",
            {"docs/a.md": text("a")},
            "docs: the entry is a file, and the tree has a directory",
        ),
        (
            "refuses a link where the tree has a directory",
            "_a_link_where_a_directory_is_wanted",
            {"docs/a.md": text("a")},
            "docs: the entry is a link, and the tree has a directory",
        ),
        (
            "refuses a second name of a file of the tree",
            "_a_second_name_of_a_file",
            {"a.txt": text("x"), "b.txt": text("y")},
            'b.txt: the file system maps the path to the entry at "a.txt"',
        ),
    ]

    @pytest.mark.parametrize(
        ("prepare", "tree", "want"),
        [t[1:] for t in refusals],
        ids=[t[0] for t in refusals],
    )
    def test_raises_the_fault_of_an_entry_that_it_cannot_write_over(
        self,
        seat: Collector,
        tmp_path: pathlib.Path,
        prepare: str,
        tree: dict[str, Entry],
        want: str,
    ) -> None:
        """The write does not write anything before the fault."""
        getattr(self, prepare)(tmp_path)
        before = names(tmp_path)
        fault = fault_of(lambda: overwrite(str(tmp_path), tree))
        check.equal(
            seat,
            [fault, names(tmp_path)],
            [want, before],
            "overwrite does not write anything",
        )

    @pytest.mark.skipif(WINDOWS, reason="Windows does not have named pipes")
    def test_raises_the_fault_of_an_entry_that_is_not_a_file_a_directory_or_a_link(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A pipe cannot be written over."""
        os.mkfifo(tmp_path / "fifo")
        fault = fault_of(lambda: overwrite(str(tmp_path), {"fifo": text("a")}))
        check.equal(
            seat,
            fault,
            "fifo: the entry is not a file, a directory or a link",
            "the fault has the path and the reason",
        )

    @pytest.mark.skipif(
        LONG_NAMES_ABSENT, reason="Windows reports such a name as absent"
    )
    def test_raises_the_fault_of_an_entry_that_cannot_be_read(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A name past the limit of its length cannot be read."""
        name = "n" * 300
        fault = fault_of(lambda: overwrite(str(tmp_path), {name: text("a")}))
        want = f"{name}: the entry cannot be read: [Errno {errno.ENAMETOOLONG}]"
        check.has_prefix(seat, fault, want, "the fault has the path and the error")

    @pytest.mark.skipif(UNENFORCED, reason="every permission is granted here")
    def test_raises_the_fault_of_an_entry_that_cannot_be_written(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A directory without the write bit does not take a new entry."""
        (tmp_path / "sealed").mkdir()
        (tmp_path / "sealed").chmod(0o500)
        fault = fault_of(lambda: overwrite(str(tmp_path), {"sealed/a.txt": text("a")}))
        (tmp_path / "sealed").chmod(0o700)
        want = f"sealed/a.txt: the entry cannot be written: [Errno {errno.EACCES}]"
        check.has_prefix(seat, fault, want, "the fault has the path and the error")

    def test_raises_the_fault_of_a_directory_that_is_a_file(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A file cannot be opened as a directory."""
        (tmp_path / "file").write_text("a")
        fault = fault_of(lambda: overwrite(str(tmp_path / "file"), {"a": text("a")}))
        want = f"the directory cannot be opened: [Errno {errno.ENOTDIR}]"
        check.has_prefix(
            seat, fault, want, "the fault has the error of the file system"
        )

    def test_raises_the_fault_of_a_tree_that_breaks_a_rule(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The tree is checked first."""
        fault = fault_of(lambda: overwrite(str(tmp_path), {"a/../b": text("a")}))
        check.equal(
            seat,
            fault,
            'a/../b: the path "a/../b" has the name ".."',
            "the fault has the path and the reason",
        )


class TestUpdate:
    """update makes a directory equal to a tree."""

    def test_creates_a_missing_directory(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The update creates the directory and its parents."""
        dir = tmp_path / "golden" / "api"
        update(str(dir), {"v1/types.go": text("package v1\n")})
        check.equal(
            seat,
            (dir / "v1" / "types.go").read_text(),
            "package v1\n",
            "update writes the file",
        )

    def test_removes_each_entry_that_the_tree_does_not_have(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The target of a removed link outside the directory keeps its content."""
        dir = tmp_path / "golden"
        (dir / "old").mkdir(parents=True)
        (dir / "old" / "stale.go").write_text("stale")
        (dir / "api.go").write_text("api")
        target = tmp_path / "target.txt"
        target.write_text("kept")
        (dir / "latest").symlink_to(target)
        update(str(dir), {"api.go": text("api")})
        check.equal(
            seat,
            [names(dir), target.read_text()],
            [["api.go"], "kept"],
            "update removes the entries and keeps the target",
        )

    def test_rewrites_only_an_entry_of_a_different_form(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """An equal file is the same file afterwards."""
        (tmp_path / "a.txt").write_text("old")
        (tmp_path / "b.txt").write_text("same")
        kept = os.stat(tmp_path / "b.txt").st_ino
        update(str(tmp_path), {"a.txt": text("new"), "b.txt": text("same")})
        check.equal(
            seat,
            [(tmp_path / "a.txt").read_text(), os.stat(tmp_path / "b.txt").st_ino],
            ["new", kept],
            "update rewrites a.txt and keeps b.txt",
        )

    def test_replaces_a_directory_where_the_tree_has_a_file(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The update removes a directory of a different form with its entries."""
        (tmp_path / "a").mkdir()
        (tmp_path / "a" / "b.txt").write_text("b")
        update(str(tmp_path), {"a": text("a")})
        check.equal(seat, (tmp_path / "a").read_text(), "a", "update writes the file")

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_ignores_the_modes_of_the_tree(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """An update does not compare or write the modes of the tree."""
        update(
            str(tmp_path),
            {"key": text("s").with_mode(0o600), "run.sh": executable("r")},
        )
        check.equal(
            seat,
            [mode_at(tmp_path / "key"), mode_at(tmp_path / "run.sh")],
            [0o644, 0o755],
            "update writes the modes of mode_of",
        )

    def test_raises_the_fault_of_a_directory_that_cannot_be_created(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A file cannot be a parent."""
        (tmp_path / "file").write_text("a")
        fault = fault_of(
            lambda: update(str(tmp_path / "file" / "golden"), {"a": text("a")})
        )
        want = f"the directory cannot be created: [Errno {errno.ENOTDIR}]"
        check.has_prefix(
            seat, fault, want, "the fault has the error of the file system"
        )

    def test_raises_the_fault_of_a_tree_that_breaks_a_rule(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The tree is checked first."""
        fault = fault_of(lambda: update(str(tmp_path), {"": text("a")}))
        check.equal(
            seat, fault, 'the path "" has the name ""', "the fault has the reason"
        )


class TestUnlock:
    """unlock gives the owner the permission to remove every entry below a directory."""

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_gives_the_owner_the_permission_to_remove_every_entry(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """The owner can open each directory and write each file."""
        (tmp_path / "a" / "b").mkdir(parents=True)
        (tmp_path / "a" / "f.txt").write_text("f")
        (tmp_path / "a" / "f.txt").chmod(0o400)
        (tmp_path / "a" / "b").chmod(0o000)
        (tmp_path / "a").chmod(0o500)
        unlock(str(tmp_path))
        check.equal(
            seat,
            [
                mode_at(tmp_path / "a"),
                mode_at(tmp_path / "a" / "b"),
                mode_at(tmp_path / "a" / "f.txt"),
            ],
            [0o700, 0o700, 0o600],
            "unlock opens the directories and the file to the owner",
        )

    def test_does_not_change_a_missing_path(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A missing directory is not an error."""
        unlock(str(tmp_path / "missing"))
        check.is_empty(seat, names(tmp_path), "unlock does not create anything")

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    def test_does_not_change_a_file(
        self, seat: Collector, tmp_path: pathlib.Path
    ) -> None:
        """A file is not a directory."""
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "a.txt").chmod(0o400)
        unlock(str(tmp_path / "a.txt"))
        check.equal(
            seat,
            mode_at(tmp_path / "a.txt"),
            0o400,
            "unlock keeps the mode of the file",
        )
