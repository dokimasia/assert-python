"""The spec of _matcher/option.py tests the relaxations of one comparison."""

from __future__ import annotations

from dokimi_assert._matcher.option import (
    Option,
    Relaxations,
    by_identity,
    equate_empty,
    equate_nans,
    settings,
)


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
