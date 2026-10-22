# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The tree literal of the definition.

A tree literal is {"type": "tree", "entries": [...]} with its entries in path
order. Each entry has path and exactly one of text, bytes, directory and link.
An entry with an execute flag or a mode also has executable or mode. A record
has a digest and a size in place of the content of a file that is longer than
its limit.
"""

from __future__ import annotations

import builtins
import hashlib
import json
import re
from typing import TYPE_CHECKING, Any, cast

from dokimi_assert._files.entry import (
    OWNER_EXECUTE,
    Entry,
    bytes,
    content_of,
    directory,
    is_permissions,
    kind_of,
    link,
    text,
    unstated,
)
from dokimi_assert._files.tree import check, order, paths_of
from dokimi_assert._matcher.fault import FaultError

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["CONTENT_LIMIT", "decode", "encode"]

#: The longest content in bytes that a record contains in full.
CONTENT_LIMIT = 65_536

#: The kind members of an entry. An entry has exactly one of them.
_KIND_MEMBERS = ("text", "bytes", "directory", "link", "digest")

#: The members that an entry of each kind can have.
_TAKES: dict[str, tuple[str, ...]] = {
    "text": ("path", "text", "executable", "mode"),
    "bytes": ("path", "bytes", "executable", "mode"),
    "directory": ("path", "directory", "mode"),
    "link": ("path", "link"),
    "digest": ("path", "digest", "size", "executable", "mode"),
}

#: The lowercase hexadecimal text of bytes.
_HEX = re.compile(r"(?:[0-9a-f]{2})*")


def _content_literal(e: Entry, limit: float) -> dict[str, Any]:
    """Return the literal of the content of a file.

    The literal has the text or the bytes. For content that is longer than
    limit, it has the digest and the size.
    """
    content = content_of(e)
    if len(content) > limit:
        digest = hashlib.sha256(content).hexdigest()
        return {"digest": f"sha256:{digest}", "size": len(content)}
    if e.text is None:
        return {"bytes": content.hex()}
    return {"text": e.text}


def _entry_literal(path: str, e: Entry, limit: float) -> dict[str, Any]:
    """Return the literal of the entry e at path."""
    out: dict[str, Any] = {"path": path}
    kind = kind_of(e)
    if kind == "file":
        out.update(_content_literal(e, limit))
    if kind == "directory":
        out["directory"] = True
    if kind == "link":
        out["link"] = e.link
    if e.executable:
        out["executable"] = True
    if e.mode is not None:
        out["mode"] = e.mode
    return out


def encode(tree: Mapping[str, Entry], limit: float) -> dict[str, Any]:
    """Return the tree literal of tree.

    Args:
        tree: The tree.
        limit: The longest content in bytes that the literal contains in
            full. A record uses CONTENT_LIMIT, and an input uses math.inf.

    Returns:
        The literal with its entries in path order. A file has its text when
        its content is UTF-8 text, and its bytes otherwise. A file whose
        content is longer than limit has its digest and its size instead.
    """
    return {
        "type": "tree",
        "entries": [_entry_literal(path, tree[path], limit) for path in paths_of(tree)],
    }


def _string_at(raw: Mapping[str, Any], member: str, at: str) -> str:
    """Return the str of member, or raise a fault at it for any other value."""
    value = raw[member]
    if not isinstance(value, str):
        at = f"{at}.{member}"
        raise FaultError(at, f"the {member} is not a string")
    return value


def _with_bits(e: Entry, raw: Mapping[str, Any], at: str) -> Entry:
    """Return e with the executable bit or the mode of raw."""
    execute = raw.get("executable")
    mode = raw.get("mode")
    if execute is not None and mode is not None:
        raise FaultError(
            at, "the entry has a mode and executable, and a mode has the execute bit"
        )
    if execute is not None and not isinstance(execute, bool):
        at = f"{at}.executable"
        raise FaultError(at, "executable is not a boolean")
    if mode is not None and not is_permissions(mode):
        at = f"{at}.mode"
        raise FaultError(
            at,
            f"the mode {json.dumps(mode)} is not an integer from 0 to 511",
        )
    if mode is not None:
        return e.with_mode(mode)
    return unstated(e.with_mode(OWNER_EXECUTE)) if execute else e


def _entry_of(raw: Mapping[str, Any], kind: str, at: str) -> Entry:
    """Return the entry of the kind kind from the members of raw."""
    if kind == "digest":
        at = f"{at}.digest"
        raise FaultError(
            at,
            "a digest does not have content, and only a record has one",
        )
    if kind == "directory":
        if raw["directory"] is not True:
            at = f"{at}.directory"
            raise FaultError(at, "directory is not true")
        return _with_bits(directory(), raw, at)
    if kind == "link":
        return link(_string_at(raw, "link", at))
    if kind == "bytes":
        hexadecimal = _string_at(raw, "bytes", at)
        if not _HEX.fullmatch(hexadecimal):
            at = f"{at}.bytes"
            raise FaultError(
                at,
                f"{json.dumps(hexadecimal)} is not lowercase hexadecimal",
            )
        return _with_bits(bytes(builtins.bytes.fromhex(hexadecimal)), raw, at)
    content = _string_at(raw, "text", at)
    try:
        file = text(content)
    except ValueError:
        at = f"{at}.text"
        raise FaultError(at, "the text is not UTF-8 text") from None
    return _with_bits(file, raw, at)


def _decode_entry(raw: object, at: str) -> tuple[str, Entry]:
    """Return the path and the entry of one entry of a tree literal."""
    if not isinstance(raw, dict):
        raise FaultError(at, "the entry is not an object")
    kinds = [member for member in _KIND_MEMBERS if member in raw]
    if len(kinds) != 1:
        raise FaultError(
            at,
            f"the entry has [{' '.join(kinds)}], and an entry has one of text, "
            "bytes, directory and link",
        )
    kind = kinds[0]
    extra = next((m for m in sorted(raw) if m not in _TAKES[kind]), None)
    if extra is not None:
        at = f"{at}.{extra}"
        raise FaultError(at, f"a {kind} entry does not take {extra}")
    return _string_at(raw, "path", at), _entry_of(raw, kind, at)


def decode(literal: object) -> dict[str, Entry]:
    """Return the tree of the tree literal of an input.

    An entry of an input does not have a digest. Only a record has one.

    Args:
        literal: The literal, as json.loads returns it.

    Returns:
        The tree with its entries in path order. Each entry is a file of its
        content, a directory or a link. The tree keeps the rules of a tree.

    Raises:
        FaultError: A member of the literal is wrong, such as entries[2].mode,
            or an entry breaks a rule of a tree. The fault is at the member
            or at the path of the entry.
    """
    if not isinstance(literal, dict):
        at = ""
        raise FaultError(at, "the literal is not an object")
    document = cast("Mapping[str, Any]", literal)
    if document.get("type") != "tree":
        at = "type"
        raise FaultError(at, f"the type {json.dumps(document.get('type'))} is not tree")
    entries = document.get("entries")
    if not isinstance(entries, list):
        at = "entries"
        raise FaultError(at, "the literal does not have a list of entries")
    tree: dict[str, Entry] = {}
    last = ""
    for i, raw in enumerate(entries):
        at = f"entries[{i}]"
        path, e = _decode_entry(raw, at)
        if i > 0 and order(path) <= order(last):
            raise FaultError(
                at, f"the path {json.dumps(path)} is not after the path before it"
            )
        last = path
        tree[path] = e
    check(tree)
    return tree
