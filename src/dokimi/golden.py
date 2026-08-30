"""Comparison against a file recording what output should be.

Use it where the expected value is too large to write in the test and
too structured to summarise: a rendered template, a serialised
document, a generator's output. The file is the assertion.

Every assertion here stops the test. A test that carried on past a
golden mismatch would report failures about data it already knows is
wrong.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from dokimi import check
from dokimi._matcher.seat import Seat

__all__ = [
    "Scrubber",
    "match",
    "match_at",
    "match_json_field",
    "scrub_hashes",
    "scrub_json_fields",
    "scrub_run_ids",
    "scrub_timestamps",
    "should_update",
]

#: Where match looks, relative to the test's working directory.
CONVENTIONAL_DIR = Path("testdata") / "golden"

#: The environment variable that lets a run rewrite its golden files.
#: pytest has no -update flag to hang this on, so it is named here.
UPDATE_ENV = "DOKIMI_UPDATE_GOLDEN"

#: How a golden JSON file is written, so a diff reads line by line.
JSON_INDENT = 2

Scrubber = Callable[[str], str]

_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:?\d{2})?"
)
_HASH = re.compile(r"\b[0-9a-fA-F]{32,128}\b")
_RUN_ID = re.compile(r"\brun_[0-9a-z]{16}\b")


def should_update() -> bool:
    """Whether this run may rewrite its golden files.

    Set ``DOKIMI_UPDATE_GOLDEN=1`` to enable it. Read the diff first: a
    golden file updated without reading it records whatever the code
    now does, which is the opposite of an assertion.
    """
    return os.environ.get(UPDATE_ENV, "") not in ("", "0")


def scrub_timestamps() -> Scrubber:
    """Replace ISO-8601 and RFC-3339 timestamps."""
    return lambda text: _TIMESTAMP.sub("SCRUBBED_TIMESTAMP", text)


def scrub_hashes() -> Scrubber:
    """Replace hex digests between 32 and 128 characters."""
    return lambda text: _HASH.sub("SCRUBBED_HASH", text)


def scrub_run_ids() -> Scrubber:
    """Replace identifiers of the form run_ and sixteen characters."""
    return lambda text: _RUN_ID.sub("SCRUBBED_RUN_ID", text)


def scrub_json_fields(*fields: str) -> Scrubber:
    """Replace the value of each named JSON field.

    Matches the field's text rather than parsing, so it works on output
    that is nearly JSON as well as output that is.
    """
    if not fields:
        return lambda text: text

    pattern = re.compile(
        r'("(?:' + "|".join(re.escape(f) for f in fields) + r')"\s*:\s*)"[^"]*"'
    )
    return lambda text: pattern.sub(r'\1"SCRUBBED"', text)


def _scrub(text: str, scrubbers: Sequence[Scrubber]) -> str:
    """Apply every scrubber in order."""
    for scrubber in scrubbers:
        text = scrubber(text)
    return text


def match(seat: Seat, name: str, got: str, update: bool, *scrubbers: Scrubber) -> None:
    """Compare got against testdata/golden/name.

    The file is the assertion. When it does not exist and update is
    false, that is a failure naming what would create it.
    """
    seat.helper()
    match_at(seat, CONVENTIONAL_DIR / name, got, update, *scrubbers)


def match_at(
    seat: Seat, path: str | Path, got: str, update: bool, *scrubbers: Scrubber
) -> None:
    """Compare got against the golden file at path, taken as given."""
    seat.helper()

    target = Path(path)
    mine = _scrub(got, scrubbers)

    if not target.exists():
        if update:
            _write(seat, target, mine)
            return
        seat.fail(
            f"{target}: the golden file does not exist; set {UPDATE_ENV}=1 to create it"
        )
        return

    theirs = _scrub(target.read_text(), scrubbers)
    if update:
        if mine != theirs:
            _write(seat, target, mine)
        return

    check.equal(
        seat,
        mine,
        theirs,
        f"{target}: output matches the golden file; "
        f"read the diff before setting {UPDATE_ENV}=1",
    )


def match_json_field(
    seat: Seat,
    path: str | Path,
    field: str,
    got: str,
    update: bool,
    *scrubbers: Scrubber,
) -> None:
    """Compare got against one named field of the JSON object at path.

    Use it where one golden file holds several independent values, one
    per field, so a failure shows that value's diff rather than the
    whole file's and two tests updating different fields do not
    overwrite each other.
    """
    seat.helper()

    target = Path(path)
    try:
        value = json.loads(got)
    except json.JSONDecodeError as err:
        seat.fail(f"{target}: the value given for field {field!r} is not JSON: {err}")
        return

    document = _read_object(seat, target, update)
    if document is None:
        return

    if field not in document:
        if not update:
            seat.fail(
                f"{target}: the golden file has no field {field!r}; "
                f"set {UPDATE_ENV}=1 to add it"
            )
            return
        document[field] = value
        _write_object(seat, target, document)
        return

    mine = _scrub(json.dumps(value, indent=JSON_INDENT, sort_keys=True), scrubbers)
    theirs = _scrub(
        json.dumps(document[field], indent=JSON_INDENT, sort_keys=True), scrubbers
    )

    if update:
        if mine != theirs:
            document[field] = value
            _write_object(seat, target, document)
        return

    check.equal(
        seat,
        mine,
        theirs,
        f"{target}: field {field!r} matches the golden file; "
        f"read the diff before setting {UPDATE_ENV}=1",
    )


def _read_object(seat: Seat, target: Path, update: bool) -> dict[str, Any] | None:
    """Read the JSON object at target, or None when the caller must stop."""
    if not target.exists():
        if not update:
            seat.fail(
                f"{target}: the golden file does not exist; "
                f"set {UPDATE_ENV}=1 to create it"
            )
            return None
        return {}

    try:
        document = json.loads(target.read_text())
    except json.JSONDecodeError as err:
        seat.fail(f"{target}: the golden file is not JSON: {err}")
        return None

    if not isinstance(document, dict):
        seat.fail(f"{target}: the golden file is not a JSON object")
        return None
    return document


def _write(seat: Seat, target: Path, content: str) -> None:
    """Record content as the golden file at target."""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)


def _write_object(seat: Seat, target: Path, document: dict[str, Any]) -> None:
    """Record document as the golden file at target."""
    _write(
        seat, target, json.dumps(document, indent=JSON_INDENT, sort_keys=True) + "\n"
    )
