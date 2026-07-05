from __future__ import annotations

from ctf.contracts import provides, requires
from ctf.descriptor import Descriptor
from ctf.dut import compose
from ctf.registry import Registry


def _build_registry():
    registry = Registry()
    registry.add_descriptor(Descriptor("transport/doip", value="endpoint"))
    registry.add_descriptor(Descriptor("endpoint/ssh", value="host"))

    @registry.register
    @provides("doip/client")
    @requires("transport/doip")
    def doip(endpoint):
        return {"kind": "doip", "endpoint": endpoint}

    @registry.register
    @provides("uds/client")
    @requires("doip/client")
    def uds(doip):
        return {"kind": "uds", "doip": doip}

    return registry


def test_require_resolves_full_chain():
    with compose(_build_registry()) as dut:
        uds = dut.require("uds/client")
        assert uds["doip"]["endpoint"] == "endpoint"


def test_require_caches_instances():
    registry = Registry()
    registry.add_descriptor(Descriptor("seed", value=0))
    counter = {"n": 0}

    @registry.register
    @provides("thing")
    @requires("seed")
    def thing(seed):
        counter["n"] += 1
        return counter["n"]

    with compose(registry) as dut:
        first = dut.require("thing")
        second = dut.require("thing")
    assert first == second == 1
    assert counter["n"] == 1


def test_lazy_only_builds_required_subgraph():
    registry = _build_registry()
    built: list[str] = []

    @registry.register
    @provides("ssh/client")
    @requires("endpoint/ssh")
    def ssh(host):
        built.append("ssh")
        return host

    with compose(registry) as dut:
        dut.require("ssh/client")
        assert built == ["ssh"]
        # doip/uds were never requested, hence never built.
        assert "doip/client" not in dut.materialized()


def test_teardown_on_close():
    registry = Registry()
    registry.add_descriptor(Descriptor("seed", value=1))
    events: list[str] = []

    @registry.register
    @provides("res")
    @requires("seed")
    def res(seed):
        events.append("up")
        yield seed
        events.append("down")

    with compose(registry) as dut:
        dut.require("res")
        assert events == ["up"]
    assert events == ["up", "down"]


def test_provides_lists_all_contracts():
    with compose(_build_registry()) as dut:
        assert {"transport/doip", "doip/client", "uds/client"} <= dut.provides()
        assert dut.can_provide("uds/client")
        assert not dut.can_provide("nope")
