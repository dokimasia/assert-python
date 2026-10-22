---
rfc: 0004
title: Definition 10.0.0 in Python
author: Roy Klopper <roy.klopper@stealthscale.io>
status: Accepted
created: 2026-10-22
updated: 2026-10-22
discussion: https://github.com/dokimasia/assert-spec/issues/18
supersedes: none
superseded-by: none
produces-adr: none
---

<!--
  ~ Copyright Dokimasia B.V. 2026
  ~ SPDX-License-Identifier: MIT
-->

# RFC-0004: Definition 10.0.0 in Python

## Summary

The library moves from definition 9.0.0 to 10.0.0.

| Change | Python API |
|---|---|
| A helper ends its call with a fault through the seat | `seat.fault`, the optional seat method `report_fault`, `Recorder.report_fault` and `Recorder.faults` |
| A check that a fault ends ends the call of `rejects` with that fault | `rejects` of `check` |
| A test reads the values of a generator for a seed | `prop.values` |
| A test reads whether its run checks allocation ceilings | `bench.allocs_checked` |
| A run of `for_all` and `fuzz` takes `using` | `prop.using` returns an `Option` |

Python declines the allocation ceilings, so the ten counts of
`max-allocs` do not apply. Every call record states 10.0.0.

## Motivation

The completeness gate fails on every row of the naming table that the
library neither offers nor declines. Definition 10.0.0 adds the rows
`seat.report-fault`, `recorder-seat.faults`, `fault`, `allocs-checked`
and `prop.values`, so the library cannot vendor 10.0.0 without them.

`using` returns a `FormOnly` today, so `for_all` and `fuzz` refuse it. The
definition gives every run of a property the option. A body that draws
`prop.of(Order)` cannot narrow the `Status` inside each order for that run
alone, and `register_values` narrows it for the whole test process.

## Detailed design

### Faults through the seat

```python
class Seat(Protocol):
    """The object through which an assertion reports a failure.

    A seat can also have the method report_fault(fault, ending), which
    receives a fault as the exception it is.
    """


def fault(seat: Seat, error: BaseException) -> None:
    """End the call of a helper with error, a fault.

    Raises:
        BaseException: error, for a seat without report_fault.
        TypeError: error is not an exception.
    """


class Recorder:
    def report_fault(self, fault: BaseException, ending: bool) -> None: ...

    @property
    def faults(self) -> list[BaseException]: ...
```

- The library passes each fault of its own to `report_fault` of the seat
  with `ending` True. It passes a fault that a call notes, such as a file
  of a property's store that the run skips, with `ending` False.
- A seat without the method raises the exception of an ending fault at the
  call, and warns with the text of a noted fault through `warnings`.
  `Collector` and `Standard` do not have the method, so a fault of the
  library raises its own exception in place of `AssertionError`. The text
  of the exception does not change.
- `Recorder` keeps each fault in order. An ending fault fails the recorder
  with the text of the fault, as `fail` does. A noted fault does not fail
  it.
- The seat of an attempt of `eventually` and the case of a property fail
  with the text of an ending fault, as they do today. They pass a noted
  fault to the seat of their assertion.
- `fault` does not write a call record, because the call is not a call of
  an assertion. It is a member of the module `dokimi_assert.seat`, beside
  the seats.

### The fault of a check

The seat of the check that `rejects` drives has `report_fault`:

- An ending fault ends the check, and the seat keeps the fault.
- A noted fault passes to the seat of `rejects`, and the check runs on.

`rejects` then ends its own call with the kept fault through
`Running.faulted`. The call record has the verdict `error`, the seat of
`rejects` receives the fault as `fault` passes it, and `rejects` returns an
empty list. A `FaultError` that the check raises ends the call in the same
way, as it does today.

### The values of a seed

```python
def values(generator: Generator[T], seed: int, n: int) -> list[T]:
    """Return n values of generator for seed.

    Raises:
        ValueError: n is not an int of 0 or more, seed is not an int in
            [0, 2**64), or the generator rejects more than 10n cases.
    """
```

