"""The runners of the files vectors.

A files vector has these parts:

- The tree of a workspace.
- The arguments or the subject of a call of an assertion that reads files.
- The golden tree of a vector of golden-match-tree.
- The verdict and the detail of the call.

A runner writes the workspace below the directory of the vector, makes the
call on a recorder, and compares the call record with the vector.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Callable, Mapping
from typing import Any, cast

from dokimi_assert import files, golden
from dokimi_assert._files.entry import Entry, directory
from dokimi_assert._files.literal import decode, encode
from dokimi_assert._files.reader import read_tree
from dokimi_assert._files.writer import create
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.literal import LiteralError, Objects, same_json
from dokimi_assert.conformance.subject import SUBJECTS
from dokimi_assert.seat import Recorder

__all__ = ["CONTRACT", "RUNNERS", "Runner"]

#: The contract of the call of a files vector.
CONTRACT = "the files match the vector"

#: The directory below the directory of the vector into which a runner writes
#: the workspace.
_WORKSPACE = "workspace"

#: A runner runs the JSON of one vector against this library in a new empty
#: directory. It raises FaultError at the part of the vector that the run
#: contradicts or that the runner cannot take.
Runner = Callable[[Mapping[str, Any], str], None]

#: A caller returns the call of the assertion of a vector from the vector, its
#: directory and its workspace. The call raises FaultError for a difference
#: outside its call record. The caller raises FaultError for an input that the
#: call cannot take.
_Caller = Callable[[Mapping[str, Any], str, str], Callable[[Recorder], None]]


def _within(under: str, tree: Mapping[str, Entry]) -> dict[str, Entry]:
    """Return tree below the directory under. under is an entry of its own."""
    return {under: directory(), **{f"{under}/{path}": e for path, e in tree.items()}}


def _tree_at(literal: object, member: str) -> dict[str, Entry]:
    """Return the tree of the tree literal at member of a vector."""
    try:
        return decode(literal)
    except FaultError as error:
        raise error.within(member) from error


def _args_of(v: Mapping[str, Any], n: int) -> list[Any]:
    """Return the n arguments of v as typed literals."""
    args = v.get("args", [])
    if not isinstance(args, list) or len(args) != n:
        count = len(args) if isinstance(args, list) else 0
        raise FaultError("args", f"the number of arguments is {count}, want {n}")
    return args


def _values_of(v: Mapping[str, Any], n: int) -> list[Any]:
    """Return the values of the n typed literals of the arguments of v."""
    objects = Objects()
    values: list[Any] = []
    for i, literal in enumerate(_args_of(v, n)):
        at = f"args[{i}]"
        try:
            values.append(objects.decode(literal))
        except LiteralError as error:
            raise FaultError(at, str(error)) from error
        except FaultError as error:
            raise error.within(at) from error
    return values


def _argument(
    values: list[Any], i: int, what: str, accepts: Callable[[Any], bool]
) -> Any:
    """Return the argument at i after a check that accepts returns True for it."""
    value = values[i]
    if not accepts(value):
        raise FaultError(f"args[{i}]", f"the argument is not {what}")
    return value


def _is_str(value: object) -> bool:
    """Report whether value is a str."""
    return isinstance(value, str)


def _path_at(values: list[Any], i: int, ws: str) -> str:
    """Return the operating system path in ws of the argument at i."""
    relative: str = _argument(values, i, "a string", _is_str)
    return os.path.join(ws, *relative.split("/"))


def _record_of(seat: Recorder) -> dict[str, Any]:
    """Return the call record of the one call of seat, parsed."""
    record: dict[str, Any] = json.loads(seat.records[0])
    return record


def _compare_verdict(
    record: Mapping[str, Any], expect: object, wanted: Mapping[str, Any]
) -> None:
    """Compare the call record with the outcome that a vector expects.

    The outcome is a pass, or a failure whose detail has exactly the fields of
    the vector with the same JSON values.
    """
    if expect not in ("pass", "fail"):
        raise FaultError(
            "expect", f"the vector expects {json.dumps(expect)}, neither pass nor fail"
        )
    verdict = record["verdict"]
    if verdict != expect:
        error = f" ({record['error']})" if "error" in record else ""
        raise FaultError("expect", f"the check ends as {verdict}{error}, want {expect}")
    if expect == "pass":
        return
    detail: Mapping[str, Any] = record["detail"]
    names = sorted(wanted)
    fields = sorted(detail)
    if fields != names:
        raise FaultError(
            "detail",
            f"the record has the fields {json.dumps(fields)}, want {json.dumps(names)}",
        )
    for name in names:
        if not same_json(detail[name], wanted[name]):
            raise FaultError(
                f"detail.{name}",
                f"the field is {json.dumps(detail[name])}, "
                f"want {json.dumps(wanted[name])}",
            )


def _check_files(build: _Caller) -> Runner:
    """Return the runner of the files vectors whose calls build returns.

    The runner writes the workspace into the directory workspace below the
    directory of the vector, makes the call on a recorder, and compares the
    verdict and the detail of its call record with the vector.
    """

    def run(raw: Mapping[str, Any], dir: str) -> None:
        tree = _tree_at(raw.get("workspace"), "workspace")
        try:
            create(dir, _within(_WORKSPACE, tree))
        except FaultError as error:
            raise error.within("workspace") from error
        call = build(raw, dir, os.path.join(dir, _WORKSPACE))
        seat = Recorder()
        call(seat)
        _compare_verdict(_record_of(seat), raw.get("expect"), raw.get("detail", {}))

    return run


def _tree_call(compare: Callable[[Any, str, Any, str], None]) -> _Caller:
    """Return the caller of a comparison of trees.

    The argument of the vector is the wanted tree.
    """

    def caller(v: Mapping[str, Any], _dir: str, ws: str) -> Callable[[Recorder], None]:
        want = _tree_at(_args_of(v, 1)[0], "args[0]")
        return lambda seat: compare(seat, ws, want, CONTRACT)

    return caller


def _unchanged_call(
    v: Mapping[str, Any], _dir: str, ws: str
) -> Callable[[Recorder], None]:
    """Return the call of a tree-unchanged vector.

    The subject of the vector reads or writes the files of the workspace. The
    call raises a fault at the subject for a subject that raises.
    """
    subject: object = v.get("subject")
    described: Mapping[str, Any] = (
        cast("Mapping[str, Any]", subject) if isinstance(subject, dict) else {}
    )
    kind = described.get("kind")
    build = SUBJECTS.get(kind) if isinstance(kind, str) else None
    touch = None if build is None else build().files
    if touch is None:
        raise FaultError(
            "subject.kind", f"{json.dumps(kind)} is not a subject of files"
        )
    found = touch

    def call(seat: Recorder) -> None:
        failed: list[Exception] = []

        def run() -> None:
            try:
                found(ws)
            except OSError as error:
                failed.append(error)

        files.unchanged(seat, ws, run, CONTRACT)
        if failed:
            raise FaultError("subject", "the subject fails", failed[0])

    return call


def _check_working_directory(dir: str) -> None:
    """Raise a fault when dir is not the working directory."""
    if not os.path.samefile(".", dir):
        raise FaultError(
            "",
            "golden.match_tree resolves a name in the working directory, and the "
            "directory of the vector is not the working directory",
        )


def _compare_after(dir: str, after: object) -> None:
    """Compare the golden tree in dir, read without its modes, with after."""
    try:
        got = encode(read_tree(dir, False), math.inf)
    except FaultError as error:
        raise FaultError("after", "the golden tree cannot be read", error) from error
    if not same_json(got, after):
        raise FaultError(
            "after",
            f"the golden tree is {json.dumps(got)}, want {json.dumps(after)}",
        )


def _golden_call(v: Mapping[str, Any], dir: str, ws: str) -> Callable[[Recorder], None]:
    """Return the call of a golden-match-tree vector.

    The arguments of the vector are the name and update. golden.match_tree
    resolves the name in the working directory, so the caller refuses a dir
    that is not the working directory. The caller writes the golden tree of the
    vector below the conventional directory of dir. After the call, the call
    raises a fault at after when the golden tree differs from the tree of the
    vector.
    """
    values = _values_of(v, 2)
    name: str = _argument(values, 0, "a string", _is_str)
    update: bool = _argument(values, 1, "a bool", lambda value: isinstance(value, bool))
    _check_working_directory(dir)
    relative = f"testdata/golden/{name}"
    if v.get("golden") is not None:
        tree = _tree_at(v.get("golden"), "golden")
        try:
            create(dir, _within(relative, tree))
        except FaultError as error:
            raise error.within("golden") from error
    after = v.get("after")

    def call(seat: Recorder) -> None:
        golden.match_tree(seat, name, ws, update)
        if after is not None:
            _compare_after(os.path.join(dir, *relative.split("/")), after)

    return call


def _kind_call(assertion: Callable[[Any, str, str], None]) -> _Caller:
    """Return the caller of an assertion about one path.

    The argument of the vector is the path.
    """

    def caller(v: Mapping[str, Any], _dir: str, ws: str) -> Callable[[Recorder], None]:
        path = _path_at(_values_of(v, 1), 0, ws)
        return lambda seat: assertion(seat, path, CONTRACT)

    return caller


def _links_to_call(
    v: Mapping[str, Any], _dir: str, ws: str
) -> Callable[[Recorder], None]:
    """Return the call of a links-to vector with the arguments path and target."""
    values = _values_of(v, 2)
    path = _path_at(values, 0, ws)
    target: str = _argument(values, 1, "a string", _is_str)
    return lambda seat: files.links_to(seat, path, target, CONTRACT)


def _has_content_call(
    v: Mapping[str, Any], _dir: str, ws: str
) -> Callable[[Recorder], None]:
    """Return the call of a has-content vector.

    Its arguments are the path and the content as text or bytes.
    """
    values = _values_of(v, 2)
    path = _path_at(values, 0, ws)
    content: str | bytes = _argument(
        values, 1, "text or bytes", lambda value: isinstance(value, (str, bytes))
    )
    return lambda seat: files.has_content(seat, path, content, CONTRACT)


def _has_mode_call(
    v: Mapping[str, Any], _dir: str, ws: str
) -> Callable[[Recorder], None]:
    """Return the call of a has-mode vector with the arguments path and mode."""
    values = _values_of(v, 2)
    path = _path_at(values, 0, ws)
    mode: int = _argument(
        values,
        1,
        "an int",
        lambda value: isinstance(value, int) and not isinstance(value, bool),
    )
    return lambda seat: files.has_mode(seat, path, mode, CONTRACT)


#: The runner of each kind of files vector, by the name of the kind.
RUNNERS: dict[str, Runner] = {
    "tree-equal": _check_files(_tree_call(files.equal)),
    "tree-contains": _check_files(_tree_call(files.contains)),
    "tree-unchanged": _check_files(_unchanged_call),
    "golden-match-tree": _check_files(_golden_call),
    "path-absent": _check_files(_kind_call(files.absent)),
    "is-file": _check_files(_kind_call(files.is_file)),
    "is-dir": _check_files(_kind_call(files.is_dir)),
    "links-to": _check_files(_links_to_call),
    "has-content": _check_files(_has_content_call),
    "has-mode": _check_files(_has_mode_call),
}
