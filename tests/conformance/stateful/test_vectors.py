# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of conformance/stateful/vectors.py tests the runner of the machines vectors.

The runner computes the verdict of every machines vector, so the spec checks
its own verdicts with the assert statement of pytest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.stateful.vectors import CONTRACT, RUNNERS
from dokimi_assert.conformance.vector import vectors

if TYPE_CHECKING:
    import pathlib

#: The machines vectors of the definition, by id.
VECTORS = {v.id: v.raw for v in vectors() if v.kind == "machines"}

#: The id of a vector of a counterexample.
FAILING = "counter-overflows/a-third-increment-without-a-reset-returns-0"

#: The id of a vector whose trace the run refuses.
REFUSED = "store-loses-on-crash/a-flush-of-an-empty-buffer-is-refused"


def vector(vector_id: str, **changes: Any) -> dict[str, Any]:
    """Return the machines vector of an id with changes to its members."""
    return {**VECTORS[vector_id], **changes}


def fault_of(raw: dict[str, Any], directory: str = "") -> tuple[str, str]:
    """Return the place and the reason of the fault of the runner, or empty strings.

    The run has its store in directory. The empty string turns the store off.
    """
    try:
        RUNNERS["machines"](raw, directory)
    except FaultError as error:
        return error.at, error.reason
    return "", ""


def test_contract_is_the_contract_of_the_property_of_a_subject() -> None:
    """The run of every subject has this contract."""
    assert CONTRACT == "the machine subject of the vector"


class TestRunners:
    """RUNNERS has the runner of the machines vectors."""

    def test_contains_the_runner_of_machines(self) -> None:
        """The kind is the name of the vector file of the family stateful."""
        assert sorted(RUNNERS) == ["machines"]

    def test_takes_the_mean_and_the_concurrent_steps_and_the_cases(self) -> None:
        """A correct counter passes five cases under any steps."""
        vector_id = "correct-counter/passes-with-two-clients"
        raw = vector(
            vector_id,
            setup={"mean": 2, "concurrent": 2, "concurrent-mean": 1},
            settings={"seed": "1", "cases": 5},
            detail={**VECTORS[vector_id]["detail"], "cases": 5},
        )
        assert fault_of(raw) == ("", "")

    def test_takes_a_limit_of_releases(self) -> None:
        """A spin fails its case at a limit of 20 releases."""
        vector_id = "spins-until-a-flag/fails-the-case-at-the-release-limit"
        raw = vector(vector_id, setup={"max-releases": 20})
        assert fault_of(raw)[0] == "detail"

    def test_takes_the_actions_that_every_case_keeps(self) -> None:
        """A kept put of a lossy queue takes no swarm choice of the case."""
        vector_id = "queue-loses-on-wrap/a-kept-put-takes-no-swarm-choice"
        assert [
            fault_of(vector(vector_id))[0],
            fault_of(vector(vector_id, setup={}))[0],
        ] == ["", "detail"]

    def test_takes_the_stored_cases_of_the_settings(
        self, tmp_path: pathlib.Path
    ) -> None:
        """The stored case of a lossy queue fails by its steps."""
        vector_id = (
            "queue-loses-on-wrap/a-stored-case-of-other-actions-replays-its-steps"
        )
        replays = vector(vector_id)
        alone = vector(vector_id, settings={"seed": "1", "cases": 1})
        assert [
            fault_of(replays, str(tmp_path / "replays"))[0],
            fault_of(alone, str(tmp_path / "alone"))[0],
        ] == ["", "detail"]

    def test_takes_a_strategy_of_pct(self) -> None:
        """A setup can run the clients of a scheduler under PCT of a depth."""
        raw = vector(
            "racy-counter/two-increments-on-two-clients-both-return-1",
            setup={"strategy": {"pct": 2}},
        )
        assert fault_of(raw)[0] != "setup.strategy"

    tests: ClassVar[list[tuple[str, dict[str, Any], tuple[str, str]]]] = [
        (
            "raises at the subject for a subject that does not exist",
            vector(FAILING, subject="widget"),
            ("subject", '"widget" is not a machine subject'),
        ),
        (
            "raises at a member of the setup that the runner does not take",
            vector(FAILING, setup={"widget": 1}),
            ("setup.widget", "the runner does not take the member"),
        ),
        (
            "raises at a strategy that is not a strategy",
            vector(FAILING, setup={"strategy": "random"}),
            ("setup.strategy", '"random" is not a strategy'),
        ),
        (
            "raises at a keep that is not a list",
            vector(FAILING, setup={"keep": "increment"}),
            ("setup.keep", '"increment" is not a list of names'),
        ),
        (
            "raises at a keep whose names are not strings",
            vector(FAILING, setup={"keep": [1]}),
            ("setup.keep", "[1] is not a list of names"),
        ),
        (
            "raises at a setting that the runner does not take",
            vector(FAILING, settings={"seed": "1", "shrink": 0}),
            ("settings.shrink", "the runner does not take the setting"),
        ),
        (
            "raises at a stored case of choices alone",
            vector(FAILING, settings={"seed": "1", "stored": [[1]]}),
            (
                "settings.stored[0]",
                (
                    "the stored case is not an object of its choices and its "
                    "counterexample"
                ),
            ),
        ),
        (
            "raises at the error of a run that does not refuse the entry",
            vector(FAILING, error={"entry": 0, "name": "reset", "reason": "step"}),
            (
                "error",
                'the run ends with "", want a refusal of entry 0 of "reset"',
            ),
        ),
        (
            "raises at the error of a run that refuses another entry",
            vector(REFUSED, error={"entry": 0, "name": "crash", "reason": "step"}),
            (
                "error",
                (
                    'the run ends with "prop.for_all: draws[1].step: the machine '
                    'cannot take the step \\"flush\\" there", want a refusal of entry '
                    '0 of "crash"'
                ),
            ),
        ),
        (
            "raises for a run of a trace that ends with a fault",
            vector(REFUSED, error=None),
            (
                "",
                (
                    'the run ends with the fault "prop.for_all: draws[1].step: the '
                    'machine cannot take the step \\"flush\\" there"'
                ),
            ),
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_for_a_vector_that_the_run_contradicts(
        self, give: dict[str, Any], want: tuple[str, str]
    ) -> None:
        """The fault is at the member of the vector."""
        assert fault_of(give) == want

    def test_raises_at_the_detail_for_a_run_of_another_detail(self) -> None:
        """The run of a failing subject has another outcome than a pass."""
        raw = vector(
            FAILING, detail={**VECTORS[FAILING]["detail"], "outcome": "passed"}
        )
        at, reason = fault_of(raw)
        assert (
            at,
            reason.startswith('the run has the detail {"outcome": "counterexample"'),
        ) == (
            "detail",
            True,
        )
