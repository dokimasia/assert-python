# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The detail of the call record of a property in the form of a vector.

The definition writes the failure of a run, and the failure of each further
failure, as an identity. The bodies of the vectors and the machine subjects
fail with a record whose assertion is that identity. Every other field of
the detail of a call record has the form of the vector already.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from dokimi_assert._matcher.fault import FaultError

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = ["detail_of"]


def _assertion_of(failure: object) -> object:
    """Return the assertion of a failure record of a call record, or None for null."""
    if not isinstance(failure, dict):
        return None
    return cast("dict[str, Any]", failure).get("assertion")


def detail_of(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the detail of the call record of a property in the form of a vector.

    Args:
        record: The call record, parsed.

    Returns:
        The detail. Its failure and the failure of each of its others are
        the assertions of their records.

    Raises:
        FaultError: The record does not have a detail, because a fault ended
            the call.
    """
    stated = record.get("detail")
    if not isinstance(stated, dict):
        error = json.dumps(record.get("error"), ensure_ascii=False)
        at = ""
        raise FaultError(at, f"the run ends with the fault {error}")
    detail = dict(cast("dict[str, Any]", stated))
    detail["failure"] = _assertion_of(detail.get("failure"))
    others = detail.get("others")
    if isinstance(others, list):
        detail["others"] = [
            {**other, "failure": _assertion_of(other.get("failure"))}
            for other in cast("list[dict[str, Any]]", others)
        ]
    return detail
