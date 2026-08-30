"""This library's surface, held to the definition.

The completeness gate: every assertion the standard states must be
present under the name the naming table gives it. A name qualified with
a dot names a member of the module the assertion table gives it, so the
golden and benchmark assertions are looked for where they live.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest

from dokimi import bench, check, expect, golden
from dokimi.conformance import definition

ASSERTIONS = definition.assertions()
NAMES = definition.names()

#: The modules a qualified name may name.
MODULES: dict[str, Any] = {"golden": golden, "bench": bench}

#: Members the recording surface is not expected to carry, with the
#: reason. Each is checked in both directions below.
CHECK_ONLY = {
    "rejects": "drives a check to failure, which needs a seat that stops",
}


def _present(name: str, module: Any) -> bool:
    """Whether module carries name, which for a method is its class."""
    owner, _, rest = name.partition(".")
    if not rest:
        return hasattr(module, name)
    return hasattr(module, owner)


def _surface_for(assertion: str, name: str) -> tuple[Any, str]:
    """Return the module holding an assertion, and the name in it."""
    package = ASSERTIONS[assertion].get("package", "")
    if package:
        return MODULES[package], name.split(".", 1)[1]
    return check, name


def test_the_definition_is_not_empty() -> None:
    """A definition that read nothing would check nothing."""
    assert ASSERTIONS, "the vendored definition states no assertions"


def test_every_assertion_has_a_python_name() -> None:
    """The naming table must cover every assertion the standard states."""
    missing = sorted(set(ASSERTIONS) - set(NAMES))
    assert not missing, f"no python name for: {missing}"


@pytest.mark.parametrize("assertion", sorted(ASSERTIONS))
def test_assertion_is_implemented(assertion: str) -> None:
    """Every assertion the standard states must be present."""
    module, name = _surface_for(assertion, NAMES[assertion])
    assert _present(name, module), f"{assertion}: {NAMES[assertion]} is not implemented"


@pytest.mark.parametrize(
    "assertion",
    sorted(a for a in ASSERTIONS if not ASSERTIONS[a].get("package")),
)
def test_unqualified_assertion_is_on_both_surfaces(assertion: str) -> None:
    """An assertion in the root namespace is on both surfaces."""
    name = NAMES[assertion]
    if name in CHECK_ONLY:
        assert name not in expect.__all__, (
            f"{name} is excused from the recording surface "
            f"({CHECK_ONLY[name]}) but present in it"
        )
        return
    assert name in check.__all__, f"{name} missing from check"
    assert name in expect.__all__, f"{name} missing from expect"


def test_the_surfaces_carry_the_same_members() -> None:
    """Neither surface may carry a member the other does not, bar excuses."""
    assert sorted(set(check.__all__) - set(CHECK_ONLY)) == sorted(expect.__all__)


def test_every_module_named_by_the_definition_exists() -> None:
    """A package the assertion table names must be importable."""
    named = {a.get("package") for a in ASSERTIONS.values()} - {"", None}
    for package in sorted(named):
        importlib.import_module(f"dokimi.{package}")
