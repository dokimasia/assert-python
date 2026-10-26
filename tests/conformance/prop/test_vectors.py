# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of conformance/prop/vectors.py tests the runners of the property vectors.

check_prop computes the verdict of every property vector, so the spec checks
its own verdicts with the assert statement of pytest.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.prop.vectors import CONTRACT, KINDS, check_prop
from dokimi_assert.conformance.vector import vectors

if TYPE_CHECKING:
    import pathlib

#: The property vectors of the definition, by kind and id.
VECTORS = {(v.kind, v.id): v.raw for v in vectors()}

#: The generator of the digits.
DIGIT: dict[str, Any] = {"gen": "integer", "min": 0, "max": 9}


def vector(kind: str, vector_id: str, **changes: Any) -> dict[str, Any]:
    """Return the vector of a kind and an id with changes to its members."""
    return {**VECTORS[(kind, vector_id)], **changes}


def without(raw: dict[str, Any], member: str) -> dict[str, Any]:
    """Return raw without one member."""
    return {name: value for name, value in raw.items() if name != member}


def fault_of(
    kind: str, raw: dict[str, Any], directory: pathlib.Path
) -> tuple[str, str]:
    """Return the place and the reason of the fault of check_prop, or empty strings."""
    try:
        check_prop(kind, raw, str(directory))
    except FaultError as error:
        return error.at, error.reason
    return "", ""


def test_contract_is_the_contract_of_the_property_of_a_vector() -> None:
    """A stored case is an entry of this property."""
    assert CONTRACT == "the property of the vector"


