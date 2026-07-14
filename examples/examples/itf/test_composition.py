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
"""DUT composition and introspection examples.

These tests demonstrate the CTF engine's runtime API — how to inspect
the resolved graph, disable capabilities for fault testing, and verify
the composition model itself.

They run on any target that provides at least exec + file_transfer.
Aliases (shell, files, etc.) are registered in conftest.py.
"""

import pytest
from score.itf.core.capability_gating import requires_capabilities


# ---------------------------------------------------------------------------
# Graph introspection
# ---------------------------------------------------------------------------


def test_dut_provides_lists_all_contracts(dut):
    """provides() returns the full set of contracts in this composition."""
    contracts = dut.provides()
    assert "ctf/target" in contracts


def test_dut_materialized_is_initially_empty(dut):
    """materialized() only shows resources that have been require()'d."""
    materialized = dut.materialized()
    assert isinstance(materialized, dict)


@requires_capabilities("exec")
def test_require_materializes_capability(dut):
    """After require(), the contract appears in materialized()."""
    dut["shell"]
    assert "itf/cap/exec" in dut.materialized()


# ---------------------------------------------------------------------------
# Fault injection: disable / enable (via aliases)
# ---------------------------------------------------------------------------


@requires_capabilities("exec")
def test_disable_makes_unavailable(dut):
    """disable() removes the capability from the live DUT."""
    assert dut.available("shell")

    dut.disable("shell")
    assert not dut.available("shell")

    dut.enable("shell")
    assert dut.available("shell")


@requires_capabilities("exec")
def test_require_disabled_raises(dut):
    """Requiring a disabled capability raises — fail-fast, not silent None."""
    dut.disable("shell")
    try:
        with pytest.raises(Exception):
            dut["shell"]
    finally:
        dut.enable("shell")


@requires_capabilities("exec", "file_transfer")
def test_disable_one_capability_leaves_others(dut):
    """Disabling one capability does not affect unrelated ones."""
    dut.disable("file_transfer")
    shell = dut["shell"]
    exit_code, _ = shell.execute("echo ok")
    assert exit_code == 0
    dut.enable("file_transfer")


# ---------------------------------------------------------------------------
# Capability gating with requires_capabilities
# ---------------------------------------------------------------------------


@requires_capabilities("itf/cap/non-existing")
def test_skipped_when_capability_missing(dut):
    """This test is auto-skipped — the capability doesn't exist."""
    pytest.fail("Should never reach here")


@requires_capabilities("exec", "file_transfer", "restart")
def test_multiple_capabilities_required(dut):
    """All three must be present or the test skips."""
    shell = dut["shell"]
    exit_code, _ = shell.execute("echo multi-cap")
    assert exit_code == 0


# ---------------------------------------------------------------------------
# Contract portability — the test doesn't know its backend
# ---------------------------------------------------------------------------


@requires_capabilities("exec")
def test_os_identity(dut):
    """Works on Docker, QEMU, or real HW — any target with exec."""
    shell = dut["shell"]
    exit_code, output = shell.execute("uname -s")
    assert exit_code == 0
    assert output.decode().strip() in ("Linux", "QNX", "Darwin")


@requires_capabilities("exec")
def test_environment_variables(dut):
    """Verify environment is sane on any target backend."""
    shell = dut["shell"]
    exit_code, output = shell.execute("echo $HOME")
    assert exit_code == 0
    assert output.decode().strip().startswith("/")


@requires_capabilities("exec", "file_transfer")
def test_deploy_and_execute_script(dut, tmp_path):
    """Deploy a script, execute it, verify output — full workflow."""
    shell = dut["shell"]
    ft = dut["file_transfer"]

    script = tmp_path / "check.sh"
    script.write_text("#!/bin/sh\necho -n DEPLOYED\n", encoding="utf-8")

    ft.upload(str(script), "/tmp/itf_check.sh")
    shell.execute("chmod +x /tmp/itf_check.sh")

    exit_code, output = shell.execute("/tmp/itf_check.sh")
    assert exit_code == 0
    assert output == b"DEPLOYED"

    shell.execute("rm -f /tmp/itf_check.sh")
