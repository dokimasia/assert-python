"""Comparison logic, shared by both public surfaces.

Each assertion takes a seat and a mode, so the surface that stops the
test and the surface that does not run the same comparison and cannot
disagree about what an assertion means.

Nothing here is public. The names a caller types are in
dokimi_assert.check and dokimi_assert.expect.
"""
