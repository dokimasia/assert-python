# dokimi

Test assertions for Python, defined by a language-neutral standard and
held to it on every run.

```python
from dokimi import check

def test_get(seat):
    item = store.get(id)

    check.is_not_none(seat, item, "Get returns the stored item")
    check.equal(seat, item.name, "widget", "and the item is the one stored")
```

Every assertion takes a message last. It states the contract under test
and is the first line of the failure.

## Two surfaces

`check` stops the test at the first failure. `expect` records the
failure and lets the test continue, for when several properties of one
value are each worth seeing. Both carry the same assertions under the
same names and run the same comparison.

## Equality, and why it differs from `==`

Python's `==` does not answer what the standard asks:

| Expression | Python | Here |
|---|---|---|
| `0 == False` | `True` | not equal |
| `1 == 1.0` | `True` | not equal |
| `[] == None` | `False` | not equal |

`bool` subclasses `int`, so `0 == False` is true, and numeric types
compare across themselves. The standard says values of different types
never compare, so this enforces it: `type(got) is type(want)`, not
`isinstance`.

An absent collection does not equal an empty one. Pass `equate_empty()`
where that difference does not matter.

## The standard

The assertions are defined in `assert-spec`, language-neutral, and
implemented in several languages. This library vendors the definition
and holds itself to it:

- 70 corpus cases state what each assertion must report. They are the
  same cases every other implementation runs.
- The naming table says what each assertion is called here, so a
  missing or misnamed one fails the build.

## State

All 41 assertions the standard states are implemented: equality, truth,
nullity, length, containment, text, numbers, ordering, errors, raising,
behaviour, waiting, golden files, benchmark ceilings, and `rejects`.

All 70 corpus cases pass. The completeness gate checks every assertion
is present under the name the naming table gives it.

### Where Python differs

Go states cancellation with `context.Context`, which appears in every
signature. Python has no such convention, so `honours_cancellation`,
`honours_deadline` and `no_task_leaks` are built on asyncio, whose
`CancelledError`, timeouts and tasks are the real analogue. They take a
coroutine function rather than a callable.

`completes_within` measures rather than interrupts: it reports whether
a subject finished in time, and a slow subject runs to completion
first.

Allocation ceilings use `tracemalloc`, which counts what Python itself
allocated and carries real overhead. Set those ceilings from a traced
run; latency ceilings need no such care.

## Development

```sh
uv pip install -e ".[dev]"
python -m pytest
ruff check src tests
```
