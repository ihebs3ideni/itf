# *******************************************************************************
# Copyright (c) 2026 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0
#
# SPDX-License-Identifier: Apache-2.0
# *******************************************************************************
"""Generic graph algorithms shared by both gates: toposort, cycle detection and reachability.
None of this names a kind (docs/octo-kit/10-spec-octo-core.md §10, §7, §8)."""

from __future__ import annotations

from typing import Iterable


def toposort_kahn(vertices: Iterable[str], edges: frozenset[tuple[str, str]]) -> tuple[str, ...]:
    """Kahn's algorithm; the ready set is popped lexicographically smallest first, always.

    Determinism is the point: equal inputs give the same order on every machine and run, so plans
    can be compared, cached and reviewed. Do not replace with an unordered set walk.
    """
    verts = sorted(set(vertices))
    incoming: dict[str, set[str]] = {v: set() for v in verts}
    outgoing: dict[str, set[str]] = {v: set() for v in verts}
    for a, b in edges:
        outgoing[a].add(b)
        incoming[b].add(a)

    ready = sorted(v for v in verts if not incoming[v])
    order: list[str] = []
    remaining_incoming = {v: set(s) for v, s in incoming.items()}
    while ready:
        ready.sort()
        v = ready.pop(0)
        order.append(v)
        for nxt in sorted(outgoing[v]):
            remaining_incoming[nxt].discard(v)
            if not remaining_incoming[nxt]:
                ready.append(nxt)
    return tuple(order)


def find_cycle(vertices: Iterable[str], edges: frozenset[tuple[str, str]]) -> tuple[str, ...] | None:
    """Returns one cycle's path, rotated to start at its lowest-sorted vertex, or None."""
    verts = sorted(set(vertices))
    outgoing: dict[str, list[str]] = {v: [] for v in verts}
    for a, b in edges:
        outgoing[a].append(b)
    for v in outgoing:
        outgoing[v].sort()

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {v: WHITE for v in verts}
    stack_path: list[str] = []

    def visit(v: str) -> tuple[str, ...] | None:
        color[v] = GRAY
        stack_path.append(v)
        for nxt in outgoing[v]:
            if color[nxt] == GRAY:
                idx = stack_path.index(nxt)
                cycle = stack_path[idx:]
                return _rotate_to_min(cycle)
            if color[nxt] == WHITE:
                found = visit(nxt)
                if found is not None:
                    return found
        stack_path.pop()
        color[v] = BLACK
        return None

    for v in verts:
        if color[v] == WHITE:
            found = visit(v)
            if found is not None:
                return found
    return None


def _rotate_to_min(path: list[str]) -> tuple[str, ...]:
    lo = min(range(len(path)), key=lambda i: path[i])
    return tuple(path[lo:] + path[:lo])


def reachable_pairs(vertices: Iterable[str], edges: frozenset[tuple[str, str]]) -> frozenset[tuple[str, str]]:
    """All (a, b) such that a directed path a -> ... -> b exists."""
    verts = sorted(set(vertices))
    outgoing: dict[str, set[str]] = {v: set() for v in verts}
    for a, b in edges:
        outgoing[a].add(b)

    pairs: set[tuple[str, str]] = set()
    for start in verts:
        seen: set[str] = set()
        stack = list(outgoing[start])
        while stack:
            nxt = stack.pop()
            if nxt in seen:
                continue
            seen.add(nxt)
            pairs.add((start, nxt))
            stack.extend(outgoing[nxt] - seen)
    return frozenset(pairs)
