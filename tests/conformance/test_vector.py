# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of conformance/vector.py tests the vectors and their runner.

The spec runs each vector of this library in a new directory. It checks its
verdicts with the assert statement of pytest, because check_vector computes
the verdict of every vector.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert.conformance.vector import (
    FAMILIES,
    RUNNERS,
    Vector,
    check_vector,
    skip_of,
    vectors,
)
from helpers import WINDOWS

if TYPE_CHECKING:
    import pathlib

VECTORS = vectors()

#: The kinds of the files vectors. Each assertion that reads files has a kind.
FILE_KINDS = [
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

#: The kinds of the history vectors.
HISTORY_KINDS = ["linearizable", "seam", "serializable", "snapshot-isolation"]

#: The kinds of the property vectors.
PROP_KINDS = [
    "behaviour",
    "bridge",
    "coverage",
    "decoding",
    "draws",
    "fixtures",
    "forms",
    "generation",
    "inverse",
    "recording",
    "shapes",
    "shrinking",
    "store",
    "token",
]

#: The kinds of the machines vectors.
STATEFUL_KINDS = ["machines"]

#: The member of a vector that has a mode or an executable flag.
_MODES = re.compile(r'"(?:mode|executable)":')


def skipped(v: Vector) -> str | None:
    """Return the reason that this platform skips v, or None when it runs v.

    A platform whose file system does not record permission bits skips each
    vector of has-mode and each vector with a mode or an executable flag. The
    definition allows these skips.
    """
    modes = v.kind == "has-mode" or _MODES.search(json.dumps(v.raw)) is not None
    if WINDOWS and modes:
        return "Windows does not record permission bits"
    return skip_of(v)


def run_of(v: Vector) -> Any:
    """Return the parameter of the case of v.

    Its id starts with the kind of v. The parameter has a skip mark where
    this platform skips v.
    """
    reason = skipped(v)
    marks = [] if reason is None else [pytest.mark.skip(reason=reason)]
    ident = v.id if v.id.startswith(f"{v.kind}/") else f"{v.kind}/{v.id}"
    return pytest.param(v, id=ident, marks=marks)


def count_of(kinds: list[str]) -> int:
    """Return the number of vectors of the kinds."""
    return len([v for v in VECTORS if v.kind in kinds])


class TestFamilies:
    """FAMILIES has the directories of the corpus that this library runs."""

    def test_contains_every_family_of_vectors(self) -> None:
        """The families are files, history, prop and stateful."""
        assert FAMILIES == ("files", "history", "prop", "stateful")


class TestRunners:
    """RUNNERS has the runner of each kind of vector of every family."""

    def test_contains_a_runner_of_each_kind(self) -> None:
        """The kinds are the kinds of the vector files."""
        kinds = FILE_KINDS + HISTORY_KINDS + PROP_KINDS + STATEFUL_KINDS
        assert sorted(RUNNERS) == sorted(kinds)


class TestVectors:
    """vectors returns every vector of the families."""

    def test_returns_the_vectors_of_every_kind(self) -> None:
        """Each vector file has its kind."""
        kinds = FILE_KINDS + HISTORY_KINDS + PROP_KINDS + STATEFUL_KINDS
        assert sorted({v.kind for v in VECTORS}) == sorted(kinds)

    counts: ClassVar[list[tuple[str, list[str], int]]] = [
        ("returns the 57 files vectors of the definition", FILE_KINDS, 57),
        ("returns the 80 history vectors of the definition", HISTORY_KINDS, 80),
        ("returns the 437 property vectors of the definition", PROP_KINDS, 437),
        ("returns the 14 machines vectors of the definition", STATEFUL_KINDS, 14),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in counts], ids=[t[0] for t in counts]
    )
    def test_returns_the_vectors_of_a_family(self, give: list[str], want: int) -> None:
        """The count is the count of the definition."""
        assert count_of(give) == want

    def test_returns_files_vectors_whose_ids_start_with_their_kinds(self) -> None:
        """An id of a files vector starts with the kind and a slash."""
        named = [v for v in VECTORS if v.kind in FILE_KINDS]
        assert [v.id for v in named if not v.id.startswith(f"{v.kind}/")] == []

    def test_returns_forms_vectors_whose_ids_start_with_their_forms(self) -> None:
        """An id of a forms vector starts with the form and a slash."""
        forms = [v for v in VECTORS if v.kind == "forms"]
        assert [v.id for v in forms if not v.id.startswith(f"{v.raw['form']}/")] == []


class TestSkipOf:
    """skip_of returns the reason for which this language skips a vector."""

    tests: ClassVar[list[tuple[str, dict[str, Any], str | None]]] = [
        (
            "returns the reason of the vector for python",
            {"skip": {"python": "no links here"}},
            "no links here",
        ),
        (
            "returns none for a vector that another language skips",
            {"skip": {"go": "no links here"}},
            None,
        ),
        ("returns none for a vector without a skip", {}, None),
        ("returns none for a skip that is not an object", {"skip": "python"}, None),
        (
            "returns none for a reason that is not a string",
            {"skip": {"python": True}},
            None,
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_reason_of_the_vector(
        self, give: dict[str, Any], want: str | None
    ) -> None:
        """The reason is a string of the member python of skip."""
        assert skip_of(Vector("is-file", "is-file/x", give)) == want

    def test_returns_the_reason_of_the_definition_for_a_shape_at_nanoseconds(
        self,
    ) -> None:
        """The definition skips one shapes vector for Python."""
        assert [v.id for v in VECTORS if skip_of(v) is not None] == [
            "zoned-date-time/nanoseconds"
        ]


class TestCheckVector:
    """check_vector runs one vector against this library."""

    def test_returns_the_fault_of_a_vector_of_an_unknown_kind(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The kind does not have a runner."""
        v = Vector("widget", "widget/x", {})
        assert (
            check_vector(v, str(tmp_path))
            == 'widget/x: "widget" is not a kind of vector'
        )

    def test_returns_the_fault_at_the_part_of_a_vector_that_the_run_contradicts(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The fault starts with the id of the vector."""
        first = next(v for v in VECTORS if v.kind == "path-absent")
        v = Vector(first.kind, first.id, {**first.raw, "expect": "fail"})
        want = f"{v.id}.expect: the check ends as pass, want fail"
        assert check_vector(v, str(tmp_path)) == want

    def test_returns_the_fault_of_a_property_vector_at_its_output(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A token vector of another token differs at the token."""
        first = next(v for v in VECTORS if v.kind == "token" and "choices" in v.raw)
        v = Vector(first.kind, first.id, {**first.raw, "token": "prop1:AAc"})
        assert (check_vector(v, str(tmp_path)) or "").startswith(
            f"{v.id}.token: the library computes"
        )

    @pytest.mark.parametrize("vector", [run_of(v) for v in VECTORS])
    def test_returns_none_for_the_vector(
        self,
        vector: Vector,
        tmp_path: pathlib.Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The run agrees with the vector."""
        if vector.kind == "golden-match-tree":
            monkeypatch.chdir(tmp_path)
        assert check_vector(vector, str(tmp_path)) is None
