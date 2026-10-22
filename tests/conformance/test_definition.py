"""The spec of conformance/definition.py tests the reader of the vendored definition."""

from __future__ import annotations

from dokimi_assert import check, expect
from dokimi_assert.conformance.definition import (
    LANGUAGE,
    assertions,
    declines_relaxation,
    declines_surface,
    detail_fields,
    diverges,
    names,
    overlay,
    relaxation_names,
    spec_dir,
    surface_names,
    version,
)
from dokimi_assert.seat import Collector


class TestLanguage:
    """LANGUAGE is the column of this library in the naming table."""

    def test_is_the_column_python(self, seat: Collector) -> None:
        """The library reads the column of its own language."""
        check.equal(seat, LANGUAGE, "python", "LANGUAGE is python")


class TestSpecDir:
    """spec_dir returns the directory of the vendored definition."""

    def test_returns_the_directory_of_the_vendored_files(self, seat: Collector) -> None:
        """The directory contains the version of the definition."""
        present = (spec_dir() / "VERSION").is_file()
        check.is_true(seat, present, "the directory contains VERSION")


class TestAssertions:
    """assertions returns the assertions of the definition."""

    def test_returns_the_110_assertions_of_the_definition(
        self, seat: Collector
    ) -> None:
        """The vendored definition has 110 assertions."""
        check.length(seat, assertions(), 110, "the definition has 110 assertions")


class TestNames:
    """names returns the Python name of each assertion."""

    def test_returns_a_python_name_for_every_assertion(self, seat: Collector) -> None:
        """Every assertion of the definition has a Python name."""
        named = names()
        check.equal(
            seat,
            [a for a in assertions() if a not in named],
            [],
            "every assertion has a name",
        )
        check.equal(
            seat, named["not-equal"], "not_equal", "the name of not-equal is not_equal"
        )


class TestVersion:
    """version returns the version of the vendored definition."""

    def test_returns_the_text_of_the_vendored_version_file(
        self, seat: Collector
    ) -> None:
        """The version is the file VERSION without its line end."""
        content = (spec_dir() / "VERSION").read_text(encoding="utf-8").strip()
        check.equal(seat, version(), content, "version returns the content of VERSION")
        check.equal(seat, version(), "9.0.0", "the vendored version is 9.0.0")


class TestOverlay:
    """overlay returns the overlay of Python on the definition."""

    def test_returns_the_overlay_of_python_on_the_vendored_version(
        self, seat: Collector
    ) -> None:
        """The overlay extends the definition that the library vendors."""
        check.equal(
            seat,
            overlay()["extends"],
            f"spec://assertions@{version()}",
            "the overlay extends the vendored version",
        )
        check.equal(
            seat,
            overlay()["language"],
            LANGUAGE,
            "the language of the overlay is python",
        )

    def test_returns_a_stance_and_a_reason_for_each_divergence(
        self, seat: Collector
    ) -> None:
        """Every divergence of the overlay is an assertion of the definition."""
        defined = assertions()
        for entry in overlay()["diverge"]:
            expect.is_not_empty(
                seat, entry["stance"].strip(), f"{entry['id']} has a stance"
            )
            expect.is_not_empty(
                seat, entry["why"].strip(), f"{entry['id']} has a reason"
            )
            expect.is_true(
                seat, entry["id"] in defined, f"{entry['id']} is an assertion"
            )


class TestRelaxationNames:
    """relaxation_names returns the Python name of each relaxation."""

    def test_returns_the_python_name_of_each_relaxation(self, seat: Collector) -> None:
        """The definition has three relaxations."""
        check.equal(
            seat,
            relaxation_names(),
            {
                "by-identity": "by_identity",
                "equate-empty": "equate_empty",
                "equate-nans": "equate_nans",
            },
            "relaxation_names returns the three names",
        )


class TestDetailFields:
    """detail_fields returns the fields of the detail of each assertion."""

    def test_returns_the_fields_of_each_assertion(self, seat: Collector) -> None:
        """The detail of a failure of equal has want and got."""
        fields = detail_fields()
        check.equal(
            seat,
            fields["equal"],
            ["want", "got"],
            "the fields of equal are want and got",
        )
        check.equal(seat, fields["true"], [], "true does not have a field")


class TestSurfaceNames:
    """surface_names returns the Python name of each surface id."""

    def test_returns_the_python_name_of_a_surface_id(self, seat: Collector) -> None:
        """The Python name of recorder-seat is Recorder."""
        check.equal(
            seat,
            surface_names()["recorder-seat"],
            "Recorder",
            "the name of recorder-seat is Recorder",
        )

    def test_returns_the_empty_string_for_an_unnamed_id(self, seat: Collector) -> None:
        """The naming table does not have a Python name for scheduler.yield."""
        check.equal(
            seat,
            surface_names()["scheduler.yield"],
            "",
            "scheduler.yield does not have a name",
        )


class TestDeclinesSurface:
    """declines_surface reports whether the overlay declines a surface id."""

    def test_returns_true_for_a_declined_id(self, seat: Collector) -> None:
        """The overlay declines scheduler.yield."""
        check.is_true(
            seat,
            declines_surface("scheduler.yield"),
            "the overlay declines scheduler.yield",
        )

    def test_returns_false_for_an_offered_id(self, seat: Collector) -> None:
        """The library offers recorder-seat."""
        check.is_false(
            seat,
            declines_surface("recorder-seat"),
            "the library offers the recorder seat",
        )


class TestDeclinesRelaxation:
    """declines_relaxation reports whether the overlay declines a relaxation."""

    def test_returns_false_for_an_offered_relaxation(self, seat: Collector) -> None:
        """The library offers equate-empty."""
        check.is_false(
            seat,
            declines_relaxation("equate-empty"),
            "the library offers equate-empty",
        )


class TestDiverges:
    """diverges reports whether the overlay declines an assertion."""

    def test_returns_true_for_a_declined_assertion(self, seat: Collector) -> None:
        """The overlay declines max-allocs."""
        check.is_true(seat, diverges("max-allocs"), "the overlay declines max-allocs")

    def test_returns_false_for_an_implemented_assertion(self, seat: Collector) -> None:
        """The library implements equal."""
        check.is_false(seat, diverges("equal"), "the library implements equal")
