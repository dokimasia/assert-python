# dokimi-assert

Test assertions for Python, defined by a language-neutral standard and
held to it on every run.

[![CI](https://github.com/dokimasia/assert-python/actions/workflows/ci.yml/badge.svg)](https://github.com/dokimasia/assert-python/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/dokimi-assert)](https://pypi.org/project/dokimi-assert/)
[![Python](https://img.shields.io/pypi/pyversions/dokimi-assert)](https://pypi.org/project/dokimi-assert/)
[![Licence](https://img.shields.io/badge/licence-MIT-blue)](LICENSE)

```sh
pip install dokimi-assert
```

The distribution is `dokimi-assert`; the package you import is
`dokimi_assert`. Python 3.11 and up. No runtime dependencies.

- [Getting started](#getting-started)
- [Two surfaces](#two-surfaces) — stop at the first failure, or see them all
- [The assertions](#the-assertions) — every signature
- [Equality](#equality) — why `0 != False` here
- [Golden files](#golden-files)
- [Testing your own assertions](#testing-your-own-assertions)
- [The standard](#the-standard)

## Getting started

Installing the package registers a pytest plugin, so the `seat` fixture
is available with no conftest and nothing to import.

```python
from dokimi_assert import check


def test_get(seat):
    item = store.get("widget")

    check.is_not_none(seat, item, "Get returns the stored item")
    check.equal(seat, item.name, "widget", "and the item is the one stored")
```

Every assertion takes the seat first and a message last. The message
states the contract under test and is the first line of the failure:

```
AssertionError: and the item is the one stored: want 'widget', got 'gadget'
```

### What a seat is

The seat is where a failure goes. Assertions never call pytest and
never raise on their own; they report to whatever seat they are handed.
That is what lets one assertion serve a real test, a benchmark, and a
test that checks the assertion itself.

You will normally use the fixture and not think about it. Three seats
exist, and the fixture hands you the first:

| Seat | `check` does | `expect` does |
|---|---|---|
| `Collector`, from the `seat` fixture | stops the test | records, reported when the body ends |
| `Standard` | stops the test | stops the test |
| `Recorder`, from the `recorder` fixture | records | records |

Use `Standard()` outside pytest, where nothing owns the end of a test.
Use `Recorder` to read back what an assertion reported instead of
suffering it.

## Two surfaces

`check` stops at the first failure. `expect` records and carries on, so
one run shows every property that failed.

```python
from dokimi_assert import check, expect


def test_reply(seat):
    reply = client.fetch(url)

    check.equal(seat, reply.status, 200, "the request succeeds")

    expect.has_prefix(seat, reply.body, "{", "the body is JSON")
    expect.length(seat, reply.items, 3, "every item comes back")
    expect.contains(seat, reply.headers, "etag", "the reply is cacheable")
```

If two of the three `expect` calls fail, both are reported together:

```
AssertionError: 2 failures:
  1. every item comes back: expected length 3, got 2
  2. the reply is cacheable: {'etag': ...} does not contain 'etag'
```

Use `check` when nothing after it makes sense, and `expect` when each
line states an independent property. Both carry the same assertions
under the same names.

## The assertions

Thirty-four in the root namespace on both surfaces, plus three for
golden files and five on the benchmark contract.

<!-- api-reference:start -->

Every assertion takes the seat first and the message last.
`check` and `expect` carry the same names and the same
signatures; only what happens on a failure differs.

**Equality** — Structural, and strict about types.

```python
check.equal(seat: Seat, got: Any, want: Any, msg: str, *options: Option)
check.not_equal(seat: Seat, got: Any, want: Any, msg: str, *options: Option)
```

**Truth and absence** — The two-value cases.

```python
check.is_true(seat: Seat, condition: bool, msg: str)
check.is_false(seat: Seat, condition: bool, msg: str)
check.is_none(seat: Seat, got: Any, msg: str)
check.is_not_none(seat: Seat, got: Any, msg: str)
```

**Size** — Anything with a length.

```python
check.length(seat: Seat, got: Any, want: int, msg: str)
check.is_empty(seat: Seat, got: Any, msg: str)
check.is_not_empty(seat: Seat, got: Any, msg: str)
```

**Containment** — What holding means follows the haystack.

```python
check.contains(seat: Seat, haystack: Any, needle: Any, msg: str, *options: Option)
check.not_contains(seat: Seat, haystack: Any, needle: Any, msg: str, *options: Option)
check.contains_in_order(seat: Seat, got: Any, needles: Sequence[str], msg: str)
```

**Text** — str and bytes.

```python
check.has_prefix(seat: Seat, got: Any, prefix: str, msg: str)
check.has_suffix(seat: Seat, got: Any, suffix: str, msg: str)
check.matches(seat: Seat, got: Any, pattern: str, msg: str)
```

**Numbers** — Where exact equality is the wrong question.

```python
check.close_to(seat: Seat, got: Any, want: float, tolerance: float, msg: str)
check.in_range(seat: Seat, got: Any, low: float, high: float, msg: str)
```

**Ordering** — Sorted, unique, and anything else that holds between neighbours.

```python
check.pairwise(seat: Seat, items: Sequence[Any], predicate: Callable[[Any, Any], bool], msg: str)
```

**Errors** — For code that hands an error back rather than raising it.

```python
check.no_error(seat: Seat, exc: BaseException | None, msg: str)
check.has_error(seat: Seat, exc: BaseException | None, msg: str)
check.error_is(seat: Seat, exc: BaseException | None, target: BaseException, msg: str)
check.error_is_not(seat: Seat, exc: BaseException | None, target: BaseException, msg: str)
check.error_as(seat: Seat, exc: BaseException | None, want: type[_E], msg: str) -> _E | None
```

**Raising** — For code that raises.

```python
check.raises(seat: Seat, fn: Callable[[], Any], msg: str) -> BaseException | None
check.does_not_raise(seat: Seat, fn: Callable[[], Any], msg: str)
```

**Cancellation** — asyncio is Python's cancellation model. These run the loop themselves, so your test stays a plain def.

```python
check.honours_cancellation(seat: Seat, fn: Callable[[], Awaitable[Any]], msg: str)
check.honours_deadline(seat: Seat, fn: Callable[[], Awaitable[Any]], msg: str)
check.completes_within(seat: Seat, within: float, fn: Callable[[], Any], msg: str)
check.none_handle_safe(seat: Seat, fn: Callable[[Any], Any], msg: str)
```

**Retrying** — For a condition something outside the test makes true. Both spend real time.

```python
check.eventually(seat: Seat, timeout: float, interval: float, body: Callable[[Any], None], msg: str)
check.eventually_true(seat: Seat, timeout: float, predicate: Callable[[], bool], msg: str)
```

**Concurrency** — Call what it returns where the scope ends.

```python
check.no_task_leaks(seat: Seat, msg: str) -> Callable[[], None]
```

**Purity** — What observe returns defines what nothing means.

```python
check.is_pure(seat: Seat, observe: Callable[[], Any], fn: Callable[[], Any], msg: str, *options: Option)
```

**Testing an assertion** — On check only: expect cannot drive a check to failure, because it does not stop.

```python
check.rejects(seat: Seat, msg: str, body: Callable[[Recorder], None]) -> str
```

**Golden files** — recorded output, compared and rewritable.

```python
golden.match(seat: Seat, name: str, got: str, update: bool, *scrubbers: Scrubber)
golden.match_at(seat: Seat, path: str | Path, got: str, update: bool, *scrubbers: Scrubber)
golden.match_json_field(seat: Seat, path: str | Path, field: str, got: str, update: bool, *scrubbers: Scrubber)
golden.should_update() -> bool
golden.scrub_timestamps() -> Scrubber
golden.scrub_hashes() -> Scrubber
golden.scrub_run_ids() -> Scrubber
golden.scrub_json_fields(*fields: str) -> Scrubber
```

**Benchmark ceilings** — chained onto one contract.

```python
Contract.loop(iterations: int) -> Iterator[int]
Contract.max_latency(seconds: float) -> Contract
Contract.max_mean(seconds: float) -> Contract
Contract.max_allocs(count: int) -> Contract
Contract.max_bytes(count: int) -> Contract
```

Each one carries a full docstring: what it states, what every
argument means, the edge cases it decides, and a worked call.
Read them with `help(check.close_to)` or in your editor.

<!-- api-reference:end -->

### A few in use

```python
from dokimi_assert import check


def test_shapes(seat):
    err = check.raises(seat, lambda: parse("{"), "a truncated body is refused")
    check.contains(seat, str(err), "unexpected end", "and it says where")

    check.pairwise(seat, timestamps, lambda a, b: a <= b, "the log is ordered")
    check.close_to(seat, elapsed, 1.0, 0.05, "the retry waited about a second")
    check.matches(seat, request_id, r"^req_[0-9a-f]{16}$", "the id is well formed")


def test_cancellation(seat):
    # The subject is a coroutine function; the test is not. The
    # assertion drives the event loop itself, so no async plugin.
    check.honours_cancellation(seat, worker.run, "the worker stops when told")
```

## Equality

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

An absent collection does not equal an empty one. Where that difference
does not matter, relax the comparison for one call:

```python
from dokimi_assert.option import equate_empty, equate_nans

check.equal(seat, reply.items, [], "no items came back", equate_empty())
```

An option applies to the call it is passed to and nothing else. There
is no global setting, because a rule changed in one place and read in
another is how two tests come to mean different things.

## Golden files

```python
from dokimi_assert import golden


def test_render(seat):
    golden.match_at(
        seat,
        "testdata/report.txt",
        render(report),
        golden.should_update(),
        golden.scrub_timestamps(),
    )
```

Set `DOKIMI_ASSERT_UPDATE_GOLDEN=1` to rewrite the files. Read the diff
before you do. Scrubbers cover timestamps, hex digests, run ids and
named JSON fields, so a value that changes every run does not fail the
comparison.

## Testing your own assertions

`rejects` states that a check fails, which is the one thing an
assertion library has to be able to say about itself:

```python
def test_the_validator_refuses_an_empty_name(seat):
    check.rejects(
        seat,
        "an empty name is refused",
        lambda inner: check.is_none(inner, validate(""), "it passes"),
    )
```

The `recorder` fixture is the lower-level version: drive an assertion
with it, then read `failed` and `message`.

## The standard

The assertions are defined in
[assert-spec](https://github.com/dokimasia/assert-spec),
language-neutral, and implemented in several languages. This library
vendors the definition and holds itself to it:

- 87 corpus cases state what each assertion must report, run against
  both surfaces. They are the same cases every other implementation
  runs.
- A completeness gate checks every assertion is present under the name
  the naming table gives it.
- An overlay records any assertion this library cannot supply. It is
  empty: all 41 are implemented.

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
make install    # create the environment
make check      # the full pre-merge gate
make test       # tests
make fmt        # format and autofix
make build      # build the sdist and wheel
make spec-sync  # refresh the vendored definition
```

`make check` runs ruff, a formatting check, mypy strict, basedpyright
and the tests with a coverage floor. CI runs it on 3.11 through 3.14.
The design is recorded in
[docs/rfc/0001-the-python-implementation.md](docs/rfc/0001-the-python-implementation.md).

Pushing a `v*` tag builds, re-runs the gate, checks the tag agrees with
`pyproject.toml`, and publishes to PyPI through Trusted Publishing.

## Licence

MIT. See [LICENSE](LICENSE).
