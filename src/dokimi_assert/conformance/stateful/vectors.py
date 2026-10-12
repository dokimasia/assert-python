"""The runner of the machines vectors.

A machines vector has a machine subject, and it can have the options of the
steps as its setup, the settings of the run and a trace. The runner runs the
subject with prop.for_all on a recorder, after the trace, and compares the
detail of the call record of the property with the detail of the vector. A
vector whose trace the run refuses has the entry, the name of its step and
the reason as its error. The runner compares the error with the fault that
ends the call.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from dokimi_assert import prop, stateful
from dokimi_assert._matcher.fault import FaultError
from dokimi_assert.conformance.files import Runner
from dokimi_assert.conformance.literal import same_json
from dokimi_assert.conformance.prop.choices import seed_of
from dokimi_assert.conformance.prop.detail import detail_of
from dokimi_assert.conformance.stateful.subjects import SUBJECTS, Setup
from dokimi_assert.seat import Recorder

__all__ = ["CONTRACT", "RUNNERS"]

#: The contract of the property that runs a machine subject.
CONTRACT = "the machine subject of the vector"

#: The clients of the setup of a vector that does not have clients.
_SETUP_CLIENTS = 2

#: The members that the setup of a vector can have.
_SETUP = frozenset({"mean", "max", "swarm", "clients", "concurrent", "strategy"})


def _strategy_of(written: object) -> stateful.Strategy:
    """Return the strategy of a setup: uniform, or {"pct": depth}.

    Raises:
        FaultError: The value is not a strategy.
    """
    if written == "uniform":
        return stateful.uniform()
    if isinstance(written, dict) and list(cast("dict[str, Any]", written)) == ["pct"]:
        return stateful.pct(cast("dict[str, Any]", written)["pct"])
    raise FaultError("setup.strategy", f"{json.dumps(written)} is not a strategy")


def _setup_of(written: Mapping[str, Any]) -> Setup:
    """Return the options of the setup of a vector.

    A setup without clients has the clients of the setup of the definition.

    Raises:
        FaultError: The setup has a member that the runner does not take, or
            a strategy that is not a strategy.
    """
    for name in sorted(written):
        if name not in _SETUP:
            raise FaultError(f"setup.{name}", "the runner does not take the member")
    steps: list[stateful.Option] = []
    if "mean" in written:
        steps.append(stateful.mean(written["mean"]))
    if "max" in written:
        steps.append(stateful.max_steps(written["max"]))
    if "swarm" in written:
        steps.append(stateful.swarm(written["swarm"] is True))
    section = [stateful.clients(written.get("clients", _SETUP_CLIENTS))]
    if "concurrent" in written:
        section.append(stateful.concurrent(written["concurrent"]))
    return Setup(steps, section, _strategy_of(written.get("strategy", "uniform")))


def _settings_of(written: Mapping[str, Any]) -> list[prop.Option]:
    """Return the options of the run of the settings of a vector.

    The run is hermetic and does not have a store.

    Raises:
        FaultError: The settings have a setting other than seed and cases.
    """
    options = [prop.hermetic(), prop.store("")]
    for name, value in written.items():
        if name == "seed":
            options.append(prop.seed(seed_of(value)))
        elif name == "cases":
            options.append(prop.cases(value))
        else:
            raise FaultError(f"settings.{name}", "the runner does not take the setting")
    return options


def _compare_refusal(record: Mapping[str, Any], error: Mapping[str, Any]) -> None:
    """Compare the fault that ends a run with the refusal of a trace entry.

    Raises:
        FaultError: The run does not end with the refusal of the entry of the
            vector.
    """
    message = str(record.get("error", ""))
    at = f"prop.for_all: draws[{error.get('entry')}].{error.get('reason')}: "
    name = json.dumps(error.get("name"))
    if not message.startswith(at) or name not in message:
        raise FaultError(
            "error",
            f"the run ends with {json.dumps(message)}, want a refusal of entry "
            f"{error.get('entry')} of {name}",
        )


def _check_machines(raw: Mapping[str, Any], _: str) -> None:
    """Run the subject of a machines vector, and compare the run with the vector.

    The subject runs under the setup and the settings of the vector, after
    its trace. The run has the detail or the error of the vector.

    Raises:
        FaultError: The vector does not have a machine subject, has a setup
            or a setting that the runner does not take, or the run differs
            from the vector.
    """
    make = SUBJECTS.get(cast("str", raw.get("subject")))
    if make is None:
        raise FaultError(
            "subject", f"{json.dumps(raw.get('subject'))} is not a machine subject"
        )
    setup = _setup_of(cast("dict[str, Any]", raw.get("setup") or {}))
    options = _settings_of(cast("dict[str, Any]", raw.get("settings") or {}))
    if raw.get("trace") is not None:
        options.append(prop.draws(json.dumps(raw["trace"])))
    subject = make()
    recorder = Recorder()
    prop.for_all(recorder, CONTRACT, lambda c: subject(c, setup), *options)
    record = json.loads(recorder.records[0])
    error = raw.get("error")
    if isinstance(error, dict):
        _compare_refusal(record, cast("dict[str, Any]", error))
        return
    detail = detail_of(record)
    if not same_json(detail, raw.get("detail")):
        raise FaultError(
            "detail",
            f"the run has the detail {json.dumps(detail)}, "
            f"want {json.dumps(raw.get('detail'))}",
        )


#: The runner of each kind of machines vector, by the kind. A runner raises a
#: fault at the part of the vector that the run contradicts, and for a vector
#: that it cannot read.
RUNNERS: dict[str, Runner] = {"machines": _check_machines}
