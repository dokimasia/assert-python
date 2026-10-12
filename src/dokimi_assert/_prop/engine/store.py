"""The format, the name and the verdict of a store entry.

The store keeps the minimal failing case of each identity in a directory of
each test. Each file has one JSON object. This module defines the object
that a runner writes, the name of the file, and the verdict that a runner
gives each file that it reads. The property chooses the directory and calls
the file system.

The name of an entry is its key followed by .json. The key is mix of the
UTF-8 bytes of the contract, a zero byte and the bytes of the replay token,
as 16 lowercase hexadecimal digits. A failure that shrinks to the same
choices has the same name in every language. A lone surrogate of a contract
counts as U+FFFD. The UTF-8 encoder of JavaScript writes it the same way.

An entry of format 1 is an object with exactly these fields.

- store is the format.
- definition is the version of the definition that wrote the entry, in the
  form MAJOR.MINOR.PATCH.
- property is the contract of the property.
- identity is the identity of the failure.
- choices is the replay token of the minimal case.
- counterexample has one object per draw. The object has the label of the
  draw, and the value when the value has a typed literal.
- found is the UTC date on which the runner wrote the entry.

A file nests objects and arrays at most 64 levels deep. The root object is
the first level.

A runner gives each file one verdict.

- replay is the verdict on an entry of the property.
- other is the verdict on an entry of another property of the test.
- skip is the verdict on an entry of a later format, or of a token of a
  later version.
- damaged is the verdict on any other file.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from dokimi_assert._prop.engine.choice import Choice
from dokimi_assert._prop.engine.source import mix, utf8
from dokimi_assert._prop.engine.strict_json import JsonError, parse
from dokimi_assert._prop.engine.tokens import decode, encode

__all__ = ["MAX_DEPTH", "Failure", "Read", "Verdict", "entry", "name", "read"]

#: The format of the entries that this module writes and replays.
_FORMAT = 1

#: The version of the tokens that the token module encodes.
_TOKEN_VERSION = 1

#: The largest line of an identity. It is the largest signed 32-bit integer.
_LINE_MAX = 2**31 - 1

#: The largest number of levels of objects and arrays in a file. The root is
#: one level.
MAX_DEPTH = 64

#: The number of levels above the value of a draw. They are the root, the
#: counterexample and the draw.
_ABOVE_VALUE = 3

#: The fields of an entry of format 1, sorted and joined by commas.
_FIELDS = "choices,counterexample,definition,found,identity,property,store"

#: The sorted keys of an identity for each way that a case fails. The ways
#: are the record of an assertion with a location, one without a location, a
#: message to the case, and a raised error.
_IDENTITIES = frozenset(
    {"assertion,file,line", "assertion,contract", "file,line", "error,file,line"}
)

#: The sorted keys of a draw of the counterexample without and with a value.
_DRAWS = frozenset({"label", "label,value"})

#: The start of a token with its version.
_TOKEN = re.compile(r"prop([1-9][0-9]*):")

#: The whole text of a definition version and of a date.
_VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")
_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")

#: The verdict of a runner on one file of the store.
Verdict = Literal["replay", "other", "skip", "damaged"]


@dataclass(frozen=True, slots=True)
class Read:
    """The verdict on a file, and for replay the choices of its entry.

    Attributes:
        verdict: The verdict.
        choices: The choices of the entry for replay, and an empty tuple
            otherwise.
    """

    verdict: Verdict
    choices: tuple[Choice, ...] = ()


@dataclass(frozen=True, slots=True)
class Failure:
    """The minimal failing case of a property in the form of an entry.

    Attributes:
        contract: The contract of the property.
        choices: The choices of the minimal case.
        identity: The identity. Its keys are those of one of the four forms
            of an identity.
        counterexample: The draws. Each draw has its label, and the typed
            literal of its value when the value has one.
    """

    contract: str
    choices: Sequence[Choice]
    identity: Mapping[str, str | int]
    counterexample: Sequence[Mapping[str, Any]]


class _LaterError(Exception):
    """The signal of an entry of a later format or token version."""


def name(contract: str, choices: Sequence[Choice]) -> str:
    """Return the file name of the entry of a contract and a minimal case.

    Args:
        contract: The contract of the property.
        choices: The choices of the minimal case.

    Returns:
        The name. It is 16 lowercase hexadecimal digits followed by .json.
    """
    data = utf8(contract) + b"\x00" + encode(choices).encode("ascii")
    return f"{mix(data):016x}.json"


def _depth(node: object) -> int:
    """Return the number of levels of objects and arrays in node. A scalar has 0."""
    if isinstance(node, list):
        items: list[object] = node
        return 1 + max((_depth(item) for item in items), default=0)
    if isinstance(node, dict):
        members: dict[str, object] = node
        return 1 + max((_depth(member) for member in members.values()), default=0)
    return 0


def entry(failure: Failure, definition: str, found: str) -> dict[str, Any]:
    """Return the entry that a runner of a definition writes on the date found.

    A draw whose value would nest the entry past 64 levels is recorded by its
    label alone.

    Args:
        failure: The failure.
        definition: The version of the definition in the form
            MAJOR.MINOR.PATCH.
        found: The UTC date in the form YYYY-MM-DD.

    Returns:
        The entry as a JSON object.
    """
    deepest = MAX_DEPTH - _ABOVE_VALUE
    draws = [
        {"label": draw["label"]}
        if "value" in draw and _depth(draw["value"]) > deepest
        else dict(draw)
        for draw in failure.counterexample
    ]
    return {
        "store": _FORMAT,
        "definition": definition,
        "property": failure.contract,
        "identity": dict(failure.identity),
        "choices": encode(failure.choices),
        "counterexample": draws,
        "found": found,
    }


def _keys_of(value: Mapping[str, object]) -> str:
    """Return the sorted keys of an object, joined by commas."""
    return ",".join(sorted(value))


def _identity_value(key: str, value: object) -> bool:
    """Report whether a value has the form of the key of an identity."""
    if key == "line":
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 1 <= value <= _LINE_MAX
        )
    if not isinstance(value, str) or value == "":
        return False
    return key != "file" or ("/" not in value and "\\" not in value)


def _is_date(found: object) -> bool:
    """Report whether found is a date of the calendar from 0001-01-01 to 9999-12-31."""
    match = _DATE.fullmatch(found) if isinstance(found, str) else None
    if match is None:
        return False
    year, month, day = int(match[1]), int(match[2]), int(match[3])
    leap = (year % 4 == 0 and year % 100 != 0) or year % 400 == 0
    lengths = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    return year >= 1 and 1 <= month <= 12 and 1 <= day <= lengths[month - 1]


def _is_draw(draw: object) -> bool:
    """Report whether a draw of the counterexample has its form."""
    if not isinstance(draw, dict):
        return False
    fields: dict[str, object] = draw
    return _keys_of(fields) in _DRAWS and isinstance(fields["label"], str)


def _well_formed(document: Mapping[str, object]) -> bool:
    """Report whether every field of an entry of format 1 has its form.

    The caller checks the form of the token apart.
    """
    definition = document["definition"]
    identity = document["identity"]
    draws = document["counterexample"]
    return (
        isinstance(definition, str)
        and _VERSION.fullmatch(definition) is not None
        and isinstance(document["property"], str)
        and isinstance(identity, dict)
        and _keys_of(identity) in _IDENTITIES
        and all(_identity_value(k, v) for k, v in identity.items())
        and isinstance(document["choices"], str)
        and isinstance(draws, list)
        and all(map(_is_draw, draws))
        and _is_date(document["found"])
    )


def _parse_entry(text: str) -> tuple[str, list[Choice]]:
    """Return the property and the choices of the entry of a text."""
    document = parse(text, MAX_DEPTH)
    fields: dict[str, object] = document if isinstance(document, dict) else {}
    version = fields.get("store")
    if not isinstance(version, int) or isinstance(version, bool) or version < _FORMAT:
        raise JsonError("prop: store is not a format")
    if version > _FORMAT:
        raise _LaterError
    if _keys_of(fields) != _FIELDS or not _well_formed(fields):
        raise JsonError("prop: the fields of the entry are not those of its format")
    token = str(fields["choices"])
    started = _TOKEN.match(token)
    if started is None:
        raise JsonError("prop: the token does not have a version")
    if int(started[1]) > _TOKEN_VERSION:
        raise _LaterError
    return str(fields["property"]), decode(token)


def read(text: str, contract: str) -> Read:
    """Return the verdict of a runner of a property on the text of a file.

    Args:
        text: The text of the file.
        contract: The contract of the property.

    Returns:
        The verdict, and for replay the choices of the entry.
    """
    try:
        found, choices = _parse_entry(text)
    except _LaterError:
        return Read("skip")
    except ValueError:
        return Read("damaged")
    if found != contract:
        return Read("other")
    return Read("replay", tuple(choices))
