"""The pieces of a pattern of the portable subset and their decoding from a case.

Each piece decodes in a fixed way. An alternation of two or more branches
chooses one with an integer that decides structure. A quantifier decodes its
repetitions as a collection. A class chooses a character with an integer
index over its members in the order of the default alphabet. The targets
give the first branch of each alternation, the fewest repetitions, and the
simplest character of each class.
"""

from __future__ import annotations

import dokimi_assert._pattern.parse as syntax
from dokimi_assert._prop.engine import alphabet
from dokimi_assert._prop.engine.case import Case
from dokimi_assert._prop.engine.choice import IntegerBounds
from dokimi_assert._prop.engine.collection import ELEMENT, Sizes, collect
from dokimi_assert._prop.engine.generator import Piece

__all__ = ["Alternation", "Class", "Literal", "Repeat", "Sequence", "piece"]

#: The span labels of an alternation and of the repetitions of a quantifier.
_ALTERNATION = "alternation"
_REPEAT = "repeat"


class Literal:
    """One character. It does not make a choice.

    Attributes:
        char: The character.
    """

    def __init__(self, char: str) -> None:
        """Return the piece of a character.

        Args:
            char: One code point.
        """
        self.char: str = char

    def emit(self, c: Case, out: list[str]) -> None:
        """Append the character."""
        del c
        out.append(self.char)


class Class:
    """One character of a set. An integer index over the members chooses it.

    The members are in the order of the default alphabet. Index 0 is the
    target and the simplest member.

    Attributes:
        intervals: The members as intervals of indices of the default
            alphabet.
        size: The number of members.
    """

    def __init__(self, intervals: list[alphabet.Interval]) -> None:
        """Return the class of the members in intervals.

        Args:
            intervals: The members as merged intervals of indices.
        """
        self.intervals: tuple[alphabet.Interval, ...] = tuple(intervals)
        self.size: int = sum(end - start + 1 for start, end in intervals)
        self._bounds: IntegerBounds = IntegerBounds(0, self.size - 1)

    def emit(self, c: Case, out: list[str]) -> None:
        """Append the member at the index that the case chooses."""
        offset = c.integer(self._bounds)
        at = 0
        start, end = self.intervals[0]
        while offset > end - start:
            offset -= end - start + 1
            at += 1
            start, end = self.intervals[at]
        out.append(alphabet.character(start + offset))

    def offset_of(self, char: str) -> int | None:
        """Return the offset of a character among the members.

        Args:
            char: One code point.

        Returns:
            The offset, or None for a character that is not a member.
        """
        position = alphabet.index_of(char)
        if position is None:
            return None
        offset = 0
        for start, end in self.intervals:
            if start <= position <= end:
                return offset + position - start
            offset += end - start + 1
        return None


class Sequence:
    """Pieces decoded one after another.

    Attributes:
        items: The pieces.
    """

    def __init__(self, items: list[Piece]) -> None:
        """Return the sequence of items.

        Args:
            items: The pieces.
        """
        self.items: tuple[Piece, ...] = tuple(items)

    def emit(self, c: Case, out: list[str]) -> None:
        """Decode each piece in order."""
        for item in self.items:
            item.emit(c, out)


class Alternation:
    """Two or more branches. An index that decides structure chooses the branch.

    Attributes:
        branches: The branches.
        bounds: The bounds of the index.
    """

    def __init__(self, branches: list[Piece]) -> None:
        """Return the alternation of branches.

        Args:
            branches: Two or more branches.
        """
        self.branches: tuple[Piece, ...] = tuple(branches)
        self.bounds: IntegerBounds = IntegerBounds(0, len(branches) - 1)

    def emit(self, c: Case, out: list[str]) -> None:
        """Decode the branch that the case chooses in a span labelled alternation."""
        with c.span(_ALTERNATION):
            self.branches[c.integer(self.bounds, 0)].emit(c, out)


class Repeat:
    """A quantified piece. Its repetitions decode as a collection.

    Attributes:
        item: The repeated piece.
        sizes: The repetitions that the quantifier allows.
    """

    def __init__(self, item: Piece, sizes: Sizes) -> None:
        """Return the repetition of item.

        Args:
            item: The repeated piece.
            sizes: The repetitions that the quantifier allows.
        """
        self.item: Piece = item
        self.sizes: Sizes = sizes

    def emit(self, c: Case, out: list[str]) -> None:
        """Decode the repetitions in a span labelled repeat."""

        def repetition() -> tuple[None, None]:
            self.item.emit(c, out)
            return None, None

        with c.span(_REPEAT):
            collect(c, self.sizes, ELEMENT, repetition)


def _piece_of(node: syntax.Node) -> Piece:
    """Return the piece of a parsed node."""
    if isinstance(node, syntax.Literal):
        return Literal(node.char)
    if isinstance(node, syntax.Class):
        intervals = alphabet.merge(
            [found for lo, hi in node.ranges for found in alphabet.indices(lo, hi)]
        )
        if not intervals:
            raise ValueError("prop: a class in the pattern does not have a member")
        return Class(intervals)
    if isinstance(node, syntax.Concat):
        return Sequence([_piece_of(item) for item in node.items])
    if isinstance(node, syntax.Alternation):
        return Alternation([_piece_of(branch) for branch in node.branches])
    return Repeat(_piece_of(node.item), Sizes(node.min, node.max))


def piece(text: str) -> Piece:
    """Return the piece of a pattern of the portable subset.

    Args:
        text: The pattern.

    Returns:
        The piece.

    Raises:
        PatternError: The pattern is outside the subset.
        ValueError: A class of the pattern does not have a member.
    """
    return _piece_of(syntax.parse(text).node)
