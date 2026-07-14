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
"""Tests for the Registry contract binding mechanism."""

import pytest

from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.core.ctf.dut import DUT, build_manager
from score.itf.core.ctf.registry import Registry
from score.itf.core.ctf.target import TARGET_ANCHOR


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def registry():
    """A registry with a target and two IP descriptors."""
    reg = Registry()

    # Target anchor
    @provides(TARGET_ANCHOR)
    def target():
        return "mock-target"

    reg.register(target)

    # Two IP addresses as descriptors
    reg.add_descriptor(Descriptor(key="itf/net/ip_address", value="192.168.1.1"))
    reg.add_descriptor(Descriptor(key="itf/net/heartbeat_ip", value="10.0.0.99"))

    # A generic capability that requires an IP
    @provides("itf/cap/udp_heartbeat")
    @requires("itf/net/ip_address")
    def udp_heartbeat(ip):
        return f"heartbeat@{ip}"

    reg.register(udp_heartbeat)
    return reg


# ---------------------------------------------------------------------------
# Tests: binding registration
# ---------------------------------------------------------------------------
class TestBindRegistration:
    """registry.bind() records requirement redirects."""

    def test_bind_records_redirect(self, registry):
        registry.bind("itf/cap/udp_heartbeat", "itf/net/ip_address", "itf/net/heartbeat_ip")
        assert registry.bindings() == {"itf/cap/udp_heartbeat": {"itf/net/ip_address": "itf/net/heartbeat_ip"}}

    def test_bind_unknown_provider_raises(self, registry):
        with pytest.raises(ValueError, match="no provider registered"):
            registry.bind("itf/cap/nonexistent", "itf/net/ip_address", "itf/net/heartbeat_ip")

    def test_bind_wrong_requirement_raises(self, registry):
        with pytest.raises(ValueError, match="does not require"):
            registry.bind("itf/cap/udp_heartbeat", "itf/net/nonexistent", "itf/net/heartbeat_ip")

    def test_bind_after_lock_raises(self, registry):
        registry.lock_bindings()
        with pytest.raises(RuntimeError, match="locked"):
            registry.bind("itf/cap/udp_heartbeat", "itf/net/ip_address", "itf/net/heartbeat_ip")


# ---------------------------------------------------------------------------
# Tests: applying bindings (rewrites provider.requires)
# ---------------------------------------------------------------------------
class TestApplyBindings:
    """apply_bindings() rewrites the provider's requires tuple."""

    def test_apply_rewrites_requires(self, registry):
        registry.bind("itf/cap/udp_heartbeat", "itf/net/ip_address", "itf/net/heartbeat_ip")
        registry.apply_bindings()

        provider = registry.provider("itf/cap/udp_heartbeat")
        assert provider.requires == ("itf/net/heartbeat_ip",)

    def test_apply_locks_bindings(self, registry):
        registry.apply_bindings()
        with pytest.raises(RuntimeError, match="locked"):
            registry.bind("itf/cap/udp_heartbeat", "itf/net/ip_address", "itf/net/heartbeat_ip")

    def test_no_bindings_is_noop(self, registry):
        original_requires = registry.provider("itf/cap/udp_heartbeat").requires
        registry.apply_bindings()
        assert registry.provider("itf/cap/udp_heartbeat").requires == original_requires


# ---------------------------------------------------------------------------
# Tests: end-to-end with DUT (binding redirects actual resolution)
# ---------------------------------------------------------------------------
class TestBindingEndToEnd:
    """Bindings redirect actual resource resolution through the DUT."""

    def test_without_binding_uses_main_ip(self, registry):
        registry.apply_bindings()  # no bindings
        assembly = build_manager(registry)
        assembly.enter()
        dut = DUT(assembly)
        result = dut.require("itf/cap/udp_heartbeat")
        assert result == "heartbeat@192.168.1.1"
        assembly.exit()

    def test_with_binding_uses_redirected_ip(self, registry):
        registry.bind("itf/cap/udp_heartbeat", "itf/net/ip_address", "itf/net/heartbeat_ip")
        registry.apply_bindings()
        assembly = build_manager(registry)
        assembly.enter()
        dut = DUT(assembly)
        result = dut.require("itf/cap/udp_heartbeat")
        assert result == "heartbeat@10.0.0.99"
        assembly.exit()

    def test_binding_does_not_affect_other_consumers(self, registry):
        """Other providers that also require itf/net/ip_address are unaffected."""

        @provides("itf/cap/ping")
        @requires("itf/net/ip_address")
        def ping_cap(ip):
            return f"ping@{ip}"

        registry.register(ping_cap)
        registry.bind("itf/cap/udp_heartbeat", "itf/net/ip_address", "itf/net/heartbeat_ip")
        registry.apply_bindings()

        assembly = build_manager(registry)
        assembly.enter()
        dut = DUT(assembly)
        # UDP heartbeat gets the redirected IP
        assert dut.require("itf/cap/udp_heartbeat") == "heartbeat@10.0.0.99"
        # Ping still uses the original IP
        assert dut.require("itf/cap/ping") == "ping@192.168.1.1"
        assembly.exit()

    def test_multiple_bindings_on_same_provider(self):
        """A provider with multiple requirements can have each redirected."""
        reg = Registry()

        @provides(TARGET_ANCHOR)
        def target():
            return "t"

        reg.register(target)
        reg.add_descriptor(Descriptor(key="itf/net/ip_a", value="1.1.1.1"))
        reg.add_descriptor(Descriptor(key="itf/net/ip_b", value="2.2.2.2"))
        reg.add_descriptor(Descriptor(key="itf/net/port_a", value=8080))
        reg.add_descriptor(Descriptor(key="itf/net/port_b", value=9090))

        @provides("itf/cap/multi")
        @requires("itf/net/ip_a", "itf/net/port_a")
        def multi(ip, port):
            return f"{ip}:{port}"

        reg.register(multi)

        reg.bind("itf/cap/multi", "itf/net/ip_a", "itf/net/ip_b")
        reg.bind("itf/cap/multi", "itf/net/port_a", "itf/net/port_b")
        reg.apply_bindings()

        assembly = build_manager(reg)
        assembly.enter()
        dut = DUT(assembly)
        assert dut.require("itf/cap/multi") == "2.2.2.2:9090"
        assembly.exit()
