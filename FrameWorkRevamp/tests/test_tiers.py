"""Derived tiers: a contract's tier falls out of the dependency graph.

Nobody declares a phase. ``compute_tiers`` gives each contract its longest-path
depth from a leaf, and the tier law ("require only lower tiers") is therefore
true by construction. Graph faults (cycles) still fail fast at ``build_manager``.
"""

from __future__ import annotations

import pytest

from ctf.assembly import compute_tiers
from ctf.contracts import provides, requires
from ctf.descriptor import Descriptor
from ctf.dut import build_manager
from ctf.errors import CyclicDependencyError
from ctf.registry import Registry


def _tiers(registry: Registry) -> dict[str, int]:
    return compute_tiers(registry, registry.contracts())


def test_descriptor_is_tier_zero():
    registry = Registry()
    registry.add_descriptor(Descriptor("fact"))
    assert _tiers(registry)["fact"] == 0


def test_provider_without_requires_is_tier_zero():
    registry = Registry()

    @registry.register
    @provides("svc")
    def svc():
        return object()

    assert _tiers(registry)["svc"] == 0


def test_tier_is_one_above_deepest_dependency():
    registry = Registry()

    @registry.register
    @provides("handle")
    def handle():
        return "handle"

    @registry.register
    @provides("reachable")
    @requires("handle")
    def reachable(handle):
        return handle

    @registry.register
    @provides("token")
    @requires("reachable")
    def token(reachable):
        return "token"

    @registry.register
    @provides("exec")
    @requires("token")
    def exec_cap(token):
        return token

    tiers = _tiers(registry)
    assert tiers == {"handle": 0, "reachable": 1, "token": 2, "exec": 3}


def test_tier_takes_the_longest_path_in_a_diamond():
    registry = Registry()

    @registry.register
    @provides("base")
    def base():
        return "base"

    @registry.register
    @provides("short")
    @requires("base")
    def short(base):
        return base

    @registry.register
    @provides("mid")
    @requires("base")
    def mid(base):
        return base

    @registry.register
    @provides("deep")
    @requires("mid")
    def deep(mid):
        return mid

    # top depends on a tier-1 (short) and a tier-2 (deep): longest path wins.
    @registry.register
    @provides("top")
    @requires("short", "deep")
    def top(short, deep):
        return (short, deep)

    tiers = _tiers(registry)
    assert tiers["base"] == 0
    assert tiers["short"] == 1
    assert tiers["mid"] == 1
    assert tiers["deep"] == 2
    assert tiers["top"] == 3


def test_realizes_in_tier_order():
    registry = Registry()
    order: list[str] = []

    @registry.register
    @provides("handle")
    def handle():
        order.append("handle")
        return "handle"

    @registry.register
    @provides("reachable")
    @requires("handle")
    def reachable(handle):
        order.append("reachable")
        return handle

    @registry.register
    @provides("exec")
    @requires("reachable")
    def exec_cap(reachable):
        order.append("exec")
        return reachable

    manager = build_manager(registry)
    manager.enter()
    manager.get("exec")
    manager.exit()

    assert order == ["handle", "reachable", "exec"]


def test_cycle_fast_exits_at_build_manager():
    registry = Registry()

    @registry.register
    @provides("a")
    @requires("b")
    def a(b):
        return b

    @registry.register
    @provides("b")
    @requires("a")
    def b(a):
        return a

    with pytest.raises(CyclicDependencyError):
        build_manager(registry)


def test_empty_contract_rejected_by_decorator():
    with pytest.raises(ValueError):

        @provides("")
        def x():
            return 1
