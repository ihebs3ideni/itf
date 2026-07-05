"""Unit tests for the session :class:`~ctf.assembly.Assembly`.

Covers lazy resolution, the eager tier walk, availability, and the run-mode
analysis rooted at the target anchor.
"""

from __future__ import annotations

import pytest

from ctf.assembly import RunMode, analyze
from ctf.contracts import provides, requires
from ctf.descriptor import Descriptor
from ctf.dut import build_manager
from ctf.errors import CapabilityUnavailableError
from ctf.registry import Registry
from ctf.resolver import GraphResolver
from ctf.target import TARGET_ANCHOR


def _spine_registry(order: list[str] | None = None) -> Registry:
    """A small target with a substrate fact and a derived-tier bring-up ladder."""
    registry = Registry()
    registry.add_descriptor(Descriptor("ctf/env/testbench", value="bench-1"))

    @registry.register
    @provides(TARGET_ANCHOR)
    @requires("ctf/env/testbench")
    def target(bench):
        if order is not None:
            order.append("target")
        return f"target@{bench}"

    @registry.register
    @provides("ctf/target/reachable")
    @requires(TARGET_ANCHOR)
    def reachable(target):
        if order is not None:
            order.append("reachable")
        return f"reachable:{target}"

    @registry.register
    @provides("ctf/sec/token")
    @requires("ctf/target/reachable")
    def token(reachable):
        if order is not None:
            order.append("token")
        return "token-1"

    @registry.register
    @provides("ctf/cap/exec")
    @requires("ctf/sec/token")
    def exec_cap(token):
        if order is not None:
            order.append("exec")
        return f"exec[{token}]"

    return registry


def test_analyze_computes_spine_rooted_at_anchor():
    registry = _spine_registry()
    resolver = GraphResolver(registry)
    plan = analyze(registry, resolver, RunMode.LOOSE)

    # The spine is the closure reachable *from* the anchor (its substrate),
    # not the capabilities that sit above it.
    assert plan.spine == frozenset({"ctf/env/testbench", TARGET_ANCHOR})
    assert "ctf/cap/exec" not in plan.spine
    assert not plan.unavailable


def test_tier_is_derived_from_graph_depth():
    registry = _spine_registry()
    resolver = GraphResolver(registry)
    plan = analyze(registry, resolver, RunMode.LOOSE)

    # Tiers fall out of the longest path from a leaf: nobody declared them.
    assert plan.tier_of["ctf/env/testbench"] == 0
    assert plan.tier_of[TARGET_ANCHOR] == 1
    assert plan.tier_of["ctf/target/reachable"] == 2
    assert plan.tier_of["ctf/sec/token"] == 3
    assert plan.tier_of["ctf/cap/exec"] == 4


def test_get_is_lazy():
    registry = _spine_registry()
    manager = build_manager(registry)
    manager.enter()
    try:
        manager.get(TARGET_ANCHOR)
        materialized = manager.materialized()
        # Only the anchor + its substrate were built.
        assert set(materialized) == {"ctf/env/testbench", TARGET_ANCHOR}
        assert "ctf/cap/exec" not in materialized
    finally:
        manager.exit()


def test_realize_walks_tiers_in_order():
    order: list[str] = []
    registry = _spine_registry(order)
    manager = build_manager(registry)
    manager.enter()
    try:
        reports = manager.realize()
        assert order == ["target", "reachable", "token", "exec"]
        # A report per tier, 0..4.
        tiers = [r.tier for r in reports]
        assert tiers == [0, 1, 2, 3, 4]
        # Tier 0 realized the substrate fact; the top tier the exec capability.
        assert reports[0].realized == ("ctf/env/testbench",)
        assert reports[-1].realized == ("ctf/cap/exec",)
        assert manager.is_ready()
    finally:
        manager.exit()


def test_teardown_is_reverse_order():
    events: list[str] = []
    registry = Registry()

    @registry.register
    @provides("a")
    def a():
        events.append("a-up")
        yield "a"
        events.append("a-down")

    @registry.register
    @provides("b")
    @requires("a")
    def b(a):
        events.append("b-up")
        yield "b"
        events.append("b-down")

    manager = build_manager(registry)
    manager.enter()
    manager.realize()
    manager.exit()
    assert events == ["a-up", "b-up", "b-down", "a-down"]


def test_unavailable_additive_is_tolerated_in_loose():
    registry = _spine_registry()

    # An additive capability whose dependency nobody provides.
    @registry.register
    @provides("ctf/cap/ssh")
    @requires("ctf/net/endpoint")
    def ssh(endpoint):  # pragma: no cover - never instantiated
        return "ssh"

    manager = build_manager(registry, RunMode.LOOSE)
    manager.enter()
    try:
        assert not manager.available("ctf/cap/ssh")
        assert manager.available("ctf/cap/exec")
        with pytest.raises(CapabilityUnavailableError):
            manager.get("ctf/cap/ssh")
        # The spine + resolvable additive still realize cleanly.
        manager.realize()
        assert "ctf/cap/exec" in manager.materialized()
        assert "ctf/cap/ssh" not in manager.materialized()
    finally:
        manager.exit()
