# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""This spec checks the surface of this library against the definition.

The completeness gate checks that every assertion of the definition has the
name that the naming table gives it. A name with a dot refers to a member of
the module that the assertion table gives, so the gate finds the golden and
benchmark assertions in their modules.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
from typing import Any, Protocol

import pytest

from dokimi_assert import (
    bench,
    check,
    expect,
    files,
    golden,
    history,
    option,
    prop,
    stateful,
)
from dokimi_assert import seat as seat_module
from dokimi_assert.conformance import definition
from dokimi_assert.seat import Standard

OUTER = Standard()

ASSERTIONS = definition.assertions()
NAMES = definition.names()

#: The modules that a qualified name can start with.
MODULES: dict[str, Any] = {
    "golden": golden,
    "bench": bench,
    "prop": prop,
    "files": files,
    "history": history,
    "stateful": stateful,
}


def _present(name: str, module: Any) -> bool:
    """Return True when module has name. A dotted name refers to a member of a class.

    A check that stops at the class reports every member of the class as
    present, and so reports a declined assertion as implemented.
    """
    owner, _, rest = name.partition(".")
    if not rest:
        return hasattr(module, name)
    holder = getattr(module, owner, None)
    return holder is not None and hasattr(holder, rest)


def _surface_for(assertion: str, name: str) -> tuple[Any, str]:
    """Return the module of an assertion and the name of the assertion in it."""
    package = ASSERTIONS[assertion].get("package", "")
    if package:
        return MODULES[package], name.split(".", 1)[1]
    return check, name


def test_the_definition_is_not_empty() -> None:
    """A definition without assertions does not check anything."""
    check.is_not_empty(OUTER, ASSERTIONS, "the vendored definition has assertions")


def test_every_assertion_has_a_python_name() -> None:
    """The naming table has a Python name for every assertion of the definition."""
    missing = sorted(set(ASSERTIONS) - set(NAMES))
    check.is_empty(OUTER, missing, f"every assertion has a python name: {missing}")


@pytest.mark.parametrize("assertion", sorted(ASSERTIONS))
def test_assertion_is_implemented(assertion: str) -> None:
    """Every assertion of the definition is present unless the overlay declines it.

    The test checks a declined assertion in both directions. The definition
    fails the build of a library that exports a member that its overlay
    declines.
    """
    module, name = _surface_for(assertion, NAMES[assertion])
    if definition.diverges(assertion):
        check.is_false(
            OUTER,
            _present(name, module),
            f"{assertion} is declined by the overlay, so {NAMES[assertion]} is absent",
        )
        return
    check.is_true(
        OUTER,
        _present(name, module),
        f"{assertion} is implemented as {NAMES[assertion]}",
    )


@pytest.mark.parametrize(
    "assertion",
    sorted(a for a in ASSERTIONS if not ASSERTIONS[a].get("package")),
)
def test_unqualified_assertion_is_on_both_surfaces(assertion: str) -> None:
    """An assertion in the root namespace is on both surfaces.

    An assertion that the overlay declines is on neither surface.
    """
    name = NAMES[assertion]
    if definition.diverges(assertion):
        declined = f"{name} is declined by the overlay"
        check.not_contains(
            OUTER,
            check.__all__,
            name,
            f"{declined}, so it is not on the aborting surface",
        )
        check.not_contains(
            OUTER,
            expect.__all__,
            name,
            f"{declined}, so it is not on the recording surface",
        )
        return
    check.contains(OUTER, check.__all__, name, f"{name} is on the aborting surface")
    check.contains(OUTER, expect.__all__, name, f"{name} is on the recording surface")


def test_the_surfaces_have_the_same_members() -> None:
    """The aborting surface and the recording surface have the same members."""
    check.equal(
        OUTER,
        sorted(expect.__all__),
        sorted(check.__all__),
        "the two surfaces have the same members",
    )


def test_every_module_of_the_definition_exists() -> None:
    """Every package of the assertion table is importable."""
    named = {a.get("package") for a in ASSERTIONS.values()} - {"", None}
    for package in sorted(named):
        importlib.import_module(f"dokimi_assert.{package}")


def test_the_overlay_extends_the_vendored_version() -> None:
    """An overlay of an older version of the definition is stale."""
    check.equal(
        OUTER,
        definition.overlay()["extends"],
        f"spec://assertions@{definition.version()}",
        "the overlay extends the definition this library vendors",
    )


def test_the_overlay_is_this_language() -> None:
    """The overlay of another language would decline the wrong assertions."""
    check.equal(
        OUTER,
        definition.overlay()["language"],
        definition.LANGUAGE,
        "the vendored overlay is the overlay of Python",
    )


def test_every_divergence_has_an_assertion_of_the_definition() -> None:
    """A divergence of an unknown assertion does not decline anything."""
    stated = set(ASSERTIONS)
    for entry in definition.overlay()["diverge"]:
        check.contains(
            OUTER,
            stated,
            entry["id"],
            f"{entry['id']} is an assertion of the definition",
        )


