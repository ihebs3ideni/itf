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

from score.itf.core.com.tcpdump import TcpDumpCapture


def test_tcpdump_binary_exists(target):
    """Verify that the tcpdump binary is present in the image."""
    exit_code, output = target.exec("which tcpdump", detach=False)
    assert exit_code == 0, f"tcpdump not found in image: {output.decode()}"
    assert "/usr/sbin/tcpdump" in output.decode()


def test_tcpdump_version(target):
    """Verify that tcpdump runs and reports the expected version."""
    exit_code, output = target.exec("tcpdump --version", detach=False)
    decoded = output.decode()
    assert "tcpdump version 4.99.5" in decoded, f"Unexpected output: {decoded}"
    assert "libpcap version 1.10.5" in decoded, f"Unexpected output: {decoded}"


# -- context manager tests with target -----------------------------------------
# TcpDumpCapture receives a handler from the target.


def test_tcpdump_captures_loopback_traffic_target(target):
    """TcpDumpCapture works with the target fixture."""
    with TcpDumpCapture(target.tcpdump_handler(), filter_expr="icmp") as cap:
        target.exec(
            ["ping", "-c", "3", "-i", "0.2", "127.0.0.1"], detach=False
        )

    assert os.path.exists(cap.host_path), "Pcap file was not created on host"
    assert os.path.getsize(cap.host_path) > 0
    os.unlink(cap.host_path)


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
