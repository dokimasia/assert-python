# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The spec of _record/call.py tests the line of JSON of one call record."""

from __future__ import annotations

import json

from dokimi_assert._record.call import DEFINITION, Call, Place, encode_call
from dokimi_assert.conformance.definition import version


class TestDefinition:
    """DEFINITION is the version of the definition in every call record."""

    def test_is_the_version_of_the_vendored_definition(self) -> None:
        """Every record contains the version that the library vendors."""
        assert version() == DEFINITION


class TestEncodeCall:
    """encode_call writes the record of a numbered call."""

    def test_writes_a_passing_call_with_the_base_name_of_its_file(self) -> None:
        """A record contains the base name of the file of the call site."""
        call = Call(
            "equal", "the count is right", "pass", True, ("/src/shop/test_store.py", 42)
        )
        assert encode_call(call, Place(seq=1)) == (
            f'{{"definition":"{DEFINITION}","seq":1,"assertion":"equal",'
            '"contract":"the count is right","verdict":"pass","aborting":true,'
            '"where":{"file":"test_store.py","line":42}}'
        )

    def test_writes_the_detail_of_a_failing_call(self) -> None:
        """The record of a failing call contains its detail."""
        call = Call(
            "equal", "c", "fail", False, detail={"got": {"type": "int", "value": 1}}
        )
        record = json.loads(encode_call(call, Place(seq=2)))
        assert record["detail"] == {"got": {"type": "int", "value": 1}}
        assert "where" not in record

    def test_writes_a_skipped_call_with_the_detail_of_its_run(self) -> None:
        """The record of a skipped property contains the verdict skip and its run."""
        call = Call(
            "prop-for-all",
            "c",
            "skip",
            True,
            detail={"outcome": "skipped", "reason": "unsupported"},
        )
        record = json.loads(encode_call(call, Place(seq=1)))
        assert (record["verdict"], record["detail"]) == (
            "skip",
            {"outcome": "skipped", "reason": "unsupported"},
        )

    def test_writes_the_text_of_the_fault_of_an_error(self) -> None:
        """The record of a faulted call contains the text of the fault."""
        call = Call("prop-for-all", "c", "error", True, error="prop.for_all: no")
        record = json.loads(encode_call(call, Place(seq=1)))
        assert (record["verdict"], record["error"]) == ("error", "prop.for_all: no")

    def test_writes_the_parent_the_run_and_the_phase_of_a_call_in_a_body(self) -> None:
        """The record of a call in a case has its parent, its run and its phase."""
        call = Call("true", "c", "pass", True)
        record = json.loads(
            encode_call(call, Place(seq=3, parent=1, run=2, phase="random"))
        )
        assert list(record)[:5] == ["definition", "seq", "parent", "run", "phase"]
        assert (record["parent"], record["run"], record["phase"]) == (1, 2, "random")

    def test_writes_no_phase_for_a_call_in_a_body_of_another_assertion(self) -> None:
        """The record of a call in an attempt of eventually does not have a phase."""
        record = json.loads(
            encode_call(Call("true", "c", "pass", True), Place(3, 1, 1))
        )
        assert "phase" not in record
        assert (record["parent"], record["run"]) == (1, 1)
