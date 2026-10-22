# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

r"""The match of text against a pattern of the portable subset.

The module re of Python reads the subset with three differences. The
expression that compile_pattern returns does not have them:

- $ also matches before a final newline, so the closing anchor becomes \Z.
- \d, \w and \s are Unicode classes, and the \s of re.ASCII contains \v, so
  each shorthand becomes the class of its members.
- The dot matches U+0085, U+2028 and U+2029, so it becomes the class of the
  dot of the subset.
"""

from __future__ import annotations

import re

from dokimi_assert._pattern.parse import parse

__all__ = ["compile_pattern"]

#: The dot of the subset. It matches any character but the five line
#: terminators.
_DOT = "[^\\n\\r\\x85\\u2028\\u2029]"

#: The members of each shorthand as the inside of a class.
_SHORTHANDS = {"d": "0-9", "w": "0-9A-Za-z_", "s": " \\t\\n\\f\\r"}


def compile_pattern(pattern: str) -> re.Pattern[str]:
    """Return the expression that reads a pattern as the portable subset reads it.

    Args:
        pattern: A pattern of the portable subset.

    Returns:
        The compiled expression for the search of re.

    Raises:
        PatternError: The pattern is outside the subset.
    """
    parse(pattern)
    source: list[str] = []
    in_class = False
    at = 0
    last = len(pattern) - 1
    # The subset escapes only ASCII characters, so the character after a
    # backslash is the whole escaped character. An unescaped [ opens a class
    # and an unescaped ] closes it, because neither is a literal there. An
    # unescaped $ at the end is the closing anchor of a pattern that parses.
    while at <= last:
        char = pattern[at]
        if char == "\\":
            escaped = pattern[at + 1]
            members = _SHORTHANDS.get(escaped)
            if members is None:
                source.append(f"\\{escaped}")
            else:
                source.append(members if in_class else f"[{members}]")
            at += 2
            continue
        if not in_class and char == ".":
            source.append(_DOT)
        elif not in_class and char == "$" and at == last:
            source.append("\\Z")
        else:
            source.append(char)
        if char in "[]":
            in_class = char == "["
        at += 1
    return re.compile("".join(source))
