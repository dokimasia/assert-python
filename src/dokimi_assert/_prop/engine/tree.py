# Copyright Dokimasia B.V. 2026
# SPDX-License-Identifier: MIT

"""The case tree is a trie of the choice sequences that a run generated.

A node is one choice request with its bounds, and an edge is the value that
the request took. A case that ends marks its last node as a leaf with its
ending. A Walker follows one case down the tree. It finds these conditions.

- A case repeats a tested case. A body is a function of its choices, so a
  choice that arrives at a leaf would end the body in the same way as the
  case of that leaf. The walker raises Repeated there, and the case does not
  count.
- A body diverges. The walker raises Diverged for a request whose bounds
  differ from the request that the tree recorded at the same position. It
  raises Diverged for a request where an earlier case ended, and for an end
  where an earlier case made a request.
- The domain is exhausted. A node is exhausted when it is a leaf, or when
  every value that its bounds allow leads to an exhausted node. A float
  choice never exhausts, and a sequence without a maximum size does not
  exhaust either.

The tree stops growing at NODE_LIMIT nodes. A walk that would add a node past
the limit stops checking for the rest of its case, and the tree does not
report an exhausted domain after that.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Literal, cast

from dokimi_assert._prop.engine.choice import (
    Bounds,
    FloatBounds,
    IntegerBounds,
    Value,
)
from dokimi_assert._prop.engine.float import NAN_BITS, bits_of

if TYPE_CHECKING:
    from dokimi_assert._prop.engine.case import Request

__all__ = ["NODE_LIMIT", "Diverged", "Ending", "Repeated", "Tree", "Walker"]

#: The largest number of nodes of a tree.
NODE_LIMIT = 2**20

#: The ending of a case.
Ending = Literal["passed", "failed", "rejected"]


class Repeated(BaseException):
    """The signal that stops a case whose choices repeat a tested case."""

    def __init__(self) -> None:
        """Return the signal."""
        super().__init__("prop: the case repeats a tested case")


class Diverged(BaseException):
    """The signal of a body that requested other choices after the same values.

    Attributes:
        index: The position.
        recorded: The bounds that the tree recorded there, or None for a
            case that ended there.
        requested: The bounds that the body requested there, or None for a
            case that ended there.
    """

    def __init__(
        self, index: int, recorded: Bounds | None, requested: Bounds | None
    ) -> None:
        """Return the divergence at an index.

        Args:
            index: The position.
            recorded: The bounds that the tree recorded, or None.
            requested: The bounds that the body requested, or None.
        """
        super().__init__(f"prop: choice {index} diverges")
        self.index: int = index
        self.recorded: Bounds | None = recorded
        self.requested: Bounds | None = requested


def _counts(bounds: Bounds, count: int) -> bool:
    """Report whether the bounds allow exactly count values.

    The function returns False for a float and for a sequence without a
    maximum size.
    """
    if isinstance(bounds, IntegerBounds):
        return bounds.hi - bounds.lo + 1 == count
    if isinstance(bounds, FloatBounds) or bounds.max_size is None:
        return False
    # The sum of k^length over the lengths soon grows past count, so the sum
    # stops there.
    power = 1
    for _ in range(bounds.min_size):
        power *= bounds.k
        if power > count:
            return False
    total = 0
    for _ in range(bounds.min_size, bounds.max_size + 1):
        total += power
        if total > count:
            return False
        power *= bounds.k
    return total == count


def _edge_key(value: Value) -> int | tuple[int, ...]:
    """Return the key of an edge.

    A float has the key of its bits, and every NaN has one key.
    """
    if isinstance(value, float):
        return NAN_BITS if math.isnan(value) else bits_of(value)
    return value


class _Node:
    """One position of the tree with its request or the end of the case."""

    def __init__(self) -> None:
        self.bounds: Bounds | None = None
        self.ending: Ending | None = None
        self.exhausted: bool = False
        self.children: dict[int | tuple[int, ...], _Node] = {}

    def settle(self) -> None:
        """Recompute from the children whether the node is exhausted.

        A node on the path of a case that ended is the leaf, or a node whose
        request the case made, so it has an ending or bounds.
        """
        if self.ending is not None:
            self.exhausted = True
            return
        self.exhausted = _counts(
            cast("Bounds", self.bounds), len(self.children)
        ) and all(child.exhausted for child in self.children.values())


class Tree:
    """The cases that the simplest, edge and random phases generated.

    Attributes:
        root: The node of the first choice of every case.
        nodes: The number of nodes so far.
        limit: The largest number of nodes.
        full: When True, a walk would have grown the tree past its limit.
    """

    def __init__(self, limit: int = NODE_LIMIT) -> None:
        """Return a tree with a root and nothing recorded.

        Args:
            limit: The largest number of nodes of the tree.
        """
        self.root: _Node = _Node()
        self.nodes: int = 1
        self.limit: int = limit
        self.full: bool = False

    @property
    def exhausted(self) -> bool:
        """True when the run has tested every input of its domain.

        Returns:
            True for a tree without an untested input.
        """
        return not self.full and self.root.exhausted

    def walker(self) -> Walker:
        """Return a walker for one new case.

        Returns:
            The walker, at the root of the tree.
        """
        return Walker(self)


class Walker:
    """The path of one case down the tree. It is the observer of the case."""

    def __init__(self, tree: Tree) -> None:
        """Return the walker that starts at the root of a tree.

        Args:
            tree: The tree.
        """
        self._tree: Tree = tree
        self._path: list[_Node] = [tree.root]
        self._off: bool = False

    def step(self, index: int, request: Request, value: Value) -> None:
        """Follow the choice at an index.

        Args:
            index: The position of the choice.
            request: The request.
            value: The value that the request took.

        Raises:
            Diverged: An earlier case ended here, or made another request.
            Repeated: The choice arrives at a leaf.
        """
        if self._off:
            return
        node = self._path[-1]
        if node.ending is not None:
            raise Diverged(index, None, request.bounds)
        if node.bounds is None:
            node.bounds = request.bounds
        elif node.bounds != request.bounds:
            raise Diverged(index, node.bounds, request.bounds)
        key = _edge_key(value)
        child = node.children.get(key)
        if child is None:
            if self._tree.nodes >= self._tree.limit:
                self._tree.full = True
                self._off = True
                return
            child = _Node()
            node.children[key] = child
            self._tree.nodes += 1
        if child.ending is not None:
            raise Repeated
        self._path.append(child)

    def end(self, ending: Ending) -> None:
        """Mark where the case ended as a leaf.

        A case does not end at an existing leaf. A choice that arrives at one
        raises Repeated. A root that is a leaf exhausts the domain, so the
        run does not start another case.

        Args:
            ending: The ending of the case.

        Raises:
            Diverged: An earlier case made a request where this one ended.
        """
        if self._off:
            return
        node = self._path[-1]
        if node.bounds is not None:
            raise Diverged(len(self._path) - 1, node.bounds, None)
        node.ending = ending
        for passed in reversed(self._path):
            passed.settle()
