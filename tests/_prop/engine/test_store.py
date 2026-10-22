# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _prop/engine/store.py tests store entries.

The pinned name is the name that the reference implementation of the
definition computes.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from dokimi_assert import check
from dokimi_assert._prop.engine.source import mix
from dokimi_assert._prop.engine.store import MAX_DEPTH, Failure, entry, name, read
from dokimi_assert._prop.engine.tokens import encode
from helpers import integers, values_of

if TYPE_CHECKING:
    from dokimi_assert.seat import Collector

#: The contract of the property whose entries the cases read.
CONTRACT = "decoding undoes encoding"

#: The choices of the minimal case. They decode to the list [0, -1].
CHOICES = integers(1, 0, 1, -1, 0)

#: The failure that the cases write.
FAILURE = Failure(
    CONTRACT,
    CHOICES,
    {"assertion": "equal", "file": "codec_test.go", "line": 18},
    [{"label": "values", "value": {"type": "list", "of": "int", "value": [0, -1]}}],
)

#: The largest line of an identity.
LINE_MAX = 2**31 - 1

#: The deepest value that a draw records. The root, the counterexample and the
#: draw take the first three levels.
DEEPEST_VALUE = MAX_DEPTH - 3


def written(**changes: object) -> dict[str, Any]:
    """Return the entry of FAILURE that definition 1.2.0 writes, with changes."""
    return {**entry(FAILURE, "1.2.0", "2026-10-01"), **changes}


def verdict_of(document: object) -> str:
    """Return the verdict on a file whose text is the JSON of document."""
    return read(json.dumps(document), CONTRACT).verdict


def nested(levels: int) -> list[object]:
    """Return a list that nests levels lists deep. The outer list is one level."""
    node: list[object] = []
    for _ in range(1, levels):
        node = [node]
    return node


def depth_of(node: object) -> int:
    """Return the number of levels of objects and arrays in node."""
    if isinstance(node, dict):
        members: dict[str, object] = node
        return 1 + max((depth_of(member) for member in members.values()), default=0)
    if isinstance(node, list):
        items: list[object] = node
        return 1 + max((depth_of(item) for item in items), default=0)
    return 0


class TestMaxDepth:
    """MAX_DEPTH is the largest number of levels in a file."""

    def test_nests_a_file_at_most_64_levels_deep(self, seat: Collector) -> None:
        """The root is one of the levels."""
        check.equal(seat, MAX_DEPTH, 64, "MAX_DEPTH is 64")


class TestName:
    """name returns the file name of an entry."""

    def test_returns_the_hexadecimal_mix_of_the_contract_with_the_token(
        self, seat: Collector
    ) -> None:
        """The name is 16 digits followed by .json."""
        data = CONTRACT.encode() + b"\x00" + encode(CHOICES).encode()
        check.equal(
            seat,
            name(CONTRACT, CHOICES),
            f"{mix(data):016x}.json",
            "the name is the hexadecimal mix",
        )

    def test_returns_the_pinned_name_of_the_failure(self, seat: Collector) -> None:
        """Every language computes this name."""
        check.equal(
            seat,
            name(CONTRACT, CHOICES),
            "ccc741d57d7f920d.json",
            "the name is the pinned name",
        )

    def test_returns_another_name_for_another_contract(self, seat: Collector) -> None:
        """Two properties do not share an entry."""
        check.not_equal(
            seat,
            name("another", CHOICES),
            name(CONTRACT, CHOICES),
            "the two contracts have two names",
        )

    def test_pads_a_small_mix_to_16_digits(self, seat: Collector) -> None:
        """The name has 16 lowercase digits."""
        check.matches(
            seat, name("", []), "^[0-9a-f]{16}\\.json$", "the name has 16 digits"
        )

    def test_counts_a_lone_surrogate_of_the_contract_as_the_replacement_character(
        self, seat: Collector
    ) -> None:
        """The surrogate has the name of U+FFFD."""
        check.equal(
            seat,
            name(chr(0xD800), []),
            name(chr(0xFFFD), []),
            "the two contracts have one name",
        )


