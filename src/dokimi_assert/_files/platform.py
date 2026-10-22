# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

r"""The facts that the file systems of the platform record.

A tree reads only what the file systems record. Windows does not record
permission bits. Its file systems keep the write bit of the owner of a file
as the read-only attribute of the file, so a tree does not read a mode or an
execute bit there.

Windows resolves the target of a link with backslashes, and it returns an
absolute target after the prefix \\?\. A write there stores a target with
backslashes, and a read returns it with slashes and without the prefix.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

__all__ = ["HOST", "Platform", "target_of", "written"]


@dataclass(frozen=True, slots=True)
class Platform:
    """The facts that the file systems of one platform record.

    Attributes:
        recorded_bits: The permission bits of an entry that a tree reads.
            They are all nine bits or none.
        namespace: The prefix of an absolute target of a link, or the empty
            string.
        separator: The separator of the names of a path.
        mode_fault: The reason that an assertion cannot read a mode, or None
            where the platform records modes.
    """

    recorded_bits: int
    namespace: str
    separator: str
    mode_fault: str | None


#: Every platform that separates the names of a path with a slash.
POSIX = Platform(recorded_bits=0o777, namespace="", separator="/", mode_fault=None)

#: The Windows platform. A backslash separates the names of its paths.
WINDOWS = Platform(
    recorded_bits=0,
    namespace="\\\\?\\",
    separator="\\",
    mode_fault="the file system does not record permission bits",
)

#: The platform of this process. os.sep selects it.
HOST = {POSIX.separator: POSIX, WINDOWS.separator: WINDOWS}[os.sep]


def target_of(stated: str) -> str:
    """Return the target of a link in the form that a tree uses.

    Args:
        stated: The target that the file system returns for the link.

    Returns:
        The names separated by slashes, without the prefix of an absolute
        target.
    """
    return stated.removeprefix(HOST.namespace).replace(HOST.separator, "/")


def written(target: str) -> str:
    """Return the target of a link in the form that the file system stores.

    Args:
        target: The target in the form that a tree uses.

    Returns:
        The names separated by the separator of the platform.
    """
    return target.replace("/", HOST.separator)
