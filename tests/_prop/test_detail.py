# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/detail.py tests the record and the sentence of a property run."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._override import override
from dokimi_assert._prop.case import Failing
from dokimi_assert._prop.detail import (
    FOR_ALL,
    Divergence,
    Drawn,
    Other,
    Shortfall,
    Step,
    detail_json,
    detail_of,
    record_of,
    register_sentences,
    sentence,
)
from dokimi_assert._prop.engine.case import Case, Failed, Place, Replaying
from dokimi_assert._prop.engine.case import Step as EngineStep
from dokimi_assert._prop.engine.choice import (
    UINT64_MAX,
    FloatBounds,
    IntegerBounds,
    SequenceBounds,
)
from dokimi_assert._prop.engine.execution import Divergence as EngineDivergence
from dokimi_assert._prop.engine.execution import Execution
from dokimi_assert._prop.engine.generator import Integer, Mapped
from dokimi_assert._prop.engine.runner import Kind, Outcome, Requirement
from dokimi_assert._prop.engine.runner import Shortfall as EngineShortfall
from dokimi_assert._prop.engine.shrink import Explained
from dokimi_assert._prop.engine.tokens import encode
from dokimi_assert._prop.identity import key_of, of_record
from dokimi_assert.failure import Failure, Where, render
from helpers import integers

if TYPE_CHECKING:
    from collections.abc import Callable

    from dokimi_assert.seat import Collector

#: The location of the failures.
WHERE = Where("/work/tests/test_total.py", 9)

#: The record of the failing cases.
RECORD = Failure("equal", "the totals agree", {"want": 1, "got": 2}, WHERE)

#: A generator of one digit.
DIGITS = Integer(IntegerBounds(0, 9))

#: The token of a case of the choice 3.
THREE = encode(integers(3))

#: The replay token of an outcome. The specs do not decode it.
REPLAY = "prop1:AQ"


class Probe:
    """A value with a fixed repr and without a typed literal."""

    @override
    def __repr__(self) -> str:
        """Return the text that the opaque literal contains."""
        return "Probe()"


def failing(value: int, fill: Callable[[Case], object] = lambda _: None) -> Execution:
    """Return a failed execution of one draw of x.

    fill adds the steps and the notes of the case.
    """
    c = Case(Replaying(integers(value)))
    c.draw(DIGITS, "x")
    fill(c)
    identity = of_record(RECORD)
    return Execution(c, "failed", Failed(key_of(identity), Failing(RECORD, identity)))


def outcome(kind: Kind, **parts: Any) -> Outcome:
    """Return an outcome of kind with 3 valid and 1 rejected cases of the seed 7."""
    return Outcome(kind, 3, 1, 7, **parts)


def flaky(divergence: EngineDivergence) -> Outcome:
    """Return the outcome of a flaky run of a divergence."""
    return outcome("flaky", divergence=divergence)


#: A counterexample of x = 5 with another failure of x = 3. The explanation of
#: x has the nearest passing value 4.
COUNTEREXAMPLE = outcome(
    "counterexample",
    failing=failing(5, lambda c: c.note("seen 5")),
    explanation=(Explained("x", 5, False, (4,)),),
    others=(failing(3),),
    token=REPLAY,
)


class TestForAll:
    """FOR_ALL is the id of the assertion of for_all."""

    def test_is_the_id_of_the_assertion_of_for_all(self, seat: Collector) -> None:
        """The id comes from the definition."""
        check.equal(seat, FOR_ALL, "prop-for-all", "FOR_ALL is prop-for-all")


class TestDrawn:
    """Drawn is one draw of a counterexample."""

    def test_does_not_have_a_nearest_passing_value_by_default(
        self, seat: Collector
    ) -> None:
        """The explain phase did not test the draw."""
        check.is_none(
            seat,
            Drawn("x", 5, None).nearest_passing,
            "the draw does not have a nearest passing value",
        )


