"""Test assertions defined by a language-neutral standard.

Two surfaces carry the same assertions under the same names:
:mod:`dokimi.check` stops the test at the first failure, and
:mod:`dokimi.expect` records the failure and lets the test continue.

    from dokimi import check

    check.equal(got, want, "Get returns the stored item")

Every assertion takes a message last. It states the contract under test
and is the first line of the failure, so a failure says what was
supposed to be true rather than only what was observed.
"""
