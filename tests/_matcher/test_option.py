# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _matcher/option.py tests the relaxations of one comparison."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from dokimi_assert._matcher.option import (
    Option,
    Relaxations,
    by_identity,
    equate_by,
    equate_empty,
    equate_nans,
    settings,
    transformed,
)


class Base:
    """A class whose subclass matches a transform of the class."""


class Child(Base):
    """A subclass of Base."""


def named(_: object) -> str:
    """Return the name of every value."""
    return "named"


class TestEquateEmpty:
    """equate_empty returns the option that equates an empty collection with None."""

    def test_returns_the_option_of_equate_empty(self) -> None:
        """The option has the canonical id of its relaxation."""
        assert equate_empty() == Option("equate-empty")


class TestEquateNans:
    """equate_nans returns the option that equates two NaNs."""

    def test_returns_the_option_of_equate_nans(self) -> None:
        """The option has the canonical id of its relaxation."""
        assert equate_nans() == Option("equate-nans")


class TestByIdentity:
    """by_identity returns the option that compares references by identity."""

    def test_returns_the_option_of_by_identity(self) -> None:
        """The option has the canonical id of its relaxation."""
        assert by_identity() == Option("by-identity")


class TestEquateBy:
    """equate_by returns the option that compares a type by a transform."""

    def test_returns_the_option_of_the_type_and_its_transform(self) -> None:
        """The option has the canonical id of its relaxation and the transform."""
        assert equate_by(str, str.lower) == Option("equate-by", (str, str.lower))

    tests: ClassVar[list[tuple[str, Any, Any, str]]] = [
        ("refuses a kind that is not a type", 3, named, "equate_by: 3 is not a type"),
        (
            "refuses a transform that is not callable",
            str,
            None,
            "equate_by: None is not callable",
        ),
    ]

    @pytest.mark.parametrize(
        ("give_kind", "give_f", "want"),
        [t[1:] for t in tests],
        ids=[t[0] for t in tests],
    )
    def test_raises_type_error(self, give_kind: Any, give_f: Any, want: str) -> None:
        """The error has the argument."""
        with pytest.raises(TypeError) as raised:
            equate_by(give_kind, give_f)
        assert str(raised.value) == want


class TestSettings:
    """settings returns the relaxations that the options of one call allow."""

    def test_allows_nothing_without_options(self) -> None:
        """A call without options does not relax any rule."""
        assert settings(()) == Relaxations()

    def test_allows_the_relaxation_of_each_option(self) -> None:
        """Each option turns its relaxation on.

        An option passed twice has the effect of one.
        """
        assert settings([equate_nans(), by_identity(), equate_nans()]) == Relaxations(
            equate_nans=True, by_identity=True
        )

    def test_keeps_the_transforms_in_the_order_of_the_call(self) -> None:
        """The other options do not change the order of the transforms."""
        assert settings(
            [equate_by(str, str.lower), equate_nans(), equate_by(int, str)]
        ) == Relaxations(equate_nans=True, transforms=((str, str.lower), (int, str)))


class TestTransformed:
    """transformed returns a value under the transform of its type."""

    def test_returns_the_result_of_the_transform_of_the_type_of_a_value(self) -> None:
        """str.lower matches a str."""
        relax = settings([equate_by(str, str.lower)])
        assert transformed("AB", relax) == "ab"

    def test_returns_the_value_that_no_transform_matches(self) -> None:
        """str.lower does not match an int."""
        relax = settings([equate_by(str, str.lower)])
        assert transformed(3, relax) == 3

    def test_returns_the_result_of_the_transform_of_a_base_class(self) -> None:
        """An instance of a subclass matches the transform of its base class."""
        relax = settings([equate_by(Base, named)])
        assert transformed(Child(), relax) == "named"

    def test_returns_the_result_of_the_last_transform_that_matches(self) -> None:
        """The transform of Child comes after the transform of Base."""
        relax = settings([equate_by(Base, named), equate_by(Child, type)])
        assert transformed(Child(), relax) is Child