class TestStep:
    """Step is one step of a machine in a counterexample."""

    def test_does_not_have_a_client_or_a_drain_mark_by_default(
        self, seat: Collector
    ) -> None:
        """The step is a step of the sequential part."""
        step = Step("put")
        check.equal(
            seat,
            [step.client, step.drain],
            [None, False],
            "the step does not have a client or a drain mark",
        )


class TestOther:
    """Other is a further failure of a run."""

    def test_keeps_its_counterexample_its_failure_and_its_token(
        self, seat: Collector
    ) -> None:
        """Other has three fields."""
        other = Other([Drawn("x", 3, None)], RECORD, THREE)
        check.equal(
            seat,
            [other.counterexample, other.failure, other.choices],
            [[Drawn("x", 3, None)], RECORD, THREE],
            "Other keeps its three fields",
        )


class TestDivergence:
    """Divergence is the first difference between a failing case and its replay."""

    def test_keeps_the_place_of_the_difference(self, seat: Collector) -> None:
        """The place is the label and the step."""
        divergence = Divergence("request", 2, None, None, "x", Place("swarm"))
        check.equal(
            seat,
            [divergence.label, divergence.step],
            ["x", Place("swarm")],
            "the divergence keeps the label and the step",
        )


class TestShortfall:
    """Shortfall is a coverage requirement that a run missed."""

    def test_keeps_the_requirement_and_its_counts(self, seat: Collector) -> None:
        """Shortfall has five fields."""
        shortfall = Shortfall("even", 0.5, 1, 100, "unmet")
        check.equal(
            seat,
            [
                shortfall.label,
                shortfall.share,
                shortfall.counted,
                shortfall.valid,
                shortfall.verdict,
            ],
            ["even", 0.5, 1, 100, "unmet"],
            "Shortfall keeps its five fields",
        )


