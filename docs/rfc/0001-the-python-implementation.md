---
rfc: 0001
title: The Python assertion library
author: Roy Klopper <roy.klopper@stealthscale.io>
status: Draft
created: 2026-08-30
updated: 2026-08-30
discussion: none
supersedes: none
superseded-by: none
produces-adr: tbd
---

# RFC-0001: The Python assertion library

## Summary

`dokimi_assert` implements the standardized assertion set in Python. The
comparison logic lives once, in a private package, taking a mode that
says whether a failure stops the test. Two public modules wrap it:
`check` stops, `expect` records and continues. A third reads the
definition and the corpus and fails the build when this library
disagrees with either.

## Motivation

Python's `==` does not answer what the standard asks, and the gap is
silent.

`bool` subclasses `int`, so `0 == False` is `True`. Numeric types
compare across themselves, so `1 == 1.0` is `True`. The standard says
values of different types never compare, and names `0` against `false`
as a case. A library that inherited `==` would pass its own tests,
read correctly, and disagree with every other implementation on an
equality rule the standard is built around.

Two more differences follow from Python having no equivalent of the
convention the first implementation was written against. There is no
`context.Context` in every signature, and `assert` is a keyword, so
neither the cancellation assertions nor the module names can be
carried across unchanged.

## Detailed design

### Modules

```
dokimi_assert.check          aborting surface, and rejects
dokimi_assert.expect         recording surface, same members
dokimi_assert.golden         golden files
dokimi_assert.bench          benchmark ceilings
dokimi_assert.seat           the seats an assertion reports through
dokimi_assert._matcher       comparison logic, private
dokimi_assert.conformance    this library checked against the standard
```

`check` and `expect` rather than `assert` and `expect`: `assert` is a
keyword, so `import assert` is a syntax error. A trailing underscore is
the convention for a keyword clash, but `assert_.equal(...)` reads
badly at every call site, and every call site is where an assertion
library is read.

### Equality is enforced, not inherited

```python
def equal(got: Any, want: Any, relax: Option) -> bool:
    if type(got) is not type(want):
        return False
    ...
```

`type(got) is type(want)`, not `isinstance`: a `bool` is not an `int`
here, and an `int` is not a `float`. That is stricter than Python users
expect, and it is what the standard asks for. It also makes the corpus
pass unmodified, including the case naming `0` against `false`.

The rule reaches inside collections, so `[1]` does not equal `[1.0]`.
Comparing only the outer type would let the difference through one
level down.

### The seat

```python
class Seat(Protocol):
    def helper(self) -> None: ...
    def fail(self, message: str) -> None: ...
    def record(self, message: str) -> None: ...
```

A Protocol rather than a base class, so anything with the three
methods is a seat without importing this library to say so.

Two are supplied. `Standard` raises `AssertionError`, which every test
framework already treats as a failing test, so nothing here needs an
exception type of its own. `Recorder` collects, which is what lets an
assertion be tested by reading what it reported and what the recording
surface reports through.

The library is not tied to pytest. It sets `__tracebackhide__` where
pytest reads it and works unchanged under `unittest` or none.

### Cancellation is asyncio

Go states cancellation with a context in every signature. Python has no
such convention: a subject might take an `asyncio` cancellation, a
`threading.Event`, a token of its own, or nothing.

asyncio is the one the language itself supplies, so
`honours_cancellation`, `honours_deadline` and `no_task_leaks` drive a
coroutine function and read `CancelledError`, timeouts and the task
set. They are not divergences: Python expresses all three, in its own
terms.

`completes_within` measures rather than interrupts. Interrupting
synchronous Python needs threads or signals, both of which change what
is being measured, so this reports whether a subject finished in time
and lets a slow one finish.

### Both surfaces are written out

Each surface declares every assertion explicitly rather than binding
them from a table at import.

Binding would be shorter. It also leaves no signature for an editor to
complete, no docstring for `help()` to show, and nothing for a type
checker to read, which is the same cost that ruled out generating the
second surface in the first implementation. The duplication is
mechanical and the conformance check catches it drifting.

## Alternatives considered

### A. Inherit Python's `==`

Compare with `==` and let Python answer.

**Why not:** `0 == False` and `1 == 1.0` are both `True`, so the
library would ship disagreeing with the standard on the equality rule
the standard is built around, and would need a declared divergence to
say so.

### B. Reject `bool` against `int` only

Enforce the one case the corpus names, and let numeric types compare
across themselves as Python does.

**Why not:** it passes the corpus while leaving `1 == 1.0` true, so
this implementation and the first would answer the same case
differently. The corpus does not cover it today, which makes the
divergence silent rather than absent.

### C. Tie the library to pytest

Raise `AssertionError` directly, use pytest hooks for the recording
surface.

**Why not:** simplest, and best pytest integration. It gives the
standard's seam nowhere to live, and the recording surface needs
somewhere to put a failure that is not the framework.

## Drawbacks

**Strict typing surprises Python users.** `check.equal(seat, 1, 1.0,
...)` fails. That is the standard, and it will read as a bug to
somebody the first time they meet it.

**The cancellation assertions need asyncio.** A synchronous subject
using a `threading.Event` cannot be driven by them. Nothing else in the
library requires asyncio.

**Allocation ceilings measure with tracemalloc**, which counts what
Python allocated and carries real overhead. A ceiling set from an
untraced run will not hold in a traced one.

**Both surfaces are written twice.** About 33 wrappers each. The
conformance check catches them diverging, but the writing is manual.

## Open questions

None.

## Unresolved and future work

A pytest plugin supplying a seat as a fixture, so a test need not
construct one, is not proposed here.

## References

| What | Where |
|---|---|
| bool as a subclass of int | https://docs.python.org/3/library/functions.html#bool |
| asyncio cancellation | https://docs.python.org/3/library/asyncio-task.html#task-cancellation |
| tracemalloc | https://docs.python.org/3/library/tracemalloc.html |
