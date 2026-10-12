"""The check of this library against the definition.

The definition is language-neutral and has a repository of its own. Each
language repository has its own copy of this check, because the check
imports the library under test, and an import does not cross a language
boundary.

The check runs two parts of the definition against this library. Every
implementation runs the same cases of the corpus, so a case fails when this
library gives a name a different meaning. The naming table lists the
assertions that exist, so the check also finds an assertion that is missing
or misnamed.
"""
