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
"""Tests for multi-anchor (multi-DUT) composition."""

import pytest

from score.itf.core.ctf.assembly import RunMode
from score.itf.core.ctf.contracts import provides, requires
from score.itf.core.ctf.descriptor import Descriptor
from score.itf.core.ctf.dut import DUT, build_manager
from score.itf.core.ctf.registry import Registry
from score.itf.core.ctf.target import TARGET_ANCHOR, is_anchor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_multi_target_registry():
    """Build a registry with two anchors: gateway and body controller."""
    registry = Registry()

    # Gateway ECU
    registry.add_descriptor(Descriptor("itf/target/gateway/config", {"ip": "10.0.0.1"}))

    @provides("ctf/target/gateway")
    @requires("itf/target/gateway/config")
    def gateway_target(config):
        return {"type": "gateway", "ip": config["ip"]}

    registry.register(gateway_target)

    @provides("itf/cap/gateway/diag")
    @requires("ctf/target/gateway")
    def gateway_diag(target):
        return f"diag@{target['ip']}"

    registry.register(gateway_diag)

    # Body controller ECU
    registry.add_descriptor(Descriptor("itf/target/body/config", {"ip": "10.0.0.2"}))

    @provides("ctf/target/body")
    @requires("itf/target/body/config")
    def body_target(config):
        return {"type": "body", "ip": config["ip"]}

    registry.register(body_target)

    @provides("itf/cap/body/window")
    @requires("ctf/target/body")
    def body_window(target):
        return f"window@{target['ip']}"

    registry.register(body_window)

    # Shared capability requiring both targets
    @provides("itf/cap/can_bridge")
    @requires("ctf/target/gateway")
    @requires("ctf/target/body")
    def can_bridge(gateway, body):
        return f"bridge:{gateway['ip']}<->{body['ip']}"

    registry.register(can_bridge)

    return registry


# ---------------------------------------------------------------------------
# Tests: is_anchor()
# ---------------------------------------------------------------------------
class TestIsAnchor:
    def test_exact_anchor(self):
        assert is_anchor("ctf/target")

    def test_sub_anchor(self):
        assert is_anchor("ctf/target/gateway")
        assert is_anchor("ctf/target/body_ctrl")
        assert is_anchor("ctf/target/ecu/deep")

    def test_not_anchor(self):
        assert not is_anchor("ctf/targets")
        assert not is_anchor("itf/cap/exec")
        assert not is_anchor("ctf/targetx")
        assert not is_anchor("ctf/targe")


# ---------------------------------------------------------------------------
# Tests: Multi-anchor composition
# ---------------------------------------------------------------------------
class TestMultiAnchorComposition:
    @pytest.fixture
    def multi_dut(self):
        registry = make_multi_target_registry()
        assembly = build_manager(registry)
        assembly.enter()
        dut = DUT(assembly)
        yield dut
        assembly.exit()

    def test_both_anchors_detected(self, multi_dut):
        anchors = multi_dut.anchors()
        assert "ctf/target/gateway" in anchors
        assert "ctf/target/body" in anchors

    def test_require_gateway(self, multi_dut):
        gw = multi_dut.require("ctf/target/gateway")
        assert gw["type"] == "gateway"
        assert gw["ip"] == "10.0.0.1"

    def test_require_body(self, multi_dut):
        body = multi_dut.require("ctf/target/body")
        assert body["type"] == "body"
        assert body["ip"] == "10.0.0.2"

    def test_capability_on_gateway(self, multi_dut):
        diag = multi_dut.require("itf/cap/gateway/diag")
        assert "10.0.0.1" in diag

    def test_capability_on_body(self, multi_dut):
        window = multi_dut.require("itf/cap/body/window")
        assert "10.0.0.2" in window

    def test_cross_target_capability(self, multi_dut):
        bridge = multi_dut.require("itf/cap/can_bridge")
        assert "10.0.0.1" in bridge
        assert "10.0.0.2" in bridge

    def test_spine_includes_both_anchors(self, multi_dut):
        spine = multi_dut._assembly.plan.spine
        assert "ctf/target/gateway" in spine
        assert "ctf/target/body" in spine
        # Descriptors needed by anchors are also in spine
        assert "itf/target/gateway/config" in spine
        assert "itf/target/body/config" in spine


# ---------------------------------------------------------------------------
# Tests: Per-anchor rebuild
# ---------------------------------------------------------------------------
class TestMultiAnchorRebuild:
    @pytest.fixture
    def multi_dut(self):
        registry = make_multi_target_registry()
        assembly = build_manager(registry)
        assembly.enter()
        assembly.realize()
        dut = DUT(assembly)
        yield dut
        assembly.exit()

    def test_rebuild_single_anchor(self, multi_dut):
        # Get initial references
        gw_before = multi_dut.require("ctf/target/gateway")
        body_before = multi_dut.require("ctf/target/body")

        # Rebuild only gateway
        torn = multi_dut.rebuild("ctf/target/gateway")
        assert "ctf/target/gateway" in torn

        # Gateway is rebuilt (new instance)
        gw_after = multi_dut.require("ctf/target/gateway")
        assert gw_after["type"] == "gateway"

        # Body was NOT torn down
        body_after = multi_dut.require("ctf/target/body")
        assert body_after is body_before

    def test_rebuild_all_anchors(self, multi_dut):
        torn = multi_dut.rebuild()
        assert "ctf/target/gateway" in torn
        assert "ctf/target/body" in torn

    def test_reprovision_single_anchor(self, multi_dut):
        # Realize a capability on each
        multi_dut.require("itf/cap/gateway/diag")
        multi_dut.require("itf/cap/body/window")

        # Reprovision only gateway
        multi_dut.reprovision("ctf/target/gateway")

        # Gateway anchor still alive
        gw = multi_dut.require("ctf/target/gateway")
        assert gw["type"] == "gateway"

        # Body window still cached (not invalidated)
        window = multi_dut.require("itf/cap/body/window")
        assert "10.0.0.2" in window


# ---------------------------------------------------------------------------
# Tests: Backward compatibility (single anchor)
# ---------------------------------------------------------------------------
class TestSingleAnchorBackwardCompat:
    @pytest.fixture
    def single_dut(self):
        registry = Registry()
        registry.add_descriptor(Descriptor("itf/target/docker/image", "ubuntu:24.04"))

        @provides("ctf/target")
        @requires("itf/target/docker/image")
        def docker_target(image):
            return {"type": "docker", "image": image}

        registry.register(docker_target)

        @provides("itf/cap/exec")
        @requires("ctf/target")
        def docker_exec(target):
            return f"exec@{target['image']}"

        registry.register(docker_exec)

        assembly = build_manager(registry)
        assembly.enter()
        assembly.realize()
        dut = DUT(assembly)
        yield dut
        assembly.exit()

    def test_single_anchor_still_works(self, single_dut):
        target = single_dut.require("ctf/target")
        assert target["type"] == "docker"

    def test_anchors_returns_single(self, single_dut):
        assert single_dut.anchors() == frozenset({"ctf/target"})

    def test_rebuild_no_arg_works(self, single_dut):
        torn = single_dut.rebuild()
        assert "ctf/target" in torn

    def test_rebuild_with_explicit_anchor(self, single_dut):
        torn = single_dut.rebuild("ctf/target")
        assert "ctf/target" in torn
