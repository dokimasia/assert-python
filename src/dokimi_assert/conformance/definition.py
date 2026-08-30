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
    """Return the assertion table: what the standard states must exist."""
    return dict(_read("assertions.json")["assertions"])


def names() -> dict[str, str]:
    """Return each assertion mapped to the name this language uses."""
    table = _read("naming.json")["names"]
    return {
        assertion: entry[LANGUAGE]
        for assertion, entry in table.items()
        if LANGUAGE in entry
    }


def version() -> str:
    """Return the definition version this library implements."""
    spec = resources.files("dokimi_assert.conformance") / "spec"
    return (spec / "VERSION").read_text().strip()


def overlay() -> dict[str, Any]:
    """Return this language's declared divergences from the standard.

    Every assertion the standard states is required. A library that
    cannot supply one says so here, with the reason, so a gap nobody
    could close and a gap nobody got to are told apart. An empty
    ``diverge`` is a claim of full compliance, not an absence of one.
    """
    return dict(_read("overlay.json"))


def diverges(assertion: str) -> bool:
    """Whether the overlay excuses assertion from being implemented."""
    return any(entry.get("id") == assertion for entry in overlay()["diverge"])
