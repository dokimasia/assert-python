# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The directory of the store of a property, and the files in it.

The store of a test is testdata/prop/<path>/<test> below the working
directory. <path> has the segments of the path of the module of the test, and
<test> is the name of the item with its class and its parameters. Each
segment escapes a character that a file name cannot contain on some system
as % and two hexadecimal digits.

Every file of the directory whose name ends in .json gets one verdict. An
entry of the property replays. The property leaves an entry of a different
property of the test in place. An entry of a later format is noted and
skipped, and any other file is damaged.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert._matcher.seat import named_test
from dokimi_assert._prop.engine.choice import Choice
from dokimi_assert._prop.engine.store import read

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "Loaded",
    "Stored",
    "claim",
    "load",
    "save",
    "seeds",
    "seeds_of",
    "store_of",
]

#: The directory of the stores of the tests of a project. It is next to
#: testdata/golden.
_STORE_ROOT = ("testdata", "prop")

#: The directory of the seed files of the fuzz targets of the tests of a
#: project.
_FUZZ_ROOT = ("testdata", "fuzz")

#: The characters that some system refuses in a file name, and the escape
#: character.
_FORBIDDEN = frozenset('%/\\:*?"<>|')

#: The first character that a file name can contain. The control characters
#: are below it.
_FIRST_PRINTABLE = 0x20

#: The claims of the running properties on the entries of their contracts.
_CLAIMS: set[str] = set()


@dataclass(frozen=True, slots=True)
class Stored:
    """An entry of a store that a property replays.

    Attributes:
        name: The name of the file.
        choices: The choices of the minimal case.
        counterexample: Each draw of the counterexample in the form of the
            entry.
    """

    name: str
    choices: tuple[Choice, ...]
    counterexample: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class Loaded:
    """The entries that a property reads from its store, and the skipped files.

    Attributes:
        entries: The entries of the property from the oldest.
        skipped: The files that the property skips.
    """

    entries: list[Stored]
    skipped: list[str]


def _escaped(segment: str) -> str:
    """Return a segment of a path with its characters escaped for a file name.

    The escaped characters are the forbidden characters, the control
    characters, and a dot or a space at the end of the segment. Some systems
    drop such a dot or space.
    """
    last = len(segment) - 1
    out: list[str] = []
    for index, char in enumerate(segment):
        ending = index == last and char in ". "
        if char in _FORBIDDEN or ord(char) < _FIRST_PRINTABLE or ending:
            out.append(f"%{ord(char):02X}")
        else:
            out.append(char)
    return "".join(out)


def _below(root: tuple[str, ...], seat: object) -> str:
    """Return the directory of the test of seat below root.

    The result is the empty string for a seat that does not run a named
    test.
    """
    path = named_test(seat)
    return "" if path is None else str(pathlib.Path(*root, *map(_escaped, path)))


def store_of(seat: object, given: str | None) -> str:
    """Return the directory of the store of a property on seat.

    The directory of the store option comes first, then the store of the test
    of the seat. The empty string turns the store off.

    Args:
        seat: The seat of the property.
        given: The directory of the store option, or None.

    Returns:
        The directory, or the empty string.
    """
    return _below(_STORE_ROOT, seat) if given is None else given


def seeds_of(seat: object) -> str:
    """Return the directory of the seed files of a fuzz target on seat.

    Args:
        seat: The seat of the property.

    Returns:
        The directory, or the empty string for a seat that does not run a
        named test.
    """
    return _below(_FUZZ_ROOT, seat)


def claim(seat: object, directory: str, contract: str) -> bool:
    """Claim the entries of a contract in a store for the test of seat.

    The claim lasts until the test ends. For a property without a store or a
    seat without cleanups, the call does not claim anything and returns True.

    Args:
        seat: The seat of the property.
        directory: The directory of the store.
        contract: The contract of the property.

    Returns:
        False when a property of a running test has claimed the entries, and
        True otherwise.
    """
    cleanup: Any = getattr(seat, "cleanup", None)
    if directory == "" or not callable(cleanup):
        return True
    key = f"{directory}\x00{contract}"
    if key in _CLAIMS:
        return False
    _CLAIMS.add(key)
    cleanup(lambda: _CLAIMS.discard(key))
    return True


def _files_of(directory: str) -> list[str]:
    """Return the names of the .json files of a directory.

    A directory that does not exist does not have files.

    Raises:
        FaultError: The directory cannot be read.
    """
    try:
        with os.scandir(directory) as found:
            return [
                one.name
                for one in found
                if not one.is_dir() and one.name.endswith(".json")
            ]
    except FileNotFoundError:
        return []
    except OSError as error:
        raise FaultError(directory, "the store cannot be read", error) from error


def load(directory: str, contract: str) -> Loaded:
    """Return the entries of a contract in a store, with the files that it skips.

    The entries come in the order of the dates on which they were found,
    and in the order of their names within one date.

    Args:
        directory: The directory of the store.
        contract: The contract of the property.

    Returns:
        The entries and the skipped files.

    Raises:
        FaultError: The store has damaged files, or the store cannot be read.
            The text of the fault has the names of the damaged files.
    """
    found: list[tuple[str, Stored]] = []
    skipped: list[str] = []
    damaged: list[str] = []
    for name in sorted(_files_of(directory)):
        try:
            text = pathlib.Path(directory, name).read_bytes().decode("utf-8")
        except (OSError, UnicodeDecodeError):
            damaged.append(name)
            continue
        verdict = read(text, contract)
        if verdict.verdict == "replay":
            parsed = json.loads(text)
            stored = Stored(name, verdict.choices, parsed["counterexample"])
            found.append((parsed["found"], stored))
        elif verdict.verdict == "skip":
            skipped.append(name)
        elif verdict.verdict == "damaged":
            damaged.append(name)
    if damaged:
        raise FaultError(
            directory, f"the store has damaged files: {', '.join(damaged)}"
        )
    found.sort(key=lambda pair: pair[0])
    return Loaded([stored for _, stored in found], skipped)


def save(directory: str, name: str, entry: Mapping[str, Any]) -> bool:
    """Write an entry into a store under a name, unless a file of that name exists.

    The file is JSON, indented by two spaces, with a final newline.

    Args:
        directory: The directory of the store.
        name: The file name of the entry.
        entry: The entry as a JSON object.

    Returns:
        True when the call wrote the entry.

    Raises:
        OSError: The file system cannot keep the entry.
        ValueError: The name contains a null character.
    """
    store = pathlib.Path(directory)
    store.mkdir(parents=True, exist_ok=True)
    try:
        with (store / name).open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, indent=2) + "\n")
    except FileExistsError:
        return False
    return True


def seeds(directory: str) -> list[tuple[str, bytes]]:
    """Return the seed files of a fuzz target as the inputs of a fuzzer.

    The files come in the order of their names. A directory that does not
    exist does not have seed files.

    Args:
        directory: The directory of the seed files.

    Returns:
        The name and the bytes of each file.

    Raises:
        FaultError: The directory cannot be read.
    """
    try:
        with os.scandir(directory) as found:
            names = sorted(one.name for one in found if one.is_file())
        return [(name, pathlib.Path(directory, name).read_bytes()) for name in names]
    except FileNotFoundError:
        return []
    except OSError as error:
        raise FaultError(directory, "the seed files cannot be read", error) from error
