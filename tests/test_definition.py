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

from dokimi_assert import bench, check, expect, golden, option
from dokimi_assert import seat as seat_module
from dokimi_assert.conformance import definition
from dokimi_assert.seat import Standard

OUTER = Standard()

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
    """Whether module carries name, following a dotted name to its member.

    Stopping at the class would report every member of it present, which
    reports a declined assertion as implemented.
    """
    owner, _, rest = name.partition(".")
    if not rest:
        return hasattr(module, name)
    holder = getattr(module, owner, None)
    return holder is not None and hasattr(holder, rest)


def _surface_for(assertion: str, name: str) -> tuple[Any, str]:
    """Return the module holding an assertion, and the name in it."""
    package = ASSERTIONS[assertion].get("package", "")
    if package:
        return MODULES[package], name.split(".", 1)[1]
    return check, name


def test_the_definition_is_not_empty() -> None:
    """A definition that read nothing would check nothing."""
    check.is_not_empty(OUTER, ASSERTIONS, "the vendored definition states assertions")


def test_every_assertion_has_a_python_name() -> None:
    """The naming table must cover every assertion the standard states."""
    missing = sorted(set(ASSERTIONS) - set(NAMES))
    check.is_empty(OUTER, missing, f"every assertion has a python name: {missing}")


@pytest.mark.parametrize("assertion", sorted(ASSERTIONS))
def test_assertion_is_implemented(assertion: str) -> None:
    """Every assertion the standard states is present unless declined.

    An overlay declining one is checked in both directions. A library
    that ships the member anyway is claiming a gap it does not have,
    which the standard fails the build for.
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
    """An assertion in the root namespace is on both surfaces."""
    name = NAMES[assertion]
    if name in CHECK_ONLY:
        check.not_contains(
            OUTER,
            expect.__all__,
            name,
            f"{name} is off the recording surface: {CHECK_ONLY[name]}",
        )
        return
    check.contains(OUTER, check.__all__, name, f"{name} is on the aborting surface")
    check.contains(OUTER, expect.__all__, name, f"{name} is on the recording surface")


def test_the_surfaces_carry_the_same_members() -> None:
    """Neither surface may carry a member the other does not, bar excuses."""
    check.equal(
        OUTER,
        sorted(expect.__all__),
        sorted(set(check.__all__) - set(CHECK_ONLY)),
        "the two surfaces carry the same members",
    )


def test_every_module_named_by_the_definition_exists() -> None:
    """A package the assertion table names must be importable."""
    named = {a.get("package") for a in ASSERTIONS.values()} - {"", None}
    for package in sorted(named):
        importlib.import_module(f"dokimi_assert.{package}")


def test_the_overlay_extends_the_vendored_version() -> None:
    """An overlay pinned to a version that moved on is stale."""
    check.equal(
        OUTER,
        definition.overlay()["extends"],
        f"spec://assertions@{definition.version()}",
        "the overlay extends the definition this library vendors",
    )


def test_the_overlay_is_this_language() -> None:
    """Vendoring another language's overlay would excuse the wrong gaps."""
    check.equal(
        OUTER,
        definition.overlay()["language"],
        definition.LANGUAGE,
        "the vendored overlay is this language's",
    )


def test_every_divergence_names_an_assertion_the_standard_states() -> None:
    """An overlay excusing a name nobody states excuses nothing."""
    stated = set(ASSERTIONS)
    for entry in definition.overlay()["diverge"]:
        check.contains(
            OUTER,
            stated,
            entry["id"],
            f"{entry['id']} is an assertion the standard states",
        )


def test_every_divergence_says_what_it_is_and_why() -> None:
    """A gap nobody could close and a gap nobody got to look alike.

    Only the reason tells them apart, so the standard requires one.
    """
    for entry in definition.overlay()["diverge"]:
        for field in ("id", "stance", "why"):
            check.is_not_empty(
                OUTER,
                entry.get(field, ""),
                f"the divergence for {entry.get('id', '?')} states {field}",
            )


