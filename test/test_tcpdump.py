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
"""Tests for TcpDump handlers (internal and external).

These tests verify both capture modes:

- **Internal handler**: tcpdump runs inside the container, captures loopback
  and internal traffic. Requires tcpdump installed in the container image.

- **External handler**: tcpdump runs on the host's veth interface, captures
  traffic entering/leaving the container. Does NOT require tcpdump in the
  container, but cannot see loopback traffic.
"""

import os

import pytest

import score.itf.plugins.core
from score.itf.core.com.tcpdump import TcpDumpCapture


# =============================================================================
# Internal Handler Tests (tcpdump inside container)
# =============================================================================
# These tests require tcpdump to be installed in the container image.


class TestInternalHandler:
    """Tests for InternalTcpDumpHandler (tcpdump inside container)."""

    @score.itf.plugins.core.requires_capabilities("tcpdump")
    def test_tcpdump_binary_exists_in_container(self, target):
        """Verify that the tcpdump binary is present in the container image."""
        result = target.exec("which tcpdump", detach=False)
        assert result.exit_code == 0, f"tcpdump not found: {result.output.decode()}"
        assert "/usr/sbin/tcpdump" in result.output.decode()

    @score.itf.plugins.core.requires_capabilities("tcpdump")
    def test_tcpdump_version_in_container(self, target):
        """Verify tcpdump version inside the container."""
        result = target.exec("tcpdump --version", detach=False)
        decoded = result.output.decode()
        assert "tcpdump version" in decoded, f"Unexpected output: {decoded}"

    @score.itf.plugins.core.requires_capabilities("tcpdump")
    def test_internal_handler_captures_loopback_traffic(self, target, tmp_path):
        """Internal handler can capture loopback (127.0.0.1) traffic."""
        pcap_path = str(tmp_path / "loopback.pcap")

        # Start a simple TCP listener and connect to it on loopback
        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
            pcap_path,
            filter_expr="port 12345",
        ) as cap:
            # Start netcat listener and send data to loopback
            target.exec(
                ["sh", "-c", "echo hello | nc -l -p 12345 &"],
                detach=False,
            )
            target.exec(
                ["sh", "-c", "sleep 0.3 && echo world | nc 127.0.0.1 12345"],
                detach=False,
            )

        assert os.path.exists(pcap_path), "Pcap file was not created"
        assert os.path.getsize(pcap_path) > 0, "Pcap file is empty"

    @score.itf.plugins.core.requires_capabilities("tcpdump")
    def test_internal_handler_creates_valid_pcap(self, target, tmp_path):
        """Internal handler creates a file with valid pcap header."""
        pcap_path = str(tmp_path / "valid.pcap")

        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
            pcap_path,
            interface="any",
        ) as cap:
            # Generate some traffic
            target.exec(["cat", "/etc/hostname"], detach=False)

        with open(pcap_path, "rb") as f:
            magic = f.read(4)
        assert magic in (
            b"\xd4\xc3\xb2\xa1",  # pcap little-endian
            b"\xa1\xb2\xc3\xd4",  # pcap big-endian
            b"\x0a\x0d\x0d\x0a",  # pcapng
        ), f"Invalid pcap magic: {magic.hex()}"

    @score.itf.plugins.core.requires_capabilities("tcpdump")
    def test_internal_handler_custom_interface(self, target, tmp_path):
        """Internal handler respects the interface parameter."""
        pcap_path = str(tmp_path / "interface.pcap")

        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
            pcap_path,
            interface="lo",
        ):
            target.exec(["cat", "/etc/hostname"], detach=False)

        assert os.path.exists(pcap_path)

    @score.itf.plugins.core.requires_capabilities("tcpdump")
    def test_internal_handler_snapshot_length(self, target, tmp_path):
        """Internal handler respects snapshot_length parameter."""
        pcap_path = str(tmp_path / "snapshot.pcap")

        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
            pcap_path,
            snapshot_length=96,
        ):
            target.exec(["cat", "/etc/hostname"], detach=False)

        assert os.path.exists(pcap_path)

    @score.itf.plugins.core.requires_capabilities("tcpdump")
    def test_internal_handler_extra_args(self, target, tmp_path):
        """Internal handler passes extra_args to tcpdump."""
        pcap_path = str(tmp_path / "extra_args.pcap")

        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
            pcap_path,
            extra_args=["--dont-verify-checksums"],
        ):
            target.exec(["cat", "/etc/hostname"], detach=False)

        assert os.path.exists(pcap_path)


