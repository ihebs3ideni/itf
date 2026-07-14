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
"""Tests for the DUT alias mechanism."""

import pytest

from score.itf.core.ctf.dut import DUT, build_manager
from score.itf.core.ctf.registry import Registry
from score.itf.core.ctf.target import TARGET_ANCHOR
from score.itf.plugins.targets.mock import plugin as mock_plugin


@pytest.fixture
def dut():
    """Build a DUT from the mock target for alias testing."""
    registry = Registry()
    mock_plugin.pytest_itf_declare(registry, config=None)
    assembly = build_manager(registry)
    assembly.enter()
    yield DUT(assembly)
    assembly.exit()


class TestAliasRegistration:
    """dut.alias() maps short names to contract strings."""

    def test_alias_creates_mapping(self, dut):
        dut.alias("shell", "itf/cap/exec")
        assert dut.aliases() == {"shell": "itf/cap/exec"}

    def test_alias_same_contract_is_idempotent(self, dut):
        dut.alias("shell", "itf/cap/exec")
        dut.alias("shell", "itf/cap/exec")  # no error
        assert dut.aliases()["shell"] == "itf/cap/exec"

    def test_alias_rebind_raises(self, dut):
        dut.alias("shell", "itf/cap/exec")
        with pytest.raises(ValueError, match="already maps"):
            dut.alias("shell", "itf/cap/file_transfer")

    def test_multiple_aliases(self, dut):
        dut.alias("shell", "itf/cap/exec")
        dut.alias("files", "itf/cap/file_transfer")
        assert len(dut.aliases()) == 2


class TestAliasResolution:
    """require/available/disable/enable all resolve aliases transparently."""

    def test_require_by_alias(self, dut):
        dut.alias("shell", "itf/cap/exec")
        result = dut.require("shell")
        assert result is not None

    def test_require_raw_contract_still_works(self, dut):
        dut.alias("shell", "itf/cap/exec")
        result = dut.require("itf/cap/exec")
        assert result is not None

    def test_subscript_access(self, dut):
        dut.alias("shell", "itf/cap/exec")
        result = dut["shell"]
        assert result is not None

    def test_available_by_alias(self, dut):
        dut.alias("shell", "itf/cap/exec")
        assert dut.available("shell")

    def test_available_missing_alias(self, dut):
        dut.alias("nonexist", "itf/cap/non-existing")
        assert not dut.available("nonexist")

    def test_disable_by_alias(self, dut):
        dut.alias("shell", "itf/cap/exec")
        dut.disable("shell")
        assert not dut.available("shell")
        assert not dut.available("itf/cap/exec")  # same thing

    def test_enable_by_alias(self, dut):
        dut.alias("shell", "itf/cap/exec")
        dut.disable("shell")
        dut.enable("shell")
        assert dut.available("shell")

    def test_invalidate_by_alias(self, dut):
        dut.alias("shell", "itf/cap/exec")
        dut.require("shell")
        torn = dut.invalidate("shell")
        assert "itf/cap/exec" in torn

    def test_can_provide_by_alias(self, dut):
        dut.alias("shell", "itf/cap/exec")
        assert dut.can_provide("shell")


class TestAliasWithoutRegistration:
    """Unregistered names pass through as raw contracts."""

    def test_unknown_name_treated_as_contract(self, dut):
        # "itf/cap/exec" is not an alias — it's a raw contract, and it resolves
        result = dut.require("itf/cap/exec")
        assert result is not None

    def test_unknown_name_not_in_registry(self, dut):
        assert not dut.available("totally_unknown")


class TestAliasLocking:
    """After lock_aliases(), no new aliases can be registered."""

    def test_lock_prevents_new_alias(self, dut):
        dut.alias("shell", "itf/cap/exec")
        dut.lock_aliases()
        with pytest.raises(RuntimeError, match="locked"):
            dut.alias("files", "itf/cap/file_transfer")

    def test_lock_does_not_affect_existing_aliases(self, dut):
        dut.alias("shell", "itf/cap/exec")
        dut.lock_aliases()
        # Existing aliases still work
        assert dut.available("shell")
        result = dut["shell"]
        assert result is not None

    def test_lock_does_not_affect_raw_contracts(self, dut):
        dut.lock_aliases()
        # Raw contract access still works
        result = dut.require("itf/cap/exec")
        assert result is not None

    def test_disable_enable_still_work_after_lock(self, dut):
        dut.alias("shell", "itf/cap/exec")
        dut.lock_aliases()
        dut.disable("shell")
        assert not dut.available("shell")
        dut.enable("shell")
        assert dut.available("shell")


class TestFaultInjection:
    """dut.fault() context manager for scoped capability disabling."""

    def test_fault_disables_during_block(self, dut):
        assert dut.available("itf/cap/exec")
        with dut.fault("itf/cap/exec"):
            assert not dut.available("itf/cap/exec")

    def test_fault_re_enables_after_block(self, dut):
        with dut.fault("itf/cap/exec"):
            pass
        assert dut.available("itf/cap/exec")

    def test_fault_re_enables_on_exception(self, dut):
        with pytest.raises(RuntimeError):
            with dut.fault("itf/cap/exec"):
                raise RuntimeError("simulated failure")
        # Capability is back
        assert dut.available("itf/cap/exec")

    def test_fault_with_alias(self, dut):
        dut.alias("shell", "itf/cap/exec")
        with dut.fault("shell"):
            assert not dut.available("shell")
            assert not dut.available("itf/cap/exec")
        assert dut.available("shell")

    def test_fault_require_raises_inside_block(self, dut):
        from score.itf.core.ctf.errors import CapabilityDisabledError

        with dut.fault("itf/cap/exec"):
            with pytest.raises(CapabilityDisabledError):
                dut.require("itf/cap/exec")

    def test_fault_resource_re_resolves_after_block(self, dut):
        # Get the resource once before
        before = dut.require("itf/cap/exec")
        with dut.fault("itf/cap/exec"):
            pass
        # After fault, re-require lazily re-instantiates
        after = dut.require("itf/cap/exec")
        assert after is not None
