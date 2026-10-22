# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The writes of a tree into a directory.

The directory is the directory of a workspace, a directory that exists, or a
golden directory that an update makes equal to a tree. A write never follows a
link. It creates the entries in path order, each with a call that refuses an
entry that is already there. Each parent is then a directory that the write
created or read before it writes below the parent.

A write sets the mode of a file after it writes the file, and the mode of a
directory after every entry below it. As a result, the umask does not change
a mode, and the mode of a directory does not stop a write below it.
"""

from __future__ import annotations

import contextlib
import functools
import os
import pathlib
import shutil
import stat
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from dokimi_assert._files.difference import differs
from dokimi_assert._files.entry import Entry, content_of, kind_of, unstated
from dokimi_assert._files.platform import written
from dokimi_assert._files.reader import kind_of_mode, read_tree
from dokimi_assert._files.tree import check, full, paths_of
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._record.literal import quoted

if TYPE_CHECKING:
    import builtins
    from collections.abc import Collection, Mapping, Sequence

__all__ = [
    "DIRECTORY_MODE",
    "EXECUTABLE_MODE",
    "FILE_MODE",
    "create",
    "mode_of",
    "overwrite",
    "unlock",
    "update",
]

#: The permission bits with which a write creates a file, before it sets the
#: mode of the file.
_CREATE_FILE = 0o600

#: The permission bits with which a write creates a directory, before it sets
#: the mode of the directory.
_CREATE_DIRECTORY = 0o700

#: The mode that a write sets on a file without a mode.
FILE_MODE = 0o644

#: The mode that a write sets on an executable file without a mode.
EXECUTABLE_MODE = 0o755

#: The mode that a write sets on a directory without a mode.
DIRECTORY_MODE = 0o755

#: The flags that open a file as bytes and do not follow a link.
_RAW = getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)

#: The flags that create a file and refuse an entry that is already there.
_CREATE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | _RAW

#: The flags that write over the content of a file that is there.
_OVERWRITE = os.O_WRONLY | os.O_TRUNC | _RAW


@dataclass(frozen=True, slots=True)
class _Step:
    """One operation of a write.

    Attributes:
        path: The path of the tree that the operation writes.
        run: The operation.
    """

    path: str
    run: Callable[[], None]


def _os_path(directory: str, path: str) -> pathlib.Path:
    """Return the operating system path of a path of a tree in dir."""
    return pathlib.Path(directory, *path.split("/"))


def mode_of(e: Entry) -> int:
    """Return the mode that a write sets on the file or the directory e.

    Args:
        e: The entry.

    Returns:
        The mode of e, or FILE_MODE, EXECUTABLE_MODE or DIRECTORY_MODE when e
        does not have one.
    """
    if e.mode is not None:
        return e.mode
    if e.directory:
        return DIRECTORY_MODE
    return EXECUTABLE_MODE if e.executable else FILE_MODE


def _write_file(at: pathlib.Path, content: builtins.bytes, flags: int) -> None:
    """Write content into the file at at, opened with flags."""
    with os.fdopen(os.open(at, flags, _CREATE_FILE), "wb") as stream:
        stream.write(content)


def _link(at: pathlib.Path, target: str) -> None:
    """Create a link to target at at.

    The link is a directory link when the target is a directory.
    """
    stored = written(target)
    # Path.is_dir raises an error of the file system before Python 3.14, and
    # os.path.isdir returns False.
    pointed = os.path.isdir(at.parent / stored)  # noqa: PTH112
    at.symlink_to(stored, target_is_directory=pointed)


def _create_entry(at: pathlib.Path, e: Entry) -> None:
    """Create the entry e at at.

    A file gets its content and its mode. A directory is created, and a link
    is created with its target.
    """
    kind = kind_of(e)
    if kind == "directory":
        at.mkdir(_CREATE_DIRECTORY)
        return
    if kind == "link":
        _link(at, cast("str", e.link))
        return
    _write_file(at, content_of(e), _CREATE)
    at.chmod(mode_of(e))


def _replace(at: pathlib.Path, e: Entry) -> None:
    """Write e over the entry of its kind at at.

    For a link, the write removes the link and creates it with the new
    target. For a file, the write gives the owner the permission to write the
    file, and then replaces the content and the mode.
    """
    if kind_of(e) == "link":
        at.unlink()
        _link(at, cast("str", e.link))
        return
    at.chmod(_CREATE_FILE)
    _write_file(at, content_of(e), _OVERWRITE)
    at.chmod(mode_of(e))


def _creating(
    directory: str,
    whole: Mapping[str, Entry],
    kept: Collection[str],
    before: Sequence[_Step],
) -> list[_Step]:
    """Return the steps that create each entry of whole that kept does not have.

    The steps start with before. Then they create each entry in path order.
    Last, they set the mode of each directory that they create, starting with
    the deepest.
    """
    steps = list(before)
    modes: list[_Step] = []
    for path in paths_of(whole):
        if path in kept:
            continue
        e = whole[path]
        at = _os_path(directory, path)
        steps.append(_Step(path, functools.partial(_create_entry, at, e)))
        if e.directory:
            modes.append(_Step(path, functools.partial(at.chmod, mode_of(e))))
    return [*steps, *reversed(modes)]


def _apply(directory: str, plan: Callable[[], list[_Step]]) -> None:
    """Check that dir opens as a directory, and run the steps of plan in order.

    Raises:
        FaultError: dir cannot be opened, plan raises a fault, or a step
            fails. The fault of a failed step is at its path.
    """
    try:
        os.scandir(directory).close()
    except OSError as error:
        at = ""
        raise FaultError(at, "the directory cannot be opened", error) from error
    for step in plan():
        try:
            step.run()
        except OSError as error:
            raise FaultError(step.path, "the entry cannot be written", error) from error


def create(directory: str, tree: Mapping[str, Entry]) -> None:
    """Write tree into the existing directory dir.

    The write creates every entry and does not write over an existing entry.
    It creates each file with its content, each directory, and each link with
    its target. A target can be inside or outside dir. Each file and each
    directory gets its mode, or the mode of mode_of when it does not have one.

    Args:
        directory: The directory.
        tree: The tree.

    Raises:
        FaultError: The tree breaks a rule of a tree, dir cannot be opened, or
            an entry cannot be written. The write checks the rules before it
            writes anything. The fault of an entry is at the path of the first
            entry that cannot be written. An example is a path that the file
            system maps to an entry that the write already wrote.
    """
    check(tree)
    _apply(directory, lambda: _creating(directory, full(tree), set(), []))


def _status_at(at: pathlib.Path, path: str) -> os.stat_result | None:
    """Return the lstat result of at, or None when at does not have an entry."""
    try:
        return at.lstat()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise FaultError(path, "the entry cannot be read", error) from error


def _refuse(
    path: str, status: os.stat_result, e: Entry, read: Mapping[str, os.stat_result]
) -> None:
    """Raise the fault of the entry at path when the write cannot write e over it.

    status is the lstat result of the entry. The write refuses an entry that
    is not a file, a directory or a link, an entry of a different kind than e,
    and the entry of a path in read.
    """
    kind = kind_of_mode(status.st_mode)
    if kind is None:
        raise FaultError(path, "the entry is not a file, a directory or a link")
    if kind != kind_of(e):
        raise FaultError(
            path, f"the entry is a {kind}, and the tree has a {kind_of(e)}"
        )
    for other, seen in read.items():
        if (seen.st_dev, seen.st_ino) == (status.st_dev, status.st_ino):
            raise FaultError(
                path, f"the file system maps the path to the entry at {quoted(other)}"
            )


def _overwriting(directory: str, tree: Mapping[str, Entry]) -> list[_Step]:
    """Return the steps that write tree over the entries in dir.

    The plan reads the entry at each path of the full tree in path order. The
    steps replace each file and each link that is there, and create each
    missing entry in the same way as create. Last, they set the mode of each
    existing directory that tree has, starting with the deepest.
    """
    whole = full(tree)
    there: set[str] = set()
    read: dict[str, os.stat_result] = {}
    replaced: list[_Step] = []
    modes: list[_Step] = []
    for path in paths_of(whole):
        e = whole[path]
        at = _os_path(directory, path)
        status = _status_at(at, path)
        if status is None:
            continue
        _refuse(path, status, e, read)
        there.add(path)
        read[path] = status
        if not e.directory:
            replaced.append(_Step(path, functools.partial(_replace, at, e)))
        elif path in tree:
            modes.append(_Step(path, functools.partial(at.chmod, mode_of(e))))
    return [*_creating(directory, whole, there, replaced), *reversed(modes)]


def overwrite(directory: str, tree: Mapping[str, Entry]) -> None:
    """Write tree over the entries of the existing directory dir.

    When a path of the tree does not have an entry, the write creates the
    entry in the same way as create. A file replaces the content of the file
    at its path, even when the owner does not have the permission to write
    that file. A link replaces the target of the link at its path. A
    directory keeps its entries. Each entry of tree gets its mode, or the
    mode of mode_of when it does not have one. An existing parent that tree
    implies keeps its mode. Every entry that tree does not have keeps its
    content and its mode.

    Args:
        directory: The directory.
        tree: The tree.

    Raises:
        FaultError: The tree breaks a rule of a tree, dir cannot be opened,
            or an entry cannot be read or written. Before the write writes
            anything, it raises the fault of the first path in path order
            whose entry cannot be read, has a different kind than in tree,
            or is the entry of an earlier path. A link has a different kind
            than a directory. Later, it raises the fault of the first entry
            that cannot be written.
    """
    check(tree)
    _apply(directory, lambda: _overwriting(directory, tree))


def _remove(at: pathlib.Path) -> None:
    """Remove the entry at at with everything below a directory.

    A missing entry is not an error.
    """
    with contextlib.suppress(FileNotFoundError):
        if stat.S_ISDIR(at.lstat().st_mode):
            shutil.rmtree(at)
            return
        at.unlink()


def update(directory: str, tree: Mapping[str, Entry]) -> None:
    """Make dir equal to tree.

    The update creates dir and its parents when they are missing. It removes
    each entry that tree does not have or has in a different form. It then
    writes each missing entry in the same way as create. It removes a link and
    never the entry that the link points to. It ignores the modes of tree.
    Each file and each directory gets the mode of mode_of for an entry
    without a mode.

    Args:
        directory: The directory.
        tree: The tree.

    Raises:
        FaultError: The tree breaks a rule of a tree, a directory cannot be
            created or read, or an entry cannot be removed or written. The
            fault of an entry is at its path.
    """
    check(tree)
    try:
        pathlib.Path(directory).mkdir(mode=DIRECTORY_MODE, parents=True, exist_ok=True)
    except OSError as error:
        at = ""
        raise FaultError(at, "the directory cannot be created", error) from error
    current = read_tree(directory, False)
    wanted = {path: unstated(e) for path, e in full(tree).items()}
    kept: set[str] = set()
    removals: list[_Step] = []
    for path in reversed(paths_of(current)):
        w = wanted.get(path)
        if w is not None and not differs(w, current[path]):
            kept.add(path)
            continue
        removals.append(
            _Step(path, functools.partial(_remove, _os_path(directory, path)))
        )
    _apply(directory, lambda: _creating(directory, wanted, kept, removals))


def unlock(directory: str | pathlib.Path) -> None:
    """Give the owner the permission to remove every entry below dir.

    dir and each directory below it get the permission of the owner to read,
    write and search them. Each file gets the permission of the owner to write
    it. The entries can then be removed, even below a directory or as a file
    whose mode forbids it. The call does not follow links, and it does not
    change anything when dir is not a directory.

    Args:
        directory: The directory.
    """
    try:
        status = os.lstat(directory)
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(status.st_mode):
        return
    root = pathlib.Path(directory)
    root.chmod(stat.S_IMODE(status.st_mode) | _CREATE_DIRECTORY)
    for path in root.iterdir():
        child = path.lstat()
        if stat.S_ISREG(child.st_mode):
            path.chmod(stat.S_IMODE(child.st_mode) | stat.S_IWUSR)
        unlock(path)
