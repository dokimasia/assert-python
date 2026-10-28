# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The assertion call that a seat observes.

A seat that has a method observe_call(call) receives each assertion call, a
passing one included: every call that a recorded run records, whatever
DOKIMI_ASSERT_RECORD states. It receives each call once, before it receives
the failure, the fault or the skip of that call. It receives the calls of a
body when the call that ran the body takes them, so the calls of the cases of
a property arrive in the order of a run on one worker.

    class Handle:
        def observe_call(self, call: Call) -> None:
            self.asserted.add(call.contract)
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Call"]


@dataclass(frozen=True, slots=True)
class Call:
    """An assertion call, with the id of the assertion and the contract.

    Attributes:
        assertion: The id of the assertion, as the definition names it.
        contract: The message of the caller, unchanged.
    """

    assertion: str
    contract: str
