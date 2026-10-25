# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""A property whose cases a fuzzer decodes from its byte inputs.

pytest does not have a fuzzer. Under pytest, fuzz replays the stored cases of
the property and the seed files of the test. It returns the target that a
fuzzer such as Atheris runs on its byte inputs. The library does not depend
on a fuzzer. A suite that fuzzes passes the target to the fuzzer that it
installs.
"""

from __future__ import annotations

import unittest
from collections.abc import Callable
from typing import TYPE_CHECKING

from dokimi_assert._matcher.fault import FaultError, of_operation
from dokimi_assert._matcher.verdict import Running
from dokimi_assert._prop.detail import FOR_ALL
from dokimi_assert._prop.directory import seeds, seeds_of
from dokimi_assert._prop.option import Option, configure
from dokimi_assert._prop.property import Call, Property
from dokimi_assert.failure import call_site
from dokimi_assert.seat import Standard

if TYPE_CHECKING:
    from dokimi_assert._matcher.seat import Seat
    from dokimi_assert._prop.case import Case

__all__ = ["Target", "fuzz"]

#: The target of a fuzzer. It runs the case of one byte input.
Target = Callable[[bytes], None]


def _refused(call: Call, error: FaultError) -> Target:
    """Return the target of a property whose call ended with a fault.

    The target raises the fault for every input.
    """

    def target(_: bytes) -> None:
        raise of_operation(call.op, error)

    return target


def fuzz(
    seat: Seat, contract: str, body: Callable[[Case], object], *options: Option
) -> Target:
    """Replay the stored cases and seed files of a property, and return its target.

    fuzz first replays the stored cases from the oldest in the same way as
    for_all. The first stored case that fails is reported as
    found. Its record of prop-for-all fails the test on seat. The record
    counts the stored cases that ran. The record of each call of a case has
    the phase stored. fuzz notes each stored case whose values differ from
    the values in its entry. fuzz does not run a campaign or a random
    case under any profile, because for_all checks the property with the
    same body and contract.

    Then each seed file of the test runs as one input in the order of the
    file names. The seed files of a test are in testdata/fuzz/<path>/<test>,
    where <path> is the path of the module of the test and <test> is the
    name of the item. The bytes of each input decode into the choices of one
    case by the bridge rules of the definition, so every input is a valid
    case. A seed file contains the bytes of the choices of a case, not a
    value. For one byte string without a maximum size, the first two bytes
    are its length in little-endian order. The bytes after them are its
    content.

    The target runs each input as a call of its own on a Standard seat. The
    record of the call has the calls of the case of the input under the
    phase fuzz. The case of a failing input is replayed, shrunk and
    explained in the same way as a failing case of for_all. Its failures are
    written to the store. The target then raises AssertionError with the sentence of
    the record. The sentence contains the replay token. The record of a
    passing input counts one valid or one rejected case. The target returns
    for an input whose case skips, and the fuzzer moves on to the next input.
    Under pytest, a stored case or a seed file that skips skips the test.

    fuzz ends the call with a fault for each fault for which for_all ends
    its call without a run, and for seed files that cannot be read. The
    target of such a call raises the fault for every input.

    Args:
        seat: The seat that receives the failure. Use the seat fixture.
        contract: The property under test.
        body: The body. It takes its inputs from its case. It can be a
            coroutine function.
        *options: The settings of the run. The options replay, draws, cases
            and require apply only to for_all and the property forms. The
            variable DOKIMI_ASSERT_PROP_REPLAY applies only to them too.

    Returns:
        The target.

    Example:
        target = prop.fuzz(seat, "parse does not raise", parses_any_input)
    """
    __tracebackhide__ = True
    seat.helper()
    where = call_site()
    running = Running.begin(seat, where)
    call = Call("prop.fuzz", FOR_ALL, contract, where)
    try:
        prop = Property.of(seat, call, configure(options))
        inputs = seeds(seeds_of(seat))
    except FaultError as error:
        Property.fault(running, call, error)
        return _refused(call, error)
    prop.replay_stored(seat, running, body)
    for _, data in inputs:
        prop.input(seat, Running.begin(seat, where), body, data)

    def target(data: bytes) -> None:
        __tracebackhide__ = True
        standard = Standard()
        try:
            prop.input(standard, Running.begin(standard, where), body, data)
        except unittest.SkipTest:
            return

    return target
