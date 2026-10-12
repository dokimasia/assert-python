r"""Trees of files for a test, and the assertions about the files of the code.

A Tree maps each path to an Entry. A path is relative to the root of the
tree, and slashes separate its names. An entry is a file with its content, a
directory or a symbolic link. text, bytes, executable, directory and link
build the entries. Entry.with_mode sets the permission bits of a file or a
directory when they are part of the contract.

    dir = files.workspace(seat, {
        "go.mod": files.text("module example.com/a\n"),
        "a/a.go": files.text("package a\n\nfunc Old() {}\n"),
        "keys/id": files.text("secret\n").with_mode(0o600),
    })

workspace writes a tree into a new directory of the test. write writes a
tree over the entries of a directory that exists. equal, contains and
unchanged compare the tree in a directory with a wanted tree. absent,
is_file, is_dir, links_to, has_content and has_mode check the entry at one
path. read returns the content of a file, so that the text assertions apply
to it.

Every assertion here stops the test at a failure in the same way as the
golden comparisons. A file system that does not record permission bits, such as a file
system of Windows, does not have modes or execute bits. A comparison then
does not compare them, and has_mode ends the call with a fault.
"""

from __future__ import annotations

import builtins
import contextlib
import functools
import os
import shutil
import tempfile
from collections.abc import Callable
from typing import Any

from dokimi_assert._files.difference import differing
from dokimi_assert._files.entry import (
    Entry,
    bytes,
    content_of,
    content_value,
    directory,
    executable,
    is_permissions,
    kind_of,
    link,
    mode_text,
    text,
)
from dokimi_assert._files.platform import HOST
from dokimi_assert._files.reader import read_path, read_tree
from dokimi_assert._files.record import comparison, report
from dokimi_assert._files.tree import Tree, check
from dokimi_assert._files.writer import create, overwrite, unlock
from dokimi_assert._matcher.fault import FaultError, of_operation
from dokimi_assert._matcher.loop import Loop
from dokimi_assert._matcher.seat import Mode, Seat
from dokimi_assert._matcher.verdict import Running, end
from dokimi_assert._record.literal import quoted
from dokimi_assert.failure import call_site

__all__ = [
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
]

#: The prefix of the name of the directory of a workspace.
_PREFIX = "dokimi-files-"

#: The detail of a failure for the entry at a path, or None for a pass.
_Detail = Callable[[Entry | None], dict[str, Any] | None]


def _remove(dir: str) -> None:
    """Remove the directory of a workspace, also where a mode forbids it."""
    unlock(dir)
    with contextlib.suppress(FileNotFoundError):
        shutil.rmtree(dir)


def workspace(seat: Seat, tree: Tree) -> str:
    r"""Write tree into a new directory of the test, and return its path.

    The test removes the directory when it ends. The call creates every
    entry and does not write over an existing entry. It never writes through
    a link, and it writes the target of a link as the tree has it. The target
    can point inside or outside the directory. Each file and each directory
    gets its mode. When the tree does not give a mode, a file gets 0o644, and
    an executable file and a directory get 0o755. The call sets each mode
    after it writes the entry, and the mode of a directory after every entry
    below it. As a result, the umask does not change a mode, and the tree is
    the same on every run. The test removes the directory even when the mode of a
    directory in it forbids the owner to write it. On Windows only the write
    bit of the owner in the mode of a file takes effect, as the read-only
    attribute of the file.

    The seat must have a method cleanup that runs a function when the test
    ends. The seat of the fixture and the case of a property have one. When
    the seat does not have cleanup, the call ends with a fault. When the tree
    breaks a rule of a tree, the call ends with a fault before it writes
    anything. The call also ends with a fault when the file system cannot
    store an entry. Examples are a link on a platform that refuses to create
    one, and a second path that the file system maps to an entry that the
    call already wrote.

    Args:
        seat: The seat that receives a fault and registers the removal of the
            directory.
        tree: The tree.

    Returns:
        The path of the directory, or the empty string when the call could
        not create a directory.

    Example:
        dir = files.workspace(seat, {
            "go.mod": files.text("module example.com/a\n"),
            "keys/id": files.text("secret\n").with_mode(0o600),
        })
    """
    __tracebackhide__ = True
    seat.helper()
    cleanup: Any = getattr(seat, "cleanup", None)
    if not callable(cleanup):
        refused = FaultError(
            "", "the seat does not have a cleanup method to remove the workspace"
        )
        end(seat, of_operation("files.workspace", refused))
        return ""
    dir = ""
    try:
        dir = tempfile.mkdtemp(prefix=_PREFIX)
        cleanup(functools.partial(_remove, dir))
        create(dir, tree)
    except (OSError, FaultError) as error:
        end(seat, of_operation("files.workspace", error))
    return dir


