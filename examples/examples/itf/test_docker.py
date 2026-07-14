# *******************************************************************************
# Copyright (c) 2025-2026 Contributors to the Eclipse Foundation
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
"""Docker target integration examples.

Demonstrates how tests interact with a Docker-backed DUT through aliases.
The test never knows it's Docker — it requests capabilities by short name.
Aliases are registered in conftest.py via the pytest_itf_aliases hook.
"""

import pytest
from score.itf.core.capability_gating import requires_capabilities


# ---------------------------------------------------------------------------
# Basic exec
# ---------------------------------------------------------------------------


@requires_capabilities("exec")
def test_command_execution(dut):
    """Execute a command on the target through the shell alias."""
    shell = dut["shell"]
    exit_code, output = shell.execute("echo -n hello")
    assert exit_code == 0
    assert output == b"hello"


@requires_capabilities("exec")
def test_command_exit_code_propagation(dut):
    """Non-zero exit codes propagate cleanly."""
    shell = dut["shell"]
    exit_code, _ = shell.execute("exit 42")
    assert exit_code == 42


# ---------------------------------------------------------------------------
# File transfer
# ---------------------------------------------------------------------------


@requires_capabilities("exec", "file_transfer")
def test_upload_and_verify(dut, tmp_path):
    """Upload a file and verify its contents via exec."""
    shell = dut["shell"]
    ft = dut["file_transfer"]

    local = tmp_path / "src.txt"
    content = "hello from host\n"
    local.write_text(content, encoding="utf-8")

    ft.upload(str(local), "/tmp/itf_upload_test.txt")
    exit_code, output = shell.execute("cat /tmp/itf_upload_test.txt")
    assert exit_code == 0
    assert output.decode() == content


@requires_capabilities("exec", "file_transfer")
def test_upload_download_roundtrip(dut, tmp_path):
    """Upload then download — content must survive the round trip."""
    ft = dut["file_transfer"]

    local_src = tmp_path / "src.txt"
    local_dst = tmp_path / "dst.txt"
    remote_path = "/tmp/itf_roundtrip_test.txt"

    content = "roundtrip payload\n"
    local_src.write_text(content, encoding="utf-8")

    ft.upload(str(local_src), remote_path)
    ft.download(remote_path, str(local_dst))
    assert local_dst.read_text(encoding="utf-8") == content


# ---------------------------------------------------------------------------
# Restart
# ---------------------------------------------------------------------------


@requires_capabilities("exec", "restart")
def test_restart_and_recover(dut):
    """Restart the target and verify it comes back healthy."""
    shell = dut["shell"]
    restart = dut["restart"]

    restart.restart()
    exit_code, output = shell.execute("echo -n restarted")
    assert exit_code == 0
    assert output == b"restarted"


# ---------------------------------------------------------------------------
# DUT introspection (available / missing capabilities)
# ---------------------------------------------------------------------------


def test_available_reports_registered_capability(dut):
    """available() works with aliases."""
    assert dut.available("shell")


def test_available_reports_missing_capability(dut):
    """available() returns False for unregistered contracts."""
    assert not dut.available("itf/cap/non-existing-capability")


# ---------------------------------------------------------------------------
# Disable / enable — fault testing
# ---------------------------------------------------------------------------


@requires_capabilities("exec")
def test_disable_blocks_capability(dut):
    """disable() works with aliases."""
    dut.disable("shell")
    assert not dut.available("shell")
    dut.enable("shell")
    assert dut.available("shell")


@requires_capabilities("exec")
def test_disable_require_raises(dut):
    """Requiring a disabled capability raises CapabilityDisabledError."""
    dut.disable("shell")
    with pytest.raises(Exception):
        dut["shell"]
    dut.enable("shell")


# ---------------------------------------------------------------------------
# Extra mount (docker-specific config, but still capability-gated)
# ---------------------------------------------------------------------------

CONTAINER_EXTRA_MNT_PATH = "/extra/mount/directory"


@requires_capabilities("exec")
def test_extra_mount(dut):
    """Verify that an extra bind-mount is visible inside the container."""
    shell = dut["shell"]
    exit_code, _ = shell.execute(f"ls -al {CONTAINER_EXTRA_MNT_PATH}")
    assert exit_code == 0, "Extra volume not mounted!"


# ---------------------------------------------------------------------------
# Backward-compat fixtures still work (exec_interface, file_transfer_interface)
# ---------------------------------------------------------------------------


def test_fixture_compat_exec(exec_interface):
    """Legacy fixture style — exec_interface auto-skips if unavailable."""
    exit_code, output = exec_interface.execute("echo -n compat")
    assert exit_code == 0
    assert output == b"compat"
