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

from dokimi_assert import bench, check, golden  # noqa: E402

#: Where the generated block starts and ends in README.md.
START = "<!-- api-reference:start -->"
END = "<!-- api-reference:end -->"

#: The families, in the order a reader meets them, and what each one
#: states. A name in no family is a bug this script reports.
FAMILIES: list[tuple[str, str, list[str]]] = [
    ("Equality", "Structural, and strict about types.", ["equal", "not_equal"]),
    (
        "Truth and absence",
        "The two-value cases.",
        ["is_true", "is_false", "is_none", "is_not_none"],
    ),
    ("Size", "Anything with a length.", ["length", "is_empty", "is_not_empty"]),
    (
        "Containment",
        "What holding means follows the haystack.",
        ["contains", "not_contains", "contains_in_order"],
    ),
    ("Text", "str and bytes.", ["has_prefix", "has_suffix", "matches"]),
    (
        "Numbers",
        "Where exact equality is the wrong question.",
        ["close_to", "in_range"],
    ),
    (
        "Ordering",
        "Sorted, unique, and anything else that holds between neighbours.",
        ["pairwise"],
    ),
    (
        "Errors",
        "For code that hands an error back rather than raising it.",
        ["no_error", "has_error", "error_is", "error_is_not", "error_as"],
    ),
    ("Raising", "For code that raises.", ["raises", "does_not_raise"]),
    (
        "Cancellation",
        "asyncio is Python's cancellation model. These run the "
        "loop themselves, so your test stays a plain def.",
        [
            "honours_cancellation",
            "honours_deadline",
            "completes_within",
            "none_handle_safe",
        ],
    ),
    (
        "Retrying",
        "For a condition something outside the test makes true. Both spend real time.",
        ["eventually", "eventually_true"],
    ),
    ("Concurrency", "Call what it returns where the scope ends.", ["no_task_leaks"]),
    ("Purity", "What observe returns defines what nothing means.", ["is_pure"]),
    (
        "Testing an assertion",
        "On check only: expect cannot drive a check to "
        "failure, because it does not stop.",
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
    tail = "" if ret == "None" else f" -> {ret}"
    return f"{prefix}{name}({', '.join(parts)}){tail}"


def render() -> str:
    """Answer the whole reference section."""
    out: list[str] = []
    placed = {n for _, _, names in FAMILIES for n in names}
    missing = sorted(set(check.__all__) - placed)
    if missing:
        raise SystemExit(f"api_reference: no family for {missing}")

    out.append("Every assertion takes the seat first and the message last.")
    out.append("`check` and `expect` carry the same names and the same")
    out.append("signatures; only what happens on a failure differs.")
    out.append("")

    for title, blurb, names in FAMILIES:
        out.append(f"**{title}** — {blurb}")
        out.append("")
        out.append("```python")
        out += [signature(check, n, "check.") for n in names]
        out.append("```")
        out.append("")

    out.append("**Golden files** — recorded output, compared and rewritable.")
    out.append("")
    out.append("```python")
    out += [
        signature(golden, n, "golden.")
        for n in ("match", "match_at", "match_json_field")
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

    out.append("**Benchmark ceilings** — chained onto one contract.")
    out.append("")
    out.append("```python")
    out.append(signature(bench.Contract, "loop", "Contract."))
    out += [
        signature(bench.Contract, n, "Contract.")
        for n in ("max_latency", "max_mean", "max_allocs", "max_bytes")
    ]
    out.append("```")
    out.append("")
    out.append("Each one carries a full docstring: what it states, what every")
    out.append("argument means, the edge cases it decides, and a worked call.")
    out.append("Read them with `help(check.close_to)` or in your editor.")
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