def write(seat: Seat, dir: str | os.PathLike[str], tree: Tree) -> None:
    r"""Write tree over the entries of the existing directory dir.

    When a path of the tree does not have an entry, the call creates the
    entry as a workspace does. A file replaces the content of the file at its
    path, a link replaces the target of the link at its path, and a directory
    keeps its entries. Each entry of the tree gets its mode. An entry without
    a mode gets 0o644, or 0o755 for an executable file and a directory. An
    existing parent that the tree implies keeps its mode, and a parent that
    the call creates gets 0o755. Every other entry of dir keeps its content
    and its mode. The call never follows a link. It replaces a link by
    removing the link itself.

    The call ends with a fault before it writes anything in these cases:

    - The tree breaks a rule of a tree.
    - dir is not a directory.
    - An entry has a different kind than in the tree. A link has a different
      kind than a directory, even a link to a directory.
    - A parent of an entry is not a directory.
    - The file system maps a path to the entry at another path of the tree.

    When the file system fails, the call ends with a fault at the path of the
    entry.

    Args:
        seat: The seat that receives a fault.
        dir: The path of the directory in the form of the operating system.
        tree: The tree.

    Example:
        dir = files.workspace(seat, {"api/store.gen.go": files.text(generated)})
        check.no_error(seat, run(dir), "the first run writes the file")
        files.write(seat, dir, {"api/store.gen.go": files.text(edited)})
    """
    __tracebackhide__ = True
    seat.helper()
    try:
        overwrite(os.fspath(dir), tree)
    except FaultError as error:
        end(seat, of_operation("files.write", error))


def read(seat: Seat, path: str | os.PathLike[str]) -> str:
    """Return the content of the file at path, decoded as UTF-8.

    A test checks the content with the text assertions. A byte sequence that
    is not UTF-8 decodes as U+FFFD. The call ends with a fault when path does
    not have a file or when the file cannot be read. The fault stops the
    test. A link to a file is not a file.

    Args:
        seat: The seat that receives a fault.
        path: The path in the form of the operating system.

    Returns:
        The content, or the empty string after a fault on a seat whose fail
        returns.

    Example:
        check.contains(seat, files.read(seat, path), "version 2",
                       "the file has the new version")
    """
    __tracebackhide__ = True
    seat.helper()
    native = os.fspath(path)
    try:
        e = read_path(native, True)
        if e is None or kind_of(e) != "file":
            raise FaultError("", f"the path {quoted(native)} does not have a file")
    except FaultError as error:
        end(seat, of_operation("files.read", error))
        return ""
    return content_of(e).decode("utf-8", "replace")


def _compare_read(
    seat: Seat,
    op: str,
    assertion: str,
    dir: str | os.PathLike[str],
    want: Tree,
    msg: str,
    contains: bool,
) -> None:
    """Compare the tree in dir with want, and report the verdict of the call."""
    __tracebackhide__ = True
    seat.helper()
    where = call_site()
    call = Running.of(seat, where)
    try:
        check(want)
        got = read_tree(os.fspath(dir), True)
    except FaultError as error:
        call.faulted(Mode.FATAL, assertion, msg, of_operation(op, error))
        return
    record = comparison(want, got, differing(want, got, contains))
    report(call, assertion, msg, record, where)


def equal(seat: Seat, dir: str | os.PathLike[str], want: Tree, msg: str) -> None:
    r"""Fail when the tree in dir differs from want.

    The comparison does not follow links. It compares a mode only where the
    wanted entry has one, and otherwise the execute bit of the owner of a
    file. Content is compared as bytes, so a file that ends in \r\n does not
    equal text that ends in \n.

    The failure is a record of tree-equal. want and got have the entries at
    the first 64 paths that differ, and differences is the number of those
    paths. An entry of got has its mode only where want has one.

    The call ends with a fault when want breaks a rule of a tree, when an
    entry of the directory is not a file, a directory or a link, or when the
    tree cannot be read.

    Args:
        seat: The seat that receives the failure.
        dir: The path of the directory in the form of the operating system.
        want: The wanted tree.
        msg: The contract under test.

    Example:
        files.equal(seat, dir, {
            "a/a.go": files.text("package a\n\nfunc New() {}\n"),
        }, "the rename rewrites the declaration")
    """
    __tracebackhide__ = True
    seat.helper()
    _compare_read(seat, "files.equal", "tree-equal", dir, want, msg, False)


