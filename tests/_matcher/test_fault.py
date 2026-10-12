"""The spec of _matcher/fault.py tests the faults of the library."""

from __future__ import annotations

from dokimi_assert._matcher.fault import FaultError, of_operation


class TestFaultError:
    """FaultError is an error at a part of an input."""

    def test_joins_its_parts_with_colons(self) -> None:
        """FaultError joins the part, the reason and the cause with colons."""
        cause = OSError("permission denied")
        error = FaultError("entries[2].mode", "the mode is refused", cause)
        assert str(error) == "entries[2].mode: the mode is refused: permission denied"
        assert (error.at, error.reason, error.__cause__) == (
            "entries[2].mode",
            "the mode is refused",
            cause,
        )

    def test_has_the_reason_alone_for_the_whole_input(self) -> None:
        """The text of a fault of the whole input without a cause is its reason."""
        assert str(FaultError("", "the tree is empty")) == "the tree is empty"


class TestFaultErrorWithin:
    """FaultError.within returns the fault as a fault of a larger input."""

    def test_returns_the_fault_within_a_larger_input(self) -> None:
        """The selector of the larger input comes first."""
        cause = OSError("gone")
        error = FaultError("mode", "refused", cause).within("give")
        assert (error.at, error.reason, error.__cause__, str(error)) == (
            "give.mode",
            "refused",
            cause,
            "give.mode: refused: gone",
        )

    def test_returns_the_fault_of_a_whole_input_within_a_larger_one(self) -> None:
        """The fault of a whole input is at the selector of the larger input."""
        assert FaultError("", "refused").within("give").at == "give"


class TestOfOperation:
    """of_operation returns the fault of an operation that an error ended."""

    def test_puts_the_operation_before_the_error(self) -> None:
        """The text starts with the operation."""
        error = of_operation("files.workspace", OSError("disk full"))
        assert str(error) == "files.workspace: disk full"
