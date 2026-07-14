# *******************************************************************************
# Copyright (c) 2025 Contributors to the Eclipse Foundation
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
"""QEMU target integration examples.

Demonstrates the same aliases as test_docker.py — running on a VM target.
Tests are portable because they request capabilities by alias, not backend.
"""

from score.itf.core.capability_gating import requires_capabilities


# ---------------------------------------------------------------------------
# Basic exec — same alias, different backend (SSH under the hood)
# ---------------------------------------------------------------------------


@requires_capabilities("exec")
def test_exec_on_target(dut):
    """Run a command on the VM — same alias as Docker, different transport."""
    shell = dut["shell"]
    exit_code, _ = shell.execute("echo 'Username:' $USER && uname -a")
    assert exit_code == 0


# ---------------------------------------------------------------------------
# SSH-specific (requires the ssh capability plugin to be loaded)
# ---------------------------------------------------------------------------


@requires_capabilities("ssh")
def test_ssh_with_alternate_user(dut):
    """SSH capability exposes raw SSH sessions with custom credentials."""
    ssh = dut["ssh"]
    with ssh.ssh(username="qnxuser") as conn:
        exit_code = conn.execute_command("echo 'Username:' $USER && uname -a")
        assert exit_code == 0


# ---------------------------------------------------------------------------
# File transfer — upload/download through the alias
# ---------------------------------------------------------------------------


@requires_capabilities("exec", "file_transfer")
def test_upload_download(dut, tmp_path):
    """Upload a file, verify via exec, then download and compare."""
    shell = dut["shell"]
    ft = dut["file_transfer"]

    local_src = tmp_path / "src.txt"
    local_dst = tmp_path / "dst.txt"
    remote_path = "/tmp/itf_upload_test.txt"

    content = "hello from host\n"
    local_src.write_text(content, encoding="utf-8")

    ft.upload(str(local_src), remote_path)
    exit_code, output = shell.execute(f"cat {remote_path}")
    assert exit_code == 0
    assert output.decode("utf-8") == content

    ft.download(remote_path, str(local_dst))
    assert local_dst.read_text(encoding="utf-8") == content

    shell.execute(f"rm -f {remote_path}")


# ---------------------------------------------------------------------------
# Restart — with health-check recovery via ping + SSH
# ---------------------------------------------------------------------------


def _wait_for_target_up(dut, *, timeout_s: int = 120) -> None:
    """Wait for the target to become reachable after restart."""
    ping = dut["ping"]
    assert ping.ping(timeout=timeout_s), "Target did not become pingable in time"

    ssh = dut["ssh"]
    with ssh.ssh(timeout=10, n_retries=max(1, int(timeout_s / 2)), retry_interval=2) as conn:
        exit_code = conn.execute_command("echo -n up")
        assert exit_code == 0


@requires_capabilities("exec", "restart", "ping", "ssh")
def test_restart_and_recover(dut):
    """Restart the VM and verify it comes back healthy."""
    shell = dut["shell"]
    restart = dut["restart"]

    exit_code, output = shell.execute("echo -n before restart")
    assert exit_code == 0
    assert output == b"before restart"

    restart.restart()
    _wait_for_target_up(dut)

    exit_code, output = shell.execute("echo -n restarted")
    assert exit_code == 0
    assert output == b"restarted"


# ---------------------------------------------------------------------------
# Network introspection — verify IP address is resolvable
# ---------------------------------------------------------------------------


@requires_capabilities("network")
def test_ip_address_resolvable(dut):
    """The target provides a routable IP address."""
    ip = dut["ip"]
    assert ip, "IP address must not be empty"
    parts = ip.split(".")
    assert len(parts) == 4


# ---------------------------------------------------------------------------
# Ping capability
# ---------------------------------------------------------------------------


@requires_capabilities("ping")
def test_target_is_pingable(dut):
    """Verify ICMP reachability through the ping alias."""
    ping = dut["ping"]
    assert ping.ping(timeout=10), "Target should be pingable"