def contains(seat: Seat, dir: str | os.PathLike[str], want: Tree, msg: str) -> None:
    r"""Fail when the tree in dir does not have an entry of want in its form.

    The tree can have more entries. The failure is a record of tree-contains.
    The comparison, the record and the faults are those of equal. A path that
    want does not have is not a difference.

    Args:
        seat: The seat that receives the failure.
        dir: The path of the directory in the form of the operating system.
        want: The wanted entries.
        msg: The contract under test.

    Example:
        files.contains(seat, dir, {"out/report.txt": files.text("ok\n")},
                       "the run writes its report")
    """
    __tracebackhide__ = True
    seat.helper()
    _compare_read(seat, "files.contains", "tree-contains", dir, want, msg, True)


def _read_or_end(call: Running, dir: str, msg: str) -> dict[str, Entry] | None:
    """Return the tree in dir, or None after the call ended with a fault."""
    __tracebackhide__ = True
    try:
        return read_tree(dir, True)
    except FaultError as error:
        call.faulted(
            Mode.FATAL, "tree-unchanged", msg, of_operation("files.unchanged", error)
        )
        return None


def unchanged(
    seat: Seat, dir: str | os.PathLike[str], fn: Callable[[], object], msg: str
) -> None:
    """Call fn, and fail when the tree in dir differs after the call.

    The comparison includes the modes. The failure is a record of
    tree-unchanged, with the tree before the call as the wanted tree. The
    comparison ignores timestamps and a write of the same bytes into a file.
    fn can be a coroutine function. The call then runs it on an event loop of
    its own.

    An exception of fn propagates, and the call does not compare anything.
    The record and the faults are those of equal.

    Args:
        seat: The seat that receives the failure.
        dir: The path of the directory in the form of the operating system.
        fn: A callable without arguments.
        msg: The contract under test.

    Example:
        files.unchanged(seat, dir, lambda: migrate.dry_run(dir),
                        "a dry run does not write")
    """
    __tracebackhide__ = True
    seat.helper()
    where = call_site()
    call = Running.of(seat, where)
    native = os.fspath(dir)
    before = _read_or_end(call, native, msg)
    if before is None:
        return
    with Loop("tree-unchanged") as loop:
        try:
            loop.resolve(fn())
        except FaultError as error:
            call.faulted(Mode.FATAL, "tree-unchanged", msg, error)
            return
    after = _read_or_end(call, native, msg)
    if after is None:
        return
    record = comparison(before, after, differing(before, after, False))
    report(call, "tree-unchanged", msg, record, where)


def _check_at(
    seat: Seat,
    op: str,
    assertion: str,
    path: str | os.PathLike[str],
    msg: str,
    content: bool,
    refused: str | None,
    detail: _Detail,
) -> None:
    """Read the entry at path, and report the verdict of the call.

    The verdict is a fault when refused is not None or when the entry cannot
    be read. Otherwise it is a pass when detail returns None, and a failure
    with the returned detail when it does not.
    """
    __tracebackhide__ = True
    seat.helper()
    call = Running.of(seat, call_site())
    try:
        if refused is not None:
            raise FaultError("", refused)
        e = read_path(os.fspath(path), content)
    except FaultError as error:
        call.faulted(Mode.FATAL, assertion, msg, of_operation(op, error))
        return
    failed = detail(e)
    if failed is None:
        call.passed(Mode.FATAL, assertion, msg)
        return
    call.failed(Mode.FATAL, assertion, msg, failed)


def _kind_is(kind: str) -> _Detail:
    """Return the detail function of an assertion that path has an entry of kind."""

    def detail(e: Entry | None) -> dict[str, Any] | None:
        return None if kind_of(e) == kind else {"got": kind_of(e)}

    return detail


def absent(seat: Seat, path: str | os.PathLike[str], msg: str) -> None:
    """Fail when path has a file, a directory or a link.

    A link whose target is missing is an entry at its path. The failure is a
    record of path-absent. Its got is the kind of the entry: file, directory
    or link.

    The assertions about one path read the entry at the path itself, and
    they do not follow a link there. The platform resolves the names before
    the last one, and it follows a link among them. A path below a file does
    not have an entry. The call ends with a fault when the entry is not a
    file, a directory or a link. It also ends with a fault when the file
    system fails with an error other than a missing entry.

    Args:
        seat: The seat that receives the failure.
        path: The path in the form of the operating system.
        msg: The contract under test.

    Example:
        files.absent(seat, os.path.join(dir, "lock"), "the run removes its lock")
    """
    __tracebackhide__ = True
    seat.helper()

    def detail(e: Entry | None) -> dict[str, Any] | None:
        return None if e is None else {"got": kind_of(e)}

    _check_at(seat, "files.absent", "path-absent", path, msg, False, None, detail)


