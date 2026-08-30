"""This library held to the standard.

The standard is language-neutral and lives in its own repository. Every
language repository carries its own copy of this check, because it
reads the library under test and nothing can do that across a language
boundary.

Two things are checked. The corpus states what an assertion must report
and is shared with every other implementation, so it catches this
library meaning something different by the same name. The definition
states which assertions exist, so it catches one missing or misnamed.
"""