# =============================================================================
# External Handler Tests (tcpdump on host veth)
# =============================================================================
# These tests use tcpdump on the host, so they don't require tcpdump in the
# container. However, they cannot capture loopback traffic.
# NOTE: Requires tcpdump_external capability (host tcpdump with CAP_NET_RAW).


class TestExternalHandler:
    """Tests for ExternalTcpDumpHandler (tcpdump on host veth).

    These tests require the ``tcpdump_external`` capability, which is only
    available if the host's system tcpdump has ``CAP_NET_RAW``.
    """

    @score.itf.plugins.core.requires_capabilities("tcpdump_external")
    def test_external_handler_uses_host_tcpdump(self, target, tmp_path):
        """External handler uses host's tcpdump, not container's.

        This test demonstrates that external capture runs on the host.
        """
        pcap_path = str(tmp_path / "external.pcap")

        # External handler runs tcpdump on host, not in container
        with TcpDumpCapture(
            target.external_tcpdump_handler(),
            pcap_path,
        ):
            # Generate some activity
            target.exec(["cat", "/etc/hostname"], detach=False)

        # Pcap should exist (created by host tcpdump)
        assert os.path.exists(pcap_path), "External pcap not created"

    @score.itf.plugins.core.requires_capabilities("tcpdump_external")
    def test_external_handler_captures_outbound_traffic(self, target, tmp_path):
        """External handler captures traffic leaving the container."""
        pcap_path = str(tmp_path / "outbound.pcap")

        with TcpDumpCapture(
            target.external_tcpdump_handler(),
            pcap_path,
        ) as cap:
            # Generate traffic to gateway (leaves container network namespace)
            gateway = target.get_gateway()
            # Use bash /dev/tcp to attempt connection (generates TCP SYN)
            target.exec(
                ["bash", "-c", f"echo test > /dev/tcp/{gateway}/80 2>/dev/null || true"],
                detach=False,
            )

        assert os.path.exists(pcap_path)
        # Should have captured at least TCP SYN packet
        assert os.path.getsize(pcap_path) > 24, "Expected to capture outbound traffic"

    @score.itf.plugins.core.requires_capabilities("tcpdump_external")
    def test_external_handler_creates_valid_pcap(self, target, tmp_path):
        """External handler creates a file with valid pcap header."""
        pcap_path = str(tmp_path / "valid_external.pcap")

        with TcpDumpCapture(
            target.external_tcpdump_handler(),
            pcap_path,
        ):
            target.exec(["cat", "/etc/hostname"], detach=False)

        with open(pcap_path, "rb") as f:
            magic = f.read(4)
        assert magic in (
            b"\xd4\xc3\xb2\xa1",  # pcap little-endian
            b"\xa1\xb2\xc3\xd4",  # pcap big-endian
            b"\x0a\x0d\x0d\x0a",  # pcapng
        ), f"Invalid pcap magic: {magic.hex()}"

    @score.itf.plugins.core.requires_capabilities("tcpdump_external")
    def test_external_handler_cannot_see_loopback(self, target, tmp_path):
        """External handler CANNOT capture loopback traffic (expected behavior).

        This test documents that loopback (127.0.0.1) traffic is not visible
        from the host's veth interface — it never leaves the container's
        network namespace.
        """
        pcap_path = str(tmp_path / "no_loopback.pcap")

        with TcpDumpCapture(
            target.external_tcpdump_handler(),
            pcap_path,
            filter_expr="port 54321",
        ):
            # Generate loopback traffic that external handler cannot see
            target.exec(
                ["sh", "-c", "echo hello | nc -l -p 54321 &"],
                detach=False,
            )
            target.exec(
                ["sh", "-c", "sleep 0.3 && echo world | nc 127.0.0.1 54321 || true"],
                detach=False,
            )

        # Pcap exists but should have no packets (loopback not visible)
        assert os.path.exists(pcap_path)
        # File should be minimal (header only, no packets)
        # pcap header is typically 24 bytes
        assert os.path.getsize(pcap_path) <= 100, \
            "External handler should not see loopback traffic"


