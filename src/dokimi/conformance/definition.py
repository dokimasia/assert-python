"""Reading the definition this library is held to."""

from __future__ import annotations

import json
from importlib import resources
from typing import Any

#: This language's column in the naming table.
LANGUAGE = "python"


def _read(name: str) -> Any:
    """Read one file from the vendored definition."""
    spec = resources.files("dokimi.conformance") / "spec"
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
    spec = resources.files("dokimi.conformance") / "spec"
    return (spec / "VERSION").read_text().strip()
