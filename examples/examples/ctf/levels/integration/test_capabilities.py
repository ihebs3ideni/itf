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
"""Target-agnostic capability tests.

Nothing here mentions docker, mock or subprocess. Each test depends on a
capability *contract*; the active ``--ctf-target`` decides what backs it.
"""

from __future__ import annotations


def test_exec_echo(shell):
    code, out = shell.execute("echo -n hello, world")
    assert code == 0
    assert out == b"hello, world"


def test_exec_nonzero_exit(shell):
    code, _ = shell.execute("cat /no/such/file/at/all")
    assert code != 0


def test_file_round_trip(files, shell, tmp_path):
    local_src = tmp_path / "src.txt"
    local_dst = tmp_path / "dst.txt"
    # A target-neutral remote location: every target has /tmp.
    remote_path = "/tmp/ctf_roundtrip.txt"
    content = "hello from host\n"
    local_src.write_text(content, encoding="utf-8")

    files.upload(str(local_src), remote_path)
    code, out = shell.execute(f"cat {remote_path}")
    assert code == 0
    assert out.decode() == content

    files.download(remote_path, str(local_dst))
    assert local_dst.read_text(encoding="utf-8") == content


def test_restart_then_usable(power, shell):
    power.restart()
    code, out = shell.execute("echo -n restarted")
    assert code == 0
    assert out == b"restarted"


def test_network_capability(network):
    # mock/subprocess do not publish ctf/cap/network, so this skips there and
    # runs only against a target that does (e.g. docker).
    ip = network.ip()
    assert ip and ip.count(".") == 3


def test_ping_derived_capability(ping):
    # ctf/cap/ping is DERIVED: host-process runner + the target's network. No
    # target implements ping. It composes on a networked target (docker) and is
    # absent on network-less targets (mock/subprocess), where this test skips.
    assert ping.ping() is True