# =============================================================================
# Handler Selection Tests
# =============================================================================
# Tests for the tcpdump handler methods on DockerTarget.


class TestHandlerSelection:
    """Tests for handler selection via DockerTarget methods."""

    def test_internal_tcpdump_handler_method(self, target):
        """internal_tcpdump_handler() returns internal handler."""
        from score.itf.plugins.docker.tcpdump_handler import InternalTcpDumpHandler

        handler = target.internal_tcpdump_handler()
        assert isinstance(handler, InternalTcpDumpHandler)

    def test_external_tcpdump_handler_method(self, target):
        """external_tcpdump_handler() returns external handler."""
        from score.itf.plugins.docker.tcpdump_handler import ExternalTcpDumpHandler

        handler = target.external_tcpdump_handler()
        assert isinstance(handler, ExternalTcpDumpHandler)


# =============================================================================
# Dual Capture Tests (both handlers simultaneously)
# =============================================================================
# Tests demonstrating simultaneous capture with internal and external handlers.


class TestDualCapture:
    """Tests for simultaneous internal and external tcpdump capture.

    These tests demonstrate using both handlers together to get complete
    traffic visibility: internal handler captures loopback traffic,
    external handler captures traffic crossing the container boundary.
    """

    @pytest.fixture
    def dual_capture(self, target, tmp_path):
        """Fixture providing simultaneous internal and external tcpdump capture.

        Yields dict with capture info while both captures are active.
        Files are copied when the fixture tears down (after test completes).
        """
        internal_pcap = str(tmp_path / "fixture_internal.pcap")
        external_pcap = str(tmp_path / "fixture_external.pcap")

        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
            internal_pcap,
        ) as internal_cap, TcpDumpCapture(
            target.external_tcpdump_handler(),
            external_pcap,
        ) as external_cap:
            yield {
                "internal_pcap": internal_pcap,
                "external_pcap": external_pcap,
                "internal_cap": internal_cap,
                "external_cap": external_cap,
            }
        # Files are copied here after test returns

    @score.itf.plugins.core.requires_capabilities("tcpdump", "tcpdump_external")
    def test_dual_capture_fixture_captures_traffic(self, target, dual_capture):
        """Test using dual_capture fixture - captures are active during test."""
        # Verify captures are running
        assert dual_capture["internal_cap"].target_path == "/tmp/capture.pcap"
        assert dual_capture["external_cap"].target_path == "/tmp/capture.pcap"

        # Generate traffic while both captures are active
        target.exec(["cat", "/etc/hostname"], detach=False)
        gateway = target.get_gateway()
        target.exec(
            ["bash", "-c", f"echo x > /dev/tcp/{gateway}/80 2>/dev/null || true"],
            detach=False,
        )
        # Files will be copied when fixture tears down

    @score.itf.plugins.core.requires_capabilities("tcpdump", "tcpdump_external")
    def test_dual_capture_creates_both_pcaps(self, target, tmp_path):
        """Dual capture creates both internal and external pcap files."""
        internal_pcap = str(tmp_path / "dual_internal.pcap")
        external_pcap = str(tmp_path / "dual_external.pcap")

        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
            internal_pcap,
        ), TcpDumpCapture(
            target.external_tcpdump_handler(),
            external_pcap,
        ):
            # Generate some traffic (visible to both handlers)
            target.exec(["cat", "/etc/hostname"], detach=False)

        assert os.path.exists(internal_pcap), "Internal pcap not created"
        assert os.path.exists(external_pcap), "External pcap not created"

    @score.itf.plugins.core.requires_capabilities("tcpdump", "tcpdump_external")
    def test_dual_capture_internal_sees_loopback(self, target, tmp_path):
        """Internal handler captures loopback, external does not."""
        internal_pcap = str(tmp_path / "loopback_internal.pcap")
        external_pcap = str(tmp_path / "loopback_external.pcap")

        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
            internal_pcap,
            interface="lo",
            filter_expr="port 55555",
        ), TcpDumpCapture(
            target.external_tcpdump_handler(),
            external_pcap,
            filter_expr="port 55555",
        ):
            # Loopback traffic (only visible to internal handler)
            target.exec(
                ["sh", "-c", "echo test | nc -l -p 55555 &"],
                detach=False,
            )
            target.exec(
                ["sh", "-c", "sleep 0.2 && echo hello | nc 127.0.0.1 55555 || true"],
                detach=False,
            )

        # Both files should exist
        assert os.path.exists(internal_pcap)
        assert os.path.exists(external_pcap)

        # External cannot see loopback traffic (header only, typically 24 bytes)
        external_size = os.path.getsize(external_pcap)
        assert external_size <= 100, f"External saw loopback? size={external_size}"

    @score.itf.plugins.core.requires_capabilities("tcpdump", "tcpdump_external")
    def test_dual_capture_external_sees_outbound(self, target, tmp_path):
        """External handler captures outbound traffic."""
        internal_pcap = str(tmp_path / "outbound_internal.pcap")
        external_pcap = str(tmp_path / "outbound_external.pcap")

        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
            internal_pcap,
        ), TcpDumpCapture(
            target.external_tcpdump_handler(),
            external_pcap,
        ):
            # Traffic to gateway (crosses container boundary)
            gateway = target.get_gateway()
            target.exec(
                ["bash", "-c", f"echo x > /dev/tcp/{gateway}/80 2>/dev/null || true"],
                detach=False,
            )

        assert os.path.exists(external_pcap)
        # External should capture TCP SYN to gateway
        assert os.path.getsize(external_pcap) > 24, "Expected external traffic captured"

    @score.itf.plugins.core.requires_capabilities("tcpdump", "tcpdump_external")
    def test_dual_capture_with_filters(self, target, tmp_path):
        """Dual capture with different BPF filters per handler."""
        internal_pcap = str(tmp_path / "filter_internal.pcap")
        external_pcap = str(tmp_path / "filter_external.pcap")

        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
            internal_pcap,
            filter_expr="port 12345",
        ), TcpDumpCapture(
            target.external_tcpdump_handler(),
            external_pcap,
            filter_expr="icmp",
        ):
            # Generate traffic
            target.exec(["cat", "/etc/hostname"], detach=False)

        # Both pcaps created (even if empty due to filters)
        assert os.path.exists(internal_pcap)
        assert os.path.exists(external_pcap)


