"""The spec of _files/literal.py tests the tree literal of the definition."""

from __future__ import annotations

import math
from typing import Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._files.entry import Entry, bytes, directory, executable, link, text
from dokimi_assert._files.literal import CONTENT_LIMIT, decode, encode
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.seat import Collector


def literal(*entries: object) -> dict[str, Any]:
    """Return a tree literal of entries."""
    return {"type": "tree", "entries": list(entries)}


class TestContentLimit:
    """CONTENT_LIMIT is the most bytes of a file that a record contains in full."""

    def test_is_65536_bytes(self, seat: Collector) -> None:
        """A record contains a file of up to 64 KiB in full."""
        check.equal(seat, CONTENT_LIMIT, 65_536, "CONTENT_LIMIT is 65536")


class TestEncode:
    """encode returns the tree literal of a tree."""

    def test_returns_the_literal_of_every_kind_of_entry_in_path_order(
        self, seat: Collector
    ) -> None:
        """Each entry has its members."""
        tree = {
            "logo.png": bytes(b"\x89\x50"),
            "bin/run": executable("#!/bin/sh\n"),
            "cache": directory(),
            "current": link("bin/run"),
            "keys/id": text("secret\n").with_mode(0o600),
        }
        check.equal(
            seat,
            encode(tree, CONTENT_LIMIT),
            literal(
                {"path": "bin/run", "text": "#!/bin/sh\n", "executable": True},
                {"path": "cache", "directory": True},
                {"path": "current", "link": "bin/run"},
                {"path": "keys/id", "text": "secret\n", "mode": 0o600},
                {"path": "logo.png", "bytes": "8950"},
            ),
            "encode returns the entries in path order",
        )

    def test_replaces_the_content_of_a_file_longer_than_the_limit_with_a_digest(
        self, seat: Collector
    ) -> None:
        """The digest is the SHA-256 of the content."""
        check.equal(
            seat,
            encode({"a.txt": text("abc")}, 2),
            literal(
                {
                    "path": "a.txt",
                    "digest": "sha256:ba7816bf8f01cfea414140de5dae2223"
                    "b00361a396177a9cb410ff61f20015ad",
                    "size": 3,
                }
            ),
            "encode returns the digest and the size of abc",
        )

    def test_keeps_a_file_as_long_as_the_limit_in_full(self, seat: Collector) -> None:
        """The limit is inclusive."""
        check.equal(
            seat,
            encode({"a.txt": text("abc")}, 3),
            literal({"path": "a.txt", "text": "abc"}),
            "encode returns the text",
        )

    def test_keeps_every_file_in_full_without_a_limit(self, seat: Collector) -> None:
        """An input does not have a limit."""
        check.equal(
            seat,
            encode({"a.txt": text("abc")}, math.inf),
            literal({"path": "a.txt", "text": "abc"}),
            "encode returns the text",
        )


