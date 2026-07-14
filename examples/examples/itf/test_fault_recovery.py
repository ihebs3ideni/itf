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
"""Fault injection and recovery examples.

Demonstrates the DUT's runtime control API:
  - disable/enable: block individual capabilities for negative testing
  - invalidate: tear down a subtree and lazily recover
  - rebuild: full target reset (re-realize everything from scratch)
  - reprovision: tear down capabilities, keep the target alive

These patterns are essential for:
  - Testing graceful degradation (what happens when SSH drops?)
  - Service recovery verification (can the system recover after a fault?)
  - Credential rotation testing (expire creds, reprovision, verify access)
  - Chaos/fault injection without restarting the entire test session

Aliases (shell, files, restart, etc.) are registered in conftest.py.
"""

import pytest
from score.itf.core.capability_gating import requires_capabilities


# ---------------------------------------------------------------------------
# disable() / enable() — Block and restore individual capabilities
# ---------------------------------------------------------------------------


@requires_capabilities("exec")
def test_disable_blocks_require(dut):
    """After disable(), require raises — the capability is gone."""
    shell = dut["shell"]
    exit_code, _ = shell.execute("echo ok")
    assert exit_code == 0

    dut.disable("shell")

    with pytest.raises(Exception, match="disabled"):
        dut["shell"]

    assert not dut.available("shell")

    dut.enable("shell")


@requires_capabilities("exec")
def test_enable_restores_capability(dut):
    """After enable(), the capability lazily re-resolves on next require()."""
    dut.disable("shell")
    assert not dut.available("shell")

    dut.enable("shell")
    assert dut.available("shell")

    shell = dut["shell"]
    exit_code, output = shell.execute("echo -n recovered")
    assert exit_code == 0
    assert output == b"recovered"


@requires_capabilities("exec")
def test_disabled_property_tracks_state(dut):
    """The disabled property reflects what's currently blocked."""
    assert "itf/cap/exec" not in dut.disabled

    dut.disable("shell")
    assert "itf/cap/exec" in dut.disabled

    dut.enable("shell")
    assert "itf/cap/exec" not in dut.disabled


@requires_capabilities("exec", "file_transfer")
def test_disable_is_surgical(dut):
    """Disabling one capability does not affect unrelated ones."""
    dut.disable("file_transfer")

    shell = dut["shell"]
    exit_code, _ = shell.execute("echo still alive")
    assert exit_code == 0

    assert not dut.available("file_transfer")
    assert dut.available("shell")

    dut.enable("file_transfer")


@requires_capabilities("exec")
def test_disable_enable_cycle_is_idempotent(dut):
    """Multiple disable/enable cycles don't corrupt state."""
    for _ in range(5):
        dut.disable("shell")
        assert not dut.available("shell")
        dut.enable("shell")
        assert dut.available("shell")

    shell = dut["shell"]
    exit_code, output = shell.execute("echo -n stable")
    assert exit_code == 0
    assert output == b"stable"


# ---------------------------------------------------------------------------
# invalidate() — Tear down a subtree and lazily recover
# ---------------------------------------------------------------------------


@requires_capabilities("exec")
def test_invalidate_tears_down_subtree(dut):
    """invalidate() removes the resource from the cache; next require re-builds it."""
    dut["shell"]
    assert "itf/cap/exec" in dut.materialized()

    torn = dut.invalidate("shell")
    assert "itf/cap/exec" in torn

    # Still available (can be rebuilt) — unlike disable()
    assert dut.available("shell")

    shell = dut["shell"]
    exit_code, output = shell.execute("echo -n rebuilt")
    assert exit_code == 0
    assert output == b"rebuilt"


@requires_capabilities("exec")
def test_invalidate_vs_disable_semantics(dut):
    """invalidate = tear down + rebuild on demand. disable = block entirely."""
    dut["shell"]
    dut.invalidate("shell")
    assert dut.available("shell")  # can be re-resolved

    dut.disable("shell")
    assert not dut.available("shell")  # blocked
    dut.enable("shell")


# ---------------------------------------------------------------------------
# rebuild() — Full target reset
# ---------------------------------------------------------------------------


@requires_capabilities("exec")
def test_rebuild_resets_entire_target(dut):
    """rebuild() tears down everything and re-realizes from the anchor up."""
    shell = dut["shell"]
    exit_code, _ = shell.execute("echo -n before")
    assert exit_code == 0

    torn = dut.rebuild()
    assert "ctf/target" in torn

    shell = dut["shell"]
    exit_code, output = shell.execute("echo -n after_rebuild")
    assert exit_code == 0
    assert output == b"after_rebuild"


# ---------------------------------------------------------------------------
# reprovision() — Keep target alive, reset capabilities
# ---------------------------------------------------------------------------


@requires_capabilities("exec")
def test_reprovision_keeps_target_alive(dut):
    """reprovision() tears down capabilities but not the target anchor."""
    dut["shell"]
    dut["target"]

    dut.reprovision()

    assert "ctf/target" in dut.materialized()

    shell = dut["shell"]
    exit_code, output = shell.execute("echo -n reprovisioned")
    assert exit_code == 0
    assert output == b"reprovisioned"


# ---------------------------------------------------------------------------
# Recovery patterns — real-world fault scenarios
# ---------------------------------------------------------------------------


@requires_capabilities("exec")
def test_recovery_after_service_failure(dut):
    """Simulate a service going down: invalidate, then re-require to recover.

    Pattern: a test detects a failure → invalidates the broken capability →
    the next require() rebuilds the resource from scratch.
    """
    shell = dut["shell"]
    exit_code, _ = shell.execute("echo before_failure")
    assert exit_code == 0

    # Simulate: the exec channel is broken
    dut.invalidate("shell")

    # Re-require: the engine builds a fresh exec resource
    shell = dut["shell"]
    exit_code, output = shell.execute("echo -n recovered")
    assert exit_code == 0
    assert output == b"recovered"


@requires_capabilities("exec", "file_transfer")
def test_graceful_degradation_pattern(dut):
    """Pattern: disable a capability, verify the system degrades gracefully.

    Use case: test that your application handles missing file transfer
    (e.g., falls back to inline config) while exec still works.
    """
    assert dut.available("shell")
    assert dut.available("file_transfer")

    dut.disable("file_transfer")

    shell = dut["shell"]
    exit_code, _ = shell.execute("echo degraded_but_alive")
    assert exit_code == 0

    assert not dut.available("file_transfer")

    dut.enable("file_transfer")
    assert dut.available("file_transfer")


@requires_capabilities("exec", "restart")
def test_full_recovery_cycle(dut):
    """Pattern: restart target → rebuild composition → verify recovery.

    Use case: the target crashed, you restart it, then rebuild the
    composition so all handles are fresh.
    """
    shell = dut["shell"]
    exit_code, _ = shell.execute("echo -n alive")
    assert exit_code == 0

    restart = dut["restart"]
    restart.restart()

    dut.rebuild()

    shell = dut["shell"]
    exit_code, output = shell.execute("echo -n fresh_start")
    assert exit_code == 0
    assert output == b"fresh_start"