class TestDetailOf:
    """detail_of returns the detail of the record of a run."""

    def test_returns_none_for_every_part_of_a_run_that_passed(
        self, seat: Collector
    ) -> None:
        """The run passed."""
        check.equal(
            seat,
            detail_of(outcome("passed")),
            {
                "outcome": "passed",
                "cases": 3,
                "rejected": 1,
                "seed": "7",
                "counterexample": None,
                "failure": None,
                "choices": None,
                "others": None,
                "divergence": None,
                "coverage": None,
                "reason": None,
            },
            "the detail of a pass has the counts and the seed alone",
        )

    def test_returns_the_reason_of_a_run_that_skipped(self, seat: Collector) -> None:
        """The run skipped."""
        check.equal(
            seat,
            detail_of(outcome("skipped", reason="unsupported")),
            {
                "outcome": "skipped",
                "cases": 3,
                "rejected": 1,
                "seed": "7",
                "counterexample": None,
                "failure": None,
                "choices": None,
                "others": None,
                "divergence": None,
                "coverage": None,
                "reason": "unsupported",
            },
            "the detail of a skip has the counts, the seed and the reason",
        )

    def test_returns_every_part_of_a_counterexample(self, seat: Collector) -> None:
        """The detail has the draw, the record, the token and the other failure."""
        d = detail_of(COUNTEREXAMPLE)
        check.equal(
            seat,
            [d["counterexample"], d["failure"], d["choices"], d["others"]],
            [
                [Drawn("x", 5, False, 4)],
                RECORD,
                "prop1:AQ",
                [Other([Drawn("x", 3, None)], RECORD, THREE)],
            ],
            "the detail has every part of the counterexample",
        )

    def test_does_not_return_a_token_for_a_counterexample_of_values(
        self, seat: Collector
    ) -> None:
        """An example of values does not have a token."""
        d = detail_of(outcome("counterexample", failing=failing(5), valued=True))
        check.is_none(seat, d["choices"], "the detail does not have a token")

    def test_returns_the_steps_of_a_machine_between_the_draws(
        self, seat: Collector
    ) -> None:
        """The steps follow the draw."""

        def fill(c: Case) -> None:
            c.step(EngineStep("put", client=1))
            c.step(EngineStep("deliver", drain=True))
            c.step(EngineStep("get"))

        d = detail_of(outcome("counterexample", failing=failing(5, fill)))
        check.equal(
            seat,
            d["counterexample"],
            [
                Drawn("x", 5, None),
                Step("put", 1),
                Step("deliver", drain=True),
                Step("get"),
            ],
            "the steps follow the draw",
        )

    def test_returns_the_case_of_a_flaky_run_without_its_token(
        self, seat: Collector
    ) -> None:
        """The detail of a flaky run does not have a token."""
        d = detail_of(outcome("flaky", failing=failing(5), token=REPLAY))
        check.equal(
            seat,
            [d["failure"], d["choices"], d["others"]],
            [RECORD, None, None],
            "the detail has the failure alone",
        )

    tests: ClassVar[list[tuple[str, EngineDivergence, list[Any]]]] = [
        (
            "returns the sides of an integer request against no request",
            EngineDivergence("request", 2, IntegerBounds(0, 9), None),
            [{"kind": "integer", "min": 0, "max": 9}, None],
        ),
        (
            "returns the sides of a float request against a sequence request",
            EngineDivergence(
                "request", 0, FloatBounds(0.0, 1.0, True, 32), SequenceBounds(4, 1)
            ),
            [
                {
                    "kind": "float",
                    "min": 0.0,
                    "max": 1.0,
                    "allow_nan": True,
                    "width": 32,
                },
                {"kind": "sequence", "k": 4, "min_size": 1, "max_size": None},
            ],
        ),
        (
            "returns the sides of two fingerprints",
            EngineDivergence("fingerprint", 1, 5, 6),
            [5, 6],
        ),
        (
            "returns the sides of the identity of a failure against a pass",
            EngineDivergence("verdict", 3, key_of(of_record(RECORD)), None),
            ["equal at test_total.py:9", None],
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_returns_the_sides_of_a_divergence(
        self, seat: Collector, give: EngineDivergence, want: list[Any]
    ) -> None:
        """The divergence has a recorded side and a replayed side."""
        divergence: Divergence = detail_of(flaky(give))["divergence"]
        check.equal(
            seat,
            [divergence.recorded, divergence.replayed],
            want,
            "the divergence has the two sides",
        )

    def test_returns_the_place_at_which_a_run_diverged(self, seat: Collector) -> None:
        """The place is the label and the step of the machine."""
        place = Place("sequential", 1, "put")
        divergence = EngineDivergence("request", 2, None, None, "x", place)
        check.equal(
            seat,
            detail_of(flaky(divergence))["divergence"],
            Divergence("request", 2, None, None, "x", place),
            "the divergence has the place",
        )

    def test_returns_the_requirement_that_a_coverage_unmet_run_missed(
        self, seat: Collector
    ) -> None:
        """The run left the requirement unmet."""
        shortfall = EngineShortfall(Requirement("even", 0.5), 1, 100, "unmet")
        check.equal(
            seat,
            detail_of(outcome("coverage-unmet", shortfall=shortfall))["coverage"],
            Shortfall("even", 0.5, 1, 100, "unmet"),
            "the detail has the shortfall",
        )


class TestDetailJson:
    """detail_json returns the detail of a run in the form of its call record."""

    def test_returns_each_generated_value_as_a_typed_literal_of_its_generator(
        self, seat: Collector
    ) -> None:
        """The value 5 and its nearest passing value 4 are typed literals."""
        json = detail_json(COUNTEREXAMPLE, detail_of(COUNTEREXAMPLE))
        check.equal(
            seat,
            json["counterexample"],
            [
                {
                    "label": "x",
                    "value": {"type": "int", "value": 5},
                    "any-value-fails": False,
                    "nearest-passing": {"type": "int", "value": 4},
                }
            ],
            "the counterexample has typed literals",
        )

    def test_returns_none_as_the_nearest_passing_value_of_an_untested_draw(
        self, seat: Collector
    ) -> None:
        """The explain phase did not test the draw."""
        run = outcome("counterexample", failing=failing(5))
        check.equal(
            seat,
            detail_json(run, detail_of(run))["counterexample"],
            [
                {
                    "label": "x",
                    "value": {"type": "int", "value": 5},
                    "any-value-fails": None,
                    "nearest-passing": None,
                }
            ],
            "the draw does not have a nearest passing value",
        )

    def test_returns_the_opaque_literal_of_a_value_without_a_typed_literal(
        self, seat: Collector
    ) -> None:
        """Both values are opaque."""
        c = Case(Replaying(integers(1)))
        c.draw(Mapped(DIGITS, lambda _: Probe()), "f")
        identity = of_record(RECORD)
        run = outcome(
            "counterexample",
            failing=Execution(
                c, "failed", Failed(key_of(identity), Failing(RECORD, identity))
            ),
            explanation=(Explained("f", Probe(), True, (Probe(),)),),
        )
        check.equal(
            seat,
            detail_json(run, detail_of(run))["counterexample"],
            [
                {
                    "label": "f",
                    "value": {"type": "opaque", "text": "Probe()"},
                    "any-value-fails": True,
                    "nearest-passing": {"type": "opaque", "text": "Probe()"},
                }
            ],
            "both values are opaque literals",
        )

    def test_returns_the_failure_as_the_json_of_its_record(
        self, seat: Collector
    ) -> None:
        """The record has an assertion, a contract, a detail and a location."""
        json = detail_json(COUNTEREXAMPLE, detail_of(COUNTEREXAMPLE))
        check.equal(
            seat,
            json["failure"],
            {
                "assertion": "equal",
                "contract": "the totals agree",
                "detail": {
                    "want": {"type": "int", "value": 1},
                    "got": {"type": "int", "value": 2},
                },
                "where": {"file": "test_total.py", "line": 9},
            },
            "the failure is the JSON of its record",
        )

    def test_returns_the_record_of_a_message_without_an_assertion_or_a_location(
        self, seat: Collector
    ) -> None:
        """The record is a message."""
        message = Failure("", "it broke")
        identity = of_record(message)
        run = outcome(
            "counterexample",
            failing=Execution(
                Case(Replaying([])),
                "failed",
                Failed(key_of(identity), Failing(message, identity)),
            ),
        )
        check.equal(
            seat,
            detail_json(run, detail_of(run))["failure"],
            {"assertion": None, "contract": "it broke", "detail": {}, "where": None},
            "the record does not have an assertion or a location",
        )

    def test_returns_each_other_failure_as_a_brief_counterexample_with_its_token(
        self, seat: Collector
    ) -> None:
        """The run has one other failure."""
        json = detail_json(COUNTEREXAMPLE, detail_of(COUNTEREXAMPLE))
        other = json["others"][0]
        check.equal(
            seat,
            [other["counterexample"], other["choices"]],
            [[{"label": "x", "value": {"type": "int", "value": 3}}], THREE],
            "the other failure has a brief counterexample and a token",
        )

    def test_returns_the_steps_of_a_machine_with_their_client_and_drain_mark(
        self, seat: Collector
    ) -> None:
        """The case has two steps."""

        def fill(c: Case) -> None:
            c.step(EngineStep("put"))
            c.step(EngineStep("deliver", 1, True))

        run = outcome("counterexample", failing=failing(5, fill))
        check.equal(
            seat,
            detail_json(run, detail_of(run))["counterexample"][1:],
            [{"step": "put"}, {"step": "deliver", "client": 1, "drain": True}],
            "the steps have their client and drain mark",
        )

    def test_returns_the_fingerprints_of_a_divergence_as_numbers(
        self, seat: Collector
    ) -> None:
        """A fingerprint past 2^53 - 1 is a decimal string."""
        run = flaky(EngineDivergence("fingerprint", 0, UINT64_MAX, None))
        divergence = detail_json(run, detail_of(run))["divergence"]
        check.equal(
            seat,
            [divergence["recorded"], divergence["replayed"]],
            [str(UINT64_MAX), None],
            "the fingerprints are numbers",
        )

    def test_returns_the_place_of_a_divergence(self, seat: Collector) -> None:
        """The place is the label and the step."""
        run = flaky(
            EngineDivergence("request", 2, None, None, "x", Place("swarm", None, "put"))
        )
        check.equal(
            seat,
            detail_json(run, detail_of(run))["divergence"],
            {
                "what": "request",
                "index": 2,
                "recorded": None,
                "replayed": None,
                "label": "x",
                "step": {"part": "swarm", "position": None, "action": "put"},
            },
            "the divergence has the place",
        )

    def test_returns_the_requirement_that_a_run_missed(self, seat: Collector) -> None:
        """The run refuted the requirement."""
        shortfall = EngineShortfall(Requirement("even", 0.5), 1, 100, "refuted")
        run = outcome("coverage-unmet", shortfall=shortfall)
        check.equal(
            seat,
            detail_json(run, detail_of(run))["coverage"],
            {
                "label": "even",
                "share": 0.5,
                "counted": 1,
                "valid": 100,
                "verdict": "refuted",
            },
            "the coverage has the requirement and its counts",
        )

    def test_returns_none_for_the_parts_that_the_outcome_does_not_use(
        self, seat: Collector
    ) -> None:
        """A pass does not use these parts."""
        json = detail_json(outcome("passed"), detail_of(outcome("passed")))
        check.equal(
            seat,
            [
                json["counterexample"],
                json["failure"],
                json["others"],
                json["divergence"],
            ],
            [None, None, None, None],
            "every unused part is None",
        )


class TestRecordOf:
    """record_of returns the record of a run that did not pass."""

    def test_returns_the_record_of_a_run_at_the_call_site_of_the_property(
        self, seat: Collector
    ) -> None:
        """The record has the call site, and its JSON has the outcome."""
        failure, json = record_of(
            COUNTEREXAMPLE, FOR_ALL, "every total is positive", WHERE
        )
        check.equal(
            seat,
            [
                failure.assertion,
                failure.contract,
                failure.where,
                failure.detail,
                json["outcome"],
            ],
            [
                FOR_ALL,
                "every total is positive",
                WHERE,
                detail_of(COUNTEREXAMPLE),
                "counterexample",
            ],
            "the record is at the call site of the property",
        )


class TestSentence:
    """sentence returns the sentence of the record of a failed run."""

    def test_renders_every_part_of_a_counterexample(self, seat: Collector) -> None:
        """The sentence has the draw, the failures, the tokens and the note."""
        failure, _ = record_of(
            COUNTEREXAMPLE, FOR_ALL, "every total is positive", WHERE
        )
        check.equal(
            seat,
            sentence(failure),
            "\n".join(
                [
                    (
                        "every total is positive: counterexample after 3 valid and 1 "
                        "rejected cases, seed 7"
                    ),
                    "  x: 5, 4 passes",
                    f"failure of equal at test_total.py:9: {render(RECORD)}",
                    (
                        'replay: prop.replay("prop1:AQ") or '
                        "DOKIMI_ASSERT_PROP_REPLAY=prop1:AQ"
                    ),
                    f"other failure of equal at test_total.py:9: {render(RECORD)}",
                    "  x: 3",
                    (
                        f'replay: prop.replay("{THREE}") or '
                        f"DOKIMI_ASSERT_PROP_REPLAY={THREE}"
                    ),
                    "note: seen 5",
                ]
            ),
            "the sentence renders every part",
        )

    def test_renders_every_entry_of_the_counterexample_of_a_machine(
        self, seat: Collector
    ) -> None:
        """Any value fails at the draw, and the case has two steps."""

        def fill(c: Case) -> None:
            c.step(EngineStep("put", 1, True))
            c.step(EngineStep("get"))

        run = outcome(
            "counterexample",
            failing=failing(5, fill),
            explanation=(Explained("x", 5, True, None),),
        )
        failure, _ = record_of(run, FOR_ALL, "c", WHERE)
        check.equal(
            seat,
            sentence(failure).split("\n")[1:4],
            [
                "  x: 5, any value fails",
                "  step put on client 1 in the drain",
                "  step get",
            ],
            "the sentence renders the draw and the steps",
        )

    def test_renders_the_failure_of_a_message_without_an_assertion_or_a_location(
        self, seat: Collector
    ) -> None:
        """The failure is a message."""
        message = Failure("", "it broke")
        identity = of_record(message)
        run = outcome(
            "flaky",
            failing=Execution(
                Case(Replaying([])),
                "failed",
                Failed(key_of(identity), Failing(message, identity)),
            ),
        )
        failure, _ = record_of(run, FOR_ALL, "c", WHERE)
        check.equal(
            seat,
            sentence(failure),
            "c: flaky after 3 valid and 1 rejected cases, seed 7\nfailure: it broke",
            "the sentence renders the message",
        )

    divergences: ClassVar[list[tuple[str, EngineDivergence, str]]] = [
        (
            "renders the divergence of a request at a draw",
            EngineDivergence("request", 2, IntegerBounds(0, 9), None, "x"),
            (
                '\ndivergence: the request at 2 (in the draw "x"), recorded '
                "{'kind': 'integer', 'min': 0, 'max': 9}, replayed no request"
            ),
        ),
        (
            "renders the divergence of a fingerprint",
            EngineDivergence("fingerprint", 1, None, 6),
            "\ndivergence: the fingerprint at 1, recorded no fingerprint, replayed 6",
        ),
        (
            "renders the divergence of a verdict",
            EngineDivergence("verdict", 3, key_of(of_record(RECORD)), None),
            (
                "\ndivergence: the verdict at 3, recorded equal at test_total.py:9, "
                "replayed no failure"
            ),
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"),
        [t[1:] for t in divergences],
        ids=[t[0] for t in divergences],
    )
    def test_renders_the_divergence(
        self, seat: Collector, give: EngineDivergence, want: str
    ) -> None:
        """The divergence is the last line."""
        failure, _ = record_of(flaky(give), FOR_ALL, "c", WHERE)
        check.has_suffix(
            seat, sentence(failure), want, "the last line is the divergence"
        )

    def test_renders_the_requirement_that_a_run_missed(self, seat: Collector) -> None:
        """The last line is the coverage line."""
        shortfall = EngineShortfall(Requirement("even", 0.5), 1, 100, "unmet")
        failure, _ = record_of(
            outcome("coverage-unmet", shortfall=shortfall), FOR_ALL, "c", WHERE
        )
        check.equal(
            seat,
            sentence(failure),
            "c: coverage-unmet after 3 valid and 1 rejected cases, seed 7\n"
            'coverage: unmet, "even" counted 1 of 100 valid cases against a '
            "required share of 0.5",
            "the sentence renders the requirement",
        )

    def test_does_not_render_a_note_for_a_record_that_record_of_did_not_return(
        self, seat: Collector
    ) -> None:
        """The sentence has the outcome alone."""
        failure = Failure(FOR_ALL, "c", detail_of(outcome("vacuous")))
        check.equal(
            seat,
            sentence(failure),
            "c: vacuous after 3 valid and 1 rejected cases, seed 7",
            "the sentence renders the outcome alone",
        )


class TestRegisterSentences:
    """register_sentences makes sentence render the records of the assertions."""

    def test_makes_the_sentence_of_a_run_the_sentence_of_each_record(
        self, seat: Collector
    ) -> None:
        """The render function uses the registered sentence."""
        register_sentences(["prop-registered"])
        failure = Failure("prop-registered", "c", detail_of(outcome("rejected")))
        check.equal(
            seat,
            render(failure),
            sentence(failure),
            "render returns the registered sentence",
        )