class TestEntry:
    """entry returns the object that a runner writes."""

    def test_has_exactly_the_fields_of_the_format(self, seat: Collector) -> None:
        """The format has seven fields."""
        one = written()
        check.equal(
            seat,
            [sorted(one), one["store"], one["found"], one["choices"]],
            [
                [
                    "choices",
                    "counterexample",
                    "definition",
                    "found",
                    "identity",
                    "property",
                    "store",
                ],
                1,
                "2026-10-01",
                encode(CHOICES),
            ],
            "the entry has the fields of the format",
        )

    def test_records_a_value_at_the_deepest_level(self, seat: Collector) -> None:
        """The entry nests 64 levels and replays."""
        failure = Failure(
            CONTRACT,
            CHOICES,
            FAILURE.identity,
            [{"label": "v", "value": nested(DEEPEST_VALUE)}],
        )
        deep = entry(failure, "1.2.0", "2026-10-01")
        check.equal(
            seat,
            [depth_of(deep), verdict_of(deep)],
            [MAX_DEPTH, "replay"],
            "the entry nests 64 levels and replays",
        )

    def test_records_a_value_past_the_deepest_level_by_its_label(
        self, seat: Collector
    ) -> None:
        """The draw has the label alone."""
        failure = Failure(
            CONTRACT,
            CHOICES,
            FAILURE.identity,
            [{"label": "v", "value": nested(DEEPEST_VALUE + 1)}],
        )
        deep = entry(failure, "1.2.0", "2026-10-01")
        check.equal(
            seat,
            deep["counterexample"],
            [{"label": "v"}],
            "the draw has its label alone",
        )


