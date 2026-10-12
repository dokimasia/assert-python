"""The spec of prop.py tests the names of the property engine and its sentences."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest

from dokimi_assert import check, prop
from dokimi_assert.failure import Failure, render
from dokimi_assert.seat import Collector

#: The detail of a run that rejected every case.
REJECTED: dict[str, Any] = {
    "outcome": "rejected",
    "cases": 0,
    "rejected": 11,
    "seed": "3",
    "counterexample": None,
    "failure": None,
    "choices": None,
    "others": None,
    "divergence": None,
    "coverage": None,
}


class TestProp:
    """prop is the module of the property engine."""

    def test_exports_the_names_of_the_property_engine(self, seat: Collector) -> None:
        """The module exports 91 names, and each name is an attribute."""
        check.equal(
            seat,
            [sorted(prop.__all__), [n for n in prop.__all__ if not hasattr(prop, n)]],
            [
                [
                    "AllowInfinity",
                    "AllowNan",
                    "Alphabet",
                    "Case",
                    "Char",
                    "FormOption",
                    "Generator",
                    "Option",
                    "Pattern",
                    "Scale",
                    "Unit",
                    "Variant",
                    "Version",
                    "WallTime",
                    "Width",
                    "accumulates",
                    "boolean",
                    "bytes",
                    "cases",
                    "close_to",
                    "composite",
                    "contains",
                    "contains_in_order",
                    "dict",
                    "does_not_raise",
                    "draws",
                    "duration",
                    "equal",
                    "error_as",
                    "error_is",
                    "error_is_not",
                    "example",
                    "examples",
                    "explain",
                    "float",
                    "for_all",
                    "fuzz",
                    "has_error",
                    "has_prefix",
                    "has_suffix",
                    "hermetic",
                    "honours_cancellation",
                    "honours_deadline",
                    "in_range",
                    "integer",
                    "is_associative",
                    "is_commutative",
                    "is_deterministic",
                    "is_empty",
                    "is_false",
                    "is_idempotent",
                    "is_none",
                    "is_not_empty",
                    "is_not_none",
                    "is_not_pure",
                    "is_permutation",
                    "is_pure",
                    "is_true",
                    "just",
                    "length",
                    "list",
                    "matches",
                    "max_choices",
                    "no_error",
                    "none_handle_safe",
                    "not_contains",
                    "not_equal",
                    "of",
                    "of_shape",
                    "one_of",
                    "optional",
                    "pairwise",
                    "permutation",
                    "raises",
                    "recursive",
                    "register",
                    "register_values",
                    "register_variants",
                    "replay",
                    "require",
                    "round_trip",
                    "sampled_from",
                    "seed",
                    "shape_of",
                    "shrink",
                    "shrink_time",
                    "store",
                    "string",
                    "string_matching",
                    "using",
                    "workers",
                ],
                [],
            ],
            "prop exports the names of the property engine",
        )

    tests: ClassVar[list[str]] = ["prop-for-all", "prop-equal", "prop-round-trip"]

    @pytest.mark.parametrize("give", tests, ids=tests)
    def test_registers_the_sentence_of_a_run_as_the_sentence_of(
        self, seat: Collector, give: str
    ) -> None:
        """The run rejected every case."""
        check.equal(
            seat,
            render(Failure(give, "every case passes", REJECTED)),
            "every case passes: rejected after 0 valid and 11 rejected cases, seed 3",
            "render returns the sentence of the run",
        )
