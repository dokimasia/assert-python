"""The spec of conformance/prop/forms.py tests the runner of the forms vectors."""

from __future__ import annotations

from typing import Any, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.prop.forms import forms_of
from dokimi_assert.conformance.vector import vectors
from dokimi_assert.seat import Collector

#: The forms vectors of the definition, by id.
FORMS = {v.id: v.raw for v in vectors() if v.kind == "forms"}


def vector(id: str, **changes: Any) -> dict[str, Any]:
    """Return the forms vector of an id with changes to its members."""
    return {**FORMS[id], **changes}


def fault_of(seat: Collector, raw: dict[str, Any]) -> tuple[str, str]:
    """Return the place and the reason of the fault that forms_of raises for raw."""
    error = check.raises(seat, lambda: forms_of(raw), "forms_of refuses the vector")
    found = cast("FaultError", check.error_as(seat, error, FaultError, "a fault"))
    return found.at, found.reason


class TestFormsOf:
    """forms_of returns the detail of the call record of the form of a vector."""

    @pytest.mark.parametrize("id", sorted(FORMS))
    def test_returns_the_detail_of_the_vector(self, seat: Collector, id: str) -> None:
        """The form of the vector runs as the definition states."""
        check.equal(
            seat,
            forms_of(FORMS[id])["detail"],
            FORMS[id]["detail"],
            "the form has the detail of its vector",
        )

    def test_returns_another_detail_for_another_subject(self, seat: Collector) -> None:
        """Two functions that return the input pass prop-equal."""
        raw = vector(
            "prop-equal/fails-when-a-sort-reorders-the-input",
            subjects=["identity", "identity"],
        )
        check.not_equal(
            seat,
            forms_of(raw)["detail"],
            raw["detail"],
            "the run of another subject has another detail",
        )

    def test_returns_the_assertion_alone_for_a_failure_without_a_detail(
        self, seat: Collector
    ) -> None:
        """The vector does not have a field of the detail of its failure."""
        raw = vector("prop-true/fails-for-a-negative-input")
        raw["detail"] = {**raw["detail"], "failure": {"assertion": "true"}}
        check.equal(
            seat,
            forms_of(raw)["detail"]["failure"],
            {"assertion": "true", "detail": {}},
            "the failure keeps the fields that the vector has",
        )

    refused: ClassVar[list[tuple[str, dict[str, Any], tuple[str, str]]]] = [
        (
            "raises at the form for a form that a vector does not run",
            {"form": "prop-widget"},
            ("form", '"prop-widget" is not a form that a vector runs'),
        ),
        (
            "raises for a vector without a shape or a generator",
            {"form": "prop-true", "subjects": ["is-non-negative"], "seed": "1"},
            ("", "the vector has neither a shape nor a generator, or both"),
        ),
        (
            "raises for a vector with a shape and a generator",
            {
                "form": "prop-true",
                "shape": {"shape": "bool"},
                "generator": {"gen": "boolean"},
                "seed": "1",
            },
            ("", "the vector has neither a shape nor a generator, or both"),
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in refused], ids=[t[0] for t in refused]
    )
    def test_raises_for_a_vector_that_the_runner_cannot_take(
        self, seat: Collector, give: dict[str, Any], want: tuple[str, str]
    ) -> None:
        """The fault is at the member of the vector."""
        check.equal(seat, fault_of(seat, give), want, "the fault is at the member")

    subjects: ClassVar[list[tuple[str, str, list[object], tuple[str, str]]]] = [
        (
            "raises for a function subject that the table does not have",
            "prop-true/fails-for-a-negative-input",
            ["triples"],
            ("subjects[0]", '"triples" is not a subject that the form takes'),
        ),
        (
            "raises for a predicate subject that the table does not have",
            "prop-pairwise/fails-for-a-list-out-of-order",
            ["identity", "descending"],
            ("subjects[1]", '"descending" is not a subject that the form takes'),
        ),
        (
            "raises for a subject kind without a member of the form",
            "prop-pure/fails-when-the-call-changes-the-state",
            ["adds"],
            ("subjects[0]", '"adds" is not a subject that the form takes'),
        ),
        (
            "raises for a subject kind that is not a string",
            "prop-pure/fails-when-the-call-changes-the-state",
            [5],
            ("subjects[0]", "5 is not a subject that the form takes"),
        ),
        (
            "raises for a vector without subjects",
            "prop-true/fails-for-a-negative-input",
            [],
            ("subjects[0]", "null is not a subject that the form takes"),
        ),
    ]

    @pytest.mark.parametrize(
        ("give_id", "give", "want"),
        [t[1:] for t in subjects],
        ids=[t[0] for t in subjects],
    )
    def test_raises_at_the_subjects_for_a_subject_that_the_form_does_not_take(
        self,
        seat: Collector,
        give_id: str,
        give: list[object],
        want: tuple[str, str],
    ) -> None:
        """The fault is at the subject kind."""
        check.equal(
            seat,
            fault_of(seat, vector(give_id, subjects=give)),
            want,
            "the fault is at the subject kind",
        )

    def test_raises_for_a_form_that_ends_with_a_fault(self, seat: Collector) -> None:
        """The generator of the input does not produce the example."""
        raw = vector(
            "prop-true/passes-its-three-examples",
            examples=[{"type": "int", "value": -5}],
        )
        at, reason = fault_of(seat, raw)
        check.equal(seat, at, "", "the fault is at the vector")
        check.has_prefix(
            seat,
            reason,
            'the form ends with the fault "prop.is_true: examples[0][0]: the '
            "generator of the input does not produce the value",
            "the fault has the fault of the form",
        )
