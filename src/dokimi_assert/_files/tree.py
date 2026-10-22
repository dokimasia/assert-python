# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""A tree of files, and the rules of every tree."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, cast

from dokimi_assert._files.entry import Entry, directory, kind_of
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._record.literal import quoted

if TYPE_CHECKING:
    import builtins

__all__ = ["Tree", "check", "full", "order", "parents_of", "path_fault", "paths_of"]

#: A tree of files maps the path of each entry to the entry. A path is
#: relative to the root of the tree, and slashes separate its names. A path
#: has one or more names. A name is not empty, "." or "..", and it does not
#: contain a backslash or NUL. An entry is never below a file or a link. The
#: directories of a tree are the directories that it has and every parent of
#: an entry.
Tree = Mapping[str, Entry]


def order(path: str) -> builtins.bytes:
    """Return the key that sorts paths by the bytes of their UTF-8 encoding.

    Args:
        path: A path of a tree. A lone surrogate sorts as its UTF-8 form.

    Returns:
        The bytes of the path.
    """
    return path.encode("utf-8", "surrogatepass")


def paths_of(paths: Iterable[str]) -> list[str]:
    """Return paths in the order of their UTF-8 bytes.

    Args:
        paths: The paths of a tree.

    Returns:
        A new list of the paths in that order.
    """
    return sorted(paths, key=order)


def parents_of(path: str) -> list[str]:
    """Return the directories above path in order from the outermost.

    Args:
        path: A path of a tree.

    Returns:
        The parents of the path. For a/b/c they are a and a/b.
    """
    names = path.split("/")
    return ["/".join(names[: i + 1]) for i in range(len(names) - 1)]


def path_fault(path: object) -> str | None:
    """Return the reason that path breaks a rule of a path.

    Args:
        path: A path of a tree.

    Returns:
        The reason, or None for a path that keeps the rules. A path breaks a
        rule when it is not a str or not UTF-8 text. It also breaks a rule
        when it has a name that is empty, "." or "..", or a name that
        contains a backslash or NUL.
    """
    if not isinstance(path, str):
        return f"the path {path!r} is not a str"
    try:
        path.encode("utf-8")
    except UnicodeEncodeError:
        return f"the path {quoted(path)} is not UTF-8 text"
    for name in path.split("/"):
        if name in ("", ".", "..") or "\\" in name or "\0" in name:
            return f"the path {quoted(path)} has the name {quoted(name)}"
    return None


def _is_target(target: str) -> bool:
    """Report whether target is UTF-8 text without NUL that is not empty."""
    try:
        target.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return target != "" and "\0" not in target


def _entry_fault(tree: Mapping[str, object], path: str) -> str | None:
    """Return the reason that the entry at path breaks a rule of a tree, or None."""
    fault = path_fault(path)
    if fault is not None:
        return fault
    e = tree[path]
    kind = kind_of(e)
    if kind is None or not isinstance(e, Entry):
        return "the entry is not a file, a directory or a link"
    if kind == "link" and not (isinstance(e.link, str) and _is_target(e.link)):
        return f"the link does not have a target of UTF-8 text without NUL: {e.link!r}"
    for parent in parents_of(path):
        above = kind_of(tree.get(parent))
        if above in ("file", "link"):
            return f"the entry is below the {above} {quoted(parent)}"
    return None


def check(tree: object) -> None:
    """Check that tree keeps the rules of a tree.

    Each path keeps the rules of a path, and each value is an entry of one
    kind. Each link has a target of UTF-8 text without NUL that is not empty.
    An entry is never below a file or a link.

    Args:
        tree: The tree. A caller can pass a value of any type.

    Raises:
        FaultError: The tree is not a mapping, or an entry breaks a rule. The
            error is at the first such path in path order. A key that is not
            a str comes first.
    """
    if not isinstance(tree, Mapping):
        at = ""
        raise FaultError(at, "the tree is not a mapping of paths to entries")
    keys: list[object] = list(tree)
    for path in keys:
        if not isinstance(path, str):
            at = ""
            raise FaultError(at, f"the path {path!r} is not a str")
    entries = cast("Mapping[str, object]", tree)
    for path in paths_of(entries):
        reason = _entry_fault(entries, path)
        if reason is not None:
            raise FaultError(path, reason)


def full(tree: Mapping[str, Entry]) -> dict[str, Entry]:
    """Return a copy of tree that also has the parent directories of each entry.

    Args:
        tree: The tree.

    Returns:
        The copy. Each parent that tree does not have is a directory without
        a mode.
    """
    out = dict(tree)
    for path in tree:
        for parent in parents_of(path):
            out.setdefault(parent, directory())
    return out
