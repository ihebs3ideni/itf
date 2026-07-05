from __future__ import annotations

import pytest

from ctf.contracts import provides, requires
from ctf.descriptor import Descriptor
from ctf.errors import CyclicDependencyError, UnresolvedContractError
from ctf.registry import Registry
from ctf.resolver import GraphResolver


def _register(registry, contract, deps=()):
    def factory(*args):
        return contract

    factory = provides(contract)(factory)
    if deps:
        factory = requires(*deps)(factory)
    registry.register(factory)


def test_plan_orders_dependencies_first():
    registry = Registry()
    registry.add_descriptor(Descriptor("transport/doip"))
    _register(registry, "doip/client", deps=["transport/doip"])
    _register(registry, "uds/client", deps=["doip/client"])

    plan = GraphResolver(registry).plan("uds/client")
    assert plan == ["transport/doip", "doip/client", "uds/client"]


def test_plan_is_deterministic():
    registry = Registry()
    registry.add_descriptor(Descriptor("a"))
    registry.add_descriptor(Descriptor("b"))
    _register(registry, "c", deps=["a", "b"])
    _register(registry, "d", deps=["c", "a"])

    resolver = GraphResolver(registry)
    assert resolver.plan("d") == resolver.plan("d") == ["a", "b", "c", "d"]


def test_leaf_descriptor_plan():
    registry = Registry()
    registry.add_descriptor(Descriptor("only"))
    assert GraphResolver(registry).plan("only") == ["only"]


def test_unresolved_contract():
    registry = Registry()
    _register(registry, "needs", deps=["missing"])
    with pytest.raises(UnresolvedContractError) as exc:
        GraphResolver(registry).plan("needs")
    assert exc.value.contract == "missing"
    assert exc.value.required_by == "needs"


def test_cycle_detected():
    registry = Registry()
    _register(registry, "a", deps=["b"])
    _register(registry, "b", deps=["a"])
    with pytest.raises(CyclicDependencyError) as exc:
        GraphResolver(registry).plan("a")
    assert exc.value.cycle[0] == exc.value.cycle[-1]


def test_diamond_dependency_visits_shared_node_once():
    registry = Registry()
    registry.add_descriptor(Descriptor("base"))
    _register(registry, "left", deps=["base"])
    _register(registry, "right", deps=["base"])
    _register(registry, "top", deps=["left", "right"])

    plan = GraphResolver(registry).plan("top")
    assert plan.count("base") == 1
    assert plan.index("base") < plan.index("left") < plan.index("top")


def test_validate_surfaces_errors():
    registry = Registry()
    _register(registry, "broken", deps=["missing"])
    with pytest.raises(UnresolvedContractError):
        GraphResolver(registry).validate()
