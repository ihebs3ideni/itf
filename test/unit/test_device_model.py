"""Tests for the multi-device model (per-device assemblies)."""

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.core.ctf.dut import DUT, build_device_assemblies, build_manager, compose
from score.itf.core.ctf.registry import Registry
from score.itf.core.ctf.target import TARGET_ANCHOR


# -- Helpers --


@provides(TARGET_ANCHOR)
def mock_anchor():
    return {"type": "mock"}


@provides("itf/cap/ssh")
@requires("itf/net/ssh_endpoint")
def ssh_provider(endpoint):
    return {"ssh": True, "endpoint": endpoint}


@provides("itf/cap/ping")
@requires("itf/net/ip_address")
def ping_provider(ip):
    return {"ping": True, "ip": ip}


# -- Tests: single device (backward compat) --


class TestSingleDevice:
    """No devices declared -- everything in root assembly."""

    def test_untagged_resolves_normally(self):
        reg = Registry()
        reg.add_descriptor(Descriptor("itf/net/ip_address", "10.0.0.1"))
        reg.register(mock_anchor)
        reg.register(ping_provider)
        asm = build_manager(reg)
        asm.enter()
        dut = DUT(asm)
        result = dut.require("itf/cap/ping")
        assert result == {"ping": True, "ip": "10.0.0.1"}
        asm.exit()

    def test_no_devices_detected(self):
        reg = Registry()
        reg.register(mock_anchor)
        asm = build_manager(reg)
        asm.enter()
        dut = DUT(asm)
        assert dut.devices() == frozenset()
        asm.exit()

    def test_getitem_falls_through_to_require(self):
        reg = Registry()
        reg.add_descriptor(Descriptor("itf/net/ip_address", "1.2.3.4"))
        reg.register(mock_anchor)
        reg.register(ping_provider)
        asm = build_manager(reg)
        asm.enter()
        dut = DUT(asm)
        dut.alias("ping", "itf/cap/ping")
        result = dut["ping"]
        assert result["ip"] == "1.2.3.4"
        asm.exit()


# -- Tests: multi-device --


class TestMultiDevice:
    """Multiple devices -- each gets its own assembly."""

    @pytest.fixture
    def multi_dut(self):
        reg = Registry()
        # Root shared descriptor
        reg.add_descriptor(Descriptor("hw/psu", {"rail": "12V"}))

        # Safety device
        with reg.device("safety") as dev:
            dev.add_descriptor(Descriptor("itf/net/ip_address", "10.0.0.1"))
            dev.add_descriptor(Descriptor("itf/net/ssh_endpoint", {"host": "10.0.0.1", "port": 22}))
            dev.register(mock_anchor)
            dev.register(ssh_provider)
            dev.register(ping_provider)

        # Integ device
        with reg.device("integ") as dev:
            dev.add_descriptor(Descriptor("itf/net/ip_address", "10.0.0.2"))
            dev.add_descriptor(Descriptor("itf/net/ssh_endpoint", {"host": "10.0.0.2", "port": 22}))
            dev.register(mock_anchor)
            dev.register(ssh_provider)
            dev.register(ping_provider)

        # Root assembly (empty except shared facts)
        asm = build_manager(reg)
        dev_asms = build_device_assemblies(reg)
        asm.enter()
        for da in dev_asms.values():
            da.enter()
        dut = DUT(asm, dev_asms)
        yield dut
        for da in reversed(list(dev_asms.values())):
            da.exit()
        asm.exit()

    def test_devices_detected(self, multi_dut):
        assert multi_dut.devices() == frozenset({"safety", "integ"})

    def test_getitem_returns_device_proxy(self, multi_dut):
        proxy = multi_dut["safety"]
        assert proxy.device == "safety"

    def test_device_proxy_require(self, multi_dut):
        result = multi_dut["safety"].require("itf/cap/ssh")
        assert result["endpoint"]["host"] == "10.0.0.1"

    def test_device_proxy_available(self, multi_dut):
        assert multi_dut["integ"].available("itf/cap/ping")

    def test_same_contract_different_devices(self, multi_dut):
        safety_ping = multi_dut["safety"].require("itf/cap/ping")
        integ_ping = multi_dut["integ"].require("itf/cap/ping")
        assert safety_ping["ip"] == "10.0.0.1"
        assert integ_ping["ip"] == "10.0.0.2"

    def test_device_inherits_root_descriptors(self, multi_dut):
        """Device assemblies can resolve descriptors from the root registry."""
        # The device registries have parent=root, so hw/psu should be visible
        safety_reg = multi_dut["safety"]._assembly.registry
        desc = safety_reg.descriptor("hw/psu")
        assert desc is not None
        assert desc.value == {"rail": "12V"}

    def test_device_isolation(self, multi_dut):
        """Resolving in one device doesn't affect the other."""
        multi_dut["safety"].require("itf/cap/ping")
        # Integ hasn't resolved ping yet
        assert "itf/cap/ping" not in multi_dut["integ"].materialized()

    def test_device_disable_enable(self, multi_dut):
        multi_dut["safety"].disable("itf/cap/ping")
        assert not multi_dut["safety"].available("itf/cap/ping")
        # Integ unaffected
        assert multi_dut["integ"].available("itf/cap/ping")
        multi_dut["safety"].enable("itf/cap/ping")
        assert multi_dut["safety"].available("itf/cap/ping")


class TestDeviceWithSharedDeps:
    """Devices that require contracts from root (descriptor cascade)."""

    def test_device_provider_uses_root_descriptor(self):
        reg = Registry()
        reg.add_descriptor(Descriptor("hw/config", {"mode": "debug"}))

        @provides("cap/debugger")
        @requires("hw/config")
        def debugger(config):
            return {"debug": True, "mode": config["mode"]}

        with reg.device("safety") as dev:
            dev.register(debugger)

        dev_asms = build_device_assemblies(reg)
        dev_asms["safety"].enter()
        proxy = DUT(build_manager(reg), dev_asms)["safety"]
        result = proxy.require("cap/debugger")
        assert result == {"debug": True, "mode": "debug"}
        dev_asms["safety"].exit()


class TestComposeContextManager:
    """The compose() context manager supports devices."""

    def test_compose_with_devices(self):
        reg = Registry()
        reg.add_descriptor(Descriptor("itf/net/ip_address", "root-ip"))
        reg.register(mock_anchor)

        with reg.device("dev1") as dev:
            dev.add_descriptor(Descriptor("itf/net/ip_address", "dev1-ip"))
            dev.register(ping_provider)

        with compose(reg) as dut:
            assert "dev1" in dut.devices()
            result = dut["dev1"].require("itf/cap/ping")
            assert result["ip"] == "dev1-ip"
