"""Test assertions defined by a language-neutral standard.

Two surfaces carry the same assertions under the same names:
dokimi_assert.check stops the test at the first failure, and
dokimi_assert.expect records the failure and lets the test continue.

    from dokimi_assert import check

    def test_get(seat):
        check.equal(seat, store.get("widget"), item, "Get returns the stored item")

Every assertion takes a seat first and a message last. The seat is
where a failure is reported, and installing this package registers a
pytest fixture called seat that supplies one. The message states
the contract under test and is the first line of the failure, so a
failure says what was supposed to be true rather than only what was
observed.
"""
