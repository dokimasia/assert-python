"""The private package of the comparisons that both public surfaces run.

Each assertion takes a seat and a mode. The surface that stops the test and
the surface that does not stop it then run the same comparison, so they
cannot disagree about the meaning of an assertion.

Nothing here is public. The names that a caller types are in
dokimi_assert.check and dokimi_assert.expect.
"""
