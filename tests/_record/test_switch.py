"""The spec of _record/switch.py tests the switch that turns call records on.

The process reads the switch once, so each case reads it in a child process
of its own.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from dokimi_assert._record.switch import VARIABLE, Reading
from helpers import run_python

PROBE = """
from dokimi_assert._record.switch import reading
print(reading())
"""


class TestVariable:
    """VARIABLE is the environment variable that turns call records on."""

    def test_contains_the_name_dokimi_assert_record(self) -> None:
        """Every implementation reads a variable of this name."""
        assert VARIABLE == "DOKIMI_ASSERT_RECORD"


class TestReading:
    """reading returns the reading of DOKIMI_ASSERT_RECORD."""

    tests: ClassVar[list[tuple[str, str, Reading]]] = [
        ("reads an empty variable as off", "", Reading(on=False)),
        ("reads 0 as off", "0", Reading(on=False)),
        ("reads 1 as on", "1", Reading(on=True)),
        (
            "reads any other value as the fault of the variable",
            "yes",
            Reading(on=False, fault="DOKIMI_ASSERT_RECORD: 'yes' is neither 0 nor 1"),
        ),
    ]

    @pytest.mark.parametrize(("name", "give", "want"), tests, ids=[t[0] for t in tests])
    def test_reads_the_variable(self, name: str, give: str, want: Reading) -> None:
        """Each value of the variable has its reading."""
        child = run_python(PROBE, **{VARIABLE: give})
        assert child.stdout.strip() == repr(want), (name, child.stderr)

    def test_reads_an_unset_variable_as_off(self) -> None:
        """Without the variable, the process does not record."""
        child = run_python(
            f"import os\nos.environ.pop({VARIABLE!r}, None)\n{PROBE}",
        )
        assert child.stdout.strip() == repr(Reading(on=False)), child.stderr

    def test_reads_the_variable_once_per_process(self) -> None:
        """A change of the variable during a run does not change the reading."""
        child = run_python(
            f"""
            import os
            from dokimi_assert._record.switch import reading
            first = reading()
            os.environ[{VARIABLE!r}] = "1"
            print(reading() is first, reading().on)
            """,
            **{VARIABLE: "0"},
        )
        assert child.stdout.strip() == "True False", child.stderr
