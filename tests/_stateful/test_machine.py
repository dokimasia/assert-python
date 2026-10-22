# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _stateful/machine.py tests what a machine must state."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest

from dokimi_assert import check
from dokimi_assert._history.spec import Spec
from dokimi_assert._stateful.machine import Action, validate
from helpers import refusal

if TYPE_CHECKING:
    from dokimi_assert._prop.case import Case
    from dokimi_assert.seat import Collector


def nothing(c: Case, client: int, value: object) -> None:
    """Do nothing on any client."""
    del c, client, value


@dataclass
class Listed:
    """A machine without a spec, of the actions that it lists."""

    actions: Sequence[Action[Any]]
    spec: Spec[Any] | None = None


class TestAction:
    """Action states one named action of a machine."""

    def test_has_a_weight_of_1_and_no_drain_enabled_or_input_by_default(
        self, seat: Collector
    ) -> None:
        """An action of a name and a run has the defaults."""
        action: Action[Any] = Action("a", nothing)
        check.equal(
            seat,
            [action.weight, action.drain, action.enabled, action.input],
            [1, False, None, None],
            "the action has the defaults",
        )


class TestValidate:
    """validate raises for a machine whose actions cannot take steps."""

    def test_accepts_actions_with_weights_of_0_and_more(self, seat: Collector) -> None:
        """The weights 0, 1 and 3 are valid."""
        machine = Listed(
            [Action("a", nothing, 0), Action("b", nothing), Action("c", nothing, 3)]
        )
        check.does_not_raise(seat, lambda: validate(machine), "the machine is valid")

    tests: ClassVar[list[tuple[str, list[Action[Any]], type[Exception], str]]] = [
        (
            "an action of a negative weight",
            [Action("a", nothing, -1)],
            ValueError,
            'stateful: the weight -1 of the action "a" is not an int of 0 or more',
        ),
        (
            "an action of a weight that is a fraction",
            [Action("a", nothing, cast("Any", 1.5))],
            ValueError,
            'stateful: the weight 1.5 of the action "a" is not an int of 0 or more',
        ),
        (
            "an action whose run is not callable",
            [Action("a", cast("Any", None))],
            TypeError,
            'stateful: the run of the action "a" is not callable',
        ),
        (
            "two actions with one name",
            [Action("a", nothing), Action("a", nothing)],
            ValueError,
            'stateful: two actions of the machine have the name "a"',
        ),
    ]

    @pytest.mark.parametrize(
        ("give", "kind", "want"), [t[1:] for t in tests], ids=[t[0] for t in tests]
    )
    def test_raises_for(
        self,
        seat: Collector,
        give: list[Action[Any]],
        kind: type[Exception],
        want: str,
    ) -> None:
        """The text of the refusal contains the name of the action."""
        check.equal(
            seat,
            refusal(seat, lambda: validate(Listed(give)), kind),
            want,
            "the text of the refusal contains the name of the action",
        )
