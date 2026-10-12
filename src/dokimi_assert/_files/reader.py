"""The reads of a tree from a directory and of the entry at one path.

A reader does not follow links, and it reads a link as an entry with its
target. It reads the permission bits of each file and each directory as the
platform records them.
"""

from __future__ import annotations

import builtins
import os
import stat

from dokimi_assert._files.entry import (
    PERMISSIONS,
    Entry,
    Kind,
    bytes,
    directory,
    link,
    unstated,
)
from dokimi_assert._files.platform import HOST, target_of
from dokimi_assert._matcher.fault import FaultError

__all__ = ["kind_of_mode", "read_path", "read_tree"]

#: The flags that open a file for reading. The file opens as bytes, and the
#: open does not follow a link where the platform has that flag.
_READ = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)


def kind_of_mode(mode: int) -> Kind | None:
    """Return the kind of an entry from its lstat mode.

    Args:
        mode: The st_mode of the entry.

    Returns:
        The kind, or None for a device, a pipe, a socket or any other entry
        that a tree cannot have.
    """
    if stat.S_ISLNK(mode):
        return "link"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    return None


def _content(os_path: str) -> builtins.bytes:
    """Return the bytes of the file at os_path, without following a link."""
    with os.fdopen(os.open(os_path, _READ), "rb") as stream:
        return stream.read()


def _entry_of(
    os_path: str, at: str, status: os.stat_result, modes: bool, content: bool
) -> Entry:
    """Return the entry at os_path. status is its lstat result.

    A link is a link with its target. A file or a directory has the
    permission bits that the platform records. When modes is False, a file has
    only the execute bit of its owner. When content is False, a file does not
    have content.
    """
    kind = kind_of_mode(status.st_mode)
    if kind is None:
        raise FaultError(at, "the entry is not a file, a directory or a link")
    if kind == "link":
        return link(target_of(os.readlink(os_path)))
    read = (
        bytes(_content(os_path) if content else b"") if kind == "file" else directory()
    )
    bits = read.with_mode(status.st_mode & PERMISSIONS & HOST.recorded_bits)
    return bits if modes and HOST.recorded_bits != 0 else unstated(bits)


def _walk(dir: str, names: list[str], modes: bool, tree: dict[str, Entry]) -> None:
    """Read the entries below the directory names of dir into tree."""
    try:
        children = os.listdir(os.path.join(dir, *names))
    except OSError as error:
        raise FaultError("/".join(names), "the tree cannot be read", error) from error
    for name in children:
        path = [*names, name]
        os_path = os.path.join(dir, *path)
        at = "/".join(path)
        try:
            e = _entry_of(os_path, at, os.lstat(os_path), modes, True)
        except OSError as error:
            raise FaultError(at, "the entry cannot be read", error) from error
        tree[at] = e
        if e.directory:
            _walk(dir, path, modes, tree)


def read_tree(dir: str, modes: bool) -> dict[str, Entry]:
    """Return the tree in dir.

    The tree has every entry below dir. Each link is a link with its target.
    Each file and each directory has the permission bits that the platform
    records. The root can be a link to a directory.

    Args:
        dir: The path of the directory in the form of the operating system.
        modes: When True, the tree has the modes of its entries. When False,
            each file has only the execute bit of its owner. An update of a
            golden tree reads the tree this way.

    Returns:
        The tree.

    Raises:
        FaultError: The root is not a directory, or the tree cannot be read.
            The fault is at the path of an entry that cannot be read or that
            is not a file, a directory or a link.
    """
    try:
        status = os.stat(dir)
    except OSError as error:
        raise FaultError("", "the tree cannot be read", error) from error
    if not stat.S_ISDIR(status.st_mode):
        raise FaultError("", "the root of the tree is not a directory")
    tree: dict[str, Entry] = {}
    _walk(dir, [], modes, tree)
    return tree


def read_path(path: str, content: bool) -> Entry | None:
    """Return the entry at path.

    The entry has the permission bits that the platform records. The read
    does not follow a link at the path. The platform resolves a link among the
    names before the last one. A path below a file does not have an entry.

    Args:
        path: The path in the form of the operating system.
        content: When True, the read reads the content of a file.

    Returns:
        The entry, or None when the path does not have an entry.

    Raises:
        FaultError: The entry is not a file, a directory or a link, or the
            file system fails with an error other than a missing entry.
    """
    try:
        status = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return None
    except OSError as error:
        raise FaultError("", "the entry cannot be read", error) from error
    try:
        return _entry_of(path, "", status, True, content)
    except OSError as error:
        raise FaultError("", "the entry cannot be read", error) from error
