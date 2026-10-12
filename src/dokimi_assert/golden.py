"""Comparison against recorded output.

A golden file contains the output with which a test compares, so a change of
rendering shows as a diff and not as a rewritten assertion. A golden tree is a
directory of such files. DOKIMI_ASSERT_UPDATE_GOLDEN=1 rewrites them. An
update accepts the current output of the code, so a person reads the diff
before the update.

Each comparison has its own contract, and the contract contains the path of
the golden file or tree. A failure is a record of the comparison. want is the
golden content, or None for a missing file, and got is the output. The
scrubbers apply to both. The call ends with a fault when a golden file cannot
be read or written. Every comparison stops the test at a failure.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from dokimi_assert._files.difference import differing
from dokimi_assert._files.entry import Entry, with_text
from dokimi_assert._files.reader import read_tree
from dokimi_assert._files.record import Comparison, comparison, missing, report
from dokimi_assert._files.tree import path_fault
from dokimi_assert._files.writer import update as update_tree
from dokimi_assert._matcher.fault import FaultError, of_operation
from dokimi_assert._matcher.seat import Mode, Seat
from dokimi_assert._matcher.verdict import Running, fail, fault, pass_
from dokimi_assert.failure import call_site

__all__ = [
    "GOLDEN_DIR",
    "UPDATE_ENV",
    "Scrubber",
    "match",
    "match_at",
    "match_json_field",
    "match_tree",
    "scrub_hashes",
    "scrub_json_fields",
    "scrub_run_ids",
    "scrub_timestamps",
    "should_update",
]

#: The environment variable that lets a run rewrite its golden files.
UPDATE_ENV = "DOKIMI_ASSERT_UPDATE_GOLDEN"

#: The directory in which match and match_tree resolve a name. It is relative
#: to the working directory.
GOLDEN_DIR = os.path.join("testdata", "golden")

#: The indent of a golden JSON file. A diff of an indented file shows each
#: changed line.
_JSON_INDENT = 2

#: A replacement applied to both sides before they are compared.
Scrubber = Callable[[str], str]

_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:?\d{2})?"
)
_HASH = re.compile(r"\b[0-9a-fA-F]{32,128}\b")
_RUN_ID = re.compile(r"\brun_[0-9a-z]{16}\b")


def should_update() -> bool:
    """Report whether this run can rewrite its golden files.

    DOKIMI_ASSERT_UPDATE_GOLDEN=1 enables the update. A golden file that a
    run updates without a reader contains the output of the code at that
    moment. Such a file does not check anything.

    Returns:
        True when the variable is set and is not 0.
    """
    return os.environ.get(UPDATE_ENV, "") not in ("", "0")


def scrub_timestamps() -> Scrubber:
    """Return a scrubber that replaces ISO 8601 and RFC 3339 timestamps.

    Returns:
        The scrubber for a comparison.
    """
    return lambda text: _TIMESTAMP.sub("SCRUBBED_TIMESTAMP", text)


def scrub_hashes() -> Scrubber:
    """Return a scrubber that replaces hex digests of 32 to 128 characters.

    Returns:
        The scrubber for a comparison.
    """
    return lambda text: _HASH.sub("SCRUBBED_HASH", text)


def scrub_run_ids() -> Scrubber:
    """Return a scrubber that replaces each run_ with sixteen characters after it.

    Returns:
        The scrubber for a comparison.
    """
    return lambda text: _RUN_ID.sub("SCRUBBED_RUN_ID", text)


def scrub_json_fields(*fields: str) -> Scrubber:
    """Return a scrubber that replaces the value of each JSON field in fields.

    The scrubber matches the text of the field and does not parse JSON. It
    also works on output that is nearly JSON.

    Args:
        *fields: The names of the fields whose values are replaced.

    Returns:
        The scrubber for a comparison.
    """
    if not fields:
        return lambda text: text
    pattern = re.compile(
        r'("(?:' + "|".join(re.escape(f) for f in fields) + r')"\s*:\s*)"[^"]*"'
    )
    return lambda text: pattern.sub(r'\1"SCRUBBED"', text)


def _scrub(text: str, scrubbers: Sequence[Scrubber]) -> str:
    """Apply the scrubbers in their order."""
    for scrubber in scrubbers:
        text = scrubber(text)
    return text


@dataclass(frozen=True, slots=True)
class _Call:
    """One call of a golden comparison.

    Attributes:
        seat: The seat of the call.
        assertion: The canonical id.
        contract: The contract of the call.
        path: The path of the golden file.
    """

    seat: Seat
    assertion: str
    contract: str
    path: str


def _file_call(seat: Seat, assertion: str, path: str) -> _Call:
    """Return the call of a comparison of output with the golden file at path."""
    contract = (
        f"the golden file {path} matches the output, and {UPDATE_ENV}=1 writes it"
    )
    return _Call(seat, assertion, contract, path)


def _faulted(call: _Call, error: FaultError) -> None:
    """End the call with the fault error."""
    __tracebackhide__ = True
    fault(call.seat, Mode.FATAL, call.assertion, call.contract, error)


def _read(call: _Call) -> str | None:
    """Return the content of the golden file of the call, or None when it is missing.

    Raises:
        FaultError: The file cannot be read as UTF-8 text.
    """
    try:
        with open(call.path, encoding="utf-8", newline="") as stream:
            return stream.read()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as error:
        raise FaultError(call.path, "the golden file cannot be read", error) from error


def _write(call: _Call, content: str) -> None:
    """Write content as the golden file of the call, and pass.

    The write creates the directory of the file when it is missing.
    """
    __tracebackhide__ = True
    try:
        parent = os.path.dirname(call.path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(call.path, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
    except (OSError, UnicodeError) as error:
        _faulted(
            call, FaultError(call.path, "the golden file cannot be written", error)
        )
        return
    pass_(call.seat, Mode.FATAL, call.assertion, call.contract)


def _match_file(
    call: _Call, got: str, update: bool, scrubbers: Sequence[Scrubber]
) -> None:
    """Compare got with the golden file of the call, and report the verdict."""
    __tracebackhide__ = True
    mine = _scrub(got, scrubbers)
    try:
        recorded = _read(call)
    except FaultError as error:
        _faulted(call, error)
        return
    theirs = None if recorded is None else _scrub(recorded, scrubbers)
    if mine == theirs:
        pass_(call.seat, Mode.FATAL, call.assertion, call.contract)
        return
    if update:
        _write(call, mine)
        return
    fail(
        call.seat,
        Mode.FATAL,
        call.assertion,
        call.contract,
        {"want": theirs, "got": mine},
    )


def match_at(
    seat: Seat,
    path: str | os.PathLike[str],
    got: str,
    update: bool,
    *scrubbers: Scrubber,
) -> None:
    """Fail when got differs from the golden file at path.

    The failure is a record of golden-match-at. want is the content of the
    golden file, or None for a missing file, and got is the output. The
    scrubbers apply to both. When update is True, the call rewrites the file
    at a difference and passes.

    Args:
        seat: The seat that receives the failure.
        path: The path of the golden file.
        got: The output.
        update: When True, a difference rewrites the file instead of failing.
        *scrubbers: The replacements applied to both sides before they are
            compared.

    Example:
        golden.match_at(seat, "testdata/report.txt", render(report),
                        golden.should_update(), golden.scrub_timestamps())
    """
    __tracebackhide__ = True
    seat.helper()
    call = _file_call(seat, "golden-match-at", os.fspath(path))
    _match_file(call, got, update, scrubbers)


def match(seat: Seat, name: str, got: str, update: bool, *scrubbers: Scrubber) -> None:
    """Fail when got differs from the golden file of the given name.

    The call resolves the name in testdata/golden below the working
    directory, so a test does not repeat the path. The failure is a record of
    golden-match with the fields of match_at.

    Args:
        seat: The seat that receives the failure.
        name: The name of the golden file in testdata/golden.
        got: The output.
        update: When True, a difference rewrites the file instead of failing.
        *scrubbers: The replacements applied to both sides before they are
            compared.

    Example:
        golden.match(seat, "report.txt", render(report), golden.should_update())
    """
    __tracebackhide__ = True
    seat.helper()
    call = _file_call(seat, "golden-match", os.path.join(GOLDEN_DIR, name))
    _match_file(call, got, update, scrubbers)


def _dumps(value: Any) -> str:
    """Return the JSON text of value in the format of a golden file."""
    return json.dumps(value, indent=_JSON_INDENT, sort_keys=True, ensure_ascii=False)


def _read_object(call: _Call) -> dict[str, Any]:
    """Return the golden JSON object of the call, or an empty object for a missing file.

    Raises:
        FaultError: The file cannot be read as a JSON object.
    """
    content = _read(call)
    if content is None:
        return {}
    try:
        document: object = json.loads(content)
    except json.JSONDecodeError as error:
        raise FaultError(
            call.path, "the golden file cannot be read as a JSON object", error
        ) from error
    if not isinstance(document, dict):
        raise FaultError(call.path, "the golden file cannot be read as a JSON object")
    return document


def match_json_field(
    seat: Seat,
    path: str | os.PathLike[str],
    field: str,
    got: str,
    update: bool,
    *scrubbers: Scrubber,
) -> None:
    """Fail when got differs from one named field of the JSON object at path.

    The call suits a golden file that has one independent value per field. A
    failure then shows only that value, and two tests that update different
    fields do not overwrite each other. The call parses both sides and writes
    them again with sorted keys and the same indent before the comparison, so
    a difference of format does not fail.

    The failure is a record of golden-match-json-field. want is the field of
    the golden file, or None for a missing file or field. got is the value,
    and field is the name. When update is True, the call writes the field at
    a difference, keeps every other field, and passes.

    The call ends with a fault when got is not JSON or when the golden file
    is not a JSON object.

    Args:
        seat: The seat that receives the failure.
        path: The path of the golden file.
        field: The name of the field to compare.
        got: The value as JSON text.
        update: When True, a difference rewrites the field instead of failing.
        *scrubbers: The replacements applied to both sides before they are
            compared.

    Example:
        golden.match_json_field(seat, "testdata/g.json", "items", "[1, 2]", False)
    """
    __tracebackhide__ = True
    seat.helper()
    native = os.fspath(path)
    contract = (
        f"the field {json.dumps(field)} of the golden file {native} matches the "
        f"value, and {UPDATE_ENV}=1 writes it"
    )
    call = _Call(seat, "golden-match-json-field", contract, native)
    try:
        value = json.loads(got)
    except json.JSONDecodeError as error:
        what = f"the value of the field {json.dumps(field)} is not JSON"
        _faulted(call, FaultError(native, what, error))
        return
    mine = _scrub(_dumps(value), scrubbers)
    try:
        document = _read_object(call)
    except FaultError as error:
        _faulted(call, error)
        return
    theirs = _scrub(_dumps(document[field]), scrubbers) if field in document else None
    if mine == theirs:
        pass_(seat, Mode.FATAL, call.assertion, contract)
        return
    if update:
        document[field] = value
        _write(call, _dumps(document) + "\n")
        return
    fail(
        seat,
        Mode.FATAL,
        call.assertion,
        contract,
        {"want": theirs, "got": mine, "field": field},
    )


def _scrubbed(
    tree: Mapping[str, Entry], scrubbers: Sequence[Scrubber]
) -> dict[str, Entry]:
    """Return tree with scrubbers applied to the content of each file of text."""
    return {
        path: e if e.text is None else with_text(e, _scrub(e.text, scrubbers))
        for path, e in tree.items()
    }


def _compare_tree(
    name: str, golden: str, dir: str, update: bool, scrubbers: Sequence[Scrubber]
) -> Comparison | None:
    """Compare the tree in dir with the golden tree in golden.

    When update is True and the two trees differ, the call makes the golden
    tree equal to the tree in dir.

    Returns:
        The record of the comparison, or None when the two trees are equal.

    Raises:
        FaultError: The name is not a path, or a tree cannot be read or
            written.
    """
    refused = path_fault(name)
    if refused is not None:
        raise FaultError("", refused)
    output = _scrubbed(read_tree(dir, True), scrubbers)
    absent = not os.path.exists(golden)
    recorded = {} if absent else _scrubbed(read_tree(golden, False), scrubbers)
    paths = differing(recorded, output, False)
    if update and (absent or paths):
        update_tree(golden, output)
    return missing(output) if absent else comparison(recorded, output, paths)


def match_tree(
    seat: Seat,
    name: str,
    dir: str | os.PathLike[str],
    update: bool,
    *scrubbers: Scrubber,
) -> None:
    """Fail when the tree in dir differs from the golden tree of the given name.

    The call resolves the name in testdata/golden below the working
    directory. The name follows the rules of a path of a tree. Slashes join
    its names, and a name is not empty, "." or "..", so the name cannot leave
    the conventional directory. The comparison does not follow links. It does
    not read the modes of the golden tree, and it compares the execute bit of
    the owner of each file. Git records that one bit. The scrubbers apply to
    the content of every file of UTF-8 text on both sides.

    The failure is a record of golden-match-tree. want and got have the
    entries at the first 64 paths that differ, and differences is the number
    of those paths. For a missing golden directory, want is None, got has the
    first 64 entries of the output, and differences is the number of its
    entries.

    When update is True, the call makes the golden directory equal to the
    output and passes. It removes each entry that the output does not have,
    and writes each entry that the directory does not have or has in a
    different form. It writes the scrubbed content. It removes a link and
    never the entry that the link points to. An update deletes every entry of
    the golden directory that the output does not have, so a golden directory
    cannot contain an input of a test.

    The call ends with a fault when the name is not a path, when an entry of
    either tree is not a file, a directory or a link, or when a tree or the
    golden directory cannot be read or written.

    Args:
        seat: The seat that receives the failure.
        name: The name of the golden tree in testdata/golden.
        dir: The path of the directory of the output in the form of the
            operating system.
        update: When True, a difference rewrites the golden tree instead of
            failing.
        *scrubbers: The replacements applied to both sides before they are
            compared.

    Example:
        golden.match_tree(seat, "api", out, golden.should_update())
    """
    __tracebackhide__ = True
    seat.helper()
    golden = os.path.join(GOLDEN_DIR, *str(name).split("/"))
    contract = (
        f"the golden tree {golden} matches the output, and {UPDATE_ENV}=1 writes it"
    )
    where = call_site()
    running = Running.of(seat, where)
    try:
        record = _compare_tree(name, golden, os.fspath(dir), update, scrubbers)
    except FaultError as error:
        running.faulted(
            Mode.FATAL,
            "golden-match-tree",
            contract,
            of_operation("golden.match_tree", error),
        )
        return
    report(running, "golden-match-tree", contract, None if update else record, where)
