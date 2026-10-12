"""The identity of a failure. The shrinker keeps a failure by its identity.

- A failure record of an assertion with a call site is kept by its
  assertion and its call site. A record without a call site is kept by its
  assertion and its contract. These two are the same for every case that
  fails at one call.
- A message that the body passes to fail or record of the case is kept by
  the innermost frame of the code of the caller.
- An exception that the body raises is kept by its class and by the
  innermost frame of the code of the caller in its traceback.

The code of the caller is every frame outside this library. Two failures
are one failure when their identities are equal, and a message is not part
of an identity.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from dokimi_assert.failure import Failure, Where, site_in

__all__ = [
    "Identity",
    "entry_of",
    "from_key",
    "key_of",
    "of_error",
    "of_record",
    "text_of",
]


@dataclass(frozen=True, slots=True)
class Identity:
    """The key by which the shrinker keeps a failure.

    Attributes:
        assertion: The assertion that reported the failure, or None for a
            message and for an exception.
        contract: The contract of a record of an assertion without a call
            site, or None.
        error: The class of a raised exception, or None.
        where: The innermost frame of the code of the caller, or the call
            site of the record of an assertion.
    """

    assertion: str | None = None
    contract: str | None = None
    error: str | None = None
    where: Where | None = None


def of_record(failure: Failure) -> Identity:
    """Return the identity of a failure record.

    A message that the body passed to the case is a record without an
    assertion.

    Args:
        failure: The record.

    Returns:
        The identity.
    """
    assertion = failure.assertion or None
    unsited = assertion is not None and failure.where is None
    return Identity(
        assertion, failure.contract if unsited else None, None, failure.where
    )


def of_error(value: BaseException, fallback: Where | None) -> Identity:
    """Return the identity of an exception that the body raised.

    The identity has the class of the exception and the innermost frame of
    the code of the caller in its traceback. An exception whose traceback
    does not have such a frame takes fallback.

    Args:
        value: The exception.
        fallback: The call site of the property.

    Returns:
        The identity.
    """
    site = site_in(value.__traceback__)
    return Identity(
        error=type(value).__name__, where=fallback if site is None else site
    )


def key_of(identity: Identity) -> str:
    """Return the text that two identities share exactly when they are equal.

    Args:
        identity: The identity.

    Returns:
        The text.
    """
    where = identity.where
    parts = [
        identity.assertion,
        identity.contract,
        identity.error,
        None if where is None else where.file,
        None if where is None else where.line,
    ]
    return json.dumps(parts, ensure_ascii=False, separators=(",", ":"))


def from_key(key: str) -> Identity:
    """Return the identity whose text key_of returned.

    Args:
        key: The text.

    Returns:
        The identity.
    """
    assertion, contract, error, file, line = json.loads(key)
    return Identity(
        assertion, contract, error, None if file is None else Where(file, line)
    )


def text_of(identity: Identity) -> str:
    """Return the text of an identity in a sentence.

    Args:
        identity: The identity.

    Returns:
        The text.
    """
    where = identity.where
    at = "" if where is None else f" at {os.path.basename(where.file)}:{where.line}"
    if identity.error is not None:
        return f"a {identity.error} raised{at}"
    if identity.assertion is None:
        return f"a message{at}"
    contract = identity.contract
    of = "" if not contract else f" of {json.dumps(contract, ensure_ascii=False)}"
    return f"{identity.assertion}{of}{at}"


def entry_of(identity: Identity) -> dict[str, str | int]:
    """Return the identity in the form of a store entry.

    The entry has the base name of the file and the line beside the
    assertion, the contract or the error.

    Args:
        identity: The identity.

    Returns:
        The identity of the entry as a JSON object.
    """
    keys: dict[str, str | int] = {}
    if identity.assertion is not None:
        keys["assertion"] = identity.assertion
    if identity.contract is not None:
        keys["contract"] = identity.contract
    if identity.error is not None:
        keys["error"] = identity.error
    if identity.where is not None:
        keys["file"] = os.path.basename(identity.where.file)
        keys["line"] = identity.where.line
    return keys