- Case k decodes from the random source of seed + k, as a random case of a
  run does. A case that the generator rejects does not give a value.
- An exception that the generator raises passes through.
- The call does not run a property. It does not try the simplest case or a
  boundary case. It does not record an assertion, write a stored case or
  read a variable of the engine. A draw of `of` uses the registration or
  the shape of its type.

### Whether a run checks allocation ceilings

```python
def allocs_checked() -> tuple[bool, str]:
    """Return False and the reason: CPython does not count allocations."""
```

The helper is a member of `dokimi_assert.bench`, beside the benchmark
ceilings. Python declines `max-allocs`, so the helper returns False in
every run.

### Using in every run

```python
def using(t: type[Any], generator: Generator[Any]) -> Option:
    """Make generator the generator of t in the run that the option is passed to."""
```

`for_all`, `fuzz` and every property form take the option. A later `using`
of one type replaces an earlier one. A run's generators apply to the draws
of `of`:

| Draw | Generator |
|---|---|
| `of(t)` of a type that the run states | The stated generator |
| `of(u)` of a type that contains a stated type | `u` read with the stated generators in place of their types |
| `of(t)` inside the stated generator of `t` | `t` without its own stated generator, with the run's other generators |
| Any other generator, such as `prop.integer(0, 9)` | The generator itself |

The third row keeps a stated generator from drawing itself without end.

`of(t)` returns a `Picking`, a deferred generator of the engine that picks
its generator where it is used. The run sets its generators in a context
variable on the thread of the call and around each run of the body, so a
draw on the thread of a worker reads them. `history.concurrently` runs each
client in a copy of the context of its caller. A stated generator decodes
inside a `Within`, which sets the run's generators without its type. The
engine decodes, inverts and walks a deferred generator inside the context
of its pick. A stored literal, an entry of `draws`, a filling that explains
a draw and an example of a form then use the generators of the run.
`prop.values` decodes outside any run.

### Version

`DEFINITION` of `dokimi_assert._record.call` becomes `10.0.0`, and every
call record states it. The library vendors the copy of 10.0.0 with spec.

## Alternatives considered

### A. A fault through `fail` for a seat without the method

`Collector` and `Standard` would keep receiving the text of a fault
through `fail`, as `AssertionError`.

**Why not:** the definition states that a seat without the method ends the
call as the helper `fault` does, and the helper raises the fault in
Python. One rule for the helper and for the library also keeps the
exception that a test catches the same for both.

### B. Keep `using` on the forms alone

The overlay of Python would declare that a run of `for_all` and `fuzz`
does not take `using`.

**Why not:** Python keeps the types of a program at run time, so a run can
give a type a generator. The registry would remain the only way to narrow a
type inside a body of `for_all`, and the registry applies to the whole test
process.

### C. Read the run's generators where `of` is called

`of(t)` would return the generator of `t` under the generators of the run
that calls it.

**Why not:** a body often builds its generators before its run, such as at
the level of the module.

## Drawbacks

- A fault of the library on `Collector` shows the traceback of its own
  exception, such as a `FaultError`, in place of an `AssertionError`.
- Each run of the body sets and resets one context variable.
- A run with `using` reads each type that its draws of `of` name once more.
- A draw of `of` whose read fails under the run's generators fails its case
  with a `TypeError`, not before the run.
- No vector covers the faults, `using` or `allocs_checked`, so the specs of
  the library alone test them.

## References

| What | Where |
|---|---|
| Ten counts of an allocation ceiling | <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0032-ten-counts-of-an-allocation-ceiling.md> |
| Faults through the seat | <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0033-faults-through-the-seat.md> |
| A check that ends with a fault | <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0034-a-check-that-ends-with-a-fault.md> |
| The values of a generator for a seed | <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0035-the-values-of-a-generator-for-a-seed.md> |
| Whether a run checks allocation ceilings | <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0036-whether-a-run-checks-allocation-ceilings.md> |
| The option of a single property | <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0011-property-forms-and-derived-inputs.md> |