def test_every_divergence_has_an_id_a_stance_and_a_reason() -> None:
    """A divergence has an id, a stance and a reason.

    The reason separates a gap that the language cannot close from a gap that
    the library has not closed, so the definition requires it.
    """
    for entry in definition.overlay()["diverge"]:
        for field in ("id", "stance", "why"):
            check.is_not_empty(
                OUTER,
                entry.get(field, ""),
                f"the divergence of {entry.get('id', '?')} has {field}",
            )


RELAXATIONS = definition.relaxation_names()


def test_the_definition_has_relaxations() -> None:
    """A definition without relaxations is a stale vendored copy."""
    assert RELAXATIONS, "the definition has relaxations"


@pytest.mark.parametrize("relaxation", sorted(RELAXATIONS))
def test_relaxation_is_offered_or_declined(relaxation: str) -> None:
    """The library either names or declines every relaxation.

    A relaxation with a name and a decline is a contradiction, and a
    relaxation with neither is a silent gap. A named relaxation is importable
    from the option module under that name.
    """
    name = RELAXATIONS[relaxation]
    declined = definition.declines_relaxation(relaxation)

    assert not (name and declined), (
        f"{relaxation}: the relaxation has the name {name!r} and a decline"
    )
    assert name or declined, (
        f"{relaxation}: the table does not have a Python name, and the overlay "
        "does not decline it"
    )
    if name:
        assert hasattr(option, name), f"{relaxation}: {name} is not importable"
        assert callable(getattr(option, name)), f"{relaxation}: {name} is not callable"


SURFACE = definition.surface_names()


#: The module of each surface row that is not in the seat module.
SURFACE_MODULES = {
    "clock": "clock",
    "system-clock": "clock",
    "failure": "failure",
    "where": "failure",
    "failure.assertion": "failure",
    "failure.contract": "failure",
    "failure.detail": "failure",
    "seat.report": "seat",
    "seat.report-fault": "seat",
    "assertion-call": "call",
    "assertion-call.assertion": "call",
    "assertion-call.contract": "call",
    "allocs-checked": "bench",
    "controlled-clock": "clock",
    "seat.clock": "seat",
    "clock.now": "clock",
    "clock.sleep": "clock",
    "controlled-clock.advance": "clock",
}


def _module_target(sid: str, name: str) -> tuple[Any, str]:
    """Return the object of a surface row of SURFACE_MODULES, and the name in it."""
    module = importlib.import_module(f"dokimi_assert.{SURFACE_MODULES[sid]}")
    if "." not in sid:
        return module, name
    owner_id = sid.split(".", 1)[0]
    # The seats have the members of a seat. The protocol does not have the
    # optional members.
    if owner_id == "seat":
        return module.Recorder, name
    return getattr(module, SURFACE[owner_id]), name


def _surface_target(sid: str, name: str) -> tuple[Any, str]:
    """Return the object that has a surface row, and the name of the row in it."""
    if sid in SURFACE_MODULES:
        return _module_target(sid, name)
    if "." in name:
        # A name that ends in () is the constructor of its class.
        owner_name, member = name.split(".", 1)
        module = importlib.import_module(f"dokimi_assert.{owner_name}")
        return module, member.removesuffix("()")
    if "." in sid:
        owner_id = sid.split(".", 1)[0]
        owner_name, _, member = SURFACE[owner_id].rpartition(".")
        module = importlib.import_module(f"dokimi_assert.{owner_name or 'seat'}")
        if name.endswith("()"):
            return module, name.removesuffix("()")
        return getattr(module, member), name
    return seat_module, name


def _offered(owner: Any, member: str) -> bool:
    """Report whether owner has member.

    A field of a dataclass without a default is not an attribute of its
    class. A protocol documents an optional member in its docstring, because
    a protocol cannot declare one, as Spec documents equal(a, b).
    """
    if hasattr(owner, member):
        return True
    if dataclasses.is_dataclass(owner):
        return member in {f.name for f in dataclasses.fields(owner)}
    if Protocol in getattr(owner, "__mro__", ()):
        return f"{member}(" in (inspect.getdoc(owner) or "")
    return False


def test_the_surface_table_has_ids() -> None:
    """An empty table is a stale vendored copy."""
    assert SURFACE, "the surface table has ids"


@pytest.mark.parametrize("sid", sorted(SURFACE))
def test_surface_id_is_offered_or_declined(sid: str) -> None:
    """The library either names or declines every surface id."""
    name = SURFACE[sid]
    declined = definition.declines_surface(sid)

    assert not (name and declined), f"{sid}: the id has the name {name!r} and a decline"
    assert name or declined, (
        f"{sid}: the table does not have a Python name, and the overlay does not "
        "decline it"
    )
    if not name:
        return

    if sid == "contract" or sid.startswith("contract."):
        owner: Any = importlib.import_module("dokimi_assert.bench").Contract
        member = name.split(".")[-1]
        found = owner if sid == "contract" else getattr(owner, member, None)
        assert found is not None, f"{sid}: {name} is not implemented"
        return

    owner, member = _surface_target(sid, name)
    assert _offered(owner, member), f"{sid}: {name} is not implemented"
