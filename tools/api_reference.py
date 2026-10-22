"""Render the README's API reference from the code itself.

A signature list written by hand goes stale the first time a parameter
moves. This reads the real signatures, so the README either matches the
code or the documentation test fails.

Run it to refresh the section between the markers in README.md:

    python tools/api_reference.py --write
"""

from __future__ import annotations

import argparse
import inspect
import pathlib
import re
import sys
from typing import Any

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

from dokimi_assert import bench, check, golden

#: Where the generated block starts and ends in README.md.
START = "<!-- api-reference:start -->"
END = "<!-- api-reference:end -->"

#: The families, in the order a reader meets them, and what each one
#: states. A name in no family is a bug this script reports.
FAMILIES: list[tuple[str, str, list[str]]] = [
    (
        "Equality",
        "The comparison is structural and strict about types.",
        ["equal", "not_equal"],
    ),
    (
        "Truth and absence",
        "Python has one null value, None.",
        ["is_true", "is_false", "is_none", "is_not_none"],
    ),
    (
        "Size",
        "Each takes anything with a length. None has no length and fails all three.",
        ["length", "is_empty", "is_not_empty"],
    ),
    (
        "Containment",
        "A str contains a substring, a mapping contains a key, and a "
        "sequence or a set contains an element by the rules of equal. "
        "is_permutation compares two sequences in any order.",
        ["contains", "not_contains", "contains_in_order", "is_permutation"],
    ),
    (
        "Text",
        "Each takes a str and fails on any other value.",
        ["has_prefix", "has_suffix", "matches"],
    ),
    (
        "Numbers",
        "Exact equality is the wrong check for a float.",
        ["close_to", "in_range"],
    ),
    (
        "Ordering",
        "pairwise covers sorted, unique and strictly increasing, because "
        "each of those is a relation between neighbours.",
        ["pairwise"],
    ),
    (
        "Errors",
        "These suit code that returns an error instead of raising it.",
        ["no_error", "has_error", "error_is", "error_is_not", "error_as"],
    ),
    (
        "Raising",
        "raises returns the exception of fn, so a test can assert on its "
        "class or its message.",
        ["raises", "does_not_raise"],
    ),
    (
        "Cancellation",
        "Python cancels work through asyncio. honours_cancellation and "
        "honours_deadline take a coroutine function and run the event "
        "loop themselves, so the test is a plain def. completes_within "
        "calls fn on a daemon thread and fails at the deadline without "
        "waiting for it.",
        [
            "honours_cancellation",
            "honours_deadline",
            "completes_within",
            "none_handle_safe",
        ],
    ),
    (
        "Retrying",
        "These suit a condition that something outside the test makes "
        "true. On the platform clock they spend real time. On a "
        "Controlled clock they advance the clock between attempts.",
        ["eventually", "eventually_true"],
    ),
    (
        "Concurrency",
        "Call what it returns where the scope ends. A thread or an "
        "asyncio task that the scope started and that still runs then "
        "is a leak.",
        ["no_task_leaks"],
    ),
    (
        "Purity",
        "observe must return a copy, because a reading that shares state "
        "with the subject compares one object with itself.",
        ["is_pure", "is_not_pure"],
    ),
    (
        "Relations",
        "Each calls the subject with the values that the test passes. A "
        "relation that compares two results compares them by the rules "
        "of equal.",
        [
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
        ],
    ),
    (
        "Testing an assertion",
        "rejects takes the message before its body. It returns the "
        "failure records of the body, and fails when the body passes.",
        ["rejects"],
    ),
]


def _clean(text: str) -> str:
    """Answer an annotation as it would be written by hand.

    Postponed evaluation means inspect hands these back as quoted
    strings, and a typing alias arrives with its module path in front.
    Neither is what anyone would type.
    """
    text = text.strip("'\"")
    text = re.sub(r"\b[a-z_]+(?:\.[a-z_]+)*\.([A-Z_])", r"\1", text)
    return text.replace("~", "")


def signature(owner: Any, name: str, prefix: str) -> str:
    """Answer one rendered signature line."""
    sig = inspect.signature(getattr(owner, name))
    parts = []
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


def render() -> str:
    """Answer the whole reference section."""
    out: list[str] = []
    placed = {n for _, _, names in FAMILIES for n in names}
    missing = sorted(set(check.__all__) - placed)
    if missing:
        raise SystemExit(f"api_reference: no family for {missing}")

    out.append("Each assertion takes the seat first and the message last.")
    out.append("`check` and `expect` have the same names and the same")
    out.append("signatures. Only what happens on a failure differs.")
    out.append("")

    for title, blurb, names in FAMILIES:
        out.append(f"**{title}.** {blurb}")
        out.append("")
        out.append("```python")
        out += [signature(check, n, "check.") for n in names]
        out.append("```")
        out.append("")

    out.append("**Golden files.** Each comparison reads recorded output and takes")
    out.append("no message. A failure stops the test.")
    out.append("")
    out.append("```python")
    out += [
        signature(golden, n, "golden.")
        for n in ("match", "match_at", "match_json_field", "match_tree")
    ]
    out += [
        signature(golden, n, "golden.")
        for n in (
            "should_update",
            "scrub_timestamps",
            "scrub_hashes",
            "scrub_run_ids",
            "scrub_json_fields",
        )
    ]
    out.append("```")
    out.append("")

    out.append("**Benchmark ceilings.** The ceilings chain onto one contract, and")
    out.append("`check` reports a verdict for each of them.")
    out.append("")
    out.append("```python")
    out.append(signature(bench, "Contract", "bench."))
    out += [
        signature(bench.Contract, n, "Contract.")
        for n in (
            "warmup",
            "max_latency",
            "max_mean",
            "max_bytes",
            "loop",
            "excluding",
            "check",
        )
    ]
    out.append("```")
    out.append("")
    out.append("Read the docstring of an assertion for its rules and the")
    out.append("meaning of each argument, with `help(check.close_to)` or in")
    out.append("your editor.")
    return "\n".join(out)


def main() -> int:
    """Print the section, or write it into the README."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="edit README.md")
    args = parser.parse_args()

    section = render()
    if not args.write:
        print(section)
        return 0

    readme = pathlib.Path(__file__).resolve().parent.parent / "README.md"
    text = readme.read_text()
    if START not in text or END not in text:
        raise SystemExit(f"api_reference: README.md has no {START} block")

    head, rest = text.split(START, 1)
    _, tail = rest.split(END, 1)
    readme.write_text(f"{head}{START}\n\n{section}\n\n{END}{tail}")
    print("README.md: api reference written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
