# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of conformance/files.py tests the runners of the files vectors.

The vectors of the definition test every runner. This spec covers the rules
that the vectors do not test. The refusal of a vector with wrong inputs or
outputs is one of them. A runner computes the verdict of every files vector,
so the spec checks its own verdicts with the assert statement of pytest.
"""

from __future__ import annotations

import errno
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.files import CONTRACT, RUNNERS
from helpers import UNENFORCED, os_fault

if TYPE_CHECKING:
    import pathlib

#: The tree without entries.
NO_FILES: dict[str, Any] = {"type": "tree", "entries": []}

#: The tree of the file a.txt with the text a.
A_FILE: dict[str, Any] = {"type": "tree", "entries": [{"path": "a.txt", "text": "a"}]}

#: The tree of the file a.txt that its owner can read and cannot write.
READ_ONLY_FILE: dict[str, Any] = {
    "type": "tree",
    "entries": [{"path": "a.txt", "text": "a", "mode": 0o400}],
}

#: A typed literal of a type other than tree.
LIST: dict[str, Any] = {"type": "list"}

#: The int literal of 1.
ONE: dict[str, Any] = {"type": "int", "value": 1}


def string(value: str) -> dict[str, Any]:
    """Return the string literal of value."""
    return {"type": "string", "value": value}


def fault_of(kind: str, raw: dict[str, Any], directory: pathlib.Path) -> str:
    """Return the text of the fault of the run of raw as a vector of kind in dir.

    Returns:
        The text, or the empty string for a run without a fault.
    """
    try:
        RUNNERS[kind](raw, str(directory))
    except FaultError as error:
        return str(error)
    return ""


def golden(args: list[Any], tree: object, after: object = None) -> dict[str, Any]:
    """Return a golden-match-tree vector of the workspace A_FILE that expects a pass."""
    return {
        "workspace": A_FILE,
        "args": args,
        "golden": tree,
        "expect": "pass",
        "after": after,
    }


def golden_args(update: bool) -> list[Any]:
    """Return the arguments of a golden-match-tree vector of the name api."""
    return [string("api"), {"type": "bool", "value": update}]


class TestContract:
    """CONTRACT is the contract of the call of a files vector."""

    def test_is_the_contract_of_the_call_of_a_files_vector(self) -> None:
        """Every runner passes it to its call."""
        assert CONTRACT == "the files match the vector"


class TestRunners:
    """RUNNERS has the runner of each kind of files vector."""

    def test_contains_a_runner_of_each_assertion_that_reads_files(self) -> None:
        """Each kind is the canonical id of its assertion."""
        assert sorted(RUNNERS) == [
            "golden-match-tree",
            "has-content",
            "has-mode",
            "is-dir",
            "is-file",
            "links-to",
            "path-absent",
            "tree-contains",
            "tree-equal",
            "tree-unchanged",
        ]

    tests: ClassVar[list[tuple[str, str, dict[str, Any], str]]] = [
        (
            "raises the fault of a workspace that is not a tree literal",
            "path-absent",
            {"workspace": LIST, "args": [string("a.txt")], "expect": "pass"},
            'workspace.type: the type "list" is not tree',
        ),
        (
            "raises the fault of a vector without a workspace",
            "path-absent",
            {"args": [string("a.txt")], "expect": "pass"},
            "workspace: the literal is not an object",
        ),
        (
            "raises the fault of a tree-equal vector with two trees",
            "tree-equal",
            {"workspace": A_FILE, "args": [A_FILE, A_FILE], "expect": "pass"},
            "args: the number of arguments is 2, want 1",
        ),
        (
            "raises the fault of a tree-contains argument that is not a tree literal",
            "tree-contains",
            {"workspace": A_FILE, "args": [LIST], "expect": "pass"},
            'args[0].type: the type "list" is not tree',
        ),
        (
            "raises the fault of a tree-unchanged vector without a subject",
            "tree-unchanged",
            {"workspace": A_FILE, "expect": "pass"},
            "subject.kind: null is not a subject of files",
        ),
        (
            "raises the fault of a tree-unchanged vector of an unknown subject",
            "tree-unchanged",
            {"workspace": A_FILE, "subject": {"kind": "widget"}, "expect": "pass"},
            'subject.kind: "widget" is not a subject of files',
        ),
        (
            "raises the fault of a tree-unchanged subject that does not read files",
            "tree-unchanged",
            {"workspace": A_FILE, "subject": {"kind": "returns-ok"}, "expect": "pass"},
            'subject.kind: "returns-ok" is not a subject of files',
        ),
        (
            "raises the fault of a golden-match-tree vector with only the name",
            "golden-match-tree",
            golden([string("api")], None),
            "args: the number of arguments is 1, want 2",
        ),
        (
            "raises the fault of a golden-match-tree name that is not a string",
            "golden-match-tree",
            golden([ONE, ONE], None),
            "args[0]: the argument is not a string",
        ),
        (
            "raises the fault of a golden-match-tree update that is not a bool",
            "golden-match-tree",
            golden([string("api"), ONE], None),
            "args[1]: the argument is not a bool",
        ),
        (
            "raises the fault of a golden vector outside the working directory",
            "golden-match-tree",
            golden(golden_args(False), None),
            (
                "golden.match_tree resolves a name in the working directory, and the "
                "directory of the vector is not the working directory"
            ),
        ),
        (
            "raises the fault of an is-file argument that is not a typed literal",
            "is-file",
            {"workspace": A_FILE, "args": [{"type": "widget"}], "expect": "pass"},
            "args[0]: unknown literal type: widget",
        ),
        (
            "raises the fault of an is-file argument of a tree literal without entries",
            "is-file",
            {
                "workspace": A_FILE,
                "args": [{"type": "tree", "entries": 1}],
                "expect": "pass",
            },
            "args[0].entries: the literal does not have a list of entries",
        ),
        (
            "raises the fault of a path-absent vector without arguments",
            "path-absent",
            {"workspace": A_FILE, "expect": "pass"},
            "args: the number of arguments is 0, want 1",
        ),
        (
            "raises the fault of a path-absent vector whose arguments are not a list",
            "path-absent",
            {"workspace": A_FILE, "args": ONE, "expect": "pass"},
            "args: the number of arguments is 0, want 1",
        ),
        (
            "raises the fault of an is-dir path that is not a string",
            "is-dir",
            {"workspace": A_FILE, "args": [ONE], "expect": "pass"},
            "args[0]: the argument is not a string",
        ),
        (
            "raises the fault of a links-to target that is not a string",
            "links-to",
            {"workspace": A_FILE, "args": [string("a.txt"), ONE], "expect": "pass"},
            "args[1]: the argument is not a string",
        ),
        (
            "raises the fault of a has-content content that is not text or bytes",
            "has-content",
            {"workspace": A_FILE, "args": [string("a.txt"), ONE], "expect": "pass"},
            "args[1]: the argument is not text or bytes",
        ),
        (
            "raises the fault of a has-mode mode that is not an integer",
            "has-mode",
            {
                "workspace": A_FILE,
                "args": [string("a.txt"), string("rw")],
                "expect": "pass",
            },
            "args[1]: the argument is not an int",
        ),
        (
            "raises the fault of a has-mode mode that is a bool",
            "has-mode",
            {
                "workspace": A_FILE,
                "args": [string("a.txt"), {"type": "bool", "value": True}],
                "expect": "pass",
            },
            "args[1]: the argument is not an int",
        ),
        (
            "raises the fault of a vector that expects neither a pass nor a failure",
            "path-absent",
            {"workspace": A_FILE, "args": [string("b.txt")], "expect": "maybe"},
            'expect: the vector expects "maybe", neither pass nor fail',
        ),
        (
            "raises the fault of a check that ends with a different verdict",
            "path-absent",
            {"workspace": A_FILE, "args": [string("a.txt")], "expect": "pass"},
            "expect: the check ends as fail, want pass",
        ),
        (
            "raises the fault of a check that ends with a fault",
            "has-mode",
            {
                "workspace": A_FILE,
                "args": [string("a.txt"), {"type": "int", "value": 0o10000}],
                "expect": "pass",
            },
            (
                "expect: the check ends as error (files.has_mode: the mode 0o10000 is "
                "not an integer from 0 to 0o777), want pass"
            ),
        ),
        (
            "raises the fault of a record with different fields",
            "path-absent",
            {
                "workspace": A_FILE,
                "args": [string("a.txt")],
                "expect": "fail",
                "detail": {"got": string("file"), "kind": string("file")},
            },
            'detail: the record has the fields ["got"], want ["got", "kind"]',
        ),
        (
            "raises the fault of a field of a different value",
            "path-absent",
            {
                "workspace": A_FILE,
                "args": [string("a.txt")],
                "expect": "fail",
                "detail": {"got": string("directory")},
            },
            (
                'detail.got: the field is {"type": "string", "value": "file"}, '
                'want {"type": "string", "value": "directory"}'
            ),
        ),
    ]

    @pytest.mark.parametrize(
        ("give_kind", "give", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_raises_the_fault_of_the_vector(
        self, tmp_path: pathlib.Path, give_kind: str, give: dict[str, Any], want: str
    ) -> None:
        """The fault is at the part of the vector that the run contradicts."""
        assert fault_of(give_kind, give, tmp_path) == want

    def test_raises_the_fault_of_a_workspace_that_cannot_be_written(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The directory of the workspace exists already."""
        (tmp_path / "workspace").mkdir()
        raw = {"workspace": A_FILE, "args": [string("a")], "expect": "pass"}
        fault = os_fault(lambda: RUNNERS["path-absent"](raw, str(tmp_path)))
        want = ("workspace.workspace: the entry cannot be written", errno.EEXIST)
        assert fault == want

    @pytest.mark.skipif(UNENFORCED, reason="every permission is granted here")
    def test_raises_the_fault_of_a_tree_unchanged_subject_that_fails(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The subject cannot write a file that its owner cannot write."""
        raw = {
            "workspace": READ_ONLY_FILE,
            "subject": {"kind": "rewrites-files"},
            "expect": "pass",
        }
        fault = os_fault(lambda: RUNNERS["tree-unchanged"](raw, str(tmp_path)))
        assert fault == ("subject: the subject fails", errno.EACCES)

    def test_raises_the_fault_of_a_golden_tree_that_is_not_a_tree_literal(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The golden tree of the vector is a list."""
        monkeypatch.chdir(tmp_path)
        raw = golden(golden_args(False), LIST)
        want = 'golden.type: the type "list" is not tree'
        assert fault_of("golden-match-tree", raw, tmp_path) == want

    def test_raises_the_fault_of_a_golden_tree_that_cannot_be_written(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The path testdata has a file."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "testdata").write_text("a file")
        raw = golden(golden_args(False), A_FILE)
        fault = os_fault(lambda: RUNNERS["golden-match-tree"](raw, str(tmp_path)))
        assert fault == ("golden.testdata: the entry cannot be written", errno.EEXIST)

    def test_raises_the_fault_of_a_golden_tree_that_differs_after_the_update(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The update writes the workspace, and the vector does not have an entry."""
        monkeypatch.chdir(tmp_path)
        raw = golden(golden_args(True), None, NO_FILES)
        assert fault_of("golden-match-tree", raw, tmp_path) == (
            'after: the golden tree is {"type": "tree", "entries": '
            '[{"path": "a.txt", "text": "a"}]}, want {"type": "tree", "entries": []}'
        )

    def test_raises_the_fault_of_a_golden_tree_that_cannot_be_read_after_the_call(
        self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A comparison without update does not write a golden tree."""
        monkeypatch.chdir(tmp_path)
        raw = golden(golden_args(False), None, NO_FILES)
        fault = os_fault(lambda: RUNNERS["golden-match-tree"](raw, str(tmp_path)))
        assert fault == (
            "after: the golden tree cannot be read: the tree cannot be read",
            errno.ENOENT,
        )
