# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The vectors of the vendored definition, and the run of one against this library.

A vector is a case of a family outside the corpus of the assertions. It has
inputs and outputs of its own. This library runs the vectors of each family
in FAMILIES: the assertions that read files, the history and its checks, the
property engine, and machines.
"""

from __future__ import annotations

import functools
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.definition import LANGUAGE, spec_dir
from dokimi_assert.conformance.files import RUNNERS as FILES
from dokimi_assert.conformance.files import Runner
from dokimi_assert.conformance.history.vectors import RUNNERS as HISTORY
from dokimi_assert.conformance.prop.vectors import KINDS, check_prop
from dokimi_assert.conformance.stateful.vectors import RUNNERS as STATEFUL

__all__ = ["FAMILIES", "RUNNERS", "Vector", "check_vector", "skip_of", "vectors"]

#: The directories of the corpus with the vectors that this library runs.
FAMILIES = ("files", "history", "prop", "stateful")

#: The runner of each kind of vector of every family, by the kind.
RUNNERS: dict[str, Runner] = {
    **FILES,
    **HISTORY,
    **{kind: functools.partial(check_prop, kind) for kind in KINDS},
    **STATEFUL,
}


@dataclass(frozen=True, slots=True)
class Vector:
    """One case of a vector file.

    Attributes:
        kind: The kind of the vector, such as tree-equal.
        id: The id of the vector.
        raw: The JSON object of the case in the vector file.
    """

    kind: str
    id: str
    raw: Mapping[str, Any]


def vectors() -> list[Vector]:
    """Return every vector of the families that this library runs.

    Returns:
        The vectors in order. The files of each family are in the order of
        their names, and the cases of each file are in file order.
    """
    found: list[Vector] = []
    for family in FAMILIES:
        directory = spec_dir() / "corpus" / family
        for entry in sorted(directory.iterdir(), key=lambda p: p.name):
            document = json.loads(entry.read_text(encoding="utf-8"))
            found.extend(
                Vector(document["kind"], raw["id"], raw) for raw in document["cases"]
            )
    return found


def skip_of(vector: Vector) -> str | None:
    """Return the reason that the definition gives this language to skip a vector.

    Args:
        vector: The vector.

    Returns:
        The reason, or None for a vector that this language runs.
    """
    skip: object = vector.raw.get("skip")
    skips: Mapping[str, Any] = (
        cast("Mapping[str, Any]", skip) if isinstance(skip, dict) else {}
    )
    reason = skips.get(LANGUAGE)
    return reason if isinstance(reason, str) else None


def check_vector(vector: Vector, directory: str) -> str | None:
    """Run vector against this library in the empty directory dir.

    A vector of golden-match-tree writes its golden tree below dir. dir is
    then the working directory, because golden.match_tree resolves a name in
    the working directory. A behaviour vector and a recording vector write
    their stored cases into dir.

    Args:
        vector: The vector.
        directory: The directory.

    Returns:
        The difference between the run and the vector, or None when the two
        agree. The difference has the path from the id of the vector to the
        part at fault, and a reason.
    """
    run = RUNNERS.get(vector.kind)
    if run is None:
        return f"{vector.id}: {json.dumps(vector.kind)} is not a kind of vector"
    try:
        run(vector.raw, directory)
    except FaultError as error:
        return str(error.within(vector.id))
    return None
