# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _files/tree.py tests a tree of files and the rules of every tree."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._files.entry import Entry, directory, link, text
from dokimi_assert._files.tree import check as check_tree
from dokimi_assert._files.tree import full, order, parents_of, path_fault, paths_of
from dokimi_assert._matcher.fault import FaultError

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector


class TestOrder:
    """order returns the key that sorts paths by their UTF-8 bytes."""

    def test_orders_a_path_below_u10000_before_one_above_it(
        self, seat: Collector
    ) -> None:
        """The UTF-8 bytes sort the two paths in the order of their code points."""
        check.is_true(
            seat, order(chr(0xFFFF)) < order(chr(0x10000)), "U+FFFF comes first"
        )

    def test_returns_the_utf8_form_of_a_lone_surrogate(self, seat: Collector) -> None:
        """A path with a lone surrogate still has a key."""
        check.equal(
            seat,
            order("\ud800"),
            b"\xed\xa0\x80",
            "order returns the UTF-8 form of the surrogate",
        )


class TestPathsOf:
    """paths_of sorts paths in the order of their UTF-8 bytes."""

    def test_returns_the_paths_in_the_order_of_their_bytes(
        self, seat: Collector
    ) -> None:
        """A slash sorts after a hyphen and a dot."""
        check.equal(
            seat,
            paths_of(["b", "a/b", "a.txt", "a-b", "a"]),
            ["a", "a-b", "a.txt", "a/b", "b"],
            "paths_of sorts the paths by their bytes",
        )


class TestParentsOf:
    """parents_of returns the directories above a path."""

    def test_returns_the_directories_above_a_path_from_the_outermost(
        self, seat: Collector
    ) -> None:
        """Each parent is a prefix of the path."""
        check.equal(
            seat, parents_of("a/b/c"), ["a", "a/b"], "parents_of returns a and a/b"
        )

    def test_returns_an_empty_list_for_a_path_of_one_name(
        self, seat: Collector
    ) -> None:
        """A name at the root does not have a parent."""
        check.is_empty(seat, parents_of("a"), "parents_of returns an empty list")


class TestPathFault:
    """path_fault returns the reason that a path breaks a rule of a path."""

    tests: ClassVar[list[tuple[str, object, str | None]]] = [
        ("returns none for a path of names", "a/b.txt", None),
        ("returns the fault of an empty path", "", 'the path "" has the name ""'),
        (
            "returns the fault of an empty name",
            "a//b",
            'the path "a//b" has the name ""',
        ),
        ("returns the fault of the name .", "./a", 'the path "./a" has the name "."'),
        (
            "returns the fault of the name ..",
            "a/..",
            'the path "a/.." has the name ".."',
        ),
        (
            "returns the fault of a name with a backslash",
            "a\\b",
            'the path "a\\\\b" has the name "a\\\\b"',
        ),
        (
            "returns the fault of a name with NUL",
            "a\0b",
            'the path "a\\u0000b" has the name "a\\u0000b"',
        ),
        (
            "returns the fault of a path that is not UTF-8 text",
            "\ud800",
            'the path "\\ud800" is not UTF-8 text',
        ),
        ("returns the fault of a path that is not a str", 3, "the path 3 is not a str"),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_fault_of_the_path(
        self, seat: Collector, give: object, want: str | None
    ) -> None:
        """Each rule has its fault."""
        check.equal(seat, path_fault(give), want, "path_fault returns the reason")


class TestCheck:
    """check raises a fault for a tree that breaks a rule."""

    def test_passes_a_tree_that_keeps_the_rules(self, seat: Collector) -> None:
        """A file, a directory and a link to a path outside the tree keep the rules."""
        tree = {"a/b.txt": text("b"), "c": directory(), "d": link("../outside")}
        check.does_not_raise(seat, lambda: check_tree(tree), "check accepts the tree")

    tests: ClassVar[list[tuple[str, object, str]]] = [
        (
            "raises the fault of a path that breaks a rule of a path",
            {"a//b": text("a")},
            'a//b: the path "a//b" has the name ""',
        ),
        (
            "raises the fault of an empty entry",
            {"a": Entry()},
            "a: the entry is not a file, a directory or a link",
        ),
        (
            "raises the fault of a value that is not an entry",
            {"a": "text"},
            "a: the entry is not a file, a directory or a link",
        ),
        (
            "raises the fault of a link without a target",
            {"a": link("")},
            "a: the link does not have a target of UTF-8 text without NUL: ''",
        ),
        (
            "raises the fault of a link whose target contains NUL",
            {"a": link("b\0")},
            "a: the link does not have a target of UTF-8 text without NUL: 'b\\x00'",
        ),
        (
            "raises the fault of a link whose target is not UTF-8 text",
            {"a": link("\ud800")},
            "a: the link does not have a target of UTF-8 text without NUL: '\\ud800'",
        ),
        (
            "raises the fault of a link whose target is not a str",
            {"a": Entry(link=cast("Any", 3))},
            "a: the link does not have a target of UTF-8 text without NUL: 3",
        ),
        (
            "raises the fault of an entry below a file",
            {"a": text("a"), "a/b": text("b")},
            'a/b: the entry is below the file "a"',
        ),
        (
            "raises the fault of an entry below a link",
            {"a": link("x"), "a/b/c": text("c")},
            'a/b/c: the entry is below the link "a"',
        ),
        (
            "raises the fault of the first path in path order",
            {"b": Entry(), "a": Entry()},
            "a: the entry is not a file, a directory or a link",
        ),
        (
            "raises the fault of a key that is not a str",
            {"b": Entry(), 1: text("a")},
            "the path 1 is not a str",
        ),
        (
            "raises the fault of a tree that is not a mapping",
            [("a", text("a"))],
            "the tree is not a mapping of paths to entries",
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_the_fault_of_a_tree_that_breaks_a_rule(
        self, seat: Collector, give: object, want: str
    ) -> None:
        """The fault has the path and the reason."""
        error = check.raises(seat, lambda: check_tree(give), "check refuses the tree")
        check.error_as(seat, error, FaultError, "the error is a FaultError")
        check.equal(seat, str(error), want, "the fault has the path and the reason")


class TestFull:
    """full adds the parent directories of the entries of a tree."""

    def test_adds_each_directory_that_a_path_implies(self, seat: Collector) -> None:
        """The parents are directories without a mode."""
        check.equal(
            seat,
            full({"a/b/c.txt": text("c")}),
            {"a/b/c.txt": text("c"), "a": directory(), "a/b": directory()},
            "full adds a and a/b",
        )

    def test_keeps_a_directory_that_the_tree_has(self, seat: Collector) -> None:
        """A directory of the tree keeps its mode."""
        given = directory().with_mode(0o700)
        whole = full({"a": given, "a/b.txt": text("b")})
        check.is_true(seat, whole["a"] is given, "full keeps the directory of the tree")