RELAXATIONS = definition.relaxation_names()


def test_the_definition_states_relaxations() -> None:
    """A definition with none would mean the vendored copy is stale."""
    assert RELAXATIONS, "the definition states relaxations"


@pytest.mark.parametrize("relaxation", sorted(RELAXATIONS))
def test_relaxation_is_offered_or_declined(relaxation: str) -> None:
    """An implementing language answers every relaxation, one way.

    Named and declined is a contradiction; neither is a silent gap. A
    named relaxation has to be importable from the option module under
    exactly that name.
    """
    name = RELAXATIONS[relaxation]
    declined = definition.declines_relaxation(relaxation)

    assert not (name and declined), (
        f"{relaxation}: named {name!r} and declined, which is a contradiction"
    )
    assert name or declined, (
        f"{relaxation}: the table gives no Python name and the overlay "
        "does not decline it"
    )
    if name:
        assert hasattr(option, name), (
            f"{relaxation}: {name} is named and not importable"
        )
        assert callable(getattr(option, name)), f"{relaxation}: {name} is not callable"


SURFACE = definition.surface_names()

#: Where each surface id resolves. A type or member row lands on the
#: seat module's classes; a qualified name reaches through OWNERS the
#: way the assertions do.
SEAT_TYPES = {"seat", "standard-seat", "recorder-seat", "collector-seat"}


#: Where a row lives when its own module owns it rather than the seat.
SURFACE_MODULES = {
    "clock": "clock",
    "system-clock": "clock",
    "failure": "failure",
    "where": "failure",
    "failure.assertion": "failure",
    "failure.contract": "failure",
    "failure.detail": "failure",
    "seat.report": "seat",
    "controlled-clock": "clock",
    "seat.clock": "seat",
    "clock.now": "clock",
    "clock.sleep": "clock",
    "controlled-clock.advance": "clock",
}


def _surface_target(sid: str, name: str) -> tuple[Any, str]:
    """Answer what to look on, and for what, for one surface row."""
    if sid in SURFACE_MODULES:
        module = importlib.import_module(f"dokimi_assert.{SURFACE_MODULES[sid]}")
        if "." not in sid:
            return module, name
        owner_id = sid.split(".", 1)[0]
        # A member of the seat is answered by the seats that carry it,
        # not by the protocol, which states only what a seat may have.
        if owner_id == "seat":
            return module.Recorder, name
        return getattr(module, SURFACE[owner_id]), name

    if sid in {"clock", "system-clock", "failure", "where"}:
        return importlib.import_module("dokimi_assert.clock"), name
    if "." in name:
        owner_name, member = name.split(".", 1)
        return importlib.import_module(f"dokimi_assert.{owner_name}"), member
    if "." in sid:
        owner_id = sid.split(".", 1)[0]
        owner = getattr(seat_module, SURFACE[owner_id])
        return owner, name
    return seat_module, name


def test_the_surface_table_states_something() -> None:
    """A table with nothing would mean the vendored copy is stale."""
    assert SURFACE, "the surface table states ids"


@pytest.mark.parametrize("sid", sorted(SURFACE))
def test_surface_id_is_offered_or_declined(sid: str) -> None:
    """An implementing language answers every surface id, one way."""
    name = SURFACE[sid]
    declined = definition.declines_surface(sid)

    assert not (name and declined), f"{sid}: named {name!r} and declined"
    assert name or declined, (
        f"{sid}: the table gives no Python name and the overlay does not decline it"
    )
    if not name:
        return

    if sid == "contract" or sid.startswith("contract."):
        owner: Any = importlib.import_module("dokimi_assert.bench").Contract
        member = name.split(".")[-1]
        found = owner if sid == "contract" else getattr(owner, member, None)
        assert found is not None, f"{sid}: {name} is named and not implemented"
        return

    owner, member = _surface_target(sid, name)
    assert hasattr(owner, member), f"{sid}: {name} is named and not implemented"
