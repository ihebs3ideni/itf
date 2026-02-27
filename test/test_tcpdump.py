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

import os

import score.itf.plugins.core
from score.itf.core.com.tcpdump import TcpDumpCapture


@score.itf.plugins.core.requires_capabilities("tcpdump")
def test_tcpdump_binary_exists(target):
    """Verify that the tcpdump binary is present in the image."""
    exit_code, output = target.exec("which tcpdump", detach=False)
    assert exit_code == 0, f"tcpdump not found in image: {output.decode()}"
    assert "/usr/sbin/tcpdump" in output.decode()


@score.itf.plugins.core.requires_capabilities("tcpdump")
def test_tcpdump_version(target):
    """Verify that tcpdump runs and reports the expected version."""
    exit_code, output = target.exec("tcpdump --version", detach=False)
    decoded = output.decode()
    assert "tcpdump version 4.99.5" in decoded, f"Unexpected output: {decoded}"
    assert "libpcap version 1.10.5" in decoded, f"Unexpected output: {decoded}"


# -- context manager tests with target -----------------------------------------
# TcpDumpCapture receives a handler from the target.


@score.itf.plugins.core.requires_capabilities("tcpdump")
def test_tcpdump_captures_loopback_traffic_target(target):
    """TcpDumpCapture works with the target fixture."""
    with TcpDumpCapture(target.tcpdump_handler(), filter_expr="icmp") as cap:
        target.exec(
            ["ping", "-c", "3", "-i", "0.2", "127.0.0.1"], detach=False
        )

    assert os.path.exists(cap.host_path), "Pcap file was not created on host"
    assert os.path.getsize(cap.host_path) > 0
    os.unlink(cap.host_path)


@score.itf.plugins.core.requires_capabilities("tcpdump")
def test_tcpdump_custom_output_path_target(target, tmp_path):
    """TcpDumpCapture writes to a caller-specified path (target fixture)."""
    pcap_path = str(tmp_path / "custom.pcap")
    with TcpDumpCapture(target.tcpdump_handler(), pcap_path, filter_expr="icmp") as cap:
        target.exec(
            ["ping", "-c", "2", "-i", "0.2", "127.0.0.1"], detach=False
        )
        assert cap.host_path == pcap_path

    assert os.path.exists(pcap_path), "Pcap not saved to custom path"
    assert os.path.getsize(pcap_path) > 0


@score.itf.plugins.core.requires_capabilities("tcpdump")
def test_tcpdump_capture_has_valid_pcap_header_target(target):
    """Captured file has a valid pcap header (target fixture)."""
    with TcpDumpCapture(target.tcpdump_handler(), filter_expr="icmp") as cap:
        target.exec(
            ["ping", "-c", "2", "-i", "0.2", "127.0.0.1"], detach=False
        )

    with open(cap.host_path, "rb") as f:
        magic = f.read(4)
    assert magic in (
        b"\xd4\xc3\xb2\xa1",  # pcap little-endian
        b"\xa1\xb2\xc3\xd4",  # pcap big-endian
        b"\x0a\x0d\x0d\x0a",  # pcapng
    ), f"Unexpected pcap magic: {magic.hex()}"
    os.unlink(cap.host_path)


# -- parameter coverage tests --------------------------------------------------
# Exercise the remaining TcpDumpCapture constructor arguments.


@score.itf.plugins.core.requires_capabilities("tcpdump")
def test_tcpdump_custom_interface(target):
    """Capture on a named interface instead of the default 'any'."""
    with TcpDumpCapture(
        target.tcpdump_handler(),
        interface="lo",
        filter_expr="icmp",
    ) as cap:
        target.exec(
            ["ping", "-c", "2", "-i", "0.2", "127.0.0.1"], detach=False
        )

    assert os.path.exists(cap.host_path)
    assert os.path.getsize(cap.host_path) > 0
    os.unlink(cap.host_path)


@score.itf.plugins.core.requires_capabilities("tcpdump")
def test_tcpdump_custom_target_pcap_path(target, tmp_path):
    """The target_pcap_path parameter controls where tcpdump writes on the target."""
    host_out = str(tmp_path / "custom_target.pcap")
    with TcpDumpCapture(
        target.tcpdump_handler(),
        host_out,
        target_pcap_path="/tmp/itf_custom.pcap",
        filter_expr="icmp",
    ) as cap:
        assert cap.target_path == "/tmp/itf_custom.pcap"
        target.exec(
            ["ping", "-c", "2", "-i", "0.2", "127.0.0.1"], detach=False
        )

    assert os.path.exists(host_out)
    assert os.path.getsize(host_out) > 0


@score.itf.plugins.core.requires_capabilities("tcpdump")
def test_tcpdump_snapshot_length(target):
    """snapshot_length limits bytes captured per packet (-s flag)."""
    with TcpDumpCapture(
        target.tcpdump_handler(),
        filter_expr="icmp",
        snapshot_length=96,
    ) as cap:
        target.exec(
            ["ping", "-c", "2", "-i", "0.2", "127.0.0.1"], detach=False
        )

    assert os.path.exists(cap.host_path)
    assert os.path.getsize(cap.host_path) > 0
    os.unlink(cap.host_path)


@score.itf.plugins.core.requires_capabilities("tcpdump")
def test_tcpdump_max_packets(target):
    """max_packets stops capture after N packets (-c flag)."""
    with TcpDumpCapture(
        target.tcpdump_handler(),
        filter_expr="icmp",
        max_packets=2,
    ) as cap:
        target.exec(
            ["ping", "-c", "5", "-i", "0.2", "127.0.0.1"], detach=False
        )

    assert os.path.exists(cap.host_path)
    assert os.path.getsize(cap.host_path) > 0
    os.unlink(cap.host_path)


@score.itf.plugins.core.requires_capabilities("tcpdump")
def test_tcpdump_extra_args(target):
    """extra_args are passed verbatim to the tcpdump command line."""
    with TcpDumpCapture(
        target.tcpdump_handler(),
        filter_expr="icmp",
        extra_args=["--dont-verify-checksums"],
    ) as cap:
        target.exec(
            ["ping", "-c", "2", "-i", "0.2", "127.0.0.1"], detach=False
        )

    assert os.path.exists(cap.host_path)
    assert os.path.getsize(cap.host_path) > 0
    os.unlink(cap.host_path)


@score.itf.plugins.core.requires_capabilities("tcpdump")
def test_tcpdump_explicit_binary_path(target):
    """tcpdump_binary overrides the default binary path on the target."""
    with TcpDumpCapture(
        target.tcpdump_handler(),
        tcpdump_binary="/usr/sbin/tcpdump",
        filter_expr="icmp",
    ) as cap:
        target.exec(
            ["ping", "-c", "2", "-i", "0.2", "127.0.0.1"], detach=False
        )

    assert os.path.exists(cap.host_path)
    assert os.path.getsize(cap.host_path) > 0
    os.unlink(cap.host_path)
