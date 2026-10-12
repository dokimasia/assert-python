"""The searches of the dependency graph of committed transactions.

The searches find the strongly connected components of the graph, the
shortest path within one component, and the simple cycle of a closed walk.
A graph maps each transaction to its targets in ascending order, so every
search visits the edges of a transaction in the order of their targets.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from typing import Literal

__all__ = [
    "RELATIONS",
    "Graph",
    "Relation",
    "Walk",
    "alternates",
    "components",
    "path",
    "simple",
]

#: A dependency of one committed transaction on another.
Relation = Literal["ww", "wr", "rw"]

#: The relations in the order in which an entry of a cycle lists them.
RELATIONS: tuple[Relation, ...] = ("ww", "wr", "rw")

#: The targets of each transaction in ascending order.
Graph = Mapping[int, Sequence[int]]

#: A closed walk. Each step has a transaction and the relation of the edge
#: that leaves it.
Walk = Sequence[tuple[int, Relation]]


class _Tarjan:
    """The state of one search for strongly connected components."""

    def __init__(self, graph: Graph) -> None:
        """Return the state of a search of graph that has not visited a transaction."""
        self.graph: Graph = graph
        self.order: dict[int, int] = {}
        self.low: dict[int, int] = {}
        self.stack: list[int] = []
        self.on_stack: set[int] = set()
        #: The transactions whose edges the search visits. Each entry has a
        #: transaction and the position of its next edge.
        self.work: list[list[int]] = []
        self.found: list[list[int]] = []

    def enter(self, node: int) -> None:
        """Visit a transaction for the first time."""
        self.order[node] = len(self.order)
        self.low[node] = self.order[node]
        self.stack.append(node)
        self.on_stack.add(node)
        self.work.append([node, 0])

    def leave(self, node: int) -> None:
        """Finish a transaction, and collect its component when it is the root."""
        self.work.pop()
        if self.work:
            parent = self.work[-1][0]
            self.low[parent] = min(self.low[parent], self.low[node])
        if self.low[node] != self.order[node]:
            return
        at = self.stack.index(node)
        component = self.stack[at:]
        del self.stack[at:]
        self.on_stack.difference_update(component)
        if len(component) > 1:
            self.found.append(sorted(component))

    def visit(self, root: int) -> None:
        """Visit every transaction on a path from root with an explicit stack."""
        if root not in self.order:
            self.enter(root)
        while self.work:
            top = self.work[-1]
            node, following = top
            targets = self.graph.get(node, ())
            top[1] = following + 1
            if following >= len(targets):
                self.leave(node)
                continue
            target = targets[following]
            if target not in self.order:
                self.enter(target)
            elif target in self.on_stack:
                self.low[node] = min(self.low[node], self.order[target])


def components(nodes: Sequence[int], graph: Graph) -> list[list[int]]:
    """Return the strongly connected components of two or more transactions.

    The search is the algorithm of Tarjan without recursion. Each component
    lists its transactions in ascending order. The components are in the
    order of their lowest transactions.

    Args:
        nodes: The transactions. The search visits them in this order.
        graph: The edges.

    Returns:
        The components.
    """
    search = _Tarjan(graph)
    for root in nodes:
        search.visit(root)
    return sorted(search.found, key=lambda component: component[0])


def path(start: int, goal: int, graph: Graph, members: Set[int]) -> list[int] | None:
    """Return the shortest path from start to goal within members.

    When two paths are shortest, the result is the one that comes first in
    the order of the targets.

    Args:
        start: The first transaction.
        goal: The last transaction.
        graph: The edges.
        members: The transactions that the path can visit.

    Returns:
        The transactions of the path from start to goal, or None when members
        does not contain a path from start to goal.
    """
    parent = {start: start}
    queue = [start]
    for node in queue:
        if node == goal:
            found = [node]
            while node != start:
                node = parent[node]
                found.append(node)
            return found[::-1]
        for target in graph.get(node, ()):
            if target in members and target not in parent:
                parent[target] = node
                queue.append(target)
    return None


def _first_repeat(walk: Walk) -> tuple[int, int] | None:
    """Return the two positions of the first transaction that a walk visits twice."""
    seen: dict[int, int] = {}
    for position, (node, _) in enumerate(walk):
        first = seen.get(node)
        if first is not None:
            return first, position
        seen[node] = position
    return None


def alternates(walk: Walk) -> bool:
    """Report whether a closed walk does not have two adjacent read-write edges.

    Args:
        walk: The closed walk.

    Returns:
        True when the walk alternates.
    """
    return not any(
        relation == "rw" and walk[(i + 1) % len(walk)][1] == "rw"
        for i, (_, relation) in enumerate(walk)
    )


def simple(walk: Walk) -> list[tuple[int, Relation]]:
    """Return a simple cycle of a closed walk without two adjacent read-write edges.

    While a transaction occurs twice, the walk splits at the first repeat
    into the part between the two occurrences and the rest. The search keeps
    the part between them when that part alternates. Otherwise it keeps the
    rest. The cycle starts at its first read-write edge.

    Args:
        walk: The closed walk. It must not have two adjacent read-write
            edges.

    Returns:
        The cycle.
    """
    current = list(walk)
    repeat = _first_repeat(current)
    while repeat is not None:
        first, second = repeat
        inner = current[first:second]
        current = inner if alternates(inner) else current[:first] + current[second:]
        repeat = _first_repeat(current)
    start = next((i for i, (_, r) in enumerate(current) if r == "rw"), 0)
    return current[start:] + current[:start]
