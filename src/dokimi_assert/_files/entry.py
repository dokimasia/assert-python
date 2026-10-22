# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""A file with its content, a directory or a link of a tree of files.

An entry has permission bits when a test gives it a mode.
"""

from __future__ import annotations

import builtins
import dataclasses
from dataclasses import dataclass
from typing import Literal

__all__ = [
    "OWNER_EXECUTE",
    "PERMISSIONS",
    "Entry",
    "Kind",
    "bits_of",
    "bytes",
    "content_of",
    "content_value",
    "directory",
    "executable",
    "is_permissions",
    "kind_of",
    "link",
    "mode_text",
    "text",
    "unstated",
    "with_text",
]

#: The kind of an entry in a record.
Kind = Literal["file", "directory", "link"]

#: The nine permission bits: read, write and execute for the owner, the group
#: and others.
PERMISSIONS = 0o777

#: The permission bit that lets the owner execute a file.
OWNER_EXECUTE = 0o100


@dataclass(frozen=True, slots=True)
class Entry:
    """A file, a directory or a symbolic link of a tree.

    An entry has the fields of the tree literal:

    - A file keeps UTF-8 content in text and other content in bytes, so two
      files of the same bytes are equal entries.
    - A directory has directory set.
    - A link keeps its target in link.
    - A file that its owner can execute has executable set.
    - An entry with permission bits keeps them in mode.

    files.text, files.bytes, files.executable, files.directory and files.link
    build entries. Any other entry does not have a kind. Entry() and an entry
    of two kinds are examples. A tree that contains such an entry breaks a
    rule of a tree.

    Attributes:
        text: The content of a file that is UTF-8 text.
        bytes: The content of a file that is not UTF-8 text.
        directory: When True, the entry is a directory.
        link: The target of a link.
        executable: When True, the owner can execute the file. Only an entry
            without a mode uses it.
        mode: The nine permission bits of a file or a directory, or None.
    """

    text: str | None = None
    bytes: builtins.bytes | None = None
    directory: bool = False
    link: str | None = None
    executable: bool = False
    mode: int | None = None

    def with_mode(self, mode: int) -> Entry:
        r"""Return this entry with the nine permission bits of mode.

        A workspace sets the mode, and a comparison compares it. The execute
        bit of the owner in mode replaces the flag executable of a file.

        Args:
            mode: The permission bits as an int from 0 to 0o777.

        Returns:
            A new entry.

        Raises:
            ValueError: mode is not an int from 0 to 0o777, or the entry is
                not a file or a directory.

        Example:
            files.text("secret\n").with_mode(0o600)
        """
        if not is_permissions(mode):
            msg = (
                f"files: with_mode({mode_text(mode)}): the mode is not an int "
                "from 0 to 0o777"
            )
            raise ValueError(msg)
        if kind_of(self) not in ("file", "directory"):
            msg = (
                f"files: with_mode({mode_text(mode)}): the entry is not a file or "
                "a directory"
            )
            raise ValueError(msg)
        return dataclasses.replace(self, executable=False, mode=mode)


def _well_formed(call: str, content: object) -> str:
    """Return content after a check that it is a str that UTF-8 can encode.

    Raises:
        TypeError: content is not a str.
        ValueError: content has a lone surrogate.
    """
    if not isinstance(content, str):
        msg = f"files: {call} takes a str, not {type(content).__name__}"
        raise TypeError(msg)
    try:
        content.encode("utf-8")
    except UnicodeEncodeError:
        msg = f"files: {call}: UTF-8 cannot encode a str with a lone surrogate"
        raise ValueError(msg) from None
    return content


def text(content: str) -> Entry:
    r"""Return a file whose content is text.

    Args:
        content: The text. The file has its UTF-8 encoding.

    Returns:
        The entry.

    Raises:
        TypeError: content is not a str.
        ValueError: content has a lone surrogate. UTF-8 cannot encode it.

    Example:
        files.text("module example.com/a\n")
    """
    return Entry(text=_well_formed("text", content))


def bytes(content: builtins.bytes | bytearray) -> Entry:
    r"""Return a file whose content is content.

    The entry keeps a copy of content. It keeps UTF-8 content as text.

    Args:
        content: The bytes of the file.

    Returns:
        The entry.

    Example:
        files.bytes(b"\x89PNG")
    """
    stored = content_value(builtins.bytes(content))
    if isinstance(stored, str):
        return Entry(text=stored)
    return Entry(bytes=stored)


def executable(content: str) -> Entry:
    r"""Return a file of text that its owner can execute.

    Args:
        content: The text. The file has its UTF-8 encoding.

    Returns:
        The entry.

    Raises:
        TypeError: content is not a str.
        ValueError: content has a lone surrogate. UTF-8 cannot encode it.

    Example:
        files.executable("#!/bin/sh\necho ok\n")
    """
    return Entry(text=_well_formed("executable", content), executable=True)


def directory() -> Entry:
    """Return a directory.

    A tree needs a directory entry only for an empty directory or for a mode,
    because every parent of an entry is a directory of the tree.

    Returns:
        The entry.
    """
    return Entry(directory=True)


def link(target: str) -> Entry:
    """Return a symbolic link to target.

    The rules of a path do not apply to the target. The target can point
    inside or outside the tree, and the library does not follow the link.
    The library reads a target with slashes on every platform, so a target
    separates its names with slashes.

    Args:
        target: The target of the link.

    Returns:
        The entry.

    Example:
        files.link("bin/run")
    """
    return Entry(link=target)


def with_text(e: Entry, content: str) -> Entry:
    """Return a copy of the file e with content as its text.

    Args:
        e: A file.
        content: The new content.

    Returns:
        A new entry.

    Raises:
        ValueError: content has a lone surrogate. UTF-8 cannot encode it.
    """
    return dataclasses.replace(e, text=_well_formed("text", content))


def kind_of(value: object) -> Kind | None:
    """Return the kind of value.

    Args:
        value: A value of a tree.

    Returns:
        The kind of an entry that has exactly one of file content, a
        directory flag and a link target. It is None for any other value.
    """
    if not isinstance(value, Entry):
        return None
    kinds: list[Kind] = []
    if value.text is not None:
        kinds.append("file")
    if value.bytes is not None:
        kinds.append("file")
    if value.directory:
        kinds.append("directory")
    if value.link is not None:
        kinds.append("link")
    return kinds[0] if len(kinds) == 1 else None


def is_permissions(mode: object) -> bool:
    """Report whether mode is a set of the nine permission bits.

    Args:
        mode: A mode that a caller passes.

    Returns:
        True for an int from 0 to 0o777 that is not a bool.
    """
    return (
        isinstance(mode, int)
        and not isinstance(mode, bool)
        and 0 <= mode <= PERMISSIONS
    )


def mode_text(mode: object) -> str:
    """Return the text of a mode.

    Args:
        mode: A mode that a caller passes.

    Returns:
        A non-negative int in octal such as 0o600, or the repr of any other
        value.
    """
    if isinstance(mode, int) and not isinstance(mode, bool) and mode >= 0:
        return f"0o{mode:o}"
    return repr(mode)


def content_of(e: Entry) -> builtins.bytes:
    """Return the content of a file as bytes, or empty bytes for any other entry.

    Args:
        e: The entry.

    Returns:
        The content.
    """
    if e.bytes is not None:
        return e.bytes
    return (e.text or "").encode("utf-8")


def content_value(content: builtins.bytes) -> str | builtins.bytes:
    """Return content in the form of a record.

    Args:
        content: The content of a file.

    Returns:
        The text when content is UTF-8 text, and the bytes otherwise.
    """
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content


def bits_of(e: Entry) -> int:
    """Return the permission bits of e.

    Args:
        e: The entry.

    Returns:
        The mode of e, or the execute bit of the owner for an executable file.
    """
    if e.mode is not None:
        return e.mode
    return OWNER_EXECUTE if e.executable else 0


def unstated(e: Entry) -> Entry:
    """Return e without its mode.

    Args:
        e: The entry.

    Returns:
        A new entry without a mode. A file whose bits include the execute bit
        of the owner is executable.
    """
    execute = kind_of(e) == "file" and bool(bits_of(e) & OWNER_EXECUTE)
    return dataclasses.replace(e, executable=execute, mode=None)
