"""Reading the definition this library is held to."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

#: This language's column in the naming table.
LANGUAGE = "python"


def _read(name: str) -> Any:
    """Read one file from the vendored definition."""
    spec = resources.files("dokimi_assert.conformance") / "spec"
    return json.loads((spec / name).read_text())


def assertions() -> dict[str, Any]:
    """Return the assertion table: what the standard states must exist.

    Returns:
        The assertion table: what the standard states must exist.
    """
    return dict(_read("assertions.json")["assertions"])


def names() -> dict[str, str]:
    """Return each assertion mapped to the name this language uses.

    Returns:
        Each assertion mapped to the name this language uses.
    """
    table = _read("naming.json")["names"]
    return {
        assertion: entry[LANGUAGE]
        for assertion, entry in table.items()
        if LANGUAGE in entry
    }


def version() -> str:
    """Return the definition version this library implements.

    Returns:
        The definition version this library implements.
    """
    spec = resources.files("dokimi_assert.conformance") / "spec"
    return (spec / "VERSION").read_text().strip()


def overlay() -> dict[str, Any]:
    """Return this language's declared divergences from the standard.

    Every assertion the standard states is required. A library that
    cannot supply one says so here, with the reason, so a gap nobody
    could close and a gap nobody got to are told apart. An empty
    diverge is a claim of full compliance, not an absence of one.

    Returns:
        This language's declared divergences from the standard.
    """
    return dict(_read("overlay.json"))


def relaxation_names() -> dict[str, str]:
    """Each relaxation the definition states, with this language's name.

    A relaxation the naming table gives Python no name for maps to the
    empty string, which is what an overlay declining it looks like.

    Returns:
        Relaxation id to the name a caller types.
    """
    stated = _read("assertions.json").get("relaxations", {})
    named = _read("naming.json").get("relaxations", {})
    return {rid: named.get(rid, {}).get("python", "") for rid in stated}


def detail_fields() -> dict[str, set[str]]:
    """What each assertion's failure carries, by canonical id.

    Returns:
        Assertion id to the field names its record holds.
    """
    stated = _read("assertions.json")["assertions"]
    return {aid: set(body.get("detail_fields") or []) for aid, body in stated.items()}


def surface_names() -> dict[str, str]:
    """Every surface id, with this language's name for it.

    An id the table gives Python no name for maps to the empty string,
    which is what an overlay declining it looks like.

    Returns:
        Surface id to the name a caller types, across the types,
        members and helpers sections.
    """
    table = _read("naming.json").get("surface", {})
    out: dict[str, str] = {}
    for section in ("types", "members", "helpers"):
        for sid, per_language in table.get(section, {}).items():
            out[sid] = per_language.get("python", "")
    return out


def declines_surface(surface_id: str) -> bool:
    """Whether the overlay declines this surface id.

    Args:
        surface_id: The id, as the surface table states it.

    Returns:
        True when the overlay declares it not offered.
    """
    entries = overlay().get("surface", [])
    return any(entry.get("id") == surface_id for entry in entries)


def declines_relaxation(relaxation: str) -> bool:
    """Whether the overlay declines this relaxation.

    Args:
        relaxation: The canonical relaxation id.

    Returns:
        True when the overlay declares it not offered.
    """
    entries = overlay().get("relaxations", [])
    return any(entry.get("id") == relaxation for entry in entries)


def diverges(assertion: str) -> bool:
    """Whether the overlay excuses assertion from being implemented.

    Args:
        assertion: The canonical id of the assertion.

    Returns:
        Whether the overlay excuses the assertion from being implemented.
    """
    return any(entry.get("id") == assertion for entry in overlay()["diverge"])