class TestRead:
    """read returns the verdict of a runner on the text of a file."""

    def test_replays_the_choices_of_an_entry_that_a_runner_wrote(
        self, seat: Collector
    ) -> None:
        """The verdict is replay with the choices."""
        got = read(json.dumps(written()), CONTRACT)
        check.equal(
            seat,
            [got.verdict, values_of(list(got.choices))],
            ["replay", values_of(CHOICES)],
            "read replays the choices",
        )

    replays: ClassVar[list[tuple[str, dict[str, object]]]] = [
        ("replays an entry of another definition version", {"definition": "1.1.0"}),
        ("replays a draw without a value", {"counterexample": [{"label": "conn"}]}),
        (
            "replays a draw whose value is not a typed literal",
            {"counterexample": [{"label": "x", "value": [1]}]},
        ),
        (
            "replays an identity of a record with a location",
            {"identity": {"assertion": "equal", "file": "a_test.go", "line": 3}},
        ),
        (
            "replays an identity of a record without a location",
            {"identity": {"assertion": "equal", "contract": "x equals y"}},
        ),
        (
            "replays an identity of a message at the largest line",
            {"identity": {"file": "a_test.go", "line": LINE_MAX}},
        ),
        (
            "replays an identity of an error",
            {"identity": {"error": "ValueError", "file": "a_test.py", "line": 3}},
        ),
        ("replays an entry found on a leap day", {"found": "2024-02-29"}),
        (
            "replays an entry found on a leap day of a fourth century",
            {"found": "2000-02-29"},
        ),
    ]

    @pytest.mark.parametrize(
        "give", [t[1] for t in replays], ids=[t[0] for t in replays]
    )
    def test_replays_an_entry_of_the_format(
        self, seat: Collector, give: dict[str, object]
    ) -> None:
        """The verdict is replay."""
        check.equal(
            seat, verdict_of(written(**give)), "replay", "the verdict is replay"
        )

    def test_returns_other_for_an_entry_of_another_property(
        self, seat: Collector
    ) -> None:
        """The entry is of another property."""
        got = read(json.dumps(written(property="another")), CONTRACT)
        check.equal(
            seat, [got.verdict, got.choices], ["other", ()], "the verdict is other"
        )

    skips: ClassVar[list[tuple[str, str]]] = [
        ("skips an entry of format 2", '{"store": 2}'),
        (
            "skips an entry of a far later format",
            '{"store": 1000000000000000000000000000000}',
        ),
        (
            "skips an entry whose token is of a later version",
            json.dumps(
                {**entry(FAILURE, "1.2.0", "2026-10-01"), "choices": "prop2:AAc"}
            ),
        ),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in skips], ids=[t[0] for t in skips])
    def test_skips_an_entry_of_a_later_format(self, seat: Collector, give: str) -> None:
        """The verdict is skip."""
        got = read(give, CONTRACT)
        check.equal(
            seat, [got.verdict, got.choices], ["skip", ()], "the verdict is skip"
        )

    texts: ClassVar[list[tuple[str, str]]] = [
        ("returns damaged for text that is not json", "{"),
        (
            "returns damaged for an object that repeats a name",
            '{"store": 1, "store": 1}',
        ),
        ("returns damaged for nan", '{"store": NaN}'),
        ("returns damaged for an array", "[1]"),
        ("returns damaged for a number", "1"),
        (
            "returns damaged for arrays nested past the parser",
            "[" * 100_000 + "]" * 100_000,
        ),
        (
            "returns damaged for a token with a version past the digit limit",
            json.dumps(
                {
                    **entry(FAILURE, "1.2.0", "2026-10-01"),
                    "choices": "prop" + "1" * 5000 + ":AAc",
                }
            ),
        ),
    ]

    @pytest.mark.parametrize("give", [t[1] for t in texts], ids=[t[0] for t in texts])
    def test_returns_damaged_for_a_text_that_is_not_an_entry(
        self, seat: Collector, give: str
    ) -> None:
        """The verdict is damaged."""
        check.equal(
            seat, read(give, CONTRACT).verdict, "damaged", "the verdict is damaged"
        )

    def test_returns_damaged_for_an_entry_nested_past_the_most_levels(
        self, seat: Collector
    ) -> None:
        """The entry nests one level past the writer."""
        deep = written(
            counterexample=[{"label": "v", "value": nested(DEEPEST_VALUE + 1)}]
        )
        check.equal(
            seat,
            [depth_of(deep), verdict_of(deep)],
            [MAX_DEPTH + 1, "damaged"],
            "the entry nests 65 levels and is damaged",
        )

    def test_returns_damaged_for_an_absent_store(self, seat: Collector) -> None:
        """The entry does not have a format."""
        absent = written()
        del absent["store"]
        check.equal(seat, verdict_of(absent), "damaged", "the verdict is damaged")

    formats: ClassVar[list[tuple[str, object]]] = [
        ("returns damaged for a store of 0", 0),
        ("returns damaged for a store that is a bool", True),
        ("returns damaged for a store that is a fraction", 1.5),
        ("returns damaged for a store that is a string", "1"),
    ]

    @pytest.mark.parametrize(
        "give", [t[1] for t in formats], ids=[t[0] for t in formats]
    )
    def test_returns_damaged_for_a_store_that_is_not_a_format(
        self, seat: Collector, give: object
    ) -> None:
        """The store is not a format."""
        check.equal(
            seat, verdict_of(written(store=give)), "damaged", "the verdict is damaged"
        )

    changes: ClassVar[list[tuple[str, dict[str, object]]]] = [
        ("returns damaged for a definition of two parts", {"definition": "1.2"}),
        (
            "returns damaged for a definition with a leading zero",
            {"definition": "1.02.0"},
        ),
        ("returns damaged for a definition that is not a string", {"definition": 1}),
        ("returns damaged for a property that is not a string", {"property": 5}),
        (
            "returns damaged for an identity of an assertion alone",
            {"identity": {"assertion": "equal"}},
        ),
        (
            "returns damaged for an identity at line 0",
            {"identity": {"file": "a_test.go", "line": 0}},
        ),
        (
            "returns damaged for an identity past the largest line",
            {"identity": {"file": "a_test.go", "line": LINE_MAX + 1}},
        ),
        (
            "returns damaged for an identity whose line is a bool",
            {"identity": {"file": "a_test.go", "line": True}},
        ),
        (
            "returns damaged for an identity whose line is a fraction",
            {"identity": {"file": "a_test.go", "line": 3.5}},
        ),
        (
            "returns damaged for an identity whose file has a slash",
            {"identity": {"file": "pkg/a_test.go", "line": 3}},
        ),
        (
            "returns damaged for an identity whose file has a backslash",
            {"identity": {"file": "pkg\\a_test.go", "line": 3}},
        ),
        (
            "returns damaged for an identity whose file is empty",
            {"identity": {"file": "", "line": 3}},
        ),
        (
            "returns damaged for an identity whose assertion is not a string",
            {"identity": {"assertion": 1, "contract": "x"}},
        ),
        (
            "returns damaged for an identity that is not an object",
            {"identity": "equal"},
        ),
        ("returns damaged for choices that are not a string", {"choices": 5}),
        ("returns damaged for choices without a version", {"choices": "AAc"}),
        (
            "returns damaged for choices with a version of a leading zero",
            {"choices": "prop01:AAc"},
        ),
        ("returns damaged for choices with padding", {"choices": "prop1:AAc="}),
        (
            "returns damaged for a counterexample that is not a list",
            {"counterexample": {"label": "x"}},
        ),
        (
            "returns damaged for a draw without a label",
            {"counterexample": [{"value": {"type": "int", "value": 1}}]},
        ),
        (
            "returns damaged for a draw with another field",
            {"counterexample": [{"label": "x", "note": "y"}]},
        ),
        (
            "returns damaged for a draw whose label is not a string",
            {"counterexample": [{"label": 5}]},
        ),
        (
            "returns damaged for a draw that is not an object",
            {"counterexample": ["x"]},
        ),
        ("returns damaged for a date that does not exist", {"found": "2026-02-30"}),
        (
            "returns damaged for a date of a century that is not a leap year",
            {"found": "1900-02-29"},
        ),
        ("returns damaged for a date of month 13", {"found": "2026-13-01"}),
        ("returns damaged for a date of month 0", {"found": "2026-00-01"}),
        ("returns damaged for a date of day 0", {"found": "2026-10-00"}),
        ("returns damaged for a date of year 0", {"found": "0000-10-01"}),
        ("returns damaged for a date in words", {"found": "1 October 2026"}),
        ("returns damaged for a date that is a number", {"found": 20_261_001}),
        (
            "returns damaged for a date with a final newline",
            {"found": "2026-10-01\n"},
        ),
    ]

    @pytest.mark.parametrize(
        "give", [t[1] for t in changes], ids=[t[0] for t in changes]
    )
    def test_returns_damaged_for_a_field_out_of_its_form(
        self, seat: Collector, give: dict[str, object]
    ) -> None:
        """A field is out of its form."""
        check.equal(
            seat, verdict_of(written(**give)), "damaged", "the verdict is damaged"
        )

    def test_returns_damaged_for_an_entry_without_a_field_of_the_format(
        self, seat: Collector
    ) -> None:
        """The entry does not have a date."""
        missing = written()
        del missing["found"]
        check.equal(seat, verdict_of(missing), "damaged", "the verdict is damaged")

    def test_returns_damaged_for_an_entry_with_a_field_outside_the_format(
        self, seat: Collector
    ) -> None:
        """The entry has a comment."""
        got = verdict_of(written(comment="found in review"))
        check.equal(seat, got, "damaged", "the verdict is damaged")
