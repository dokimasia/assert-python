# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _files/difference.py tests how a tree read differs from a wanted tree."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._files.difference import differing, differs
from dokimi_assert._files.entry import Entry, bytes, directory, executable, link, text
from helpers import WINDOWS

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


class TestDiffers:
    """differs compares an entry read with the wanted entry."""

    tests: ClassVar[list[tuple[str, Entry, Entry | None, bool]]] = [
        ("returns true for an entry that was not read", text("a"), None, True),
        ("returns true for entries of different kinds", directory(), text(""), True),
        ("returns true for files of different content", text("a"), text("b"), True),
        (
            "returns true for files of different bytes",
            bytes(b"\x89"),
            bytes(b"\x8a"),
            True,
        ),
        ("returns true for links of different targets", link("a"), link("b"), True),
        ("returns false for equal links", link("a"), link("a"), False),
        (
            "returns false for a directory of any mode when no mode is wanted",
            directory(),
            directory().with_mode(0o700),
            False,
        ),
        (
            "returns false for a file whose mode differs outside the execute bit",
            text("a"),
            text("a").with_mode(0o600),
            False,
        ),
    ]

    @pytest.mark.parametrize(
        ("give_want", "give_got", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_returns_the_verdict(
        self, seat: Collector, give_want: Entry, give_got: Entry | None, want: bool
    ) -> None:
        """The comparison checks the kind, the content and the target everywhere."""
        check.equal(
            seat, differs(give_want, give_got), want, "differs returns the verdict"
        )

    modes: ClassVar[list[tuple[str, Entry, Entry, bool]]] = [
        (
            "returns true for a mode that differs from the wanted mode",
            text("a").with_mode(0o600),
            text("a").with_mode(0o644),
            True,
        ),
        (
            "returns false for the wanted mode",
            text("a").with_mode(0o600),
            text("a").with_mode(0o600),
            False,
        ),
        (
            "returns true for a different execute bit when no mode is wanted",
            text("a"),
            text("a").with_mode(0o755),
            True,
        ),
        (
            "returns false for the same execute bit when no mode is wanted",
            executable("a"),
            text("a").with_mode(0o700),
            False,
        ),
    ]

    @pytest.mark.skipif(WINDOWS, reason="Windows does not record permission bits")
    @pytest.mark.parametrize(
        ("give_want", "give_got", "want"),
        [t[1:] for t in modes],
        ids=[t[0] for t in modes],
    )
    def test_returns_the_verdict_on_the_bits(
        self, seat: Collector, give_want: Entry, give_got: Entry, want: bool
    ) -> None:
        """The comparison checks every bit of a wanted mode.

        For a wanted file without a mode, it checks the execute bit.
        """
        check.equal(
            seat, differs(give_want, give_got), want, "differs returns the verdict"
        )


class TestDiffering:
    """differing returns the paths at which two trees differ."""

    WANT: ClassVar[dict[str, Entry]] = {"a.txt": text("a"), "docs/b.md": text("b")}

    def test_returns_an_empty_list_for_a_tree_with_the_wanted_entries(
        self, seat: Collector
    ) -> None:
        """The tree read has the implied directory too."""
        got = {"a.txt": text("a"), "docs": directory(), "docs/b.md": text("b")}
        check.is_empty(seat, differing(self.WANT, got, False), "no path differs")

    def test_returns_each_path_that_one_tree_does_not_have(
        self, seat: Collector
    ) -> None:
        """A path that one tree does not have differs."""
        got = {"z.txt": text("z"), "a.txt": text("a")}
        check.equal(
            seat,
            differing(self.WANT, got, False),
            ["docs", "docs/b.md", "z.txt"],
            "differing returns the paths in path order",
        )

    def test_ignores_an_extra_path_when_contains_is_true(self, seat: Collector) -> None:
        """An extra path is not a difference."""
        got = {
            "a.txt": text("a"),
            "docs": directory(),
            "docs/b.md": text("b"),
            "z.txt": text("z"),
        }
        check.is_empty(seat, differing(self.WANT, got, True), "no path differs")
