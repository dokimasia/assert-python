# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The reader of the vendored definition that this library implements.

The files are vendored, so a build is reproducible and a test run does not
need the network. make spec-sync refreshes them.
"""

from __future__ import annotations

import json
from importlib import resources
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from importlib.resources.abc import Traversable

__all__ = [
    "LANGUAGE",
    "assertions",
    "declines_relaxation",
    "declines_surface",
    "detail_fields",
    "diverges",
    "names",
    "overlay",
    "relaxation_names",
    "spec_dir",
    "surface_names",
    "version",
]

#: The column of this language in the naming table.
LANGUAGE = "python"


def spec_dir() -> Traversable:
    """Return the directory of the vendored definition.

    The directory is the package dokimi_assert.conformance. Each file of the
    definition is at its path in assert-spec, such as spec/assertions.json.

    Returns:
        The directory as a traversable of importlib.resources.
    """
    return resources.files("dokimi_assert.conformance")


def _read(name: str) -> Any:
    """Return the JSON of one file in the directory spec of the definition."""
    return json.loads((spec_dir() / "spec" / name).read_text(encoding="utf-8"))


def assertions() -> dict[str, Any]:
    """Return the assertion table of the definition.

    Returns:
        Every assertion of the definition, by canonical id.
    """
    return dict(_read("assertions.json")["assertions"])


def names() -> dict[str, str]:
    """Return the Python name of each assertion of the naming table.

    Returns:
        The canonical id of each assertion that has a Python name, with that
        name.
    """
    table = _read("naming.json")["names"]
    return {aid: row[LANGUAGE] for aid, row in table.items() if LANGUAGE in row}


def version() -> str:
    """Return the version of the vendored definition.

    Returns:
        The content of the file VERSION.
    """
    return (spec_dir() / "VERSION").read_text(encoding="utf-8").strip()


def overlay() -> dict[str, Any]:
    """Return the overlay of this language.

    The overlay lists each assertion that this language does not supply, and
    the reason for each.

    Returns:
        The vendored overlay.
    """
    overlay_file = spec_dir() / "overlays" / f"{LANGUAGE}.json"
    return dict(json.loads(overlay_file.read_text(encoding="utf-8")))


def relaxation_names() -> dict[str, str]:
    """Return the Python name of each relaxation of the definition.

    Returns:
        The id of each relaxation with its Python name. The name is the empty
        string when the naming table does not give a Python name.
    """
    declared = _read("assertions.json").get("relaxations", {})
    named = _read("naming.json").get("relaxations", {})
    return {rid: named.get(rid, {}).get(LANGUAGE, "") for rid in declared}


def detail_fields() -> dict[str, list[str]]:
    """Return the detail fields that each assertion declares.

    Returns:
        The canonical id of each assertion, with the fields of its failure
        record.
    """
    table = _read("assertions.json")["assertions"]
    return {aid: list(body.get("detail_fields") or []) for aid, body in table.items()}


def surface_names() -> dict[str, str]:
    """Return the Python name of each surface id of the naming table.

    Returns:
        The id of each type, member and helper with its Python name. The name
        is the empty string when the table does not give a Python name.
    """
    table = _read("naming.json").get("surface", {})
    out: dict[str, str] = {}
    for section in ("types", "members", "helpers"):
        for sid, row in table.get(section, {}).items():
            out[sid] = row.get(LANGUAGE, "")
    return out


def _lists(section: str, ident: str) -> bool:
    """Report whether a list section of the overlay has an entry of ident."""
    return any(entry.get("id") == ident for entry in overlay().get(section, []))


def declines_surface(surface_id: str) -> bool:
    """Report whether the overlay declines a surface id.

    Args:
        surface_id: The id in the surface table.

    Returns:
        True when the overlay lists the id as one that the library does not
        offer.
    """
    return _lists("surface", surface_id)


def declines_relaxation(relaxation: str) -> bool:
    """Report whether the overlay declines a relaxation.

    Args:
        relaxation: The canonical id of the relaxation.

    Returns:
        True when the overlay lists the relaxation as one that the library
        does not offer.
    """
    return _lists("relaxations", relaxation)


def diverges(assertion: str) -> bool:
    """Report whether the overlay lists a divergence from an assertion.

    Args:
        assertion: The canonical id of the assertion.

    Returns:
        True when the overlay lists a divergence for the assertion.
    """
    return _lists("diverge", assertion)
