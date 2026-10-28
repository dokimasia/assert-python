# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""Render the API reference of the README from the code itself.

A signature list written by hand goes stale the first time a parameter
moves. This reads the real signatures, so the README either matches the
code or the documentation test fails.

The reference has a block for each section of the README that describes a
module. Two markers in README.md enclose each block. Run the tool to refresh
every block:

    python tools/api_reference.py --write

Without --write, the tool prints every block between its markers.
"""

from __future__ import annotations

import argparse
import inspect
import os
import pathlib
import pkgutil
import re
import sys
import types
from dataclasses import dataclass
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

import dokimi_assert
from dokimi_assert import (
    bench,
    call,
    check,
    clock,
    failure,
    files,
    golden,
    history,
    option,
    prop,
    seat,
    stateful,
)

#: The prefix of an entry that renders a type by its name alone, without the
#: parameters of its constructor.
TYPE = "type "

#: The public modules that the reference does not render, and why.
UNRENDERED = {
    "conformance": "The tests run the cases of the definition with it.",
    "expect": "It has the names and the signatures of check.",
    "pytest_plugin": "pytest loads it, and the README describes its fixtures.",
    "rejects": "check and expect export its one function.",
}


@dataclass(frozen=True)
class Family:
    """A group of names of one module that the reference renders together.

    Attributes:
        module: The module.
        title: The title of the group.
        blurb: What the group states. A newline breaks the line in README.md.
        entries: A name of the module, a member of one of its classes as
            Class.member, or a name after TYPE for a type without its
            constructor.
    """

    module: types.ModuleType
    title: str
    blurb: str
    entries: tuple[str, ...]


@dataclass(frozen=True)
class Block:
    """One block of the reference between its two markers in README.md.

    Attributes:
        lead: The lines before the families.
        families: The families, in the order in which a reader meets them.
        tail: The lines after the families.
    """

    lead: tuple[str, ...]
    families: tuple[Family, ...]
    tail: tuple[str, ...] = ()


def _family(module: types.ModuleType, title: str, blurb: str, *entries: str) -> Family:
    """Return a family of the names of module."""
    return Family(module, title, blurb, entries)


#: The families of check, in the order a reader meets them.
CHECK = (
    _family(
        check,
        "Equality",
        "The comparison is structural and strict about types.",
        "equal",
        "not_equal",
    ),
    _family(
        check,
        "Truth and absence",
        "Python has one null value, None.",
        "is_true",
        "is_false",
        "is_none",
        "is_not_none",
    ),
    _family(
        check,
        "Size",
        "Each takes anything with a length. None has no length and fails all three.",
        "length",
        "is_empty",
        "is_not_empty",
    ),
    _family(
        check,
        "Containment",
        "A str contains a substring, a mapping contains a key, and a "
        "sequence or a set contains an element by the rules of equal. "
        "is_permutation compares two sequences in any order.",
        "contains",
        "not_contains",
        "contains_in_order",
        "is_permutation",
    ),
    _family(
        check,
        "Text",
        "Each takes a str and fails on any other value.",
        "has_prefix",
        "has_suffix",
        "matches",
    ),
    _family(
        check,
        "Numbers",
        "Exact equality is the wrong check for a float.",
        "close_to",
        "in_range",
    ),
    _family(
        check,
        "Ordering",
        "pairwise covers sorted, unique and strictly increasing, because "
        "each of those is a relation between neighbours.",
        "pairwise",
    ),
    _family(
        check,
        "Errors",
        "These suit code that returns an error instead of raising it.",
        "no_error",
        "has_error",
        "error_is",
        "error_is_not",
        "error_as",
    ),
    _family(
        check,
        "Raising",
        "raises returns the exception of fn, so a test can assert on its "
        "class or its message.",
        "raises",
        "does_not_raise",
    ),
    _family(
        check,
        "Cancellation",
        "Python cancels work through asyncio. honours_cancellation and "
        "honours_deadline take a coroutine function and run the event "
        "loop themselves, so the test is a plain def. completes_within "
        "calls fn on a daemon thread and fails at the deadline without "
        "waiting for it.",
        "honours_cancellation",
        "honours_deadline",
        "completes_within",
        "none_handle_safe",
    ),
    _family(
        check,
        "Retrying",
        "These suit a condition that something outside the test makes "
        "true. On the platform clock they spend real time. On a "
        "Controlled clock they advance the clock between attempts.",
        "eventually",
        "eventually_true",
    ),
    _family(
        check,
        "Concurrency",
        "Call what it returns where the scope ends. A thread or an "
        "asyncio task that the scope started and that still runs then "
        "is a leak.",
        "no_task_leaks",
    ),
    _family(
        check,
        "Purity",
        "observe must return a copy, because a reading that shares state "
        "with the subject compares one object with itself.",
        "is_pure",
        "is_not_pure",
    ),
    _family(
        check,
        "Relations",
        "Each calls the subject with the values that the test passes. A "
        "relation that compares two results compares them by the rules "
        "of equal.",
        "is_idempotent",
        "accumulates",
        "is_deterministic",
        "is_commutative",
        "is_associative",
        "round_trip",
        "has_stable_order",
        "no_duplicates",
        "is_monotonic",
        "is_total",
        "fails_after_close",
        "is_poisoned",
    ),
    _family(
        check,
        "Testing an assertion",
        "rejects takes the message before its body. It returns the "
        "failure records of the body, and fails when the body passes.",
        "rejects",
    ),
)

#: The families of the other modules of the block of the assertions.
SUPPORT = (
    _family(
        golden,
        "Golden files",
        "Each comparison reads recorded output and takes\n"
        "no message. A failure stops the test.",
        "match",
        "match_at",
        "match_json_field",
        "match_tree",
        "should_update",
        "scrub_timestamps",
        "scrub_hashes",
        "scrub_run_ids",
        "scrub_json_fields",
        "Scrubber",
        "GOLDEN_DIR",
        "UPDATE_ENV",
    ),
    _family(
        bench,
        "Benchmark ceilings",
        "The ceilings chain onto one contract, and\n"
        "`check` reports a verdict for each of them. `allocs_checked`\n"
        "returns whether a run checks allocation ceilings.",
        "Contract",
        "Contract.warmup",
        "Contract.max_latency",
        "Contract.max_mean",
        "Contract.max_bytes",
        "Contract.loop",
        "Contract.excluding",
        "Contract.check",
        "allocs_checked",
    ),
    _family(
        seat,
        "Seats",
        "An assertion reports each failure to its seat. The seat fixture "
        "is a Collector, and the recorder fixture is a Recorder.",
        "Seat.helper",
        "Seat.fail",
        "Seat.record",
        "Collector",
        "Collector.cleanup",
        "Collector.with_clock",
        "Standard",
        "Recorder",
        "Recorder.with_clock",
        "Recorder.failed",
        "Recorder.message",
        "Recorder.messages",
        "Recorder.failures",
        "Recorder.faults",
        "Recorder.records",
        "Recorder.helper_calls",
        "clean_up",
        "fault",
    ),
    _family(
        call,
        "Observed calls",
        "A seat with a method observe_call receives each assertion call, "
        "a passing one included.",
        "Call",
    ),
    _family(
        option,
        "Options of a comparison",
        "An option relaxes or narrows equality for the one call that it is passed to.",
        "equate_empty",
        "equate_nans",
        "by_identity",
        f"{TYPE}Option",
    ),
    _family(
        failure,
        "Failure records",
        "A failure is a record of the assertion, the contract and the "
        "detail. render returns the sentence of a record.",
        "Failure",
        "Failure.want",
        "Failure.got",
        "Failure.case_failure",
        "Where",
        "render",
        "register_sentence",
        "call_site",
        "site_in",
    ),
    _family(
        clock,
        "Clocks",
        "An assertion that waits, retries or measures reads the clock of "
        "its seat. A Controlled clock moves only when a test advances it.",
        "Clock.now",
        "Clock.sleep",
        "System",
        "Controlled",
        "Controlled.advance",
    ),
)

#: The blocks of the reference, by the name of their markers.
BLOCKS = {
    "assertions": Block(
        lead=(
            "Each assertion takes the seat first and the message last.",
            "`check` and `expect` have the same names and the same",
            "signatures. Only what happens on a failure differs.",
        ),
        families=CHECK + SUPPORT,
        tail=(
            "Read the docstring of an assertion for its rules and the",
            "meaning of each argument, with `help(check.close_to)` or in",
            "your editor.",
        ),
    ),
    "files": Block(
        lead=(),
        families=(
            _family(
                files,
                "Trees",
                "A tree maps each path to an entry. A path is relative to the "
                "root of the tree, and slashes separate its names.",
                "Tree",
                "text",
                "bytes",
                "executable",
                "directory",
                "link",
                "Entry.with_mode",
            ),
            _family(
                files,
                "Writing and reading",
                "workspace writes a tree into a new directory that the test "
                "removes when it ends.",
                "workspace",
                "write",
                "read",
            ),
            _family(
                files,
                "Comparing a tree",
                "Each compares the tree in a directory with a wanted tree.",
                "equal",
                "contains",
                "unchanged",
            ),
            _family(
                files,
                "Checking one path",
                "Each reads the entry at the path itself and does not follow a "
                "link there.",
                "absent",
                "is_file",
                "is_dir",
                "links_to",
                "has_content",
                "has_mode",
            ),
        ),
    ),
    "prop": Block(
        lead=(),
        families=(
            _family(
                prop,
                "Running a property",
                "for_all runs the body against generated cases, and the body "
                "draws its inputs from its case.",
                "for_all",
                "fuzz",
                "Case.draw",
                "Case.assume",
                "Case.skip",
                "Case.classify",
                "Case.target",
                "Case.note",
                "Case.observe",
                "Case.cleanup",
                "Case.rand",
                "Case.history",
                "values",
            ),
            _family(
                prop,
                "Options of a run",
                "A later option of one kind replaces an earlier one. Each "
                "require and each using adds to the earlier ones.",
                f"{TYPE}Option",
                "cases",
                "seed",
                "replay",
                "require",
                "shrink",
                "shrink_time",
                "max_choices",
                "store",
                "explain",
                "workers",
                "hermetic",
                "draws",
                "around",
                "Wrapper",
                "using",
            ),
            _family(
                prop,
                "Generators",
                "Each returns a Generator. map, filter and bind derive a new "
                "generator from one.",
                "Generator.map",
                "Generator.filter",
                "Generator.bind",
                "boolean",
                "integer",
                "float",
                "duration",
                "string",
                "string_matching",
                "bytes",
                "list",
                "dict",
                "optional",
                "one_of",
                "just",
                "sampled_from",
                "permutation",
                "recursive",
                "composite",
            ),
            _family(
                prop,
                "Types and shapes",
                "of derives the generator of a type from its shape. A "
                "registration replaces the generator or the shape of a type in "
                "the test process.",
                "of",
                "of_shape",
                "shape_of",
                "register",
                "register_values",
                "register_variants",
                "Variant",
                "WallTime",
            ),
            _family(
                prop,
                "Constraints",
                "Each is an argument of typing.Annotated, as the constraints of "
                "annotated-types are.",
                "AllowInfinity",
                "AllowNan",
                "Alphabet",
                "Char",
                "Pattern",
                "Scale",
                "Unit",
                "Version",
                "Width",
            ),
            _family(
                prop,
                "Forms",
                "Each form runs its assertion on every generated input. A form "
                "takes the options of a run, the options of a comparison that "
                "its assertion takes, and example and examples.",
                "equal",
                "not_equal",
                "is_true",
                "is_false",
                "is_none",
                "is_not_none",
                "length",
                "is_empty",
                "is_not_empty",
                "contains",
                "not_contains",
                "contains_in_order",
                "is_permutation",
                "has_prefix",
                "has_suffix",
                "matches",
                "close_to",
                "in_range",
                "pairwise",
                "no_error",
                "has_error",
                "error_is",
                "error_is_not",
                "error_as",
                "raises",
                "does_not_raise",
                "honours_cancellation",
                "honours_deadline",
                "none_handle_safe",
                "is_pure",
                "is_not_pure",
                "is_idempotent",
                "accumulates",
                "is_deterministic",
                "is_commutative",
                "is_associative",
                "round_trip",
                "example",
                "examples",
                "FormOption",
            ),
        ),
    ),
    "history": Block(
        lead=(),
        families=(
            _family(
                history,
                "Recording",
                "A test records each call before the call starts, and completes "
                "it after the call returns.",
                "History",
                "History.invoke",
                "History.events",
                "Call.ok",
                "Call.fail",
                "Call.unknown",
                "concurrently",
                "Outcome",
                "from_intervals",
                "Interval",
                "IntervalError",
            ),
            _family(
                history,
                "Events",
                "History.events returns the events in recording order.",
                "Event",
                "Invocation",
                "Completion",
                "Kind",
            ),
            _family(
                history,
                "Specifications",
                "A spec returns the states that an operation can lead to from a "
                "state, and no state for an operation that it refuses.",
                "Spec.initial",
                "Spec.next",
                "Operation.name",
                "Operation.args",
                "Operation.known",
                "Operation.output",
                "Operation.returned",
                "spec_from",
            ),
            _family(
                history,
                "Checks",
                "is_linearizable checks a history against a spec. is_serializable "
                "and has_snapshot_isolation read a history of list-append "
                "transactions.",
                "is_linearizable",
                "is_serializable",
                "has_snapshot_isolation",
            ),
            _family(
                history,
                "Options of a check",
                "Each bounds the search of is_linearizable.",
                f"{TYPE}Option",
                "budget",
                "memo_limit",
                "time_limit",
                "workers",
            ),
            _family(
                history,
                "Calls and evidence",
                "These are the types of the calls, the transactions and the "
                "evidence that the checks and their records use.",
                "Span",
                "Transaction",
                "Link",
                "Edge",
                "Observation",
                "Evidence",
            ),
        ),
    ),
    "stateful": Block(
        lead=(),
        families=(
            _family(
                stateful,
                "Machines",
                "A machine has the spec of a subject and its actions. steps "
                "takes the steps of a machine in a case.",
                "Machine.spec",
                "Machine.actions",
                "Action",
                "steps",
            ),
            _family(
                stateful,
                "Options of steps",
                "Each sets one bound of the steps of a case, or the way in which "
                "the clients of a concurrent section run.",
                f"{TYPE}Option",
                "clients",
                "concurrent",
                "max_steps",
                "mean",
                "repeat",
                "swarm",
                "tasks",
            ),
            _family(
                stateful,
                "Schedulers",
                "With tasks, the clients run as tasks of a Scheduler. Its "
                "releases are choices of the case.",
                "Scheduler",
                "Scheduler.spawn",
                "Scheduler.run",
                f"{TYPE}Strategy",
                "uniform",
                "pct",
            ),
        ),
    ),
}


def _start(name: str) -> str:
    """Return the marker where the block of name starts in README.md."""
    return f"<!-- api-reference:{name}:start -->"


def _end(name: str) -> str:
    """Return the marker where the block of name ends in README.md."""
    return f"<!-- api-reference:{name}:end -->"


def _short(module: types.ModuleType) -> str:
    """Return the name of module without the name of the package."""
    return module.__name__.rsplit(".", 1)[-1]


def _clean(text: str) -> str:
    """Return an annotation as it would be written by hand.

    Postponed evaluation means inspect hands these back as quoted
    strings, and a typing alias arrives with its module path in front.
    Neither is what anyone would type.
    """
    text = text.strip("'\"")
    text = re.sub(r"\b[a-z_]+(?:\.[a-z_]+)*\.([A-Z_])", r"\1", text)
    return text.replace("~", "")


def signature(owner: Any, name: str, prefix: str) -> str:
    """Return one rendered signature line."""
    sig = inspect.signature(getattr(owner, name))
    parts: list[str] = []
    for p in sig.parameters.values():
        if p.name == "self":
            continue
        stars = "*" if p.kind is p.VAR_POSITIONAL else ""
        ann = _clean(inspect.formatannotation(p.annotation))
        parts.append(f"{stars}{p.name}: {ann}")

    ret = _clean(inspect.formatannotation(sig.return_annotation))
    constructor = inspect.isclass(getattr(owner, name))
    tail = "" if ret == "None" or constructor else f" -> {ret}"
    return f"{prefix}{name}({', '.join(parts)}){tail}"


def _public_names() -> dict[object, str]:
    """Return the name of each class that a rendered module exports."""
    names: dict[object, str] = {}
    for block in BLOCKS.values():
        for family in block.families:
            for name in family.module.__all__:
                value = getattr(family.module, name)
                if inspect.isclass(value):
                    names.setdefault(value, f"{_short(family.module)}.{name}")
    return names


def _alias(value: object) -> str:
    """Return the text of a type alias, with each class by its public name."""
    if isinstance(value, types.UnionType):
        public = _public_names()
        return " | ".join(
            public.get(member, getattr(member, "__name__", str(member)))
            for member in value.__args__
        )
    return _clean(inspect.formatannotation(value))


def line(module: types.ModuleType, entry: str) -> str:
    """Return the rendered line of one entry of a family of module."""
    prefix = f"{_short(module)}."
    if entry.startswith(TYPE):
        return f"{prefix}{entry.removeprefix(TYPE)}"
    if "." in entry:
        owner_name, member = entry.split(".", 1)
        owner = getattr(module, owner_name)
        static = inspect.getattr_static(owner, member)
        if isinstance(static, property) and static.fget is not None:
            returned = inspect.signature(static.fget).return_annotation
            return f"{entry}: {_clean(inspect.formatannotation(returned))}"
        return signature(owner, member, f"{owner_name}.")
    value = getattr(module, entry)
    if inspect.isclass(value) or inspect.isfunction(value):
        return signature(module, entry, prefix)
    if isinstance(value, str):
        # The README states a path such as GOLDEN_DIR with slashes, as POSIX
        # writes it, so the reference is the same on every system.
        return f"{prefix}{entry} = {value.replace(os.sep, '/')!r}"
    return f"{prefix}{entry} = {_alias(value)}"


def _placed(family: Family) -> set[str]:
    """Return the names of the module of family that its entries render."""
    return {entry.removeprefix(TYPE).split(".", 1)[0] for entry in family.entries}


def _gaps() -> list[str]:
    """Return every name and every module that the reference leaves out.

    Every name of the __all__ of each rendered module has an entry. An entry
    names a member of __all__. Every public module of the package is
    rendered or has a reason in UNRENDERED.
    """
    placed: dict[types.ModuleType, set[str]] = {}
    for block in BLOCKS.values():
        for family in block.families:
            placed.setdefault(family.module, set()).update(_placed(family))
    gaps: list[str] = []
    for module, names in placed.items():
        exported = set(module.__all__)
        gaps.extend(
            f"no entry for {_short(module)}.{name}" for name in sorted(exported - names)
        )
        gaps.extend(
            f"an entry for {_short(module)}.{name}, which __all__ lacks"
            for name in sorted(names - exported)
        )
    rendered = {_short(module) for module in placed}
    public = {
        info.name
        for info in pkgutil.iter_modules(dokimi_assert.__path__)
        if not info.name.startswith("_")
    }
    gaps.extend(
        f"no block or reason for the module {name}"
        for name in sorted(public - rendered - set(UNRENDERED))
    )
    gaps.extend(
        f"a reason for {name}, which is no public module"
        for name in sorted(set(UNRENDERED) - public)
    )
    return gaps


def _render_block(block: Block) -> str:
    """Return the text of one block, without its markers."""
    out: list[str] = []
    if block.lead:
        out += [*block.lead, ""]
    for family in block.families:
        out.append(f"**{family.title}.** {family.blurb}")
        out.append("")
        out.append("```python")
        out += [line(family.module, entry) for entry in family.entries]
        out.append("```")
        out.append("")
    out += block.tail
    return "\n".join(out).rstrip("\n")


def render() -> dict[str, str]:
    """Return the text of each block, by the name of its markers."""
    gaps = _gaps()
    if gaps:
        raise SystemExit("api_reference: " + "; ".join(gaps))
    return {name: _render_block(block) for name, block in BLOCKS.items()}


def main() -> int:
    """Print the blocks, or write them into the README."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="edit README.md")
    args = parser.parse_args()

    blocks = render()
    if not args.write:
        for name, text in blocks.items():
            print(f"{_start(name)}\n\n{text}\n\n{_end(name)}\n")
        return 0

    readme = pathlib.Path(__file__).resolve().parent.parent / "README.md"
    text = readme.read_text(encoding="utf-8")
    for name, section in blocks.items():
        start, end = _start(name), _end(name)
        if start not in text or end not in text:
            msg = f"api_reference: README.md has no {start} block"
            raise SystemExit(msg)
        head, rest = text.split(start, 1)
        _, tail = rest.split(end, 1)
        text = f"{head}{start}\n\n{section}\n\n{end}{tail}"
    readme.write_text(text, encoding="utf-8")
    print(f"README.md: {len(blocks)} blocks of the api reference written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
