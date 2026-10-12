"""The faults of this library.

A fault is an error of the library. An input that a call cannot take is a
fault. An error of the platform that ends a call is a fault too. The text of
a fault contains the place of the fault in the input, the reason, and the
error that caused it. A colon separates the parts.
"""

from __future__ import annotations

from dokimi_assert._matcher.verdict import fault_text

__all__ = ["FaultError", "of_operation"]


class FaultError(Exception):
    """An error of this library at a part of an input or at the whole input.

    Attributes:
        at: The place of the fault in the input. It is a selector such as
            entries[2].mode, a path of a tree, or the empty string for the
            whole input.
        reason: A clause that describes what is wrong.
    """

    def __init__(
        self, at: str, reason: str, cause: BaseException | None = None
    ) -> None:
        """Return the fault at a part of an input.

        Args:
            at: The place of the fault in the input, or the empty string.
            reason: A clause that describes what is wrong.
            cause: The error that caused the fault, or None. It can be an
                error of the file system.
        """
        parts = [at, reason, "" if cause is None else fault_text(cause)]
        super().__init__(": ".join(part for part in parts if part))
        self.at: str = at
        self.reason: str = reason
        self.__cause__: BaseException | None = cause

    def within(self, outer: str) -> FaultError:
        """Return this fault as a fault of a larger input that contains this one.

        Args:
            outer: The selector of this input within the larger input. An
                example is the member of a vector that contains a tree.

        Returns:
            The fault at the joined selector. It has the same reason and the
            same cause.
        """
        at = ".".join(part for part in (outer, self.at) if part)
        cause = self.__cause__
        return FaultError(at, self.reason, cause)


def of_operation(op: str, error: object) -> Exception:
    """Return the fault that a seat receives when error ended an operation.

    Args:
        op: The name of the operation in the form module.function.
        error: The error that ended the operation.

    Returns:
        An exception whose text is op, a colon and the text of error.
    """
    return Exception(f"{op}: {fault_text(error)}")
