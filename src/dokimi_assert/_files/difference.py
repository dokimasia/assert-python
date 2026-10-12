"""The rules by which a tree read from a directory differs from a wanted tree.

Two entries at one path differ in these cases:

- Their kinds differ.
- Two files have different content, or two links have different targets.
- The wanted entry has a mode, and the entry read has different permission
  bits.
- The wanted file does not have a mode, and the execute bits of the owner
  differ.

On a platform that does not record permission bits, the comparison skips
both checks of bits.
"""

from __future__ import annotations

from collections.abc import Mapping

from dokimi_assert._files.entry import (
    OWNER_EXECUTE,
    PERMISSIONS,
    Entry,
    bits_of,
    content_of,
    kind_of,
)
from dokimi_assert._files.platform import HOST
from dokimi_assert._files.tree import full, paths_of

__all__ = ["differing", "differs"]


def _compared(w: Entry) -> int:
    """Return the permission bits that a comparison checks when w is wanted."""
    if w.mode is not None:
        return PERMISSIONS & HOST.recorded_bits
    return OWNER_EXECUTE & HOST.recorded_bits if kind_of(w) == "file" else 0


def differs(w: Entry, g: Entry | None) -> bool:
    """Report whether the entry g read at a path differs from the wanted entry w.

    Args:
        w: The wanted entry.
        g: The entry read, or None when the tree read does not have the path.

    Returns:
        True when the two differ.
    """
    if g is None or kind_of(w) != kind_of(g):
        return True
    return (
        content_of(w) != content_of(g)
        or w.link != g.link
        or bool((bits_of(w) ^ bits_of(g)) & _compared(w))
    )


def differing(
    want: Mapping[str, Entry], got: Mapping[str, Entry], contains: bool
) -> list[str]:
    """Return the paths at which a tree read from a directory differs from want.

    The parents of the entries of want are wanted directories. A path differs
    when one of the two trees has it and the other does not, or when the
    entries at it differ.

    Args:
        want: The wanted tree.
        got: The tree read.
        contains: When True, a path that want does not have is not a
            difference.

    Returns:
        The differing paths in path order.
    """
    wanted = full(want)
    out = [path for path in wanted if differs(wanted[path], got.get(path))]
    if not contains:
        out.extend(path for path in got if path not in wanted)
    return paths_of(out)
