---
rfc: 0003
title: Definition 9.0.0 in Python
author: Roy Klopper <roy.klopper@stealthscale.io>
status: Accepted
created: 2026-10-22
updated: 2026-10-22
discussion: none
supersedes: none
superseded-by: none
produces-adr: none
---

<!--
  ~ Copyright Dokimasia B.V. 2026
  ~ SPDX-License-Identifier: MIT
-->

# RFC-0003: Definition 9.0.0 in Python

## Summary

The library moves from definition 8.0.0 to 9.0.0. Definition 8.1.0 adds
the property option `around`, which the naming table gives Python as
`prop.around`. Definition 9.0.0 renames TypeScript names alone, so no
other Python name changes. Every call record states 9.0.0.

```python
def per_run(run: Callable[[], None]) -> None:
    with time_machine.travel(EPOCH, tick=False):
        run()


prop.for_all(seat, "a retry waits for its backoff", body, prop.around(per_run))
```

## Motivation

The completeness gate fails on every row of the naming table that the
library neither offers nor declines. Definition 9.0.0 has the row
`prop.around`, so the library cannot vendor 9.0.0 without it.

A test that enters an environment around a whole property runs every case
inside that one environment. Under a frozen clock, each case then starts
where the case before it left the clock. A patch that one case changes
stays changed for the cases after it. A wrapper that the engine calls for
each run gives each run an environment of its own.

## Detailed design

### The option

```python
#: The wrapper of the runs of a property's body. It calls run once inside an
#: environment that it chooses, and returns after run returns.
Wrapper = Callable[[Callable[[], None]], object]


def around(wrapper: Wrapper) -> Option:
    """Run each run of the body inside wrapper.

    Raises:
        ValueError: wrapper is not callable.
    """
```

- `run` takes no argument, because the environments of Python take no
  test.
- `run` returns None after the body and its cleanups end. It raises
  nothing for a failing case, so a wrapper that calls it inside `try` and
  `finally` cannot change the verdict.
- Given more than once, the last wrapper applies.
- `prop.for_all`, `prop.fuzz` and every property form take the option.

### What runs inside the wrapper

The wrapper runs every run of the body: the case of `draws`, each stored
case, each generated case, each shrink candidate, each filling that
explains a draw, each case of a campaign, the case of `replay` and the
case of each fuzz input. The engine's own work runs outside it, such as
the store, the shrinker's choice of the next candidate and the limit of
`shrink_time`. A coroutine body runs on the event loop of its run, inside
the wrapper.

### The verdict and the faults

| Wrapper | Effect |
|---|---|
| Returns without calling `run` | The call ends with the fault `around: the wrapper returned without calling run` |
| Calls `run` a second time | The second call runs nothing, and the call ends with the fault `around: the wrapper called run a second time` |
| Raises an exception | The call ends with the fault `around: the wrapper raised`, followed by the text of the exception |
| Calls `run` on another thread and returns before it ends | The engine waits for the body and its cleanups before it reads the verdict |
| Calls `run` after it returned | The call runs nothing |

The text of each fault starts with the operation, such as
`prop.for_all: around: the wrapper returned without calling run`.

### Workers

Under `workers(n)` the engine calls the wrapper on up to n threads at
once. A wrapper must then be safe to run concurrently with itself, as the
body must be.

### The cancellation handle

`run` hands the case no test, so a case takes its handle from the
property's seat, as it does without the option.

### Version

`DEFINITION` of `dokimi_assert._record.call` becomes `9.0.0`, and every
call record states it. The library vendors the copy of 9.0.0 with spec.

## Alternatives considered

### A. A function that returns a context manager

The option would take a function that returns a context manager, such as
`prop.around(lambda: time_machine.travel(EPOCH))`, and the engine would
run each case inside a `with` block of it.

**Why not:** a `with` block cannot pass the run to another thread or to a
call that takes a function, such as `contextvars.Context.run`. The
definition states a wrapper of `run`, and a wrapper can enter any context
manager itself.

### B. A coroutine function as the wrapper

The option would take a coroutine function, and `run` would return an
awaitable.

**Why not:** the environments that a test enters for one run are
synchronous context managers. time-machine's `travel`, freezegun's
`freeze_time` and `unittest.mock.patch` are three of them. A coroutine
wrapper also needs an event loop for every case, and a synchronous body
runs without one.

## Drawbacks

- Every run of the body costs a call of the wrapper, a lock and an event.
- A wrapper that blocks stalls the run.
- A property on more than one worker needs a wrapper that is safe to run
  concurrently with itself.
- No vector covers the option, so the specs of the library alone test it.

## References

| What | Where |
|---|---|
| The option and its rules | <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0031-a-wrapper-around-each-run-of-a-property.md> |
| The renamed TypeScript names | <https://github.com/dokimasia/assert-spec/blob/main/docs/rfc/0013-typescript-names-free-on-vitest-expect.md> |
| time-machine's `travel` | <https://github.com/adamchainz/time-machine> |
| freezegun's `freeze_time` | <https://github.com/spulec/freezegun> |