class TestDecode:
    """decode returns the tree of a tree literal."""

    def test_returns_the_tree_of_every_kind_of_entry(self, seat: Collector) -> None:
        """Each entry decodes to its kind. A mode or a flag decodes too."""
        tree = decode(
            literal(
                {"path": "bin/run", "text": "#!/bin/sh\n", "executable": True},
                {"path": "cache", "directory": True, "mode": 0o700},
                {"path": "current", "link": "bin/run"},
                {"path": "keys/id", "text": "secret\n", "mode": 0o600},
                {"path": "logo.png", "bytes": "8950", "executable": True},
                {"path": "notes.txt", "text": "notes\n", "executable": False},
            )
        )
        check.equal(
            seat,
            tree,
            {
                "bin/run": executable("#!/bin/sh\n"),
                "cache": directory().with_mode(0o700),
                "current": link("bin/run"),
                "keys/id": text("secret\n").with_mode(0o600),
                "logo.png": Entry(bytes=b"\x89\x50", executable=True),
                "notes.txt": text("notes\n"),
            },
            "decode returns every kind of entry",
        )

    def test_returns_a_file_of_utf8_bytes_as_text(self, seat: Collector) -> None:
        """Two files of the same bytes are equal."""
        tree = decode(literal({"path": "a.txt", "bytes": "610a"}))
        check.equal(
            seat, tree, {"a.txt": text("a\n")}, "decode returns the bytes as text"
        )

    refusals: ClassVar[list[tuple[str, object, str]]] = [
        ("refuses a literal that is not an object", [], "the literal is not an object"),
        (
            "refuses a literal of another type",
            {"type": "list"},
            'type: the type "list" is not tree',
        ),
        (
            "refuses a literal without a list of entries",
            {"type": "tree"},
            "entries: the literal does not have a list of entries",
        ),
        (
            "refuses an entry that is not an object",
            literal(None),
            "entries[0]: the entry is not an object",
        ),
        (
            "refuses an entry of two kinds",
            literal({"path": "a", "text": "a", "link": "b"}),
            "entries[0]: the entry has [text link], and an entry has one of "
            "text, bytes, directory and link",
        ),
        (
            "refuses an entry without a kind",
            literal({"path": "a"}),
            "entries[0]: the entry has [], and an entry has one of text, "
            "bytes, directory and link",
        ),
        (
            "refuses a member that the kind does not take",
            literal({"path": "a", "link": "b", "mode": 0o644}),
            "entries[0].mode: a link entry does not take mode",
        ),
        (
            "refuses a path that is not a string",
            literal({"path": 1, "text": "a"}),
            "entries[0].path: the path is not a string",
        ),
        (
            "refuses a digest in an input",
            literal({"path": "a", "digest": "sha256:00", "size": 1}),
            "entries[0].digest: a digest does not have content, and only a record "
            "has one",
        ),
        (
            "refuses a directory that is not true",
            literal({"path": "a", "directory": False}),
            "entries[0].directory: directory is not true",
        ),
        (
            "refuses a link that is not a string",
            literal({"path": "a", "link": 1}),
            "entries[0].link: the link is not a string",
        ),
        (
            "refuses bytes in uppercase",
            literal({"path": "a", "bytes": "AB"}),
            'entries[0].bytes: "AB" is not lowercase hexadecimal',
        ),
        (
            "refuses bytes of an odd number of digits",
            literal({"path": "a", "bytes": "abc"}),
            'entries[0].bytes: "abc" is not lowercase hexadecimal',
        ),
        (
            "refuses a text that is not a string",
            literal({"path": "a", "text": 1}),
            "entries[0].text: the text is not a string",
        ),
        (
            "refuses a text that is not UTF-8 text",
            literal({"path": "a", "text": "\ud800"}),
            "entries[0].text: the text is not UTF-8 text",
        ),
        (
            "refuses an entry with a mode and executable",
            literal({"path": "a", "text": "a", "executable": True, "mode": 0o755}),
            "entries[0]: the entry has a mode and executable, and a mode has "
            "the execute bit",
        ),
        (
            "refuses an executable that is not a boolean",
            literal({"path": "a", "text": "a", "executable": "yes"}),
            "entries[0].executable: executable is not a boolean",
        ),
        (
            "refuses a mode that is not a number",
            literal({"path": "a", "text": "a", "mode": "rw"}),
            'entries[0].mode: the mode "rw" is not an integer from 0 to 511',
        ),
        (
            "refuses a mode beyond the nine permission bits",
            literal({"path": "a", "text": "a", "mode": 512}),
            "entries[0].mode: the mode 512 is not an integer from 0 to 511",
        ),
        (
            "refuses a path that repeats the path before it",
            literal({"path": "a", "text": "a"}, {"path": "a", "text": "b"}),
            'entries[1]: the path "a" is not after the path before it',
        ),
        (
            "refuses a path before the path before it",
            literal({"path": "b", "text": "b"}, {"path": "a", "text": "a"}),
            'entries[1]: the path "a" is not after the path before it',
        ),
        (
            "refuses a tree that breaks a rule of a tree",
            literal({"path": "a", "text": "a"}, {"path": "a/b", "text": "b"}),
            'a/b: the entry is below the file "a"',
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refusals], ids=[t[0] for t in refusals]
    )
    def test_raises_the_fault_of_a_literal_that_it_cannot_take(
        self, seat: Collector, give: object, want: str
    ) -> None:
        """The fault has the member that is wrong."""
        error = check.raises(seat, lambda: decode(give), "decode refuses the literal")
        check.error_as(seat, error, FaultError, "the error is a FaultError")
        check.equal(seat, str(error), want, "the fault has the member and the reason")