def is_file(seat: Seat, path: str | os.PathLike[str], msg: str) -> None:
    """Fail when path does not have a file.

    A link to a file is a link. The failure is a record of is-file. Its got is
    the kind of the entry at the path, or None. The assertion reads the path
    in the same way as absent.

    Args:
        seat: The seat that receives the failure.
        path: The path in the form of the operating system.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    _check_at(
        seat, "files.is_file", "is-file", path, msg, False, None, _kind_is("file")
    )


def is_dir(seat: Seat, path: str | os.PathLike[str], msg: str) -> None:
    """Fail when path does not have a directory.

    A link to a directory is a link. The failure is a record of is-dir. Its
    got is the kind of the entry at the path, or None. The assertion reads
    the path in the same way as absent.

    Args:
        seat: The seat that receives the failure.
        path: The path in the form of the operating system.
        msg: The contract under test.
    """
    __tracebackhide__ = True
    seat.helper()
    detail = _kind_is("directory")
    _check_at(seat, "files.is_dir", "is-dir", path, msg, False, None, detail)


def links_to(seat: Seat, path: str | os.PathLike[str], target: str, msg: str) -> None:
    """Fail when path does not have a symbolic link to target.

    The target is compared as text with slashes as separators on every
    platform, and the call does not follow the link. The failure is a record
    of links-to. want is target, got is the target of the link at the path or
    None, and kind is the kind of the entry there or None. The assertion
    reads the path in the same way as absent.

    Args:
        seat: The seat that receives the failure.
        path: The path in the form of the operating system.
        target: The wanted target.
        msg: The contract under test.

    Example:
        files.links_to(seat, os.path.join(dir, "current"), "releases/2",
                       "the deploy moves the link")
    """
    __tracebackhide__ = True
    seat.helper()

    def detail(e: Entry | None) -> dict[str, Any] | None:
        if e is not None and e.link == target:
            return None
        return {
            "want": target,
            "got": None if e is None else e.link,
            "kind": kind_of(e),
        }

    _check_at(seat, "files.links_to", "links-to", path, msg, False, None, detail)


def has_content(
    seat: Seat,
    path: str | os.PathLike[str],
    want: str | builtins.bytes | bytearray,
    msg: str,
) -> None:
    r"""Fail when path does not have a file whose bytes equal want.

    The call compares bytes, so a file that ends in \r\n does not equal text
    that ends in \n. The failure is a record of has-content. want is want, got
    is the content of the file or None, and kind is the kind of the entry
    there or None. A content is a str when it is UTF-8 text, and bytes
    otherwise. The assertion reads the path in the same way as absent.

    The call ends with a fault when want is a str with a lone surrogate.
    UTF-8 cannot encode such a str.

    Args:
        seat: The seat that receives the failure.
        path: The path in the form of the operating system.
        want: The wanted content, as text or as bytes.
        msg: The contract under test.

    Example:
        files.has_content(seat, os.path.join(dir, "go.mod"),
                          "module example.com/a\n", "the module is renamed")
    """
    __tracebackhide__ = True
    seat.helper()
    refused: str | None = None
    wanted = b""
    if isinstance(want, str):
        try:
            wanted = want.encode("utf-8")
        except UnicodeEncodeError:
            refused = "UTF-8 cannot encode the wanted text with a lone surrogate"
    else:
        wanted = builtins.bytes(want)

    def detail(e: Entry | None) -> dict[str, Any] | None:
        content = content_of(e) if e is not None and kind_of(e) == "file" else None
        if content is not None and content == wanted:
            return None
        got = None if content is None else content_value(content)
        return {"want": content_value(wanted), "got": got, "kind": kind_of(e)}

    op = "files.has_content"
    _check_at(seat, op, "has-content", path, msg, True, refused, detail)


def has_mode(seat: Seat, path: str | os.PathLike[str], want: int, msg: str) -> None:
    """Fail when path does not have a file or a directory with the mode want.

    A link does not have a mode. The failure is a record of has-mode. want is
    want, got is the permission bits of the file or the directory there or
    None, and kind is the kind of the entry there or None. The assertion
    reads the path in the same way as absent.

    The call ends with a fault when want is not an int from 0 to 0o777. It
    also ends with a fault on a file system that does not record permission
    bits, because such a file system does not have bits to compare.

    Args:
        seat: The seat that receives the failure.
        path: The path in the form of the operating system.
        want: The wanted permission bits.
        msg: The contract under test.

    Example:
        files.has_mode(seat, key_path, 0o600, "the key is private")
    """
    __tracebackhide__ = True
    seat.helper()
    refused = HOST.mode_fault
    if not is_permissions(want):
        refused = f"the mode {mode_text(want)} is not an integer from 0 to 0o777"

    def detail(e: Entry | None) -> dict[str, Any] | None:
        mode = e.mode if e is not None and kind_of(e) in ("file", "directory") else None
        if mode is not None and mode == want:
            return None
        return {"want": want, "got": mode, "kind": kind_of(e)}

    _check_at(seat, "files.has_mode", "has-mode", path, msg, False, refused, detail)
