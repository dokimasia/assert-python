"""The spec of _files/entry.py tests the entries of a tree of files."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._files.entry import (
    OWNER_EXECUTE,
    PERMISSIONS,
    Entry,
    Kind,
    bits_of,
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
    unstated,
    with_text,
)
from dokimi_assert.seat import Collector

#: The signature of a PNG file. Its bytes are not UTF-8 text.
PNG = b"\x89PNG"


class TestPermissions:
    """PERMISSIONS has the nine permission bits."""

    def test_contains_the_nine_permission_bits(self, seat: Collector) -> None:
        """The bits are read, write and execute for the owner, the group and others."""
        check.equal(seat, PERMISSIONS, 0o777, "PERMISSIONS is 0o777")


class TestOwnerExecute:
    """OWNER_EXECUTE is the execute bit of the owner."""

    def test_is_the_execute_bit_of_the_owner(self, seat: Collector) -> None:
        """Git records this one bit."""
        check.equal(seat, OWNER_EXECUTE, 0o100, "OWNER_EXECUTE is 0o100")


class TestEntry:
    """Entry is a file, a directory or a link."""

    def test_returns_an_empty_entry(self, seat: Collector) -> None:
        """An entry of the default fields is not a file, a directory or a link."""
        check.is_none(seat, kind_of(Entry()), "the entry does not have a kind")


class TestEntryWithMode:
    """Entry.with_mode returns the entry with the permission bits of a mode."""

    def test_returns_a_file_with_the_mode(self, seat: Collector) -> None:
        """The file has the mode."""
        entry = text("secret\n").with_mode(0o600)
        check.equal(
            seat,
            entry,
            Entry(text="secret\n", mode=0o600),
            "with_mode sets the mode of the file",
        )

    def test_returns_an_executable_file_whose_mode_replaces_the_execute_flag(
        self, seat: Collector
    ) -> None:
        """The mode of an executable file has its execute bit."""
        entry = executable("#!/bin/sh\n").with_mode(0o700)
        check.equal(
            seat,
            entry,
            Entry(text="#!/bin/sh\n", mode=0o700),
            "the mode replaces the flag executable",
        )

    def test_returns_a_directory_with_the_mode(self, seat: Collector) -> None:
        """The directory has the mode."""
        entry = directory().with_mode(0o700)
        check.equal(
            seat,
            entry,
            Entry(directory=True, mode=0o700),
            "with_mode sets the mode of the directory",
        )

    def test_does_not_change_the_entry(self, seat: Collector) -> None:
        """The call returns a new entry."""
        e = text("a")
        e.with_mode(0o600)
        check.is_none(seat, e.mode, "the entry does not have a mode")

    refusals: ClassVar[list[tuple[str, Entry, Any, str]]] = [
        (
            "refuses a mode beyond the nine permission bits",
            text("a"),
            0o1000,
            "files: with_mode(0o1000): the mode is not an int from 0 to 0o777",
        ),
        (
            "refuses a negative mode",
            text("a"),
            -1,
            "files: with_mode(-1): the mode is not an int from 0 to 0o777",
        ),
        (
            "refuses a mode that is not an int",
            text("a"),
            1.5,
            "files: with_mode(1.5): the mode is not an int from 0 to 0o777",
        ),
        (
            "refuses a bool",
            text("a"),
            True,
            "files: with_mode(True): the mode is not an int from 0 to 0o777",
        ),
        (
            "refuses the mode of a link",
            link("a"),
            0o644,
            "files: with_mode(0o644): the entry is not a file or a directory",
        ),
        (
            "refuses the mode of an empty entry",
            Entry(),
            0o644,
            "files: with_mode(0o644): the entry is not a file or a directory",
        ),
    ]

    @pytest.mark.parametrize(
        ("e", "mode", "want"),
        [t[1:] for t in refusals],
        ids=[t[0] for t in refusals],
    )
    def test_raises_value_error_for_a_mode_that_it_refuses(
        self, seat: Collector, e: Entry, mode: Any, want: str
    ) -> None:
        """The error has the mode and the reason."""
        error = check.raises(
            seat, lambda: e.with_mode(mode), "with_mode refuses the mode"
        )
        check.error_as(seat, error, ValueError, "the error is a ValueError")
        check.equal(seat, str(error), want, "the error has the mode and the reason")


class TestText:
    """text returns a file of text."""

    def test_returns_a_file_whose_content_is_the_text(self, seat: Collector) -> None:
        """The file keeps its text."""
        check.equal(
            seat, text("a\n"), Entry(text="a\n"), "text returns a file with the text"
        )

    def test_raises_value_error_for_a_lone_surrogate(self, seat: Collector) -> None:
        """UTF-8 cannot encode a lone surrogate."""
        error = check.raises(seat, lambda: text("\ud800"), "text refuses the str")
        check.equal(
            seat,
            str(error),
            "files: text: UTF-8 cannot encode a str with a lone surrogate",
            "the error has the reason",
        )

    def test_raises_type_error_for_content_that_is_not_a_str(
        self, seat: Collector
    ) -> None:
        """Bytes are not a str."""
        content: Any = b"a"
        error = check.raises(seat, lambda: text(content), "text refuses the bytes")
        check.error_as(seat, error, TypeError, "the error is a TypeError")
        check.equal(
            seat,
            str(error),
            "files: text takes a str, not bytes",
            "the error has the type of the content",
        )


class TestBytes:
    """bytes returns a file of bytes."""

    def test_returns_a_file_of_text_for_utf8_content(self, seat: Collector) -> None:
        """Two files of the same bytes are equal entries."""
        check.equal(
            seat, bytes(b"a\n"), Entry(text="a\n"), "bytes returns a file of text"
        )

    def test_returns_a_file_of_bytes_for_other_content(self, seat: Collector) -> None:
        """Content that is not UTF-8 text keeps its bytes."""
        check.equal(seat, bytes(PNG), Entry(bytes=PNG), "bytes returns a file of bytes")

    def test_copies_a_bytearray(self, seat: Collector) -> None:
        """A change of the argument does not change the entry."""
        content = bytearray(PNG)
        e = bytes(content)
        content[0] = 0
        check.equal(seat, e.bytes, PNG, "the entry keeps the original bytes")


class TestExecutable:
    """executable returns a file that its owner can execute."""

    def test_returns_an_executable_file_of_text(self, seat: Collector) -> None:
        """The file has the flag executable."""
        entry = executable("#!/bin/sh\n")
        check.equal(
            seat,
            entry,
            Entry(text="#!/bin/sh\n", executable=True),
            "executable sets the flag",
        )

    def test_raises_value_error_for_a_lone_surrogate(self, seat: Collector) -> None:
        """UTF-8 cannot encode a lone surrogate."""
        error = check.raises(
            seat, lambda: executable("\udc00"), "executable refuses the str"
        )
        check.equal(
            seat,
            str(error),
            "files: executable: UTF-8 cannot encode a str with a lone surrogate",
            "the error has the reason",
        )


class TestDirectory:
    """directory returns a directory."""

    def test_returns_a_directory(self, seat: Collector) -> None:
        """A directory does not have other fields."""
        check.equal(
            seat,
            directory(),
            Entry(directory=True),
            "directory returns an entry with the flag directory",
        )


class TestLink:
    """link returns a symbolic link."""

    def test_returns_a_link_to_its_target(self, seat: Collector) -> None:
        """A link keeps its target."""
        check.equal(
            seat,
            link("../a.txt"),
            Entry(link="../a.txt"),
            "link returns an entry with the target",
        )


class TestWithText:
    """with_text returns a file with new text."""

    def test_keeps_the_other_fields_of_the_file(self, seat: Collector) -> None:
        """The mode does not change."""
        changed = with_text(text("a").with_mode(0o600), "b")
        check.equal(
            seat, changed, Entry(text="b", mode=0o600), "with_text keeps the mode"
        )

    def test_raises_value_error_for_a_lone_surrogate(self, seat: Collector) -> None:
        """UTF-8 cannot encode a lone surrogate."""
        check.raises(
            seat, lambda: with_text(text("a"), "\ud800"), "with_text refuses the str"
        )


class TestKindOf:
    """kind_of returns the kind of a value of a tree."""

    tests: ClassVar[list[tuple[str, object, Kind | None]]] = [
        ("returns file for a file of text", text("a"), "file"),
        ("returns file for a file of bytes", bytes(PNG), "file"),
        ("returns directory for a directory", directory(), "directory"),
        ("returns link for a link", link("a"), "link"),
        ("returns none for an entry of two kinds", Entry(text="a", link="b"), None),
        ("returns none for a file of text and bytes", Entry(text="a", bytes=PNG), None),
        ("returns none for a value that is not an entry", {"text": "a"}, None),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_kind(
        self, seat: Collector, give: object, want: Kind | None
    ) -> None:
        """An entry of one kind has that kind."""
        check.equal(seat, kind_of(give), want, "kind_of returns the kind")


class TestIsPermissions:
    """is_permissions reports whether a mode is a set of the nine permission bits."""

    tests: ClassVar[list[tuple[str, object, bool]]] = [
        ("returns true for 0", 0, True),
        ("returns true for 0o777", 0o777, True),
        ("returns false for 0o1000", 0o1000, False),
        ("returns false for a negative int", -1, False),
        ("returns false for a float", 1.0, False),
        ("returns false for a bool", True, False),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_verdict(
        self, seat: Collector, give: object, want: bool
    ) -> None:
        """An int from 0 to 0o777 is a set of the bits."""
        check.equal(
            seat, is_permissions(give), want, "is_permissions returns the verdict"
        )


class TestModeText:
    """mode_text returns the text of a mode."""

    tests: ClassVar[list[tuple[str, object, str]]] = [
        ("returns a non-negative int in octal", 0o640, "0o640"),
        ("returns a negative int as its repr", -8, "-8"),
        ("returns a float as its repr", 1.5, "1.5"),
        ("returns a bool as its repr", False, "False"),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_text(self, seat: Collector, give: object, want: str) -> None:
        """A mode has one text."""
        check.equal(seat, mode_text(give), want, "mode_text returns the text")


class TestContentOf:
    """content_of returns the content of a file as bytes."""

    def test_returns_the_utf8_bytes_of_a_file_of_text(self, seat: Collector) -> None:
        """Text encodes as UTF-8."""
        check.equal(
            seat,
            content_of(text("\N{LATIN SMALL LETTER E WITH ACUTE}")),
            b"\xc3\xa9",
            "content_of returns the UTF-8 bytes",
        )

    def test_returns_the_bytes_of_a_file_of_bytes(self, seat: Collector) -> None:
        """The content of a file of bytes is its bytes."""
        check.equal(seat, content_of(bytes(PNG)), PNG, "content_of returns the bytes")

    def test_returns_empty_bytes_for_a_directory(self, seat: Collector) -> None:
        """A directory does not have content."""
        check.equal(
            seat, content_of(directory()), b"", "content_of returns empty bytes"
        )


class TestContentValue:
    """content_value returns content in the form of a record."""

    def test_returns_text_for_utf8_content(self, seat: Collector) -> None:
        """Content of UTF-8 text is a str."""
        check.equal(seat, content_value(b"a"), "a", "content_value returns a str")

    def test_returns_bytes_for_other_content(self, seat: Collector) -> None:
        """Other content is bytes."""
        check.equal(seat, content_value(PNG), PNG, "content_value returns the bytes")


class TestBitsOf:
    """bits_of returns the permission bits of an entry."""

    tests: ClassVar[list[tuple[str, Entry, int]]] = [
        ("returns the mode of an entry", text("a").with_mode(0o640), 0o640),
        ("returns the execute bit of an executable file", executable("a"), 0o100),
        ("returns 0 for a file without a mode", text("a"), 0),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_bits(self, seat: Collector, give: Entry, want: int) -> None:
        """An entry has its bits."""
        check.equal(seat, bits_of(give), want, "bits_of returns the bits")


class TestUnstated:
    """unstated returns an entry without its mode."""

    tests: ClassVar[list[tuple[str, Entry, Entry]]] = [
        (
            "returns a file whose mode has the execute bit as executable",
            text("a").with_mode(0o750),
            Entry(text="a", executable=True),
        ),
        (
            "returns a file whose mode does not have the execute bit as a plain file",
            text("a").with_mode(0o640),
            Entry(text="a"),
        ),
        (
            "returns a directory without its mode",
            directory().with_mode(0o700),
            Entry(directory=True),
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_entry_without_its_mode(
        self, seat: Collector, give: Entry, want: Entry
    ) -> None:
        """The execute bit of a file becomes its flag."""
        check.equal(
            seat, unstated(give), want, "unstated returns the entry without the mode"
        )
