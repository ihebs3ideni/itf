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
"""Tests validating the new plugin composition structure.

These tests use the mock target + ping capability to prove
that the CTF composition engine correctly wires plugins together.
"""

import pytest

from score.itf.core.ctf.registry import Registry
from score.itf.core.ctf.target import TARGET_ANCHOR
from score.itf.plugins.targets.mock import plugin as mock_plugin
from score.itf.plugins.capabilities.ping import plugin as ping_plugin
from score.itf.plugins.capabilities.ssh import plugin as ssh_plugin
from score.itf.plugins.targets.docker import plugin as docker_plugin
from score.itf.plugins.targets.qemu import plugin as qemu_plugin
from score.itf.core import itf_plugin


class TestMockTargetComposition:
    """Mock target registers all expected contracts."""

    def test_mock_registers_target_anchor(self):
        registry = Registry()
        mock_plugin.pytest_itf_declare(registry, config=None)
        assert registry.has(TARGET_ANCHOR)

    def test_mock_registers_exec(self):
        registry = Registry()
        mock_plugin.pytest_itf_declare(registry, config=None)
        assert registry.has("itf/cap/exec")

    def test_mock_registers_file_transfer(self):
        registry = Registry()
        mock_plugin.pytest_itf_declare(registry, config=None)
        assert registry.has("itf/cap/file_transfer")

    def test_mock_registers_ip_address(self):
        registry = Registry()
        mock_plugin.pytest_itf_declare(registry, config=None)
        assert registry.has("itf/net/ip_address")


class TestPingCapabilityComposition:
    """Ping capability wires into any target that provides ip_address."""

    def test_ping_registers_on_ip_address(self):
        registry = Registry()
        mock_plugin.pytest_itf_declare(registry, config=None)
        ping_plugin.pytest_itf_declare(registry, config=None)
        assert registry.has("itf/cap/ping")

    def test_ping_requires_ip_address(self):
        registry = Registry()
        # Ping alone without a target providing ip_address
        ping_plugin.pytest_itf_declare(registry, config=None)
        provider = registry.provider("itf/cap/ping")
        assert "itf/net/ip_address" in provider.requires


class TestSshCapabilityComposition:
    """SSH capability wires into any target that provides ssh_endpoint."""

    def test_ssh_registers_contracts(self):
        registry = Registry()
        ssh_plugin.pytest_itf_declare(registry, config=None)
        assert registry.has("itf/cap/ssh")
        assert registry.has("itf/cap/sftp")

    def test_ssh_requires_endpoint(self):
        registry = Registry()
        ssh_plugin.pytest_itf_declare(registry, config=None)
        provider = registry.provider("itf/cap/ssh")
        assert "itf/net/ssh_endpoint" in provider.requires


class TestDockerTargetContracts:
    """Docker target provides self-contained exec (no SSH needed)."""

    def test_docker_provides_exec_requiring_only_anchor(self):
        """Docker exec depends only on TARGET_ANCHOR (not on itf/cap/ssh)."""
        registry = Registry()

        class FakeConfig:
            def getoption(self, name, default=None):
                return {"docker_image": "test:latest"}.get(name, default)

        docker_plugin.pytest_itf_declare(registry, FakeConfig())
        exec_provider = registry.provider("itf/cap/exec")
        assert TARGET_ANCHOR in exec_provider.requires
        assert "itf/cap/ssh" not in exec_provider.requires


class TestQemuTargetContracts:
    """QEMU target delegates exec through SSH capability."""

    def test_qemu_exec_requires_ssh(self):
        """QEMU exec depends on itf/cap/ssh (not self-contained)."""
        registry = Registry()

        class FakeConfig:
            def getoption(self, name, default=None):
                return {
                    "qemu_config": None,
                    "qemu_image": "/tmp/fake.img",
                }.get(name, default)

        # Need to mock load_configuration since it reads a file
        import score.itf.plugins.targets.qemu.plugin as qemu_plugin_mod
        from score.itf.core.utils.bunch import Bunch

        original = qemu_plugin_mod.load_configuration

        def fake_load(path):
            return Bunch(
                networks=[Bunch(name="tap0", ip_address="10.0.0.1", gateway="10.0.0.254")],
                ssh_port=22,
                qemu_num_cores=2,
                qemu_ram_size="1G",
            )

        qemu_plugin_mod.load_configuration = fake_load
        try:
            qemu_plugin.pytest_itf_declare(registry, FakeConfig())
        finally:
            qemu_plugin_mod.load_configuration = original

        exec_provider = registry.provider("itf/cap/exec")
        assert "itf/cap/ssh" in exec_provider.requires
        assert TARGET_ANCHOR not in exec_provider.requires

    def test_qemu_file_transfer_requires_sftp(self):
        """QEMU file_transfer depends on itf/cap/sftp."""
        registry = Registry()

        class FakeConfig:
            def getoption(self, name, default=None):
                return {
                    "qemu_config": None,
                    "qemu_image": "/tmp/fake.img",
                }.get(name, default)

        import score.itf.plugins.targets.qemu.plugin as qemu_plugin_mod
        from score.itf.core.utils.bunch import Bunch

        original = qemu_plugin_mod.load_configuration

        def fake_load(path):
            return Bunch(
                networks=[Bunch(name="tap0", ip_address="10.0.0.1", gateway="10.0.0.254")],
                ssh_port=22,
                qemu_num_cores=2,
                qemu_ram_size="1G",
            )

        qemu_plugin_mod.load_configuration = fake_load
        try:
            qemu_plugin.pytest_itf_declare(registry, FakeConfig())
        finally:
            qemu_plugin_mod.load_configuration = original

        ft_provider = registry.provider("itf/cap/file_transfer")
        assert "itf/cap/sftp" in ft_provider.requires


class TestItfPluginFallback:
    """ITF plugin provides fallback when no target is loaded."""

    def test_itf_fallback_does_not_override_real_target(self):
        registry = Registry()
        mock_plugin.pytest_itf_declare(registry, config=None)
        itf_plugin.pytest_itf_declare(registry, config=None)
        # Mock provider name wins
        assert registry.provider(TARGET_ANCHOR).name == "mock_anchor"