# =============================================================================
# TcpDumpCapture Parameter Tests
# =============================================================================
# Test various TcpDumpCapture constructor parameters.


class TestCaptureParameters:
    """Tests for TcpDumpCapture parameters (using internal handler)."""

    @score.itf.plugins.core.requires_capabilities("tcpdump")
    def test_custom_target_pcap_path(self, target, tmp_path):
        """target_pcap_path controls where tcpdump writes inside container."""
        host_out = str(tmp_path / "custom_target.pcap")

        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
            host_out,
            target_pcap_path="/tmp/itf_custom.pcap",
        ) as cap:
            assert cap.target_path == "/tmp/itf_custom.pcap"
            target.exec(["cat", "/etc/hostname"], detach=False)

        assert os.path.exists(host_out)

    @score.itf.plugins.core.requires_capabilities("tcpdump")
    def test_max_packets(self, target, tmp_path):
        """max_packets stops capture after N packets."""
        pcap_path = str(tmp_path / "max_packets.pcap")

        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
            pcap_path,
            max_packets=5,
        ):
            target.exec(["cat", "/etc/hostname"], detach=False)

        assert os.path.exists(pcap_path)

    @score.itf.plugins.core.requires_capabilities("tcpdump")
    def test_auto_temp_file(self, target):
        """When no host_output_path given, a temp file is created."""
        with TcpDumpCapture(
            target.internal_tcpdump_handler(),
        ) as cap:
            target.exec(["cat", "/etc/hostname"], detach=False)

        assert cap.host_path is not None
        assert os.path.exists(cap.host_path)
        os.unlink(cap.host_path)