class TestKinds:
    """KINDS has the function of each kind of property vector."""

    def test_contains_a_function_of_each_kind(self) -> None:
        """Each kind is the name of a vector file of the family prop."""
        assert sorted(KINDS) == [
            "behaviour",
            "bridge",
            "coverage",
            "decoding",
            "draws",
            "fixtures",
            "forms",
            "generation",
            "inverse",
            "recording",
            "shapes",
            "shrinking",
            "store",
            "token",
        ]

    def test_computes_the_recorded_choices_of_a_decode_that_rejects_its_case(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A filter that keeps no value rejects the case."""
        raw: dict[str, Any] = {
            "generator": {"gen": "filter", "of": DIGIT, "keep": {"kind": "never"}},
            "choices": [1],
        }
        assert KINDS["decoding"](raw, str(tmp_path)) == {
            "recorded": [1],
            "value": None,
            "rejected": True,
        }

    def test_computes_the_targets_of_the_draws_after_the_entries(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The second draw does not have an entry."""
        raw = {
            "draws": [
                {"label": "a", "generator": DIGIT},
                {"label": "b", "generator": DIGIT},
            ],
            "entries": [{"label": "a", "value": {"type": "int", "value": 4}}],
        }
        assert KINDS["draws"](raw, str(tmp_path)) == {
            "choices": [4],
            "values": [
                {"label": "a", "value": {"type": "int", "value": 4}},
                {"label": "b", "value": {"type": "int", "value": 0}},
            ],
            "error": None,
        }

    def test_computes_the_error_of_an_entry_whose_value_the_generator_lacks(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A digit is not 40."""
        raw = {
            "draws": [{"label": "a", "generator": DIGIT}],
            "entries": [{"label": "a", "value": {"type": "int", "value": 40}}],
        }
        assert KINDS["draws"](raw, str(tmp_path)) == {
            "choices": None,
            "values": None,
            "error": {"label": "a", "reason": "value"},
        }

    def test_computes_the_outcome_of_a_shrinking_vector_that_passes(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A run of a body that never fails has every case of the digits."""
        raw = {"generator": DIGIT, "fails-when": {"kind": "never"}, "seed": "7"}
        assert KINDS["shrinking"](raw, str(tmp_path)) == {
            "outcome": "passed",
            "cases": 10,
            "value": None,
            "choices": None,
            "token": None,
            "runs": 0,
        }

    def test_computes_the_verdict_and_the_choices_of_a_store_file(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The entry of a vector replays its choices."""
        written = VECTORS[("store", "store/names-an-entry-by-its-contract-and-token")]
        raw = {"contract": written["contract"], "text": json.dumps(written["entry"])}
        assert KINDS["store"](raw, str(tmp_path)) == {
            "verdict": "replay",
            "choices": [1, 0, 1, -1, 0],
        }

    def test_computes_the_verdict_of_a_damaged_store_file(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The text is not JSON."""
        assert KINDS["store"]({"contract": "c", "text": "{"}, str(tmp_path)) == {
            "verdict": "damaged",
            "choices": None,
        }

    def test_computes_the_token_of_choices(self, tmp_path: pathlib.Path) -> None:
        """One integer choice has one tag and one number."""
        assert KINDS["token"]({"choices": [1]}, str(tmp_path)) == {"token": "prop1:AAE"}

    def test_computes_the_error_of_a_token_that_does_not_decode(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The payload of the token is cut short."""
        assert KINDS["token"]({"token": "prop1:A"}, str(tmp_path)) == {
            "decoded": None,
            "error": True,
        }

    def test_computes_the_inverse_of_a_shape(self, tmp_path: pathlib.Path) -> None:
        """True is the choice 1 of a bool."""
        raw = {"shape": {"shape": "bool"}, "value": {"type": "bool", "value": True}}
        assert KINDS["inverse"](raw, str(tmp_path)) == {"choices": [1], "error": False}

    def test_computes_the_verdict_of_a_recording_vector_whose_body_rejects_every_case(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A rejected case does not call true."""
        raw = {
            "body": {"draw": DIGIT, "rejects-when": {"kind": "always"}},
            "settings": {"seed": "7", "cases": 1},
            "calls": [],
        }
        assert KINDS["recording"](raw, str(tmp_path)) == {
            "verdict": "fail",
            "reason": None,
        }

    def test_computes_the_reason_of_a_recording_vector_whose_cases_skip(
        self, tmp_path: pathlib.Path
    ) -> None:
        """Every digit is at least 0, so the first case skips."""
        raw = {
            "body": {
                "draw": DIGIT,
                "skips": [
                    {"reason": "unsupported", "when": {"kind": "at-least", "n": 0}}
                ],
            },
            "settings": {"seed": "7"},
            "calls": [],
        }
        assert KINDS["recording"](raw, str(tmp_path)) == {
            "verdict": "skip",
            "reason": "unsupported",
        }

    def test_computes_the_detail_of_a_behaviour_vector_with_an_example(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The example of the choices [7] fails first."""
        raw = {
            "body": {
                "draw": DIGIT,
                "fails": [{"identity": "big", "when": {"kind": "at-least", "n": 5}}],
            },
            "settings": {"seed": "7", "examples": [[7]], "shrink": 0},
        }
        detail = KINDS["behaviour"](raw, str(tmp_path))["detail"]
        assert detail["counterexample"][0]["value"] == {"type": "int", "value": 7}


class TestCheckProp:
    """check_prop runs a property vector and compares each output with the vector."""

    def test_returns_for_the_vectors_of_each_kind(self, tmp_path: pathlib.Path) -> None:
        """Every output agrees with the vector."""
        for kind, vector_id in [
            ("behaviour", "behaviour/tries-a-stored-case-before-the-simplest"),
            ("recording", "recording/records-the-examples-then-the-stored-cases"),
            ("fixtures", "fixtures/tree"),
        ]:
            check_prop(kind, vector(kind, vector_id), str(tmp_path / kind))

    def test_raises_at_the_output_that_the_library_computes_otherwise(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The vector has another value."""
        raw = vector(
            "decoding",
            "integer/decodes-a-choice-inside-its-bounds",
            value={"type": "int", "value": -18},
        )
        assert fault_of("decoding", raw, tmp_path) == (
            "value",
            (
                'the library computes {"type": "int", "value": -17}, '
                'want {"type": "int", "value": -18}'
            ),
        )

    def test_raises_at_the_first_output_that_differs(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The recorded choices come before the rejection."""
        raw = vector(
            "decoding",
            "integer/decodes-a-choice-inside-its-bounds",
            recorded=[-18],
            rejected=True,
        )
        assert fault_of("decoding", raw, tmp_path)[0] == "recorded"

    def test_raises_for_a_vector_with_a_shape_and_a_generator(
        self, tmp_path: pathlib.Path
    ) -> None:
        """An inverse vector has one of the two."""
        raw = {
            "shape": {"shape": "bool"},
            "generator": {"gen": "boolean"},
            "value": {"type": "bool", "value": True},
        }
        assert fault_of("inverse", raw, tmp_path) == (
            "",
            "the vector has neither a shape nor a generator, or both",
        )

    def test_raises_for_a_vector_that_does_not_run(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The function of the map takes a list, and the digit is not one."""
        raw = {
            "generator": {"gen": "map", "of": DIGIT, "subject": "drops-the-first"},
            "choices": [1],
        }
        at, reason = fault_of("decoding", raw, tmp_path)
        assert (at, reason.split(":")[0]) == ("", "the vector does not run")

    def test_raises_for_a_behaviour_vector_without_settings(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A run needs a seed."""
        raw = without(
            vector("behaviour", "behaviour/passes-a-body-that-never-fails"), "settings"
        )
        at, reason = fault_of("behaviour", raw, tmp_path)
        assert (at, reason.split(":")[0]) == ("", "the vector does not run")

    def test_raises_at_a_setting_that_the_runner_does_not_take(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The settings do not have the member widget."""
        raw = vector(
            "recording",
            "recording/records-every-case-of-a-passing-run",
            settings={"seed": "7", "widget": 1},
        )
        assert fault_of("recording", raw, tmp_path) == (
            "settings.widget",
            "the runner does not take the setting",
        )

    def test_raises_for_two_examples(self, tmp_path: pathlib.Path) -> None:
        """A run follows one trace."""
        raw = {
            "body": {"draw": DIGIT},
            "settings": {"seed": "7", "examples": [[1], [2]]},
        }
        assert fault_of("behaviour", raw, tmp_path) == (
            "settings.examples",
            "the settings have 2 examples, and a run follows one trace",
        )

    def test_raises_for_an_example_of_a_body_that_does_not_draw(
        self, tmp_path: pathlib.Path
    ) -> None:
        """draws-nothing does not have a draw."""
        raw = {
            "body": {"kind": "draws-nothing"},
            "settings": {"seed": "7", "examples": [[1]]},
        }
        assert fault_of("behaviour", raw, tmp_path) == (
            "settings.examples[0]",
            "the body does not draw a value",
        )

    def test_raises_for_a_stored_case_of_a_body_that_does_not_draw(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The entry of a stored case has the draw of its choices."""
        raw = {
            "body": {"kind": "diverges"},
            "settings": {"seed": "7", "stored": [[1]]},
        }
        assert fault_of("behaviour", raw, tmp_path) == (
            "settings.stored[0]",
            "the body does not draw a value",
        )

    def test_raises_for_a_stored_case_whose_choices_do_not_decode(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A filter that keeps no value rejects the choices of the case."""
        never = {"gen": "filter", "of": DIGIT, "keep": {"kind": "never"}}
        raw = {
            "body": {"draw": never},
            "settings": {"seed": "7", "stored": [[1], [2]]},
        }
        assert fault_of("behaviour", raw, tmp_path) == (
            "settings.stored[0]",
            "the choices do not decode to a value",
        )

    def test_raises_for_an_example_whose_choices_do_not_decode(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A filter that keeps no value rejects the choices."""
        never = {"gen": "filter", "of": DIGIT, "keep": {"kind": "never"}}
        raw = {"body": {"draw": never}, "settings": {"seed": "7", "examples": [[1]]}}
        assert fault_of("behaviour", raw, tmp_path) == (
            "settings.examples[0]",
            "the choices do not decode to a value",
        )

    def test_raises_at_the_calls_of_a_recording_vector_that_differ(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The vector has a call that the run does not make."""
        raw = vector("recording", "recording/records-the-one-case-of-a-replay-token")
        raw["calls"] = [*raw["calls"], {"run": 2, "phase": "token", "verdict": "pass"}]
        at, reason = fault_of("recording", raw, tmp_path)
        assert at == "calls"
        assert reason.startswith(
            'the library records [{"seq": 2, "parent": 1, "run": 1'
        )

    def test_raises_at_the_reason_of_a_recording_vector_that_differs(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The case of the run skips for another reason."""
        raw = vector(
            "recording",
            "recording/records-the-cases-before-a-case-that-skips",
            reason="the disk is full",
        )
        assert fault_of("recording", raw, tmp_path) == (
            "reason",
            'the library computes "unsupported", want "the disk is full"',
        )

    def test_raises_at_the_entry_of_a_store_vector_that_does_not_read_back(
        self, tmp_path: pathlib.Path
    ) -> None:
        """A file of an identity is a base name, so a path does not read back."""
        raw = vector(
            "store",
            "store/names-an-entry-by-its-contract-and-token",
            identity={"assertion": "equal", "file": "pkg/codec_test.go", "line": 18},
        )
        assert fault_of("store", raw, tmp_path) == (
            "entry",
            "the entry does not read back as a replay of its choices",
        )
